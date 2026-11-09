"""In-memory event store. Same contract as the Postgres one; used by tests and the demo mode."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import replace

from ...domain.events import Event
from .broadcast import Broadcast


class MemoryEventStore(Broadcast):
    durable = False
    def __init__(self) -> None:
        super().__init__()
        self._snapshots: dict[str, dict] = {}
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

    async def commit(self, event: Event, snapshot: dict) -> Event:
        import copy
        self._snapshots[event.session_id] = copy.deepcopy(snapshot)
        return await self.append(event)

    async def snapshots(self) -> list[dict]:
        import copy
        return copy.deepcopy(list(self._snapshots.values()))

    def all_rows(self, session_id: str) -> list[dict]:
        return list(self._rows.get(session_id, []))

    def clear(self) -> None:
        self._snapshots.clear()
        self._rows.clear()
        self._subs.clear()
