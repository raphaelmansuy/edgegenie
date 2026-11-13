"""The agent-work application facade. Coordinates ports; routes and the orchestrator share it."""

import dataclasses
import time
from ..domain.asset import WorkError, PendingCleanup, AssetRef, public_record
from ..domain.operation import ACTIVE
from ..ports.stores import ledger_rows
from ..domain.redact import redact_value


class AgentWork:
    def __init__(
        self, sessions, toolbox, changes, operations, capabilities, registry, store, events, actor
    ):
        self.sessions, self.toolbox, self.changes, self.operations = sessions, toolbox, changes, operations
        self.capabilities, self.registry, self.store, self.events, self.actor = (
            capabilities,
            registry,
            store,
            events,
            actor,
        )

    async def commit_transition(self, journal, event, snapshot, state):
        turn = next((t for t in state.turns if t.id == event.turn_id), None)
        if turn is None:
            return await journal.commit(event, snapshot)
        row = redact_value(
            {
                **dataclasses.asdict(turn),
                "id": turn.id,
                "sessionId": event.session_id,
                "owner": state.session.user_id,
                "state": turn.status.value,
                "updatedAt": time.time(),
            }
        )
        return await self.store.commit_transition(journal, event, snapshot, row)

    async def prepare(self, sid):
        return await self.sessions.prepare(sid)

    async def startup(self):
        await self.maintenance()
        await self.changes.recover()
        await self.operations.recover()
        await self.events.flush()

    async def maintenance(self):
        previous = await self.store.prune_previous(time.time() - 30 * 86400)
        await self.store.prune_wakeups()
        return previous

    async def continuation_count(self, sid, limit=5):
        """Count durable consumed receipts, including pre-migration wake-ups, once each."""
        consumed = set()
        async for row in ledger_rows(self.store, "operation", session_id=sid):
            if row.get("wakeFiredAt"):
                consumed.add(row["id"])
                if len(consumed) >= limit:
                    return len(consumed)
        async for row in ledger_rows(self.store, "wakeup", session_id=sid, states=("fired",)):
            consumed.add(row["id"])
            if len(consumed) >= limit:
                break
        return len(consumed)

    async def close(self):
        await self.operations.close()
        for close in getattr(self, "close_adapters", []):
            await close()
        await self.store.close()

    async def purge_session(self, journal, sid, *, erase_local=None):
        async for row in ledger_rows(self.store, "operation", session_id=sid, states=ACTIVE):
            raise WorkError("Resolve active or unknown operations before deleting history.")
        async for row in ledger_rows(self.store, "resource", session_id=sid):
            if row["state"] not in ("deleted", "acknowledged"):
                raise WorkError("Clean up session resources before deleting history.")
        if erase_local:
            await erase_local()
        await self.store.purge_session(journal, sid)
        self.toolbox.revoke(sid)
        self.sessions.forget(sid)
        self.capabilities.forget(sid)

    async def pending(self, sid, tid=""):
        match = lambda r: not tid or r.get("turnId") == tid
        return {
            "changes": [
                public_record(r)
                async for r in ledger_rows(
                    self.store, "change", session_id=sid, states=("awaiting_review",)
                )
                if match(r)
            ],
            "operations": [
                public_record(r)
                async for r in ledger_rows(self.store, "operation", session_id=sid, states=ACTIVE)
                if match(r)
            ],
            "reviews": [
                public_record(r)
                async for r in ledger_rows(self.store, "approval", session_id=sid, states=("pending",))
                if match(r)
            ],
        }

    async def expire(self, sid):
        await self.changes.expire(sid)
        cursor = ""
        while True:
            page = await self.store.page(
                "wakeup", session_id=sid, cursor=cursor, states=("armed",), limit=100
            )
            for row in page["items"]:
                await self.store.put("wakeup", {**row, "state": "cancelled"}, row["version"])
            cursor = page["nextCursor"]
            if not cursor:
                break
        async for row in ledger_rows(self.store, "approval", session_id=sid, states=("pending",)):
            await self.store.put("approval", {**row, "state": "expired"}, row["version"])

    async def native_proposal(self, sid, tid, request):
        raw = request.get("input")
        if not raw:
            return None
        title = request.get("action", "")
        name = next(
            (
                n
                for n in ("dbx_edit", "dbx_create", "dbx_define", "dbx_run_sql", "dbx_run")
                if title.endswith(n)
            ),
            None,
        )
        if not name:
            return None
        if name in ("dbx_run", "dbx_run_sql"):
            ref, params = self.toolbox.run_request(name, raw)
            result = await self.toolbox.run(sid, tid, "", ref, params, force_review=True)
            request["runReviewId"] = result.get("reviewId", "")
            linked = request["runReviewId"]
        else:
            result = await self.toolbox.proposal(sid, tid, name, raw, force_review=True)
            request["changeId"] = result["id"]
            linked = result["id"]
        # Repeated ACP requests must not strand a hidden, already-decided card.
        # Authority is the exact argument-bound grant recorded by the first owner decision.
        state = result.get("state")
        if result.get("decidedBy") and result.get("decision"):
            request["_recordedOutcome"] = "deny" if result["decision"] == "reject" else "allow_once"
        elif name in ("dbx_run", "dbx_run_sql") and state != "awaiting_review":
            request["_recordedOutcome"] = "allow_once"  # run() checked the exact durable permit
        elif state not in ("awaiting_review", "planned"):
            request.pop("changeId", None)
            request.pop("runReviewId", None)
            raise WorkError(
                result.get(
                    "reason", "This proposal is invalid; read its base revision and correct the input."
                ),
                422,
            )
        # Expose only the change card as the one decision surface.
        await self.events.commit(
            [],
            sid,
            tid,
            "approval.linked",
            {"approvalId": request["approvalId"], "changeId": linked},
            self.actor(sid, tid).user_id,
        )
        return result

    async def evidence_calls(self, sid, tid):
        cursor = ""
        rows = []
        while True:
            page = await self.store.page("invocation", session_id=sid, cursor=cursor, limit=100)
            rows.extend(r for r in page["items"] if r.get("turnId") == tid)
            cursor = page["nextCursor"]
            if not cursor:
                break
        return sorted(rows, key=lambda r: r["createdAt"])

    async def observed(self, sid, tid, related_change="", related_operation=""):
        return (await self.observation_proof(sid, tid, related_change, related_operation))["missing"]

    async def observation_proof(self, sid, tid, related_change="", related_operation=""):
        calls = await self.evidence_calls(sid, tid)
        missing, effects = [], 0
        async for change in ledger_rows(self.store, "change", session_id=sid):
            if change.get("turnId") != tid and change["id"] != related_change:
                continue
            if change["state"] in ("unknown", "applying", "reverting"):
                effects += 1
                missing.append("Reconcile uncertain change " + change["id"])
                continue
            if change["state"] not in (
                "applied",
                "verified",
            ):
                continue
            effects += 1
            matched = any(
                c["state"] == "completed"
                and c["asset"] == change["asset"]
                and c["tool"] in ("dbx_read", "dbx_describe", "dbx_operation")
                and c["createdAt"] > change.get("appliedAt", change["createdAt"])
                and c.get("observedRevision") == change["newRevision"]
                for c in calls
            )
            if matched and change["state"] == "applied":
                await self.changes.mark_observed(change)
            if not matched:
                missing.append("Read back or run " + change["asset"]["id"])
        async for operation in ledger_rows(self.store, "operation", session_id=sid):
            if operation.get("turnId") != tid and operation["id"] != related_operation:
                continue
            effects += 1
            matched = any(
                c["tool"] == "dbx_operation"
                and c["state"] == "completed"
                and c.get("effectState") == "succeeded"
                and c["asset"] == operation["asset"]
                and c["createdAt"] >= operation["createdAt"]
                for c in calls
            )
            if not matched:
                missing.append("Observe successful operation " + operation["id"])
        return {"missing": missing, "effects": effects}

    async def list_resources(self, sid):
        return await self.store.page(
            "resource", session_id=sid, states=("present", "cleanup_pending"), limit=100
        )

    async def propose_cleanup(self, sid, rid):
        row = await self.store.get("resource", rid)
        if row["sessionId"] != sid or row["state"] != "present":
            raise WorkError("No created resource is available for cleanup.", 404)
        who = self.actor(sid, "")
        ref = AssetRef(**row["asset"])
        handler = self.registry.handler(ref.kind)
        if not handler.inside(ref, who):
            raise WorkError("Cleanup refused: the resource is outside the session fence.", 403)
        current = await getattr(handler, "cleanup_snapshot", handler.read)(ref, who)
        if current.revision != row["revision"]:
            raise WorkError("Cleanup refused: this resource changed since the session created it.")
        row = await self.store.put("resource", {**row, "state": "cleanup_pending"}, row["version"])
        await self.events.commit(
            [], sid, None, "resource.updated", {"resource": public_record(row)}, who.user_id
        )
        return public_record(row)

    async def cleanup(self, sid, rid, confirm):
        row = await self.store.get("resource", rid)
        if row["sessionId"] != sid or row["state"] != "cleanup_pending":
            raise WorkError("Review the resource before deleting it.")
        who = self.actor(sid, "")
        ref = AssetRef(**row["asset"])
        handler = self.registry.handler(ref.kind)
        if not confirm:
            row = await self.store.put("resource", {**row, "state": "present"}, row["version"])
            return public_record(row)
        if not handler.inside(ref, who):
            raise WorkError("Cleanup refused: outside the fence.", 403)
        row = await self.store.put("resource", {**row, "state": "deleting"}, row["version"])
        try:
            await handler.remove(ref, row["revision"], who)
            row = {**row, "state": "deleted", "deletedAt": time.time()}
        except PendingCleanup as exc:
            row = {**row, "state": "unknown", "cleanupOperationId": exc.operation_id, "reason": str(exc)}
        except WorkError as exc:
            row = {**row, "state": "present", "reason": str(exc)}
        except PermissionError as exc:
            row = {**row, "state": "present", "reason": str(exc)}
        except Exception:
            row = {
                **row,
                "state": "unknown",
                "reason": "Cleanup outcome unknown; do not repeat automatically.",
            }
        saved = await self.store.put("resource", row, row["version"])
        await self.events.commit(
            [], sid, None, "resource.updated", {"resource": public_record(saved)}, who.user_id
        )
        return public_record(saved)

    async def reconcile_cleanup(self, sid, rid):
        row = await self.store.get("resource", rid)
        if row["sessionId"] != sid or row["state"] not in ("unknown", "deleting"):
            raise WorkError("No uncertain cleanup is available to observe.", 404)
        handler = self.registry.handler(row["asset"]["kind"])
        if row.get("cleanupOperationId") and hasattr(handler, "cleanup_outcome"):
            outcome = await handler.cleanup_outcome(row["cleanupOperationId"], self.actor(sid, ""))
            if outcome not in ("succeeded", "failed"):
                return public_record(row)
            state = "deleted" if outcome == "succeeded" else "present"
            row = await self.store.put(
                "resource",
                {
                    **row,
                    "state": state,
                    "reason": "Native cleanup statement observed: " + outcome,
                    **({"deletedAt": time.time()} if state == "deleted" else {}),
                },
                row["version"],
            )
            await self.events.commit(
                [], sid, None, "resource.updated", {"resource": public_record(row)}, row["owner"]
            )
            return public_record(row)
        try:
            await handler.read(AssetRef(**row["asset"]), self.actor(sid, ""))
        except LookupError:
            row = await self.store.put(
                "resource",
                {
                    **row,
                    "state": "absent",
                    "reason": "The original reference is absent. It may have been moved; inspect the workspace or acknowledge keeping external resources.",
                },
                row["version"],
            )
            await self.events.commit(
                [], sid, None, "resource.updated", {"resource": public_record(row)}, row["owner"]
            )
        return public_record(row)

    async def acknowledge_resource(self, sid, rid):
        row = await self.store.get("resource", rid)
        if row["sessionId"] != sid or row["state"] not in ("present", "absent"):
            raise WorkError("Resolve pending cleanup before acknowledging a resource.", 409)
        row = await self.store.put(
            "resource",
            {
                **row,
                "state": "acknowledged",
                "acknowledgedAt": time.time(),
                "reason": "You chose to keep external resources. Ongoing compute or storage charges are not stopped.",
            },
            row["version"],
        )
        await self.events.commit(
            [], sid, None, "resource.updated", {"resource": public_record(row)}, row["owner"]
        )
        return public_record(row)
