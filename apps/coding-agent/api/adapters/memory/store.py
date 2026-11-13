"""In-memory event store. Same contract as the Postgres one; used by tests and the demo mode."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import replace

from ...domain.events import Event
from .broadcast import Broadcast
from ...domain.session_index import header, cursor_decode, cursor_encode


class MemoryEventStore(Broadcast):
    durable = False

    def __init__(self) -> None:
        super().__init__()
        self._snapshots: dict[str, dict] = {}
        self._headers = {}
        self._rows: dict[str, list[dict]] = defaultdict(list)
        self._subs: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def append(self, event: Event) -> Event:
        assert event.session_id, "event without a session id"
        async with self._lock:
            rows = self._rows[event.session_id]
            stored = event if event.seq else replace(event, seq=len(rows) + 1)
            rows.append(stored.to_dict())
        self.publish(event.session_id, stored.to_dict())
        return stored

    async def since(self, session_id: str, seq: int, limit: int = 2000) -> list[dict]:
        return [r for r in self._rows.get(session_id, []) if r["seq"] > seq][:limit]

    async def latest_seq(self, session_id: str) -> int:
        rows = self._rows.get(session_id, [])
        return rows[-1]["seq"] if rows else 0

    async def commit(self, event: Event, snapshot: dict, *, participant=None) -> Event:
        import copy

        copied = copy.deepcopy(snapshot)
        h = header(snapshot) if snapshot and snapshot.get("session") else None
        async with self._lock:
            if participant:
                await participant(None)
            rows = self._rows[event.session_id]
            stored = replace(event, seq=len(rows) + 1)
            if copied is not None:
                self._snapshots[event.session_id] = copied
            if h:
                self._headers[event.session_id] = h
            rows.append(stored.to_dict())
        self.publish(event.session_id, stored.to_dict())
        return stored

    async def snapshot(self, sid):
        import copy

        if sid not in self._snapshots:
            raise KeyError(sid)
        return copy.deepcopy(self._snapshots[sid])

    async def session_page(self, user, cursor="", limit=50):
        position = cursor_decode(cursor)
        limit = min(max(limit, 1), 100)
        rows = sorted(
            (
                r
                for r in self._headers.values()
                if r["user_id"] == user
                and r["status"] != "archived"
                and (not position or (r["updatedAt"], r["id"]) < position)
            ),
            key=lambda r: (r["updatedAt"], r["id"]),
            reverse=True,
        )
        return {
            "items": rows[:limit],
            "nextCursor": cursor_encode(rows[limit - 1]["updatedAt"], rows[limit - 1]["id"])
            if len(rows) > limit
            else "",
        }

    async def snapshots(self) -> list[dict]:
        import copy

        return copy.deepcopy(list(self._snapshots.values()))

    def all_rows(self, session_id: str) -> list[dict]:
        return list(self._rows.get(session_id, []))

    async def storage(self, sid):
        import json

        rows = self._rows.get(sid, [])
        return {
            "eventRows": len(rows),
            "eventPayloadBytes": sum(len(json.dumps(r).encode()) for r in rows),
            "snapshotPayloadBytes": len(json.dumps(self._snapshots[sid]).encode())
            if sid in self._snapshots
            else 0,
        }

    async def purge_session(self, sid, *, participant=None):
        async with self._lock:
            if participant:
                await participant(None)
            for rows in (self._rows, self._snapshots, self._headers):
                rows.pop(sid, None)

    def clear(self) -> None:
        self._snapshots.clear()
        self._rows.clear()
        self._subs.clear()
