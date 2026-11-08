"""create_app(): wire adapters to ports. The only place that chooses implementations."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .adapters.acp.runtime import AcpAgentRuntime
from .adapters.databricks.catalog import CatalogBrowser
from .adapters.databricks.serving import ServingBrowser
from .adapters.databricks.workspace import WorkspaceBrowser
from .adapters.mcp.registry import NullToolRegistry, SubprocessToolRegistry
from .adapters.memory.store import MemoryEventStore

log = logging.getLogger("app.main")
from .config import Settings
from .config import settings as load_settings
from .routers.api import router
from .routers.llm import router as llm_router
from .routers.llm_admin import router as llm_admin_router
from .routers.internal import router as internal_router
from .services.catalogue import SettingsModelCatalog
from .services.health_service import HealthService
from .services.identity import ForwardedIdentity, NullGroups
from .services.model_registry import Registry, build_registry
from .services.orchestrator import Orchestrator

WEB_DIST = Path(__file__).resolve().parents[1] / "web" / "dist"


def build(settings: Settings | None = None, *, llm: Registry | None = None) -> FastAPI:
    cfg = settings or load_settings()
    store = MemoryEventStore()
    identity = ForwardedIdentity(cfg)
    groups = NullGroups()

    # A deployed app installs the agent with npm; its binary lives in node_modules/.bin.
    local_bin = Path(__file__).resolve().parents[1] / "node_modules" / ".bin"
    if local_bin.is_dir():
        os.environ["PATH"] = f"{local_bin}{os.pathsep}{os.environ.get('PATH', '')}"

    if cfg.agent_mode == "fake":
        # The interpreter running this app (the container may not have `python3` on PATH), and our
        # package root on PYTHONPATH: the child's cwd is the user's working folder, not the app.
        pkg_root = str(Path(__file__).resolve().parents[1])
        runtime = AcpAgentRuntime(
            f"{sys.executable} -m api.adapters.fake.agent {cfg.demo_scenario}",
            extra_env={
                "PYTHONPATH": os.pathsep.join(filter(None, [pkg_root, os.environ.get("PYTHONPATH")]))
            },
        )
    elif cfg.agent_mode == "stdio":
        runtime = AcpAgentRuntime(cfg.agent_command)
    else:
        from .adapters.acp.http_runtime import HttpAcpAgentRuntime

        runtime = HttpAcpAgentRuntime(cfg.agent_config_dir or None)

    # The agent's tool server cannot submit runs as the user (an App has no jobs scope); it asks the
    # app, over loopback, to run the notebook as the app. The key only opens one session's door.
    from .services.run_bridge import RunBridge

    bridge = RunBridge(cfg.internal_url or f"http://127.0.0.1:{os.environ.get('DATABRICKS_APP_PORT') or '8000'}")
    tools = (
        SubprocessToolRegistry(
            # `python3` on a container's PATH is not the interpreter that has our dependencies (mcp).
            python=sys.executable if cfg.tool_server_python == "python3" else cfg.tool_server_python,
            bridge=bridge)
        if cfg.tool_mode == "subprocess"
        else NullToolRegistry()
    )
    # The catalogue is a facade over the registry, so the orchestrator's existing synchronous calls
    # keep working while every route reads the async catalogue (spec 005, one resolution path).
    models = SettingsModelCatalog(cfg, llm.catalogue if llm is not None else None)
    orch = Orchestrator(runtime, tools, store, models, demo=cfg.agent_mode == "fake",
                        resolver=llm.resolver if llm is not None else None,
                        credentials=llm.credentials if llm is not None else None,
                        store_llm=llm.store if llm is not None else None,
                        health=llm.health if llm is not None else None)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # A background reaper, because `archive()` tears a session down properly but nothing called
        # it: every session a user opened kept its agent subprocess for the life of the server. An
        # afternoon of testing accumulated 29 live agents, which is what exhausted the machine and
        # produced intermittent renderer crashes.
        reaper = asyncio.create_task(_reap_loop(app))
        discovery = asyncio.create_task(_discover_loop(app))
        database = asyncio.create_task(_database_loop(app))
        try:
            yield
        finally:
            for task in (reaper, discovery, database):
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            for live in list(app.state.orchestrator._live.values()):  # noqa: SLF001 - orderly shutdown
                if live.handle:
                    await runtime.close(live.handle)
            registry = getattr(app.state, "llm", None)
            if registry is not None:
                with contextlib.suppress(Exception):
                    await registry.store.close()

    app = FastAPI(title="OpenGenie", version="0.1.0", lifespan=lifespan)
    app.state.settings = cfg
    app.state.run_bridge = bridge
    app.state.store = store
    app.state.models = models
    app.state.orchestrator = orch
    app.state.idempotency = {}
    app.state.groups = groups
    app.state.workspace = WorkspaceBrowser(
        os.environ.get("DATABRICKS_HOST", ""),
        lambda: os.environ.get("DATABRICKS_TOKEN") or None,
    )
    app.state.catalog = CatalogBrowser(
        os.environ.get("DATABRICKS_HOST", ""),
        lambda: os.environ.get("DATABRICKS_TOKEN") or None,
    )
    from .adapters.databricks.serverless import ServerlessRunner
    from .services.pyrun_service import PythonRuns

    # Built here, authenticated lazily: a demo that never runs a Python cell never needs SDK auth.
    app.state.pyruns = PythonRuns(ServerlessRunner())
    app.state.serving = ServingBrowser(
        os.environ.get("DATABRICKS_HOST", ""),
        lambda: os.environ.get("DATABRICKS_TOKEN") or None,
    )
    app.state.dev_token = os.environ.get("APP_DEV_TOKEN") or os.environ.get("DATABRICKS_TOKEN")
    # A dev token expires in an hour. In a deployed app the proxy supplies a fresh one per request, so
    # this only affects local work — but there it silently turns into an empty file tree and a search
    # that never finishes, which reads as a product bug and costs an afternoon. When a dev token is
    # configured and `databricks` is on PATH, it is re-minted on demand (see `dev_token` below).
    app.state.dev_token_auto = bool(os.environ.get("APP_DEV_TOKEN")) and bool(
        os.environ.get("APP_DEV_TOKEN_AUTO", "1") != "0")
    # The registry is built by the caller when it can await (`app_factory`) and synchronously here
    # for the TestClient path, where there is no loop at import time.
    if llm is not None:
        app.state.llm = llm
    else:
        app.state.llm = _sync_registry(cfg)
    app.state.orchestrator.attach_registry(app.state.llm)

    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    @app.middleware("http")
    async def identity_middleware(request: Request, call_next):
        if request.url.path.startswith("/internal/"):
            # The app's own tool servers, over loopback: no forwarded user, and a per-session key
            # instead (routers/internal.py). Nothing here is reachable without it.
            request.state.user_id, request.state.home, request.state.groups = "internal", "internal", []
            return await call_next(request)
        try:
            headers = dict(request.headers)
            request.state.user_id = identity.user_id(headers)
            request.state.home = identity.home_name(headers, request.state.user_id)
            request.state.groups = groups.groups_for(request.state.user_id)
        except PermissionError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=401)
        return await call_next(request)

    app.include_router(router)
    app.include_router(llm_router)
    app.include_router(llm_admin_router)
    app.include_router(internal_router)

    if WEB_DIST.exists():
        app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

        @app.get("/")
        async def index() -> FileResponse:
            return FileResponse(WEB_DIST / "index.html")

        @app.get("/{path:path}")
        async def spa(path: str) -> FileResponse:
            target = WEB_DIST / path
            return FileResponse(target if target.is_file() else WEB_DIST / "index.html")

    return app


def _sync_registry(cfg: Settings) -> Registry:
    """Build the registry without an event loop.

    `asyncio.run` would refuse inside a running loop, and a TestClient app is built at import. The
    seed store is loaded synchronously here, so this path needs no loop at all; a configured
    `LLM_DATABASE_URL` on this path is connected lazily on first use instead.
    """
    from .services.model_registry import build_registry_sync

    return build_registry_sync(cfg)


async def app_factory(settings: Settings | None = None) -> FastAPI:
    """The async construction path: `uvicorn api.main:factory --factory`."""
    cfg = settings or load_settings()
    registry = await build_registry(cfg, host=os.environ.get("DATABRICKS_HOST", ""))
    return build(cfg, llm=registry)


app = build()


async def _reap_loop(app: FastAPI) -> None:
    """Archive idle sessions on a timer.

    One minute is far more often than the policy needs (it reaps after 30 idle minutes) and cheap:
    the loop only reads timestamps. Errors are logged and swallowed — a reaper that dies takes the
    leak with it.
    """
    interval = 60.0
    while True:
        try:
            await asyncio.sleep(interval)
            reaped = await app.state.orchestrator.reap_idle()
            if reaped:
                log.info("reaped %d idle session(s)", len(reaped))
        except asyncio.CancelledError:
            raise
        except Exception:            # noqa: BLE001 - a reaper must outlive its own failures
            log.warning("the session reaper failed once; continuing", exc_info=True)


async def _database_loop(app: FastAPI) -> None:
    """Bring the registry onto the database, retrying until it is reachable.

    A Lakebase compute that was suspended takes a few seconds to wake, and a network that is not up
    at boot is not a reason to serve the seed for the life of the process.
    """
    from .services.model_registry import adopt_database

    cfg = app.state.settings
    registry = getattr(app.state, "llm", None)
    if registry is None:
        return
    delay = 1.0
    while True:
        try:
            if await adopt_database(registry, cfg):
                app.state.orchestrator.attach_registry(registry)
                return
        except asyncio.CancelledError:
            raise
        except Exception:             # noqa: BLE001 - a retry loop must outlive its own failures
            log.warning("adopting the database failed once; retrying", exc_info=True)
        if not (cfg.llm_pg_endpoint or cfg.llm_database_url):
            return
        await asyncio.sleep(delay)
        delay = min(delay * 2, 30.0)


async def _discover_loop(app: FastAPI) -> None:
    """Refresh discovery on a schedule, never per request (C-6).

    The first pass runs immediately: a cold catalogue that waits five minutes for its first look at
    the workspace is a worse experience than one extra call at boot.
    """
    registry = getattr(app.state, "llm", None)
    if registry is None or getattr(registry, "discovery", None) is None:
        return
    interval = float(app.state.settings.llm_discovery_seconds or 300)
    await asyncio.sleep(1.0)          # let the server finish binding before the first outbound call
    while True:
        try:
            discovery = registry.discovery
            discovery.invalidate()
            result = await discovery.fetch(None)
            for spec in result.specs:
                try:
                    await registry.store.upsert_model(spec)
                except ValueError:
                    continue
            await registry.store.record_discovery(discovery.provider_id, result.outcome,
                                                  len(result.specs), result.detail)
            registry.catalogue.invalidate()
            log.info("discovery: %s, %d models", result.outcome, len(result.specs))
            if result.outcome == "denied":
                # Three consecutive denials is an alert (12 §Alerts). One is worth a debug line.
                log.debug("discovery was denied: the catalogue is unchanged")
        except asyncio.CancelledError:
            raise
        except Exception:             # noqa: BLE001 - discovery must outlive its own failures
            log.warning("the discovery pass failed once; continuing", exc_info=True)
        await asyncio.sleep(max(interval, 30.0))
