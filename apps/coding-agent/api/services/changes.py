"""The only writer of planned assets: policy -> durable intent -> revision check -> apply -> readback."""

import asyncio
import json
import time
from dataclasses import asdict
from uuid import uuid4
from ..domain.asset import AssetRef, Plan, WorkError, digest, public_record
from ..domain.policy.verdict import Mode, ActionClass, verdict


class ChangeService:
    def __init__(self, registry, store, events, actor, mode, *, can_run=None):
        self.registry, self.store, self.events = registry, store, events
        self.actor, self.mode = actor, mode
        self.can_run = can_run or (lambda sid, kind: True)
        self._locks = {}

    def lock(self, cid):
        return self._locks.setdefault(cid, asyncio.Lock())

    async def _commit(self, row, event, expected=None, extra=()):
        writes = [("change", row, expected), *extra]
        rows = await self.events.commit(
            writes,
            row["sessionId"],
            row.get("turnId"),
            event,
            {"change": public_record({**row, "version": expected + 1 if expected else 1})},
            row["owner"],
        )
        return rows[0]

    def _plan(self, row):
        return Plan(
            AssetRef(**row["asset"]),
            row["baseRevision"],
            "",
            row["_after"],
            row["operations"],
            row["diff"],
            ActionClass(row["actionClass"]),
            row.get("language", ""),
            row["undoAvailable"],
            row.get("effect", "edit"),
        )

    async def propose(self, sid, tid, invocation, ref, base, ops, content=None, *, force_review=False):
        who = self.actor(sid, tid)
        handler = self.registry.handler(ref.kind)
        if not hasattr(handler, "plan"):
            raise WorkError("This asset cannot be changed here.", 422)
        try:
            plan = await handler.plan(ref, base, ops, who, content=content)
        except WorkError as exc:
            if not exc.current:
                raise
            before_id = digest([sid, ref.to_dict(), base])
            row = {
                "id": "chg_" + uuid4().hex[:20],
                "sessionId": sid,
                "owner": who.user_id,
                "turnId": tid,
                "invocationId": invocation,
                "asset": ref.to_dict(),
                "baseRevision": base,
                "newRevision": "",
                "state": "conflicted",
                "actionClass": "change",
                "verdict": "deny",
                "diff": "The base revision changed. Review the saved base, proposed operations and current content; read the current revision before proposing again.",
                "operations": ops,
                "previousContentId": before_id,
                "_after": content or "",
                "undoAvailable": False,
                "effect": "edit",
                "createdAt": time.time(),
                "reason": str(exc),
                "currentRevision": exc.current,
            }
            return public_record(await self._commit(row, "change.settled"))
        mode = Mode(self.mode(sid))
        decision = verdict(
            Mode.REVIEW if force_review and mode is not Mode.PLAN else mode,
            handler.inside(ref, who),
            plan.action,
        )
        row = {
            "id": "chg_" + uuid4().hex[:20],
            "sessionId": sid,
            "owner": who.user_id,
            "turnId": tid,
            "invocationId": invocation,
            "asset": plan.ref.to_dict(),
            "baseRevision": base,
            "newRevision": "",
            "state": "awaiting_review"
            if decision == "ask"
            else "refused"
            if decision == "deny"
            else "planned",
            "canRun": self.can_run(sid, ref.kind)
            and hasattr(handler, "submit")
            and plan.ref.kind == ref.kind,
            "actionClass": plan.action.value,
            "verdict": decision,
            "diff": plan.diff,
            "diffTruncated": len(plan.diff.encode()) >= 65536,
            "previousContentId": "",
            "_after": plan.after,
            "operations": ops,
            "language": plan.language,
            "undoAvailable": plan.undo_available,
            "effect": plan.effect,
            "createdAt": time.time(),
            "reason": (
                "Defined, not deployed. Run databricks bundle validate, then databricks bundle deploy from this definition folder."
                if plan.ref.kind != ref.kind
                else ""
            ),
        }
        previous = []
        if plan.undo_available and base:
            row["previousContentId"] = row["id"]
            previous = [
                (
                    "previous_content",
                    {
                        "id": row["id"],
                        "sessionId": sid,
                        "owner": who.user_id,
                        "asset": plan.ref.to_dict(),
                        "state": "retained",
                        "createdAt": row["createdAt"],
                        "_content": plan.before,
                    },
                    None,
                )
            ]
        row = await self._commit(row, "change.proposed", extra=previous)
        if decision == "deny":
            row = {**row, "reason": "Refused: Plan mode or outside the working fence."}
            return public_record(await self._commit(row, "change.settled", row["version"]))
        if decision == "allow":
            return await self.decide(sid, row["id"], "apply", "auto:" + row["id"], who.user_id)
        return public_record(row)

    async def bind_invocation(self, sid, cid, invocation):
        async with self.lock(cid):
            row = await self.get(sid, cid)
            if not row.get("invocationId"):
                row = await self._commit(
                    {**row, "invocationId": invocation}, "change.settled", row["version"]
                )
            return public_record(row)

    async def get(self, sid, cid):
        row = await self.store.get("change", cid)
        if row["sessionId"] != sid:
            raise WorkError("No such change.", 404)
        return row

    async def decide(self, sid, cid, decision, key, user):
        if decision not in ("apply", "apply_and_run", "reject"):
            raise WorkError("Unknown decision.", 422)
        async with self.lock(cid):
            row = await self.get(sid, cid)
            if row.get("decisionKey") == key and row.get("decision") == decision:
                return public_record(row)
            if row["state"] not in ("awaiting_review", "planned"):
                raise WorkError("This change is already decided or expired.")
            who = self.actor(sid, row["turnId"])
            if who.expires_at and who.expires_at <= time.time():
                raise WorkError("Sign in again before applying this change.", 401)
            row = {
                **row,
                "decidedBy": user,
                "decision": decision,
                "decisionKey": key,
                "decidedAt": time.time(),
            }
            if decision == "reject":
                return public_record(
                    await self._commit(
                        {
                            **row,
                            "state": "rejected",
                            "reason": "You rejected this change. Nothing was written.",
                        },
                        "change.decided",
                        row["version"],
                    )
                )
            if not self.registry.handler(row["asset"]["kind"]).inside(AssetRef(**row["asset"]), who):
                raise WorkError("Refused: this asset is now outside the session fence.", 403)
            row = await self._commit({**row, "state": "applying"}, "change.decided", row["version"])
            try:
                applied = await self.registry.handler(row["asset"]["kind"]).apply(self._plan(row), who)
                extra = []
                if row["effect"] == "create":
                    rid = digest([sid, applied.ref.to_dict()])
                    extra = [
                        (
                            "resource",
                            {
                                "id": rid,
                                "sessionId": sid,
                                "owner": user,
                                "asset": applied.ref.to_dict(),
                                "revision": applied.revision,
                                "changeId": cid,
                                "state": "present",
                                "createdAt": time.time(),
                            },
                            None,
                        )
                    ]
                row = await self._commit(
                    {
                        **row,
                        "state": "applied",
                        "asset": applied.ref.to_dict(),
                        "newRevision": applied.revision,
                        "appliedAt": time.time(),
                    },
                    "change.applied",
                    row["version"],
                    extra,
                )
            except WorkError as exc:
                row = await self._commit(
                    {**row, "state": "conflicted", "currentRevision": exc.current, "reason": str(exc)},
                    "change.settled",
                    row["version"],
                )
            except (PermissionError, LookupError) as exc:
                row = await self._commit(
                    {**row, "state": "failed", "reason": str(exc)}, "change.settled", row["version"]
                )
            except Exception:
                row = await self._commit(
                    {
                        **row,
                        "state": "unknown",
                        "reason": "The write outcome is unknown. Read to reconcile; do not apply again.",
                    },
                    "change.settled",
                    row["version"],
                )
            return public_record(row)

    async def undo(self, sid, cid, user):
        async with self.lock(cid):
            row = await self.get(sid, cid)
            if (
                row["state"] not in ("applied", "verified")
                or not row["undoAvailable"]
                or not row["baseRevision"]
            ):
                raise WorkError(
                    "Undo is unavailable for this change. Created resources can be removed through cleanup."
                )
            if time.time() - row["createdAt"] > 30 * 86400:
                raise WorkError("The 30-day undo window expired.")
            who = self.actor(sid, row["turnId"])
            ref = AssetRef(**row["asset"])
            handler = self.registry.handler(ref.kind)
            if not handler.inside(ref, who):
                raise WorkError("Undo refused: outside the fence.", 403)
            # Persist intent before restoring. Recovery must never repeat the restore automatically.
            row = await self._commit({**row, "state": "reverting"}, "change.decided", row["version"])
            try:
                previous = await self.store.get("previous_content", row["previousContentId"])
                value = await handler.restore(
                    ref, row["newRevision"], previous["_content"], who, row.get("language", "")
                )
                row = {**row, "state": "reverted", "restoredRevision": value.revision, "decidedBy": user}
            except WorkError as exc:
                row = {**row, "state": "conflicted", "reason": str(exc), "currentRevision": exc.current}
            except PermissionError as exc:
                row = {**row, "state": "failed", "reason": str(exc)}
            except Exception:
                row = {
                    **row,
                    "state": "unknown",
                    "reason": "Undo outcome is unknown; reconcile by reading.",
                }
            return public_record(await self._commit(row, "change.settled", row["version"]))

    async def versions(self, sid, cid):
        row = await self.get(sid, cid)
        who = self.actor(sid, row.get("turnId", ""))
        before = ""
        before_available = False
        if row.get("previousContentId"):
            try:
                old = await self.store.get("previous_content", row["previousContentId"])
                before = old["_content"]
                before_available = True
            except WorkError:
                pass
        current = await self.registry.handler(row["asset"]["kind"]).read(AssetRef(**row["asset"]), who)
        after = row.get("_after", "")
        if not after and before_available and row.get("operations"):
            render = getattr(self.registry.handler(row["asset"]["kind"]), "render_edit", None)
            if render:
                after = render(before, row["operations"], row.get("language", "PYTHON"))
        cap = 100000
        return {
            "base": {
                "revision": row["baseRevision"],
                "text": before[:cap],
                "available": before_available,
                "truncated": len(before) > cap,
            },
            "proposed": {
                "text": after[:cap],
                "operations": row.get("operations", []),
                "truncated": len(after) > cap,
            },
            "current": {
                "revision": current.revision,
                "text": current.content[:cap],
                "truncated": len(current.content) > cap,
            },
        }

    async def reconcile(self, sid, cid):
        async with self.lock(cid):
            row = await self.get(sid, cid)
            if row["state"] != "unknown":
                return public_record(row)
            ref = AssetRef(**row["asset"])
            actual = await self.registry.handler(ref.kind).read(ref, self.actor(sid, row["turnId"]))
            before = ""
            if row.get("previousContentId"):
                before = (await self.store.get("previous_content", row["previousContentId"]))["_content"]
            state = (
                "applied"
                if digest(actual.content) == digest(row["_after"])
                else "failed"
                if digest(actual.content) == digest(before)
                else "conflicted"
            )
            return public_record(
                await self._commit(
                    {
                        **row,
                        "state": state,
                        "newRevision": actual.revision,
                        "reason": "Reconciled by read-back.",
                    },
                    "change.settled",
                    row["version"],
                )
            )

    async def mark_observed(self, row):
        return await self._commit({**row, "state": "verified"}, "change.settled", row["version"])

    async def expire(self, sid, reason="The session or turn ended before a decision."):
        cursor = ""
        while True:
            page = await self.store.page(
                "change", session_id=sid, cursor=cursor, states=("awaiting_review",), limit=100
            )
            for row in page["items"]:
                await self._commit(
                    {**row, "state": "expired", "reason": reason}, "change.settled", row["version"]
                )
            cursor = page["nextCursor"]
            if not cursor:
                break

    async def recover(self):
        for state, target in [
            ("applying", "unknown"),
            ("reverting", "unknown"),
            ("awaiting_review", "expired"),
        ]:
            cursor = ""
            while True:
                page = await self.store.page("change", cursor=cursor, states=(state,), limit=100)
                for row in page["items"]:
                    await self._commit(
                        {**row, "state": target, "reason": "Server restarted; no write was repeated."},
                        "change.settled",
                        row["version"],
                    )
                cursor = page["nextCursor"]
                if not cursor:
                    break
