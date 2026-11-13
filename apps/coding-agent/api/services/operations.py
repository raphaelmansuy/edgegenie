"""Server-owned operations: submit once, observe by native handle, settle and wake once."""

import asyncio
import time
from uuid import uuid4
from ..domain.asset import WorkError, digest, public_record

from ..domain.operation import TERMINAL, ACTIVE
from ..domain.sqlquery import SqlError


class OperationService:
    def __init__(self, registry, store, events, actor, wake, *, interval=2, on_denial=None, concurrency=8):
        self.registry, self.store, self.events, self.actor, self.wake = registry, store, events, actor, wake
        self.on_denial = on_denial
        self.interval = interval
        self._tasks = {}
        self._locks = {}
        self._closed = False
        self._native_slots = asyncio.Semaphore(max(1, concurrency))

    async def _native_call(self, action, *args):
        async def call():
            async with self._native_slots:
                return await action(*args)

        # Admission and I/O share the bound, so a busy observer cannot strand a tool request.
        return await asyncio.wait_for(call(), 25)

    def lock(self, key):
        return self._locks.setdefault(key, asyncio.Lock())

    async def _save(self, row, event, extra=()):
        rows = await self.events.commit(
            [("operation", row, row["version"]), *extra],
            row["sessionId"],
            row.get("turnId"),
            event,
            {"operation": public_record({**row, "version": row["version"] + 1})},
            row["owner"],
        )
        return rows[0]

    async def submit(self, sid, tid, tool, ref, params):
        who = self.actor(sid, tid)
        handler = self.registry.handler(ref.kind)
        if not hasattr(handler, "submit"):
            raise WorkError("This asset cannot be run by this session.", 422)
        key = digest([sid, tid, tool, ref.to_dict(), params])
        row, fresh = await self.store.reserve(
            "operation",
            key,
            {
                "id": "op_" + uuid4().hex[:20],
                "sessionId": sid,
                "owner": who.user_id,
                "turnId": tid,
                "asset": ref.to_dict(),
                "submitKey": key,
                "state": "submitting",
                "nativeId": "",
                "ranAs": who.run_as,
                "tier": "api",
                "createdAt": time.time(),
                "stateVersion": 0,
                "_params": params,
                "wakeup": "notify",
            },
        )
        if fresh:
            try:
                native = await self._native_call(handler.submit, ref, params, who, row["id"])
                if not native.get("nativeId"):
                    raise RuntimeError("Native handle missing")
                row = await self._save(
                    {**row, **native, "state": native.get("state", "running")}, "operation.started"
                )
            except (PermissionError, WorkError, LookupError, SqlError) as exc:
                if isinstance(exc, PermissionError) and self.on_denial:
                    await self.on_denial(sid, ref.kind, str(exc), "run")
                row = await self._save(
                    {**row, "state": "rejected", "reason": str(exc)}, "operation.settled"
                )
            except Exception:
                row = await self._save(
                    {
                        **row,
                        "state": "unknown",
                        "reason": "Submission outcome unknown. Lookup only; never resubmit.",
                    },
                    "operation.settled",
                )
        if row["state"] not in TERMINAL:
            self.watch(row["id"])
        return public_record(row)

    async def get(self, sid, oid):
        row = await self.store.get("operation", oid)
        if row["sessionId"] != sid:
            raise WorkError("No such operation.", 404)
        return row

    def watch(self, oid):
        if not self._closed and (oid not in self._tasks or self._tasks[oid].done()):
            self._tasks[oid] = asyncio.create_task(self._watch(oid))

    async def _watch(self, oid):
        delay = self.interval
        try:
            while not self._closed:
                row = await self.store.get("operation", oid)
                if row["state"] in TERMINAL:
                    return
                try:
                    await self.observe(row["sessionId"], oid)
                except (WorkError, KeyError):
                    pass
                await asyncio.sleep(delay)
                delay = min(30, delay * 1.5)
        except asyncio.CancelledError:
            pass

    async def observe(self, sid, oid):
        async with self.lock(oid):
            row = await self.get(sid, oid)
            if row["state"] in TERMINAL:
                await self._wake(row)
                return public_record(row)
            who = self.actor(sid, row.get("turnId", ""))
            if who.expires_at and who.expires_at <= time.time():
                if row["state"] != "unobserved":
                    row = await self._save(
                        {
                            **row,
                            "state": "unobserved",
                            "reason": "Sign in again to refresh. Last seen state is retained.",
                        },
                        "operation.progress",
                    )
                return public_record(row)
            handler = self.registry.handler(row["asset"]["kind"])
            if not row.get("nativeId"):
                if hasattr(handler, "lookup"):
                    try:
                        native = await self._native_call(handler.lookup, row["id"], who)
                    except (PermissionError, LookupError, TimeoutError, RuntimeError) as exc:
                        reason = "Native lookup unavailable; submission remains unknown: " + str(exc)[:200]
                        if row.get("reason") != reason:
                            row = await self._save(
                                {**row, "state": "unknown", "reason": reason}, "operation.progress"
                            )
                        return public_record(row)
                    if native:
                        row = await self._save(
                            {**row, "nativeId": native, "state": "running"}, "operation.progress"
                        )
                return public_record(row)
            try:
                observation = await self._native_call(handler.observe, row["nativeId"], who)
            except (PermissionError, LookupError, TimeoutError, RuntimeError) as exc:
                if isinstance(exc, PermissionError) and self.on_denial:
                    await self.on_denial(sid, row["asset"]["kind"], str(exc), "run")
                if row["state"] != "unobserved":
                    row = await self._save(
                        {**row, "state": "unobserved", "reason": str(exc)[:300]}, "operation.progress"
                    )
                return public_record(row)
            remote = observation.get("stateVersion", row.get("remoteVersion", 0))
            if remote < row.get("remoteVersion", 0):
                return public_record(row)
            state = observation.get("state", "running")
            if state not in TERMINAL and state not in ACTIVE:
                state = "running"
            # Keep a persisted observation heartbeat, but do not snapshot unchanged poll replies.
            unchanged = state == row["state"] and all(
                row.get(k) == v for k, v in observation.items() if k not in ("stateVersion", "state")
            )
            if state not in TERMINAL and unchanged and time.time() - row.get("lastObservedAt", 0) < 30:
                return public_record(row)
            next_row = {
                **row,
                **observation,
                "state": state,
                "remoteVersion": remote,
                "lastObservedAt": time.time(),
                "stateVersion": row.get("stateVersion", 0) + 1,
                "reason": observation.get("reason", ""),
            }
            resources = []
            if (
                state == "succeeded"
                and not row.get("resourcesRecorded")
                and hasattr(handler, "created_resources")
            ):
                # Account for native SQL creations before publishing a settled operation. Lost
                # acknowledgements use the original SQL intent, not an inferred model summary.
                try:
                    produced = await self._native_call(handler.created_resources, row["nativeId"], who)
                except (PermissionError, LookupError, TimeoutError, RuntimeError, WorkError) as exc:
                    return public_record(
                        await self._save(
                            {
                                **row,
                                "state": "unobserved",
                                "reason": "Native run settled; created-resource verification is pending: "
                                + str(exc)[:200],
                            },
                            "operation.progress",
                        )
                    )
                for item in produced:
                    rid = digest([sid, item["asset"]])
                    try:
                        old = await self.store.get("resource", rid)
                    except WorkError:
                        old = None
                    resources.append(
                        (
                            "resource",
                            {
                                "id": rid,
                                "sessionId": sid,
                                "owner": who.user_id,
                                "operationId": oid,
                                "state": "present",
                                "createdAt": time.time(),
                                **item,
                            },
                            old["version"] if old else None,
                        )
                    )
                next_row.update(resourcesRecorded=True, resourceIds=[r[1]["id"] for r in resources])
            if state in TERMINAL:
                next_row["finishedAt"] = time.time()
            row = await self._save(
                next_row, "operation.settled" if state in TERMINAL else "operation.progress", resources
            )
            await self._wake(row)
            return public_record(row)

    async def result_page(self, sid, oid, chunk):
        row = await self.get(sid, oid)
        handler = self.registry.handler(row["asset"]["kind"])
        if not row.get("nativeId") or not hasattr(handler, "result_page"):
            raise WorkError("This operation has no paged SQL result.", 422)
        return await handler.result_page(row["nativeId"], chunk, self.actor(sid, row.get("turnId", "")))

    async def cancel(self, sid, oid):
        async with self.lock(oid):
            row = await self.get(sid, oid)
            if row["state"] in TERMINAL:
                return public_record(row)
            if not row.get("nativeId"):
                raise WorkError("The submission outcome is unknown; lookup its native handle first.")
            who = self.actor(sid, row.get("turnId", ""))
            extras = []
            try:
                wake = await self.store.get("wakeup", oid)
            except WorkError:
                wake = None
            if wake and wake["state"] == "armed":
                extras = [("wakeup", {**wake, "state": "cancelled"}, wake["version"])]
            row = await self._save(
                {**row, "state": "cancelling", "wakeup": "none"}, "operation.progress", extras
            )
            await self._native_call(
                self.registry.handler(row["asset"]["kind"]).cancel, row["nativeId"], who
            )
        return await self.observe(sid, oid)

    async def set_wakeup(self, sid, oid, action):
        if action not in ("continue", "notify", "none"):
            raise WorkError("Choose continue, notify or none.", 422)
        row = await self.get(sid, oid)
        who = self.actor(sid, row.get("turnId", ""))
        try:
            old = await self.store.get("wakeup", oid)
        except WorkError:
            old = None
        if row.get("wakeFiredAt") or (old and old["state"] == "fired"):
            raise WorkError("This wake-up already fired.")
        wake = {
            "id": oid,
            "sessionId": sid,
            "owner": who.user_id,
            "state": "armed" if action == "continue" else "cancelled",
            "action": action,
            "operationId": oid,
            "createdAt": old["createdAt"] if old else time.time(),
        }
        row = await self._save(
            {**row, "wakeup": action},
            "operation.progress",
            [("wakeup", wake, old["version"] if old else None)],
        )
        await self._wake(row)
        return public_record(row)

    async def _wake(self, row):
        async with self.lock("wake:" + row["sessionId"]):
            await self._wake_once(row)

    async def _wake_once(self, row):
        if row["state"] not in TERMINAL:
            return
        try:
            wake = await self.store.get("wakeup", row["id"])
        except WorkError:
            return
        if wake["state"] != "armed" or wake["action"] != "continue":
            return
        who = self.actor(row["sessionId"], row.get("turnId", ""))
        if who.expires_at and who.expires_at <= time.time():
            return
        # The turn's request key is the operation id. A crash before marking fired reuses that turn.
        try:
            await self.wake(row)
        except WorkError:
            return
        now = time.time()
        current = await self.store.get("operation", row["id"])
        # Keep the deduplication receipt with the operation, so the disposable wake-up
        # can be pruned without allowing an already consumed continuation to be armed again.
        await self._save(
            {**current, "wakeFiredAt": now, "wakeup": "none"},
            "operation.progress",
            [("wakeup", {**wake, "state": "fired", "firedAt": now}, wake["version"])],
        )

    async def recover(self):
        cursor = ""
        while True:
            page = await self.store.page("operation", cursor=cursor, states=ACTIVE, limit=100)
            for row in page["items"]:
                if row["state"] == "submitting":
                    row = await self._save(
                        {
                            **row,
                            "state": "unknown",
                            "reason": "Server restarted during submit. Lookup only.",
                        },
                        "operation.progress",
                    )
                self.watch(row["id"])
            cursor = page["nextCursor"]
            if not cursor:
                break

    async def close(self):
        self._closed = True
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
