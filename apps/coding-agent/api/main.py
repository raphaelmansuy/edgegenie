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
from .services.identity import ForwardedIdentity, StaticModelCatalog
from .services.orchestrator import Orchestrator

WEB_DIST = Path(__file__).resolve().parents[1] / "web" / "dist"


def build(settings: Settings | None = None) -> FastAPI:
    cfg = settings or load_settings()
    store = MemoryEventStore()
    models = StaticModelCatalog(cfg)
    identity = ForwardedIdentity(cfg)

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

    tools = (
        SubprocessToolRegistry(
            # `python3` on a container's PATH is not the interpreter that has our dependencies (mcp).
            python=sys.executable if cfg.tool_server_python == "python3" else cfg.tool_server_python)
        if cfg.tool_mode == "subprocess"
        else NullToolRegistry()
    )
    orch = Orchestrator(runtime, tools, store, models, demo=cfg.agent_mode == "fake")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # A background reaper, because `archive()` tears a session down properly but nothing called
        # it: every session a user opened kept its agent subprocess for the life of the server. An
        # afternoon of testing accumulated 29 live agents, which is what exhausted the machine and
        # produced intermittent renderer crashes.
        reaper = asyncio.create_task(_reap_loop(app))
        try:
            yield
        finally:
            reaper.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reaper
            for live in list(app.state.orchestrator._live.values()):  # noqa: SLF001 - orderly shutdown
                if live.handle:
                    await runtime.close(live.handle)

    app = FastAPI(title="Databricks Coding Agents", version="0.1.0", lifespan=lifespan)
    app.state.settings = cfg
    app.state.store = store
    app.state.models = models
    app.state.orchestrator = orch
    app.state.idempotency = {}
    app.state.workspace = WorkspaceBrowser(
        os.environ.get("DATABRICKS_HOST", ""),
        lambda: os.environ.get("DATABRICKS_TOKEN") or None,
    )
    app.state.catalog = CatalogBrowser(
        os.environ.get("DATABRICKS_HOST", ""),
        lambda: os.environ.get("DATABRICKS_TOKEN") or None,
    )
    app.state.serving = ServingBrowser(
        os.environ.get("DATABRICKS_HOST", ""),
        lambda: os.environ.get("DATABRICKS_TOKEN") or None,
    )
    app.state.dev_token = os.environ.get("APP_DEV_TOKEN") or os.environ.get("DATABRICKS_TOKEN")

    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    @app.middleware("http")
    async def identity_middleware(request: Request, call_next):
        try:
            headers = dict(request.headers)
            request.state.user_id = identity.user_id(headers)
            request.state.home = identity.home_name(headers, request.state.user_id)
        except PermissionError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=401)
        return await call_next(request)

    app.include_router(router)

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
