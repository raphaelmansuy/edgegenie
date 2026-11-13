"""Owner-scoped agent work API plus the credential-free facade boundary."""

from __future__ import annotations
import json
import asyncio
from contextlib import contextmanager
from fastapi import APIRouter, Request, HTTPException, Header
from pydantic import BaseModel, Field
from ..domain.asset import AssetRef, WorkError, public_record, digest
from ..domain.session import updated
from ..domain.operation import ACTIVE
from ..domain.sqlquery import SqlError

router = APIRouter()


@contextmanager
def errors():
    try:
        yield
    except WorkError as exc:
        raise HTTPException(exc.status, {"message": str(exc), "currentRevision": exc.current}) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except SqlError as exc:
        raise HTTPException(exc.status, {"code": exc.code, "message": exc.message}) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def work(request):
    value = getattr(request.app.state, "work", None)
    if value is None:
        raise HTTPException(404, "Agent work is unavailable in this deployment.")
    return value


def owner(request, sid):
    with errors():
        try:
            return request.app.state.orchestrator.owned(sid, request.state.user_id)
        except KeyError:
            raise HTTPException(404, "No such session") from None


class ModeBody(BaseModel):
    mode: str = Field(pattern="^(plan|review|auto)$")


class BudgetBody(BaseModel):
    limit: float = Field(gt=0, allow_inf_nan=False)
    unit: str = Field(pattern="^(tokens|money)$")


class DecisionBody(BaseModel):
    decision: str = Field(pattern="^(apply|apply_and_run|reject)$")
    key: str = Field(min_length=1, max_length=200)


class WakeBody(BaseModel):
    action: str = Field(pattern="^(continue|notify|none)$")


class ConfirmBody(BaseModel):
    confirm: bool


class PurgeBody(BaseModel):
    confirmSessionId: str = Field(min_length=1, max_length=64)


@router.get("/api/sessions/{sid}/storage")
async def storage_report(request: Request, sid: str):
    owner(request, sid)
    with errors():
        return await request.app.state.orchestrator.storage_report(sid)


@router.delete("/api/sessions/{sid}/history")
async def purge_history(request: Request, sid: str, body: PurgeBody):
    from .llm_admin import can_configure

    owner(request, sid)
    if not can_configure(request):
        raise HTTPException(403, "History purge requires an app administrator and the session owner.")
    if body.confirmSessionId != sid:
        raise HTTPException(422, "Confirm the exact session ID before permanently deleting history.")
    with errors():
        await request.app.state.orchestrator.purge_session(
            sid, erase_blobs=request.app.state.blob_store.delete_session
        )
        return {"deleted": True, "sessionId": sid}


class ToolBody(BaseModel):
    session: str = Field(min_length=1, max_length=64)
    key: str = Field(min_length=1, max_length=128)
    arguments: dict = Field(default_factory=dict)


@router.get("/api/sessions/{sid}/work")
async def session_work(request: Request, sid: str):
    live = owner(request, sid)
    w = work(request)
    with errors():
        settings = await w.prepare(sid)
        pages = {
            kind: (await w.store.page(kind, session_id=sid, limit=50))
            for kind in ("change", "operation", "resource", "approval")
        }
        return {
            "mode": settings["mode"],
            "budget": settings.get("budget"),
            "usedTokens": settings["usedTokens"],
            "usedCost": settings["usedCost"],
            "currency": settings.get("currency", ""),
            "capabilities": w.capabilities.rows(sid),
            **{kind: [public_record(r) for r in page["items"]] for kind, page in pages.items()},
            "cursors": {kind: page["nextCursor"] for kind, page in pages.items()},
            "toolCount": len(w.toolbox.catalogue(sid)),
            "fence": {"folder": live.state.session.folder, "schema": live.state.session.schema},
        }


@router.post("/api/sessions/{sid}/mode")
async def mode(request: Request, sid: str, body: ModeBody):
    live = owner(request, sid)
    w = work(request)
    with errors():
        async with live.lock:
            if live.state.running():
                raise WorkError("Change autonomy between turns.")
            result = await w.sessions.set_mode(sid, body.mode, request.state.user_id)
            live.state.session = updated(live.state.session, mode=body.mode)
            await request.app.state.orchestrator.sync_mode(sid)
            return result


@router.post("/api/sessions/{sid}/budget")
async def budget(request: Request, sid: str, body: BudgetBody):
    owner(request, sid)
    with errors():
        return await work(request).sessions.budget(sid, body.limit, body.unit)


@router.get("/api/sessions/{sid}/capabilities")
async def capabilities(request: Request, sid: str):
    owner(request, sid)
    w = work(request)
    with errors():
        await w.prepare(sid)
        return {"items": w.capabilities.rows(sid), "toolCount": len(w.toolbox.catalogue(sid))}


@router.post("/api/sessions/{sid}/capabilities/recheck")
async def recheck(request: Request, sid: str):
    owner(request, sid)
    w = work(request)
    with errors():
        return await w.capabilities.probe(sid)


@router.get("/api/sessions/{sid}/changes")
async def changes(request: Request, sid: str, cursor: str = "", limit: int = 50):
    owner(request, sid)
    with errors():
        page = await work(request).store.page("change", session_id=sid, cursor=cursor, limit=limit)
        return {**page, "items": [public_record(r) for r in page["items"]]}


@router.get("/api/sessions/{sid}/changes/{cid}")
async def change(request: Request, sid: str, cid: str):
    owner(request, sid)
    with errors():
        return public_record(await work(request).changes.get(sid, cid))


@router.post("/api/sessions/{sid}/changes/{cid}/decision")
async def decide(request: Request, sid: str, cid: str, body: DecisionBody):
    live = owner(request, sid)
    w = work(request)
    orch = request.app.state.orchestrator
    with errors():
        if body.decision == "apply_and_run":
            candidate = await w.changes.get(sid, cid)
            if not w.capabilities.allows(sid, candidate["asset"]["kind"], "run"):
                raise WorkError("This asset cannot run as your identity. Apply the change separately.", 422)
        result = await w.changes.decide(sid, cid, body.decision, body.key, request.state.user_id)
        native = next(
            (a for a in live.extra.get("approvals", {}).values() if a.get("changeId") == cid), None
        )
        if native:
            outcome = "deny" if body.decision == "reject" else "allow_once"
            option = next(
                (
                    o["optionId"]
                    for o in native.get("options", [])
                    if o["kind"] == ("reject_once" if outcome == "deny" else "allow_once")
                ),
                None,
            )
            await orch.approve(sid, native["approvalId"], outcome, option, request.state.user_id)
        elif result["state"] == "applied":
            if body.decision == "apply_and_run":
                operation = await w.operations.submit(
                    sid, result.get("turnId", ""), "apply_and_run", AssetRef(**result["asset"]), {}
                )
                result["operation"] = operation
            else:
                await orch.wake_change(result)
        elif result["state"] == "rejected":
            await orch.decline_change(result)
        return result


@router.post("/api/sessions/{sid}/changes/{cid}/undo")
async def undo(request: Request, sid: str, cid: str):
    owner(request, sid)
    with errors():
        return await work(request).changes.undo(sid, cid, request.state.user_id)


@router.post("/api/sessions/{sid}/changes/{cid}/reconcile")
async def reconcile(request: Request, sid: str, cid: str):
    owner(request, sid)
    with errors():
        return await work(request).changes.reconcile(sid, cid)


@router.get("/api/sessions/{sid}/operations")
async def operations(request: Request, sid: str, cursor: str = "", limit: int = 50, active: bool = False):
    owner(request, sid)
    with errors():
        page = await work(request).store.page(
            "operation", session_id=sid, cursor=cursor, limit=limit, states=ACTIVE if active else ()
        )
        return {**page, "items": [public_record(r) for r in page["items"]]}


@router.get("/api/sessions/{sid}/operations/{oid}")
async def operation(request: Request, sid: str, oid: str):
    owner(request, sid)
    with errors():
        return public_record(await work(request).operations.get(sid, oid))


@router.post("/api/sessions/{sid}/operations/{oid}/cancel")
async def cancel(request: Request, sid: str, oid: str):
    owner(request, sid)
    with errors():
        return await work(request).operations.cancel(sid, oid)


@router.post("/api/sessions/{sid}/operations/{oid}/wakeup")
async def wakeup(request: Request, sid: str, oid: str, body: WakeBody):
    owner(request, sid)
    with errors():
        return await work(request).operations.set_wakeup(sid, oid, body.action)


@router.post("/api/sessions/{sid}/run-reviews/{rid}")
async def run_review(request: Request, sid: str, rid: str, body: ConfirmBody):
    live = owner(request, sid)
    w = work(request)
    orch = request.app.state.orchestrator
    with errors():
        review = await w.store.get("approval", rid)
        result = await w.toolbox.decide_run(sid, rid, body.confirm)
        native = next(
            (a for a in live.extra.get("approvals", {}).values() if a.get("runReviewId") == rid), None
        )
        if native:
            kind = "allow_once" if body.confirm else "reject_once"
            option = next((o["optionId"] for o in native.get("options", []) if o["kind"] == kind), None)
            await orch.approve(
                sid,
                native["approvalId"],
                "allow_once" if body.confirm else "deny",
                option,
                request.state.user_id,
            )
        elif not body.confirm:
            await orch.decline_change(review)
        return result


@router.get("/api/sessions/{sid}/resources")
async def resources(request: Request, sid: str, cursor: str = "", limit: int = 50):
    owner(request, sid)
    with errors():
        return await work(request).store.page("resource", session_id=sid, cursor=cursor, limit=limit)


@router.post("/api/sessions/{sid}/resources/{rid}/review")
async def cleanup_review(request: Request, sid: str, rid: str):
    owner(request, sid)
    with errors():
        return await work(request).propose_cleanup(sid, rid)


@router.post("/api/sessions/{sid}/resources/{rid}/cleanup")
async def cleanup(request: Request, sid: str, rid: str, body: ConfirmBody):
    owner(request, sid)
    with errors():
        return await work(request).cleanup(sid, rid, body.confirm)


@router.post("/api/sessions/{sid}/keepalive")
async def keepalive(request: Request, sid: str):
    owner(request, sid)
    w = work(request)
    with errors():
        page = await w.store.page("operation", session_id=sid, states=("unobserved",), limit=100)
        for row in page["items"]:
            w.operations.watch(row["id"])
        return {"refreshed": True}


@router.post("/api/sessions/{sid}/resources/{rid}/reconcile")
async def reconcile_cleanup(request: Request, sid: str, rid: str):
    owner(request, sid)
    with errors():
        return await work(request).reconcile_cleanup(sid, rid)


@router.post("/api/sessions/{sid}/resources/{rid}/acknowledge")
async def acknowledge_resource(request: Request, sid: str, rid: str, body: ConfirmBody):
    owner(request, sid)
    if not body.confirm:
        raise HTTPException(422, "Confirm keeping the external resource.")
    with errors():
        return await work(request).acknowledge_resource(sid, rid)


@router.get("/api/changes")
async def all_changes(request: Request, cursor: str = "", limit: int = 50):
    with errors():
        page = await work(request).store.page(
            "change", owner=request.state.user_id, cursor=cursor, limit=limit
        )
        return {**page, "items": [public_record(r) for r in page["items"]]}


@router.get("/api/operations")
async def all_operations(request: Request, cursor: str = "", limit: int = 50):
    with errors():
        page = await work(request).store.page(
            "operation", owner=request.state.user_id, cursor=cursor, limit=limit
        )
        return {**page, "items": [public_record(r) for r in page["items"]]}


@router.get("/api/sessions/{sid}/assets/{kind}")
async def find_assets(request: Request, sid: str, kind: str, query: str = "", limit: int = 25):
    owner(request, sid)
    w = work(request)
    with errors():
        return {"items": await w.registry.handler(kind).find(query, w.actor(sid, ""), min(limit, 100))}


@router.get("/api/sessions/{sid}/assets/{kind}/describe")
async def describe_asset(request: Request, sid: str, kind: str, id: str):
    owner(request, sid)
    w = work(request)
    with errors():
        return await w.registry.handler(kind).describe(AssetRef(kind, id), w.actor(sid, ""))


@router.post("/internal/tools/{name}")
async def internal_tool(request: Request, name: str, body: ToolBody):
    w = work(request)
    if not w.toolbox.verify(body.session, body.key):
        raise HTTPException(403, "Invalid or expired session key.")
    with errors():
        if name == "catalogue":
            return {"tools": w.toolbox.catalogue(body.session)}
        live = request.app.state.orchestrator.get(body.session)
        turn = live.state.running()
        if turn is None:
            raise HTTPException(409, "No active turn may dispatch tools.")
        return await w.toolbox.dispatch(body.session, turn.id, name, body.arguments)


@router.get("/api/sessions/{sid}/changes/{cid}/versions")
async def change_versions(request: Request, sid: str, cid: str):
    owner(request, sid)
    with errors():
        return await work(request).changes.versions(sid, cid)


@router.get("/api/sessions/{sid}/operations/{oid}/results")
async def result_page(request: Request, sid: str, oid: str, chunk: int = 0):
    owner(request, sid)
    with errors():
        return await work(request).operations.result_page(sid, oid, chunk)


@router.get("/api/sessions/{sid}/skills")
async def skills(request: Request, sid: str, name: str = ""):
    owner(request, sid)
    w = work(request)
    with errors():
        try:
            return await asyncio.wait_for(w.preferences.get(w.actor(sid, ""), name), 10)
        except TimeoutError:
            raise WorkError(
                "Skill discovery reached its bounded deadline. Built-in templates remain available.", 503
            ) from None
