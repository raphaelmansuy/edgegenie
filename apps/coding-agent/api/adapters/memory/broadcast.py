"""Lossless stream hints: overflow forces replay from the committed event log."""

import asyncio
from collections import defaultdict


class Broadcast:
    def __init__(self) -> None:
        self._subs: dict[str, list[asyncio.Queue]] = defaultdict(list)

    def subscriber_count(self, session_id: str) -> int:
        return len(self._subs.get(session_id, []))

    def subscribe(self, session_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=2000)
        self._subs[session_id].append(q)
        return q

    def unsubscribe(self, session_id: str, q: asyncio.Queue) -> None:
        subs = self._subs.get(session_id, [])
        if q in subs:
            subs.remove(q)
        if not subs:
            self._subs.pop(session_id, None)

    def publish(self, session_id: str, row: dict) -> None:
        for q in list(self._subs.get(session_id, [])):
            if q.full():
                # A slow viewer is disposable; committed progress is not. The stream treats None
                # as a replay hint, and never advances its cursor over omitted rows.
                while not q.empty():
                    q.get_nowait()
                q.put_nowait(None)
            else:
                q.put_nowait(row)
