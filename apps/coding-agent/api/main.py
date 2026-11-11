"""create_app(): wire adapters to ports. The only place that chooses implementations."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import inspect
import os
import re
import tempfile
import sys
import time
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
from .adapters.durable.postgres import JournalUnavailable
from .adapters.mcp.registry import NullToolRegistry, SubprocessToolRegistry
from .adapters.memory.store import MemoryEventStore

log = logging.getLogger("app.main")
from .config import Settings
from .config import settings as load_settings
from .routers.api import plain_reason, router
from .routers.infra import router as infra_router
from .routers.jobs import router as jobs_router
from .routers.llm import router as llm_router
from .routers.llm_admin import router as llm_admin_router
from .routers.internal import router as internal_router
from .services.catalogue import SettingsModelCatalog
from .services.identity import ForwardedIdentity, NullGroups
from .services.model_registry import Registry, build_registry
from .services.orchestrator import Orchestrator

WEB_DIST = Path(__file__).resolve().parents[1] / "web" / "dist"

#: A session id in an API path, under any prefix, in any position.
#:
#: The owner check used to list the two prefixes that existed when it was written
#: (`/api/sessions`, `/api/approvals`). That is a rule about today's router table, not about the
#: boundary: `/api/llm/sessions/{sid}/turns` was added later, names a session, and was outside the
#: list — so any signed-in user could read another user's model provenance by guessing or observing
#: an id. `tests/test_cross_user_boundary.py` proves it for both shapes, and this pattern is why a
#: third router cannot reintroduce it.
SESSION_IN_PATH = re.compile(
    r"^/api/(?:(?:[^/]+/)*sessions|approvals)/(?P<sid>[^/]+)(?:/|$)")


def build(settings: Settings | None = None, *, llm: Registry | None = None) -> FastAPI:
    cfg = settings or load_settings()
    if cfg.session_database_url or cfg.session_use_lakebase:
        from .adapters.durable.postgres import PostgresSessionStore
        store = PostgresSessionStore(cfg)
    elif cfg.session_db_path:
        from .adapters.durable.sqlite import SqliteSessionStore
        store = SqliteSessionStore(cfg.session_db_path)
    else:
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
            f"{sys.executable} -m api.adapters.fake.agent {cfg.demo_scenario} {cfg.demo_event_delay}",
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
            bridge=bridge,
            # User and workspace skills ([R-18]): the conventions Genie Code reads. The workspace path
            # is fixed by the platform; the user path depends on who is signed in, so the tool server
            # resolves it from the token's home when this is empty.
            workspace_skills=os.environ.get("APP_SKILLS_WORKSPACE_DIR", "/Workspace/.assistant/skills"),
            user_skills=os.environ.get("APP_SKILLS_USER_DIR", ""),
            # The workspace's declarative hooks ([R-13]). Off unless an administrator supplies both the file
            # and the switch that permits a `then: run` program.
            hooks_file=os.environ.get("APP_HOOKS_FILE", ""),
            hooks_allow_run=os.environ.get("APP_HOOKS_ALLOW_RUN", "0") == "1")
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
                        health=llm.health if llm is not None else None,
                        max_run_seconds=cfg.session_max_run_seconds, max_concurrent=cfg.max_concurrent_agents,
                        max_turns=cfg.max_turns_per_session)
    # The app's own identity, so a session's tool server can call the Postgres API that a user token
    # can never call (spec 013 [RB-10]).
    from .adapters.databricks.sp_token import ServicePrincipalToken

    orch._sp_token = ServicePrincipalToken()      # noqa: SLF001 - one owner, set at construction

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if cfg.production and not (cfg.session_db_path or cfg.session_database_url or cfg.session_use_lakebase):
            raise RuntimeError("a durable session journal is required in production (Lakebase, Postgres, or persistent SQLite)")
        await orch.restore()
        # A background reaper, because `archive()` tears a session down properly but nothing called
        # it: every session a user opened kept its agent subprocess for the life of the server. An
        # afternoon of testing accumulated 29 live agents, which is what exhausted the machine and
        # produced intermittent renderer crashes.
        reaper = asyncio.create_task(_reap_loop(app))
        discovery = asyncio.create_task(_discover_loop(app))
        database = asyncio.create_task(_database_loop(app))
        sweeper = asyncio.create_task(_blob_sweep_loop(app))
        try:
            yield
        finally:
            for task in (reaper, discovery, database, sweeper):
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            await orch.shutdown()
            if hasattr(store, "close"):
                result = store.close()
                if inspect.isawaitable(result):
                    await result
            registry = getattr(app.state, "llm", None)
            if registry is not None:
                with contextlib.suppress(Exception):
                    await registry.store.close()

    app = FastAPI(title="OpenGenie", version="0.1.0", lifespan=lifespan)
    app.state.settings = cfg

    @app.exception_handler(JournalUnavailable)
    async def journal_unavailable(request: Request, exc: JournalUnavailable):
        # Any route that writes the journal can find it unreachable. That is "try again", not a 500
        # with a stack trace, and the body carries one clear sentence for the UI to show.
        log.warning("journal unavailable on %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(status_code=503, content={"detail": plain_reason(exc)},
                            headers={"Retry-After": "2"})

    app.state.run_bridge = bridge
    app.state.store = store
    app.state.models = models
    app.state.orchestrator = orch
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
    # The two object types a coding task builds with (spec 013). They authenticate as the APP'S
    # SERVICE PRINCIPAL, not as the signed-in user, and that is a platform rule rather than a choice:
    # `postgres` is "always bound to the SP, not OBO" (spec 013 [RB-10]), so a forwarded user token
    # never carries it and every Lakebase call 403s no matter how many times the user signs in.
    # Unity Catalog is still the boundary for what the *agent* may touch; this is the app reading the
    # infrastructure it is allowed to manage.
    from .adapters.databricks.apps import AppsBrowser
    from .adapters.databricks.jobs import JobsBrowser
    from .adapters.databricks.lakebase import LakebaseBrowser
    from .adapters.databricks.pipelines import PipelinesBrowser
    from .adapters.databricks.sp_token import ServicePrincipalToken, provider

    sp = ServicePrincipalToken()
    app.state.sp_token = sp
    app.state.lakebase = LakebaseBrowser(os.environ.get("DATABRICKS_HOST", ""), provider(sp))
    app.state.apps = AppsBrowser(os.environ.get("DATABRICKS_HOST", ""), provider(sp))
    # Spec 014: jobs and pipelines are behind the same wall as `postgres` — neither `jobs` nor `pipelines`
    # is a grantable `user_api_scopes` value, so the forwarded user token cannot call either API and every
    # read here is the app reading what it is allowed to see ([RB-1]).
    app.state.jobs = JobsBrowser(os.environ.get("DATABRICKS_HOST", ""), provider(sp))
    app.state.pipelines = PipelinesBrowser(os.environ.get("DATABRICKS_HOST", ""), provider(sp))
    app.state.dev_token = os.environ.get("APP_DEV_TOKEN") or os.environ.get("DATABRICKS_TOKEN")

    # Bytes the user hands us (spec 009). A directory in dev, memory in tests; the port makes a third
    # implementation additive rather than a migration ([BLB-5]).
    from .adapters.blob import FileBlobStore
    from .services.blobs import BlobService

    blob_root = os.environ.get("APP_BLOB_DIR") or os.path.join(tempfile.gettempdir(), "agent-blobs")
    app.state.blob_store = FileBlobStore(blob_root)
    # `emit` is wired, not optional in practice: `blob.attached` is part of the event vocabulary and a
    # transcript that never records an attachment cannot say where a chip's bytes came from. It was
    # passed by nobody, so the event was a type the app declared and never produced.
    async def _record_blob(session_id: str, name: str, payload: dict) -> None:
        try:
            await orch.record_blob_attached(session_id, name, payload)
        except KeyError:
            # No session yet: a blob uploaded before the first message lives under `pending:<user>`,
            # and its event belongs to the turn that adopts it. Nothing to record, and nothing wrong.
            log.debug("blob %s uploaded before its session existed", payload.get("blobId"))

    app.state.blobs = BlobService(app.state.blob_store, emit=_record_blob)
    # The orchestrator reads image bytes through the same stage, so an image reaches the model as an
    # image block when the agent advertises the capability — not as base64 in a prompt.
    orch.attach_blobs(app.state.blobs)
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

    # CORS is same-origin by default: uvicorn serves the built front end, so a browser on the app's
    # own URL needs no cross-origin grant at all. `allow_origins=["*"]` was here from the first
    # prototype, when the Vite dev server talked to the API on another port. A wildcard on an app
    # that is authenticated by a proxy is wider than it needs to be — it lets any page a user visits
    # call this API with whatever credentials that page can send. A development setup names its
    # origin instead (`APP_CORS_ORIGINS=http://localhost:5173`).
    origins = [o.strip() for o in (cfg.cors_origins or "").split(",") if o.strip()]
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"],
                           allow_headers=["*"])

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
        # Every route that names a session has one owner boundary, whatever its prefix. Returning 404
        # avoids disclosing the existence of another person's journal.
        #
        # The first pattern covered `/api/sessions/…` and `/api/approvals/…`. That was the whole
        # surface when this middleware was written, and it silently stopped being the whole surface
        # when `/api/llm/sessions/{sid}/turns` was added: it is provenance for a session, it names
        # one in its path, and its prefix is `/api/llm`. So the rule is expressed as "a session id in
        # the path", not as a list of prefixes — a new router cannot reopen the hole by choosing a
        # name this regex never heard of. `tests/test_cross_user_boundary.py` holds both sides.
        match = SESSION_IN_PATH.search(request.url.path)
        if match:
            live = orch._live.get(match.group("sid"))
            if live is None or live.state.session.user_id != request.state.user_id:
                return JSONResponse({"detail": "no such session"}, status_code=404)
        return await call_next(request)

    app.include_router(router)
    app.include_router(llm_router)
    app.include_router(llm_admin_router)
    app.include_router(internal_router)
    app.include_router(infra_router)
    app.include_router(jobs_router)

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
            # The projections of sessions that are already archived. Separate from the reaper because
            # it answers a different question: the process may be gone already, and only the copy in
            # memory is at stake. The journal is untouched, so this is a cache eviction.
            evicted = app.state.orchestrator.evict_archived()
            if evicted:
                log.info("evicted %d archived projection(s) from memory", len(evicted))
        except asyncio.CancelledError:
            raise
        except Exception:            # noqa: BLE001 - a reaper must outlive its own failures
            log.warning("the session reaper failed once; continuing", exc_info=True)


async def _blob_sweep_loop(app: FastAPI) -> None:
    """Delete attachment bytes that nothing can reach, on a timer.

    The gap this closes: `BlobStore.sweep()` existed on both stores and was called by nothing, so
    bytes accumulated for the life of the container. A working function with no caller is a leak.

    The loop owns no rule. `domain/retention.py` decides what may go — never a referenced blob, and
    otherwise a TTL per state — and this only asks it, once a minute. The interval is far more often
    than the shortest TTL (one hour) needs, and cheap: it reads row metadata, not bytes.

    A store without `sweep` (a test double, or a future backend that expires on its own) is skipped
    rather than faked, so "no sweeper" is a fact the log states once instead of a silent no-op.
    """
    store = getattr(app.state, "blob_store", None)
    if store is None or not hasattr(store, "sweep"):
        log.debug("no blob store to sweep")
        return
    interval = float(app.state.settings.blob_sweep_seconds)
    if interval <= 0:
        log.debug("the attachment sweeper is switched off (APP_BLOB_SWEEP_SECONDS=0)")
        return
    while True:
        try:
            await asyncio.sleep(interval)
            report = await store.sweep(time.time())
            removed = sum(report.values()) if isinstance(report, dict) else 0
            if removed:
                log.info("swept %s expired attachment(s)", removed)
        except asyncio.CancelledError:
            raise
        except Exception:            # noqa: BLE001 - a sweeper must outlive its own failures
            log.warning("the blob sweeper failed once; continuing", exc_info=True)


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
