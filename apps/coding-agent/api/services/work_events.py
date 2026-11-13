"""Atomic ledger changes plus a durable event outbox; replay never repeats a workspace effect."""

import asyncio
import time
from uuid import uuid4
from ..domain.events import Event


class WorkEvents:
    def __init__(self, store, emit):
        self.store, self.emit = store, emit
        self._lock = asyncio.Lock()

    async def commit(self, writes, sid, tid, kind, payload, owner):
        event = {
            "id": "event_" + uuid4().hex,
            "sessionId": sid,
            "owner": owner,
            "turnId": tid,
            "type": kind,
            "payload": payload,
            "state": "pending",
            "createdAt": time.time(),
        }
        rows = await self.store.batch([*writes, ("outbox", event, None)])
        await self.flush(sid)
        return rows[:-1]

    async def flush(self, sid=""):
        async with self._lock:
            cursor = ""
            pending = []
            while True:
                page = await self.store.page(
                    "outbox", session_id=sid, cursor=cursor, states=("pending",), limit=100
                )
                pending.extend(page["items"])
                cursor = page["nextCursor"]
                if not cursor:
                    break
            # Global chronological order, including when more than one page was pending.
            for row in sorted(pending, key=lambda r: (r["createdAt"], r["id"])):
                try:
                    await self.emit(
                        Event(
                            row["sessionId"],
                            row["type"],
                            {**row["payload"], "eventId": row["id"]},
                            turn_id=row.get("turnId"),
                        )
                    )
                except KeyError:
                    continue  # archived sessions are hydrated on demand
                await self.store.put("outbox", {**row, "state": "delivered"}, row["version"])
