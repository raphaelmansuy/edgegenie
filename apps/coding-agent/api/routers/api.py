"""HTTP API. Thin: validate, delegate to the orchestrator, map domain errors to statuses."""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import logging
import os
from contextlib import contextmanager
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..adapters.databricks.http import normalize_host
from ..domain import approval, scope as scope_mod, version
from ..domain.llm import ModelError
from ..domain import context as ctx
from ..domain import events
from ..domain.blob import BlobRefusal
from ..domain.redact import token_scopes
from ..domain.workspace_ops import child_path, is_protected
from ..domain.session import DomainError, Session
from ..services import context as ctx_service
from ..services.pyrun_service import PythonRuns
from .llm_admin import can_configure
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


def _session_json(s: Session, orch: Orchestrator | None = None) -> dict[str, Any]:
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
        "requiresResume": s.requires_resume,
        **({"execution": orch.activity(s.id)} if orch else {}),
        # Omitted rather than null when unknown, so the client can tell "no timestamp" from "epoch 0".
        **({"createdAt": s.created_at} if s.created_at is not None else {}),
    }


def _cause(orch, sid: str, turns) -> dict:
    """The agent's own explanation for the last failed turn, or `{}` when there is nothing to explain."""
    if not turns:
        return {}
    last = turns[-1]
    if last.status.value not in ("failed", "blocked"):
        return {}
    try:
        tail = orch.agent_stderr(sid)
    except Exception:  # noqa: BLE001 - a diagnostic must never fail a session read
        return {}
    return {"cause": tail} if tail else {"cause": last.error or ""}


def _orch(request: Request) -> Orchestrator:
    return request.app.state.orchestrator


def _default_model(request: Request) -> str:
    """The catalogue's default, which is the seeded one rather than a config string."""
    registry = getattr(request.app.state, "llm", None)
    if registry is not None:
        cat = registry.catalogue.last()
        if cat is not None and cat.default_model:
            return cat.default_model
        if registry.default_model:
            return registry.default_model
    return request.app.state.settings.default_model


def _model_error(exc: Exception) -> HTTPException:
    """Map a typed model failure to a status, in one place (see `routers/llm.map_error`)."""
    from .llm import map_error

    return map_error(exc)


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
            # What the signed-in token is allowed to do through this app. Names only, never the token.
            "tokenScopes": token_scopes(token),
            "demo": request.app.state.settings.agent_mode == "fake",
            "pythonRun": python_run_policy(request)}


@router.get("/models")
async def models(request: Request) -> dict:
    """The catalogue the picker reads (FR-1, FR-5, FR-11, C-5).

    `source` is not decoration: the settings screen states it, so a user who added a key to an app in
    degraded mode is told it was not saved rather than discovering it next session.
    """
    registry = getattr(request.app.state, "llm", None)
    if registry is not None:
        cat = await registry.catalogue.catalogue(_user(request),
                                                 getattr(request.state, "groups", frozenset()))
        body = cat.to_dict()
        body["default"] = cat.default_model
        return body
    allowed = request.app.state.models.allowed(_user(request))
    # Offer only what the workspace serves; if that cannot be read, offer the allow-list unfiltered.
    served = await request.app.state.serving.served(_user_token(request))
    if served is not None:
        from ..services.model_registry import static_spec

        kept = []
        for m in allowed:
            try:
                if static_spec(m["id"]).endpoint in served:
                    kept.append(m)
            except Exception:  # noqa: BLE001 - an unresolved id is filtered, not a 500
                continue
        allowed = kept or allowed
    return {"available": allowed, "default": request.app.state.settings.default_model,
            "source": "static"}


@router.get("/sessions")
async def list_sessions(request: Request) -> dict:
    return {"sessions": [_session_json(s, _orch(request)) for s in _orch(request).sessions_for(_user(request))]}


@router.post("/sessions", status_code=201)
async def create_session(request: Request, body: CreateSession) -> dict:
    model = body.model or _default_model(request)
    try:
        s = await _orch(request).create(_user(request), body.folder, model, body.schema_, body.title,
                                        user_token=_user_token(request))
    except ModelError as exc:
        # A model the catalogue refuses is the caller's problem and has its own status and sentence.
        raise _model_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - provisioning failures are 503, never a 200
        # Log it: in a deployed app the only diagnostic channel is stdout.
        log.exception("session provisioning failed")
        raise HTTPException(503, f"the agent did not start: {exc}") from exc
    # Whether the agent may run notebooks (as the app) is decided once, by who this user is.
    if python_run_policy(request)["enabled"]:
        request.app.state.run_bridge.grant(s.id)
    return _session_json(s, _orch(request))


@router.get("/sessions/{sid}")
async def get_session(request: Request, sid: str) -> dict:
    try:
        live = _orch(request).get(sid)
    except KeyError:
        raise HTTPException(404, "no such session") from None
    turn = live.state.running()
    return {
        **_session_json(live.state.session, _orch(request)),
        "turns": [
            {
                "id": t.id,
                "index": t.index,
                "status": t.status.value,
                "prompt": t.prompt,
                "model": t.model,
                "queuedReason": t.queued_reason,
                "attachments": t.attachments,
                "usage": {"input": t.input_tokens, "output": t.output_tokens, "cached": t.cached_tokens},
            }
            for t in live.state.turns
        ],
        "running": turn.index if turn else None,
        "scope": _orch(request).scope_description(sid),
        # When a turn ends without an answer, the agent's own stderr is the only place the reason exists.
        # It was captured all along and never read, so a blocked turn looked causeless — measured on a
        # real agent: status=blocked, 0 tokens, no message. Empty for a healthy session.
        **_cause(_orch(request), sid, live.state.turns),
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
    except ModelError as exc:
        raise _model_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/sessions/{sid}/model-facts")
async def session_model_facts(request: Request, sid: str) -> dict:
    """The inspector's model block: the resolved model and which turn used which model (FR-10)."""
    try:
        return await _orch(request).model_facts(sid)
    except KeyError:
        raise HTTPException(404, "no such session") from None


# -- turns -------------------------------------------------------------------
@router.post("/sessions/{sid}/messages", status_code=202)
async def send_message(
    request: Request, sid: str, body: Message, idempotency_key: str | None = Header(default=None)
) -> dict:
    orch = _orch(request)
    if idempotency_key and len(idempotency_key) > 200:
        raise HTTPException(422, "retry key must be at most 200 characters")
    fingerprint = hashlib.sha256(json.dumps(body.model_dump(), sort_keys=True).encode()).hexdigest()
    try:
        orch.get(sid)
    except KeyError:
        raise HTTPException(404, "no such session") from None
    try:
        items = ctx.parse(body.attachments)
    except ctx.ContextError as exc:
        raise HTTPException(422, str(exc)) from exc
    resolved = await ctx_service.resolve(
        items, _browser(request), request.app.state.catalog, _user_token(request),
        blobs=getattr(request.app.state, "blobs", None), user_id=_user(request))
    orch.touch(sid)
    try:
        turn = await orch.submit(sid, body.text, ctx.render(resolved), [a.to_dict() for a in items],
                                user_token=_user_token(request), request_key=idempotency_key or "",
                                request_hash=fingerprint)
    except KeyError:
        raise HTTPException(404, "no such session") from None
    except DomainError as exc:
        raise HTTPException(409, str(exc)) from exc
    out = {"turnId": turn.id, "status": turn.status.value}
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
    except DomainError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"ok": True}


@router.post("/sessions/{sid}/resume")
async def resume_session(request: Request, sid: str) -> dict:
    try:
        s = await _orch(request).resume(sid, _user_token(request))
    except DomainError as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, f"the agent could not restore this session: {exc}") from exc
    if python_run_policy(request)["enabled"]:
        request.app.state.run_bridge.grant(s.id)
    return _session_json(s, _orch(request))


# -- stream ------------------------------------------------------------------
def _sse(event: dict) -> str:
    return f"id: {event['seq']}\ndata: {json.dumps(event, separators=(',', ':'))}\n\n"


@router.get("/sessions/{sid}/events")
async def session_events(request: Request, sid: str, after: int = 0, limit: int = 2000) -> dict:
    """The stored events, as a plain JSON list. A FINITE read of the same log `/stream` follows.

    `/stream` is an open connection that never ends by design — it is how a live turn arrives. That makes
    it useless for "show me what happened", which is what a test, a bug report, or any client that was not
    watching needs. Measured: reading a finished turn meant holding an SSE stream open and timing out.
    """
    orch = _orch(request)
    try:
        orch.get(sid)
    except KeyError:
        raise HTTPException(404, "no such session") from None
    if after < 0 or not 1 <= limit <= 2000:
        raise HTTPException(422, "after must be nonnegative and limit must be between 1 and 2000")
    rows = await request.app.state.store.since(sid, after, limit)
    next_after = rows[-1]["seq"] if rows else after
    return {"events": rows, "after": after, "count": len(rows), "nextAfter": next_after,
            "hasMore": next_after < await request.app.state.store.latest_seq(sid)}


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
    if after < 0:
        raise HTTPException(422, "after must be nonnegative")
    cursor = max(after, int(last_event_id) if last_event_id and last_event_id.isdigit() else 0)
    if cursor > await store.latest_seq(sid):
        raise HTTPException(409, "the replay cursor is ahead of the session journal")
    heartbeat = request.app.state.settings.stream_heartbeat_seconds
    # An open stream is a watcher: the reaper must never archive a session someone is looking at.
    orch.touch(sid)

    async def gen() -> AsyncIterator[str]:
        queue = store.subscribe(sid)
        try:
            seq = cursor
            while True:
                # The queue is a wakeup, the committed journal is truth. This also closes the
                # subscribe/replay race and heals slow-viewer overflow without dropping events.
                backlog = await store.since(sid, seq)
                for ev in backlog:
                    seq = ev["seq"]
                    yield _sse(ev)
                if backlog:
                    continue
                try:
                    await asyncio.wait_for(queue.get(), heartbeat)
                except TimeoutError:
                    yield ": heartbeat\n\n"
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
    forwarded = headers.get("x-forwarded-access-token")
    if forwarded:
        return forwarded
    # Local development: the configured token, re-minted when it is close to expiring. A deployed app
    # never takes this path (the proxy always forwards one), so this cannot affect production.
    return _dev_token(request.app.state)


def _dev_token(state) -> str | None:
    """The development token, refreshed shortly before it expires.

    The refresher itself lives in the Databricks adapter, because it shells out to a vendor command and
    the core must not name one; this is only the one-line seam the routers call.
    """
    from ..adapters.databricks.devtoken import refresh_if_stale

    return refresh_if_stale(state, normalize_host(os.environ.get("DATABRICKS_HOST", "")))


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

    The four listings run **concurrently**. Sequentially this endpoint took 3.6 s on a real
    workspace — four round trips before the tree can draw its first row, paid on every page load.
    Nothing here depends on anything else, so waiting for them in turn was pure latency.
    """
    home = _home(request)
    repo_owner = home.removeprefix("/Users/").split("@")[0].replace(".", "_")
    candidates = [
        {"path": home, "name": "My home", "kind": "directory"},
        {"path": "/Shared", "name": "Shared", "kind": "directory"},
        {"path": f"/Repos/{repo_owner}", "name": "Repos", "kind": "repo"},
        {"path": "/Repos", "name": "All repos", "kind": "repo"},
    ]
    token = _user_token(request)
    browser = _browser(request)
    listed = await asyncio.gather(
        *(browser.list_dir(c["path"], token) for c in candidates), return_exceptions=True)

    out = []
    for candidate, result in zip(candidates, listed, strict=True):
        if isinstance(result, BaseException):
            # A root this user cannot read is not shown — but the failure of one must not hide the
            # others, so it is skipped rather than raised.
            continue
        if result or candidate["path"] == home:
            out.append({**candidate, "childCount": len(result)})
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
    except FileExistsError as exc:
        raise HTTPException(409, str(exc)) from exc
    except RuntimeError as exc:
        log.warning("%s failed: %s", what, exc)
        raise HTTPException(502, str(exc)) from exc


@router.get("/workspace/object")
async def workspace_object(request: Request, path: str) -> dict:
    """A notebook as cells (or a file as text), read with the user's token."""
    with _dbx_errors("workspace read"):
        obj = await _browser(request).read(_ws_path(path), _user_token(request))
    return obj.to_dict()


@router.get("/workspace/version")
async def workspace_version(request: Request, path: str) -> dict:
    """Has this object changed? One cheap `get-status`, no content.

    The editor asks while the agent works, when the window regains focus and when a turn ends, so an
    object changed by anyone (the agent, another tab, the Databricks UI) is brought up to date even
    when no tool event named it. The token is the one `/workspace/object` returns, so the two are
    directly comparable.
    """
    with _dbx_errors("workspace status"):
        status = await _browser(request).status(_ws_path(path), _user_token(request))
    v = version.of(status)
    return {"path": path, "version": v.token if v else "", "modifiedAt": status.get("modified_at", 0)}


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
    """Create a folder as the signed-in user. Does not overwrite: mkdirs is idempotent on the platform."""
    path = _ws_path(body.path)
    with _dbx_errors("workspace mkdir"):
        await _browser(request).mkdirs(path, _user_token(request))
    return {"path": path}


class CreateObject(BaseModel):
    parent: str = Field(min_length=1, max_length=512)
    name: str = Field(min_length=1, max_length=200)
    kind: str = Field(pattern="^(notebook|file|folder)$")
    language: str | None = None


class ImportObject(BaseModel):
    parent: str = Field(min_length=1, max_length=512)
    name: str = Field(min_length=1, max_length=200)
    #: Base64 of the file bytes. Capped so a right-click cannot upload an unbounded body.
    content: str = Field(min_length=0, max_length=12_000_000)
    format: str = "AUTO"
    language: str | None = None


class RemoveObject(BaseModel):
    path: str = Field(min_length=2, max_length=1024)
    recursive: bool = False


class TransferObject(BaseModel):
    source: str = Field(min_length=2, max_length=1024)
    destination: str = Field(min_length=2, max_length=1024)
    mode: str = Field(pattern="^(copy|move)$")


_EXPORT_FORMATS = {"SOURCE", "HTML", "JUPYTER", "DBC", "R_MARKDOWN", "AUTO"}
_IMPORT_FORMATS = _EXPORT_FORMATS
_NOTEBOOK_LANGUAGES = {"PYTHON", "SQL", "SCALA", "R"}
_EMPTY_NOTEBOOK = b"# Databricks notebook source\n"


def _guard(path: str, home: str, what: str) -> None:
    if is_protected(path, home):
        raise HTTPException(422, what)


def _named(parent: str, name: str) -> str:
    try:
        return child_path(parent, name)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/workspace/object", status_code=201)
async def workspace_create(request: Request, body: CreateObject) -> dict:
    """Create a notebook, file or folder. Refuses when the path is already taken."""
    parent = _ws_path(body.parent)
    path = _named(parent, body.name)
    _guard(path, _home(request), "that path is a workspace root")
    token = _user_token(request)
    browser = _browser(request)
    with _dbx_errors("workspace create"):
        if await browser.exists(path, token):
            raise FileExistsError(f"{path} already exists")
        if body.kind == "folder":
            await browser.mkdirs(path, token)
        elif body.kind == "notebook":
            lang = (body.language or "PYTHON").upper()
            if lang not in _NOTEBOOK_LANGUAGES:
                raise ValueError("language must be PYTHON, SQL, SCALA or R")
            await browser.import_content(path, _EMPTY_NOTEBOOK, token, format="SOURCE", language=lang)
        else:
            await browser.import_content(path, b"\n", token, format="AUTO")
    return {"path": path}


@router.post("/workspace/import", status_code=201)
async def workspace_import(request: Request, body: ImportObject) -> dict:
    """Import a file the user chose, into a folder. Does not overwrite an existing object."""
    import base64

    parent = _ws_path(body.parent)
    path = _named(parent, body.name)
    _guard(path, _home(request), "that path is a workspace root")
    fmt = body.format.upper()
    if fmt not in _IMPORT_FORMATS:
        raise HTTPException(422, "unsupported import format")
    try:
        raw = base64.b64decode(body.content, validate=True)
    except Exception as exc:
        raise HTTPException(422, "content must be base64") from exc
    lang = (body.language or "").upper()
    if lang and lang not in _NOTEBOOK_LANGUAGES:
        raise HTTPException(422, "language must be PYTHON, SQL, SCALA or R")
    token = _user_token(request)
    browser = _browser(request)
    with _dbx_errors("workspace import"):
        if await browser.exists(path, token):
            raise FileExistsError(f"{path} already exists")
        await browser.import_content(path, raw, token, format=fmt, language=lang)
    return {"path": path}


@router.post("/workspace/delete")
async def workspace_delete(request: Request, body: RemoveObject) -> dict:
    """Move an object to the workspace trash. Roots are refused here, not only in the menu."""
    path = _ws_path(body.path)
    _guard(path, _home(request), "a workspace root cannot be moved to trash")
    with _dbx_errors("workspace delete"):
        await _browser(request).remove(path, _user_token(request), recursive=body.recursive)
    return {"path": path}


@router.post("/workspace/transfer")
async def workspace_transfer(request: Request, body: TransferObject) -> dict:
    """Copy, or copy-then-trash. The original is removed only after the copy exists."""
    source, dest = _ws_path(body.source), _ws_path(body.destination)
    home = _home(request)
    _guard(source, home, "a workspace root cannot be renamed, moved or cloned")
    _guard(dest, home, "the destination is a workspace root")
    with _dbx_errors("workspace transfer"):
        await _browser(request).relocate(source, dest, _user_token(request), move=body.mode == "move")
    return {"path": dest}


@router.get("/workspace/export")
async def workspace_export(request: Request, path: str, format: str = "SOURCE") -> Response:
    """The object's bytes, for the browser to save. Format is one the workspace API accepts."""
    fmt = format.upper()
    if fmt not in _EXPORT_FORMATS:
        raise HTTPException(422, "unsupported export format")
    target = _ws_path(path)
    with _dbx_errors("workspace export"):
        raw = await _browser(request).export_content(target, _user_token(request), fmt)
    leaf = target.rsplit("/", 1)[-1] or "download"
    filename = "".join(ch if ch.isascii() and ch not in '"\\' else "_" for ch in leaf)
    media = {"HTML": "text/html", "JUPYTER": "application/json", "SOURCE": "text/plain"}.get(fmt, "application/octet-stream")
    return Response(content=raw, media_type=media, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/workspace/permissions")
async def workspace_permissions(request: Request, path: str) -> dict:
    """The access list Databricks holds for this object. Changing it is done in Databricks."""
    target = _ws_path(path)
    with _dbx_errors("workspace permissions"):
        entries = await _browser(request).permissions(target, _user_token(request))
    return {"path": target, "entries": entries}


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
    # No session, so there is no writable folder. `folder=""` rather than a fabricated path: the
    # `__no_scope__` sentinel used to be returned as the *reason*, so the approval sheet told the
    # user their file was "outside /Users/them/__no_scope__/" — an internal placeholder, shown to a
    # person, naming a folder that does not exist. The reason is now stated in words instead
    # (see the `reason` handling in `workspace_save` and `workspace_fence`).
    return scope_mod.Scope.for_session("nosession", "", None)


@router.post("/workspace/fence")
async def workspace_fence(request: Request, body: AskFence) -> dict:
    """What would happen if we saved this path. The client asks before the user types (WR-5)."""
    path = _ws_path(body.path)
    scope = _save_scope(request, body.sessionId)
    decision = scope_mod.check_path(scope, path)
    return {
        "verdict": decision.verdict.value,
        "action": decision.action.value,
        "target": decision.target,
        "reason": _ask_reason(scope, decision.reason),
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


def _ask_reason(scope: scope_mod.Scope, reason: str) -> str:
    """Why the save needs approval, in words a person can act on.

    Two cases: there is a writable folder and the path is outside it, or there is no session and
    therefore no folder at all. The second must not pretend a folder exists — the old code returned
    the scope's internal path, so the sheet said "outside /Users/them/__no_scope__/".
    """
    if not scope.folder:
        return "no session is open, so there is no working folder to save into"
    return reason or f"outside {scope.folder}"


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


class RunCell(BaseModel):
    """A cell to execute. The text is the cell's source, which the client already holds."""

    language: str = Field(default="sql", max_length=24)
    source: str = Field(min_length=1, max_length=200_000)


@router.post("/notebook/run-cell")
async def notebook_run_cell(request: Request, body: RunCell) -> dict:
    """Run one cell and return its result (spec 006 X1–X4).

    Deliberately narrow: **SQL only**, on a SQL warehouse, as the signed-in user. A Python cell needs
    a cluster and a runtime this app does not own, and offering a control that cannot run would be the
    inert-button bug again (00 P4, NB-2). The refusal is a *state with a reason*, not an error, so the
    UI can say what would work instead.
    """
    from ..domain import cellrun

    ok, why = cellrun.is_runnable(body.language, body.source)
    if not ok:
        return cellrun.refused(why).to_dict()
    _, statement = cellrun.without_skip(body.source)
    clock = cellrun.Clock()
    started = clock.start()
    try:
        payload, warehouse = await request.app.state.catalog.run_sql(
            statement, _user_token(request), limit=cellrun.MAX_ROWS,
            wait_seconds=cellrun.MAX_WAIT_SECONDS)
    except PermissionError as exc:
        return cellrun.refused(str(exc)).to_dict()
    except LookupError as exc:
        return cellrun.refused(str(exc)).to_dict()
    except RuntimeError as exc:
        log.warning("cell run failed: %s", exc)
        return cellrun.RunResult(state=cellrun.RunState.FAILED,
                                 error=str(exc)[:400]).to_dict()
    result = cellrun.result_from_statement(payload, waited=round(clock.since(started), 2))
    # The warehouse is the adapter's knowledge, not the domain's: attach it here rather than teaching
    # `result_from_statement` about a second parameter it would only ever pass through.
    return dataclasses.replace(result, warehouse=warehouse).to_dict()


# -- Python cells, on serverless compute, as the app -------------------------
def python_run_policy(request: Request) -> dict:
    """May this caller run Python cells, and if not, why not (in words they can act on).

    The run is as the app's service principal, not as the caller, so it is an administrator's
    capability: anyone allowed to run code there could read whatever the app can.
    """
    if not request.app.state.settings.python_run:
        return {"enabled": False, "reason": "Python cells are switched off for this app (APP_PYTHON_RUN=false)."}
    if not can_configure(request):
        return {"enabled": False,
                "reason": "Python cells run as the app's service principal, not as you, so only the app's "
                          "administrators can run them. Ask the agent to run it, or ask an administrator."}
    return {"enabled": True, "reason": "Runs on serverless compute as the app, not as you."}


class PyCellIn(BaseModel):
    language: str = Field(default="python", max_length=24)
    source: str = Field(default="", max_length=200_000)


class PythonRunIn(BaseModel):
    """The notebook's cells as the client holds them, and which one(s) to run.

    `show` are the cells whose output is wanted (0-based); every Python cell above the last of them runs
    too, so it has the variables the cells above it made. Empty `show` means every Python cell.
    """

    cells: list[PyCellIn] = Field(max_length=200)
    show: list[int] = Field(default_factory=list, max_length=200)


def _pyruns(request: Request) -> PythonRuns:
    policy = python_run_policy(request)
    if not policy["enabled"]:
        raise HTTPException(403, policy["reason"])
    return request.app.state.pyruns


def _who_ran(request: Request) -> str:
    return (request.headers.get("x-forwarded-email") or request.state.user_id).strip().lower()


@router.post("/notebook/python-runs")
async def python_run_start(request: Request, body: PythonRunIn) -> dict:
    """Start Python cells on serverless compute; returns a handle to poll. Administrators only."""
    from ..domain import pyrun

    runs = _pyruns(request)
    cells = [pyrun.PyCell(i, c.language, c.source) for i, c in enumerate(body.cells)]
    show = set(body.show) or None
    if show is not None and any(i < 0 or i >= len(cells) for i in show):
        raise HTTPException(422, "show names a cell that is not in the notebook")
    upto = max(show) if show else None
    try:
        started = await runs.start(_who_ran(request), cells, upto=upto, show=show)
    except Exception as exc:  # noqa: BLE001 - the platform's own words are the useful part
        log.warning("python run could not start: %s", exc)
        raise HTTPException(502, f"could not start the run: {str(exc)[:400]}") from exc
    return started


@router.get("/notebook/python-runs/{handle}")
async def python_run_poll(request: Request, handle: str) -> dict:
    runs = _pyruns(request)
    try:
        return await runs.poll(_who_ran(request), handle)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log.warning("python run poll failed: %s", exc)
        raise HTTPException(502, f"could not read the run: {str(exc)[:400]}") from exc


@router.delete("/notebook/python-runs/{handle}")
async def python_run_cancel(request: Request, handle: str) -> dict:
    runs = _pyruns(request)
    try:
        await runs.cancel(_who_ran(request), handle)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"cancelled": True}


# -- misc --------------------------------------------------------------------
@router.get("/health")
async def health() -> dict:
    return {"ok": True}


@router.get("/version")
async def version_info(request: Request) -> dict:
    """Which build is running, and where its documentation lives.

    `/api/health` answers `{"ok": true}` for every build ever deployed, so it cannot tell a fresh
    deployment from a stale one — and a stale one is exactly what `scripts/verify-deployed.sh` exists
    to catch. This route is the fingerprint: a version read from the `VERSION` file that ships inside
    the deployed tree, the commit the platform resolved (empty when there is none, never invented),
    and the three links a reader wants next.

    No identity is required beyond the proxy's own, and nothing here is secret: it is the same
    information the page prints in its footer.
    """
    from .. import buildinfo

    return buildinfo.BUILD.to_dict(extra={"agentMode": request.app.state.settings.agent_mode})


@router.get("/ready")
async def ready(request: Request) -> dict:
    try:
        await request.app.state.store.latest_seq("probe")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"store not ready: {exc}") from exc
    return {"ok": True, "agentMode": request.app.state.settings.agent_mode}


# -- blobs (spec 009) ---------------------------------------------------------
class UploadBlob(BaseModel):
    """Bytes the browser hands us. The base64 cap is the framework's, checked before the handler runs."""
    #: Optional, and that is the fix for a real bug: a session does not exist until the FIRST message, so
    #: requiring one here made the first attachment of every conversation fail with "no session is open".
    #: That is the moment a user most wants to attach something — a screenshot they are about to ask
    #: about. When absent the blob is held under a per-USER pending key and bound to the session when the
    #: message that references it is sent (spec 009 [D2]).
    sessionId: str | None = Field(default=None, max_length=64)
    name: str = Field(min_length=1, max_length=400)
    mime: str = Field(default="", max_length=120)
    #: 8 MB decoded is ~10.7 MB of base64. The cap is that plus room for padding, and it refuses a
    #: 2 GB body in the framework rather than in a check a handler might forget ([D3]).
    content: str = Field(min_length=0, max_length=11_300_000)


def _blobs(request: Request):
    svc = getattr(request.app.state, "blobs", None)
    if svc is None:                      # a server started without the stage: say so, do not 500
        raise HTTPException(503, "attachment storage is not configured")
    return svc


async def _model_sees_images(request: Request, session_id: str) -> bool:
    """Whether the session's model can consume an image — the DECLARED property, not a guess from its name.

    The fact lives on `ModelSpec.sees_images`, seeded per model, and reaches the client on the catalogue so
    the picker can refuse before an upload. A name is not evidence: matching on "llama" told a user their
    model was blind based on a substring, which is a policy living in a string.

    `find` is asynchronous — awaiting it matters. Called without `await`, it returns a coroutine, `getattr`
    on that finds no `sees_images`, and every image is refused as if no model could see. That failure is
    silent and looks like a policy decision.
    """
    try:
        model = _orch(request).get(session_id).state.session.model
    except (KeyError, AttributeError):
        return False
    try:
        spec = await request.app.state.models.find(model)
    except Exception:  # noqa: BLE001 - an unknown model is not evidence of sight
        return False
    return bool(getattr(spec, "sees_images", False))


@router.post("/blobs", status_code=201)
async def blob_upload(request: Request, body: UploadBlob) -> dict:
    """Accept bytes the user handed the browser: paste, drop, or file picker.

    This is the ONLY route that takes content from the client, and it takes it through the same rules as
    every other write: validate (size, magic bytes, declared type, name, emptiness, capability), store
    once under a server-generated id, and record an event that carries metadata but never bytes.
    """
    orch = _orch(request)
    user = _user(request)
    if body.sessionId:
        try:
            orch.get(body.sessionId)
        except KeyError:
            raise HTTPException(404, "no such session") from None
        scope_id = body.sessionId
    else:
        # No session yet. The blob is still the user's, and still validated — only its owner-scoped key
        # differs. It is not a "session" and never pretends to be one: `pending:` cannot collide with a
        # session id, and every read is authorised by user_id anyway.
        scope_id = f"pending:{user}"
    svc = _blobs(request)
    try:
        row = await svc.accept(
            scope_id, user, body.name, body.mime, body.content,
            model_sees_images=await _model_sees_images(request, body.sessionId or ""),
        )
    except BlobRefusal as exc:
        raise HTTPException(422, {"code": exc.code, "detail": exc.message}) from None
    out = row.to_dict()
    # The client must not have to know about the pending key; it gets a blob id and nothing else.
    out.pop("sessionId", None)
    return out


@router.get("/blobs/{blob_id}")
async def blob_bytes(request: Request, blob_id: str, thumb: int = 0) -> Response:
    """The blob's own bytes, served so a browser cannot execute them (spec 03 [SEC-4]).

    Images are `inline` and the verified type, because a thumbnail that downloads is not a thumbnail.
    Everything else is `attachment` and `application/octet-stream`, so a crafted HTML "text" file cannot
    become a page on our origin.
    """
    svc = _blobs(request)
    try:
        row = await svc.store.meta(blob_id, _user(request))
        raw = await svc.store.bytes_for(blob_id, _user(request))
    except LookupError:
        raise HTTPException(404, "no such attachment") from None
    if thumb:
        raw = await svc.thumb(row, raw)
    inline = row.mime.startswith("image/")
    media = row.mime if inline else "application/octet-stream"
    disposition = "inline" if inline else f'attachment; filename="{row.stored_name}"'
    return Response(content=raw, media_type=media, headers={
        "Content-Disposition": disposition,
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, max-age=3600",
    })


class MaterialiseBlob(BaseModel):
    folder: str = Field(min_length=1, max_length=512)
    #: The session whose fence judges this write. Sent by the client because the folder alone cannot say
    #: which scope it belongs to — and without it every save would ask, which is the wrong answer for a
    #: file the user is putting inside the folder they already chose.
    sessionId: str | None = None
    approval: str | None = None


@router.post("/blobs/{blob_id}/materialise", status_code=201)
async def blob_materialise(request: Request, blob_id: str, body: MaterialiseBlob) -> dict:
    """Write a blob into the workspace, through the fence, exactly as `workspace_save` does.

    The order is the design ([D5]): path, verdict, approval, bytes, import, record. Nothing here is a
    second policy — `scope.check_path` is called, not re-implemented, and a mutation test that forces it to
    deny must make this route deny too.
    """
    folder = _ws_path(body.folder)
    scope = _save_scope(request, body.sessionId)
    svc = _blobs(request)
    try:
        row = await svc.store.meta(blob_id, _user(request))
    except LookupError:
        raise HTTPException(404, "no such attachment") from None
    # `folder` IS the destination directory; the stored name is appended to it. Joining to its parent
    # would put the file one level up, outside the folder the user named.
    target = f"{folder.rstrip('/')}/{row.stored_name}"
    decision = scope_mod.check_path(scope, target)
    if decision.verdict is scope_mod.Verdict.DENY:
        raise HTTPException(403, decision.reason or "this path cannot be written")
    if decision.verdict is scope_mod.Verdict.ASK:
        if not approval.verify(body.approval, target, ""):
            raise HTTPException(403, {
                "fence": "ask", "reason": decision.reason or "outside the working folder",
                "approval": approval.issue(target, ""), "target": target,
            })
    raw = await svc.store.bytes_for(blob_id, _user(request))
    with _dbx_errors("blob save"):
        browser = _browser(request)
        if await browser.exists(target, _user_token(request)):
            raise FileExistsError(f"{row.stored_name} already exists in that folder")
        await browser.import_content(target, raw, _user_token(request), format="AUTO")
    return {"path": target, "bytes": row.size}
