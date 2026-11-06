"""HTTP API. Thin: validate, delegate to the orchestrator, map domain errors to statuses."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..domain.session import DomainError, Session
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
    }


def _orch(request: Request) -> Orchestrator:
    return request.app.state.orchestrator


def _user(request: Request) -> str:
    return request.state.user_id


# -- sessions ----------------------------------------------------------------
@router.get("/models")
async def models(request: Request) -> dict:
    return {
        "available": request.app.state.models.allowed(_user(request)),
        "default": request.app.state.settings.default_model,
    }


@router.get("/sessions")
async def list_sessions(request: Request) -> dict:
    return {"sessions": [_session_json(s) for s in _orch(request).sessions_for(_user(request))]}


@router.post("/sessions", status_code=201)
async def create_session(request: Request, body: CreateSession) -> dict:
    model = body.model or request.app.state.settings.default_model
    try:
        s = await _orch(request).create(_user(request), body.folder, model, body.schema_, body.title)
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
        turn = await orch.submit(sid, body.text)
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
    user = _user(request)
    target = path or f"/Users/{user}"
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
    user = _user(request)
    home = f"/Users/{user}"
    repo_owner = user.split("@")[0].replace(".", "_")
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
