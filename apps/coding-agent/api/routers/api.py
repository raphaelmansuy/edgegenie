"""HTTP API. Thin: validate, delegate to the orchestrator, map domain errors to statuses."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import contextmanager
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..adapters.acp.agent_config import config_for
from ..adapters.databricks.http import normalize_host
from ..domain import approval, scope as scope_mod, version
from ..domain import context as ctx
from ..domain import events
from ..domain.session import DomainError, Session
from ..services import context as ctx_service
from ..services.orchestrator import Orchestrator

log = logging.getLogger("app.api")
router = APIRouter(prefix="/api")


# -- schemas -----------------------------------------------------------------
class CreateSession(BaseModel):
    folder: str = Field(min_length=1, max_length=512)
    schema_: str | None = Field(default=None, alias="schema")
    model: str | None = None
    title: str = "New session"

    model_config = {"populate_by_name": True}


class Message(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)
    #: References only ({kind, ref}); the server reads the content with the user's own token.
    attachments: list[dict] = Field(default_factory=list, max_length=ctx.MAX_ATTACHMENTS * 2)


class Approval(BaseModel):
    outcome: str = Field(pattern="^(allow_once|allow_session|deny)$")
    optionId: str | None = None


class ModelChoice(BaseModel):
    model: str


def _session_json(s: Session) -> dict[str, Any]:
    return {
        "id": s.id,
        "title": s.title,
        "folder": s.folder,
        "schema": s.schema,
        "model": s.model,
        "status": s.status.value,
        "tools": s.tools,
        "agent": s.agent,
        "agentVersion": s.agent_version,
        # Omitted rather than null when unknown, so the client can tell "no timestamp" from "epoch 0".
        **({"createdAt": s.created_at} if s.created_at is not None else {}),
    }


def _orch(request: Request) -> Orchestrator:
    return request.app.state.orchestrator


def _user(request: Request) -> str:
    return request.state.user_id


def _home(request: Request) -> str:
    """The user's workspace home folder, named by e-mail (not by the proxy's opaque user id)."""
    return f"/Users/{getattr(request.state, 'home', request.state.user_id)}"


# -- sessions ----------------------------------------------------------------
@router.get("/me")
async def whoami(request: Request) -> dict:
    """The signed-in user and the folder this app suggests as scratch space."""
    user = _user(request)
    # Warm the table-name cache for THIS user, in the background. The app is opened here before any
    # search, so by the time someone types in the palette the walk is usually done. Only a real
    # token counts: the token is the permission boundary, and an anonymous walk finds nothing.
    token = _user_token(request)
    warm = getattr(request.app.state.catalog, "table_names", None)
    if token and warm is not None:
        task = asyncio.create_task(warm(token))
        request.app.state.warm = getattr(request.app.state, "warm", set())
        request.app.state.warm.add(task)          # keep a reference: a bare task can be collected
        task.add_done_callback(request.app.state.warm.discard)
    return {"user": user, "home": _home(request), "scratch": f"{_home(request)}/agent_scratch",
            "workspace": {"host": normalize_host(os.environ.get("DATABRICKS_HOST")),
                          "orgId": os.environ.get("DATABRICKS_WORKSPACE_ID", "")},
            "demo": request.app.state.settings.agent_mode == "fake"}


@router.get("/models")
async def models(request: Request) -> dict:
    allowed = request.app.state.models.allowed(_user(request))
    # Offer only what the workspace serves; if that cannot be read, offer the allow-list unfiltered.
    served = await request.app.state.serving.served(_user_token(request))
    if served is not None:
        allowed = [m for m in allowed if config_for(m["id"], "").endpoint in served] or allowed
    return {"available": allowed, "default": request.app.state.settings.default_model}


@router.get("/sessions")
async def list_sessions(request: Request) -> dict:
    return {"sessions": [_session_json(s) for s in _orch(request).sessions_for(_user(request))]}


@router.post("/sessions", status_code=201)
async def create_session(request: Request, body: CreateSession) -> dict:
    model = body.model or request.app.state.settings.default_model
    try:
        s = await _orch(request).create(_user(request), body.folder, model, body.schema_, body.title,
                                        user_token=_user_token(request))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - provisioning failures are 503, never a 200
        # Log it: in a deployed app the only diagnostic channel is stdout.
        log.exception("session provisioning failed")
        raise HTTPException(503, f"the agent did not start: {exc}") from exc
    return _session_json(s)


@router.get("/sessions/{sid}")
async def get_session(request: Request, sid: str) -> dict:
    try:
        live = _orch(request).get(sid)
    except KeyError:
        raise HTTPException(404, "no such session") from None
    turn = live.state.running()
    return {
        **_session_json(live.state.session),
        "turns": [
            {
                "id": t.id,
                "index": t.index,
                "status": t.status.value,
                "prompt": t.prompt,
                "model": t.model,
                "queuedReason": t.queued_reason,
                "usage": {"input": t.input_tokens, "output": t.output_tokens, "cached": t.cached_tokens},
            }
            for t in live.state.turns
        ],
        "running": turn.index if turn else None,
        "scope": _orch(request).scope_description(sid),
    }


@router.delete("/sessions/{sid}", status_code=204)
async def archive_session(request: Request, sid: str) -> Response:
    await _orch(request).archive(sid)
    return Response(status_code=204)


@router.get("/sessions/{sid}/models")
async def session_models(request: Request, sid: str) -> dict:
    try:
        return await _orch(request).model_options(sid)
    except KeyError:
        raise HTTPException(404, "no such session") from None


@router.post("/sessions/{sid}/model")
async def set_model(request: Request, sid: str, body: ModelChoice) -> dict:
    try:
        return await _orch(request).set_model(sid, body.model)
    except KeyError:
        raise HTTPException(404, "no such session") from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


# -- turns -------------------------------------------------------------------
@router.post("/sessions/{sid}/messages", status_code=202)
async def send_message(
    request: Request, sid: str, body: Message, idempotency_key: str | None = Header(default=None)
) -> dict:
    orch = _orch(request)
    cache = request.app.state.idempotency
    key = f"{sid}:{idempotency_key}" if idempotency_key else None
    if key and key in cache:
        return cache[key]
    try:
        orch.get(sid)
    except KeyError:
        raise HTTPException(404, "no such session") from None
    try:
        items = ctx.parse(body.attachments)
    except ctx.ContextError as exc:
        raise HTTPException(422, str(exc)) from exc
    resolved = await ctx_service.resolve(items, _browser(request), request.app.state.catalog,
                                         _user_token(request))
    try:
        turn = await orch.submit(sid, body.text, ctx.render(resolved), [a.to_dict() for a in items],
                                user_token=_user_token(request))
    except KeyError:
        raise HTTPException(404, "no such session") from None
    except DomainError as exc:
        raise HTTPException(409, str(exc)) from exc
    out = {"turnId": turn.id, "status": turn.status.value}
    if key:
        cache[key] = out
    return out


@router.post("/sessions/{sid}/cancel", status_code=202)
async def cancel(request: Request, sid: str) -> dict:
    try:
        await _orch(request).cancel(sid)
    except KeyError:
        raise HTTPException(404, "no such session") from None
    return {"cancelled": True}


@router.post("/approvals/{sid}/{approval_id}")
async def decide(request: Request, sid: str, approval_id: str, body: Approval) -> dict:
    try:
        await _orch(request).approve(sid, approval_id, body.outcome, body.optionId, _user(request))
    except KeyError:
        raise HTTPException(404, "no such session") from None
    return {"ok": True}


# -- stream ------------------------------------------------------------------
def _sse(event: dict) -> str:
    return f"id: {event['seq']}\ndata: {json.dumps(event, separators=(',', ':'))}\n\n"


@router.get("/sessions/{sid}/stream")
async def stream(
    request: Request, sid: str, after: int = 0, last_event_id: str | None = Header(default=None)
) -> StreamingResponse:
    orch = _orch(request)
    store = request.app.state.store
    try:
        orch.get(sid)
    except KeyError:
        raise HTTPException(404, "no such session") from None
    # A reloaded page cannot set a header from EventSource, so ?after= is the primary cursor;
    # Last-Event-ID covers a browser-initiated reconnect of the same EventSource.
    cursor = after or (int(last_event_id) if last_event_id and last_event_id.isdigit() else 0)
    heartbeat = request.app.state.settings.stream_heartbeat_seconds

    async def gen() -> AsyncIterator[str]:
        queue = store.subscribe(sid)
        try:
            backlog = await store.since(sid, cursor)
            for ev in backlog:
                yield _sse(ev)
            seq = backlog[-1]["seq"] if backlog else cursor
            while True:
                try:
                    ev = await __import__("asyncio").wait_for(queue.get(), heartbeat)
                except __import__("asyncio").TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                if ev["seq"] <= seq:
                    continue
                seq = ev["seq"]
                yield _sse(ev)
        finally:
            store.unsubscribe(sid, queue)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


# -- workspace tree ----------------------------------------------------------
def _browser(request: Request):
    return request.app.state.workspace


def _user_token(request: Request) -> str | None:
    """The signed-in user's token, forwarded by the Databricks proxy. Never stored."""
    headers = {k.lower(): v for k, v in request.headers.items()}
    return headers.get("x-forwarded-access-token") or getattr(request.app.state, "dev_token", None)


@router.get("/workspace")
async def workspace_dir(request: Request, path: str | None = None, depth: int = 1) -> dict:
    """List a workspace folder (one level by default). The tree loads lazily as the user expands."""
    browser = _browser(request)
    target = path or _home(request)
    try:
        node = await browser.tree(target, _user_token(request), depth=max(1, min(depth, 3)))
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except RuntimeError as exc:
        log.warning("workspace list failed for %s: %s", target, exc)
        raise HTTPException(502, str(exc)) from exc
    return {"node": node.to_dict(), "root": target}


@router.get("/workspace/roots")
async def workspace_roots(request: Request) -> dict:
    """The places worth showing first: the user's home, Shared, Repos.

    A root that does not exist for this user is not shown: an entry that opens onto nothing is
    worse than an absent entry. The user's own home is always first when it exists.
    """
    home = _home(request)
    repo_owner = home.removeprefix("/Users/").split("@")[0].replace(".", "_")
    candidates = [
        {"path": home, "name": "My home", "kind": "directory"},
        {"path": "/Shared", "name": "Shared", "kind": "directory"},
        {"path": f"/Repos/{repo_owner}", "name": "Repos", "kind": "repo"},
        {"path": "/Repos", "name": "All repos", "kind": "repo"},
    ]
    out = []
    for c in candidates:
        try:
            children = await _browser(request).list_dir(c["path"], _user_token(request))
        except (PermissionError, RuntimeError):
            continue
        if children or c["path"] == home:
            out.append({**c, "childCount": len(children)})
    return {"roots": out or [{"path": "/", "name": "Workspace", "kind": "directory"}]}


def _ws_path(path: str) -> str:
    if not path.startswith("/") or ".." in path.split("/") or "\x00" in path:
        raise HTTPException(422, "a workspace path starts with / and has no ..")
    return path


@contextmanager
def _dbx_errors(what: str):
    """Platform failures -> honest HTTP statuses. A denial is a 403, never an empty result."""
    try:
        yield
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except (LookupError, IsADirectoryError) as exc:
        raise HTTPException(404 if isinstance(exc, LookupError) else 422, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        log.warning("%s failed: %s", what, exc)
        raise HTTPException(502, str(exc)) from exc


@router.get("/workspace/object")
async def workspace_object(request: Request, path: str) -> dict:
    """A notebook as cells (or a file as text), read with the user's token."""
    with _dbx_errors("workspace read"):
        obj = await _browser(request).read(_ws_path(path), _user_token(request))
    return obj.to_dict()


@router.get("/workspace/search")
async def workspace_search(request: Request, q: str, path: str | None = None) -> dict:
    """Name search under a root. `complete` is false when a bound stopped the walk."""
    root = _ws_path(path or _home(request))
    if len(q.strip()) < 2:
        raise HTTPException(422, "type at least two characters")
    with _dbx_errors("workspace search"):
        hits, complete = await _browser(request).search(root, q, _user_token(request))
    return {"root": root, "complete": complete, "results": [h.to_dict() for h in hits]}


class MakeDir(BaseModel):
    path: str = Field(min_length=2, max_length=512)


@router.post("/workspace/mkdir", status_code=201)
async def workspace_mkdir(request: Request, body: MakeDir) -> dict:
    """Create a folder as the signed-in user. Creation only: the app never deletes or overwrites."""
    path = _ws_path(body.path)
    with _dbx_errors("workspace mkdir"):
        await _browser(request).mkdirs(path, _user_token(request))
    return {"path": path}


class SaveDocument(BaseModel):
    """A whole-object save, which is the only granularity the workspace API offers."""

    path: str = Field(min_length=2, max_length=1024)
    text: str = Field(max_length=8_000_000)
    #: The token the client held when it loaded. Absent means "I did not load, just write".
    version: str | None = None
    #: Present when the fence answered ASK and the user approved. Path- and version-bound.
    approval: str | None = None
    #: The notebook's language, only used when the object does not exist yet.
    language: str | None = None
    #: The session this save belongs to, so the write lands in that session's audit stream.
    sessionId: str | None = None


class AskFence(BaseModel):
    """Ask the server what the fence thinks, without writing anything."""

    path: str = Field(min_length=2, max_length=1024)
    version: str | None = None
    #: The same session the save would name. Without it there is no writable folder, so every path
    #: is outside and every answer is "ask" — correct, but useless as a preview.
    sessionId: str | None = None


def _save_scope(request: Request, session_id: str | None) -> scope_mod.Scope:
    """The scope a save is judged against.

    With a session, it is that session's scope — the same object the agent's tools get, so a human
    and an agent saving the same path see the same verdict (WR-1). Without a session there is no
    folder to be inside, so the scope is an empty folder: every path is outside it and every save
    asks. That is the honest answer rather than a default-allow.
    """
    if session_id:
        try:
            return _orch(request).scope(session_id)
        except KeyError:
            raise HTTPException(404, "no such session") from None
    home = _home(request)
    return scope_mod.Scope.for_session("nosession", f"{home}/__no_scope__/", None)


@router.post("/workspace/fence")
async def workspace_fence(request: Request, body: AskFence) -> dict:
    """What would happen if we saved this path. The client asks before the user types (WR-5)."""
    path = _ws_path(body.path)
    decision = scope_mod.check_path(_save_scope(request, body.sessionId), path)
    return {
        "verdict": decision.verdict.value,
        "action": decision.action.value,
        "target": decision.target,
        "reason": decision.reason,
        "approval": approval.issue(path, body.version or "") if decision.verdict is scope_mod.Verdict.ASK else None,
    }


@router.post("/workspace/save")
async def workspace_save(request: Request, body: SaveDocument) -> dict:
    """Save a document, fenced.

    The order of the checks is the design (spec 003 WR-1..WR-7, CX-2):

      1. the path is well formed            -> 422
      2. `check_path` says what may happen  -> ASK requires an approval token, or 403
      3. the version the client held still  -> 409 with both versions
      4. import                             -> the object is replaced or it is not
      5. record the write                   -> the audit stream

    Step 2 calls `scope.check_path`, the same function the agent's tools call. This route contains
    no path policy of its own; a mutation test flips `check_path` to always-deny and requires this
    route to obey.
    """
    path = _ws_path(body.path)
    scope = _save_scope(request, body.sessionId)
    decision = scope_mod.check_path(scope, path)

    if decision.verdict is scope_mod.Verdict.DENY:
        raise HTTPException(403, decision.reason or "this path cannot be written")

    if decision.verdict is scope_mod.Verdict.ASK:
        # The approval is bound to this exact path and this exact version, so it cannot be reused
        # for another object or replayed onto a revision the user never saw (approval.py).
        if not approval.verify(body.approval, path, body.version or ""):
            raise HTTPException(
                403,
                {"fence": "ask", "reason": decision.reason or f"outside {scope.folder}",
                 "hint": "ask the fence for an approval for this path, then send it back"},
            )

    browser = _browser(request)
    token = _user_token(request)

    with _dbx_errors("workspace status"):
        current_status = await browser.status(path, token) if not _is_missing(body) else None

    current_version = version.of(current_status)
    supplied = body.version or ""
    # A version was supplied: it must still describe the object, or this is an overwrite of
    # somebody else's edit and the user has to see both (CX-2, CX-3).
    if supplied and not version.matches(current_version, supplied):
        raise HTTPException(409, {
            "conflict": True,
            "current": (current_version.to_dict() if current_version else None),
            "yours": supplied,
            "path": path,
        })
    if not supplied and current_status is not None:
        # Client did not say what it held. That is only acceptable when it is creating a new
        # object; overwriting an existing one without a version is exactly the silent-clobber this
        # whole path exists to prevent.
        raise HTTPException(409, {
            "conflict": True,
            "current": current_version.to_dict() if current_version else None,
            "yours": None,
            "path": path,
            "reason": "no version supplied for an object that already exists",
        })

    with _dbx_errors("workspace save"):
        # SOURCE import needs a language: after the overwrite's delete there is no object to infer
        # from. Prefer the caller's, then what the object already had, then the path's extension.
        lang = (body.language or "").upper()
        if not lang and current_status:
            existing = current_status.get("language")
            lang = str(existing or "").upper()
        if not lang:
            lang = _language_for_path(path)
        await browser.import_source(path, body.text, token, language=lang)

    with _dbx_errors("workspace status"):
        after = version.of(await browser.status(path, token))

    if body.sessionId:
        try:
            await _orch(request).record_document_saved(
                body.sessionId, path, len(body.text.encode()), by="human")
        except (KeyError, AttributeError):
            # Recording is valuable but must never fail a save that already landed.
            log.warning("could not record the save of %s in session %s", path, body.sessionId)

    return {
        "path": path,
        "size": len(body.text.encode("utf-8")),
        "version": after.to_dict() if after else None,
        "fence": decision.verdict.value,
    }


#: Extension -> workspace language, for a create where the caller did not say.
_EXT_LANGUAGE = {
    ".py": "PYTHON", ".sql": "SQL", ".scala": "SCALA", ".r": "R", ".md": "PYTHON",
    ".json": "PYTHON", ".yaml": "PYTHON", ".yml": "PYTHON", ".sh": "PYTHON",
    ".js": "PYTHON", ".ts": "PYTHON", ".html": "PYTHON", ".css": "PYTHON", ".toml": "PYTHON",
}


def _language_for_path(path: str) -> str:
    """The notebook language for a path with no extension information.

    Databricks notebooks are stored without an extension, so the usual case is "unknown" and
    PYTHON is the honest default: it is what the workspace itself assumes, and a wrong language on a
    *new* object is recoverable, whereas a missing one fails the write outright.
    """
    for ext, lang in _EXT_LANGUAGE.items():
        if path.lower().endswith(ext):
            return lang
    return "PYTHON"


def _is_missing(body: SaveDocument) -> bool:
    """A create: the caller declared it is writing something new, so there is no prior version."""
    return body.version == ""



# -- unity catalog -------------------------------------------------------------
@router.get("/catalog")
async def catalog_children(request: Request, catalog: str = "", schema: str = "") -> dict:
    with _dbx_errors("catalog list"):
        rows = await request.app.state.catalog.children(_user_token(request), catalog, schema)
    return {"items": rows}


@router.get("/catalog/find")
async def catalog_find(request: Request, q: str, limit: int = 8) -> dict:
    """Table name search for the composer's @ picker, in the same shape as workspace search."""
    items = await request.app.state.catalog.find(_user_token(request), q, max(1, min(limit, 20)))
    return {"results": items}


@router.get("/catalog/table")
async def catalog_table(request: Request, name: str) -> dict:
    with _dbx_errors("catalog table"):
        return await request.app.state.catalog.table(name, _user_token(request))


@router.get("/catalog/preview")
async def catalog_preview(request: Request, name: str) -> dict:
    with _dbx_errors("table preview"):
        return await request.app.state.catalog.preview(name, _user_token(request))


# -- misc --------------------------------------------------------------------
@router.get("/health")
async def health() -> dict:
    return {"ok": True}


@router.get("/ready")
async def ready(request: Request) -> dict:
    try:
        await request.app.state.store.latest_seq("probe")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"store not ready: {exc}") from exc
    return {"ok": True, "agentMode": request.app.state.settings.agent_mode}
