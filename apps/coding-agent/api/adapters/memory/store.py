"""In-memory event store. Same contract as the Postgres one; used by tests and the demo mode."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import replace

from ...domain.events import Event


class MemoryEventStore:
    def __init__(self) -> None:
        self._rows: dict[str, list[dict]] = defaultdict(list)
        self._subs: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def append(self, event: Event) -> Event:
        assert event.session_id, "event without a session id"
        async with self._lock:
            rows = self._rows[event.session_id]
            stored = event if event.seq else replace(event, seq=len(rows) + 1)
            rows.append(stored.to_dict())
        for q in list(self._subs[event.session_id]):
            if not q.full():
                q.put_nowait(stored.to_dict())
        return stored

    async def since(self, session_id: str, seq: int) -> list[dict]:
        return [r for r in self._rows.get(session_id, []) if r["seq"] > seq]

    async def latest_seq(self, session_id: str) -> int:
        rows = self._rows.get(session_id, [])
        return rows[-1]["seq"] if rows else 0

    def subscriber_count(self, session_id: str) -> int:
        """How many live streams this session has. The reaper treats a watcher as activity."""
        return len(self._subs.get(session_id, []))

    def subscribe(self, session_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=2_000)
        self._subs[session_id].append(q)
        return q

    def unsubscribe(self, session_id: str, q: asyncio.Queue) -> None:
        subs = self._subs.get(session_id, [])
        if q in subs:
            subs.remove(q)

    def all_rows(self, session_id: str) -> list[dict]:
        return list(self._rows.get(session_id, []))

    def clear(self) -> None:
        self._rows.clear()
        self._subs.clear()
