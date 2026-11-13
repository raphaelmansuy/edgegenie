"""Coalesce adjacent text deltas for at most 100 ms or 2 KiB before durable publish.

Only text may be lost within that explicit crash window. Transitions flush pending text first.
"""

import asyncio
from dataclasses import replace


class JournalWriter:
    def __init__(self, commit, window=0.1, maximum=2048):
        self.commit, self.window, self.maximum = commit, window, maximum
        self.pending = {}
        self.tasks = {}
        self.locks = {}

    async def emit(self, event):
        sid = event.session_id
        async with self.locks.setdefault(sid, asyncio.Lock()):
            if event.type not in ("message.delta", "thought.delta"):
                await self._flush(sid)
                return await self.commit(event, True)
            previous = self.pending.get(sid)
            if previous and (previous.type != event.type or previous.turn_id != event.turn_id):
                await self._flush(sid)
                previous = None
            self.pending[sid] = replace(
                event,
                payload={
                    **event.payload,
                    "text": (previous.payload.get("text", "") if previous else "")
                    + event.payload.get("text", ""),
                },
            )
            if len(self.pending[sid].payload["text"].encode()) >= self.maximum:
                await self._flush(sid)
            elif sid not in self.tasks:
                self.tasks[sid] = asyncio.create_task(self._later(sid))
            return event

    async def _later(self, sid):
        try:
            await asyncio.sleep(self.window)
            async with self.locks[sid]:
                await self._flush(sid)
        except asyncio.CancelledError:
            pass

    async def _flush(self, sid):
        task = self.tasks.pop(sid, None)
        if task and task is not asyncio.current_task():
            task.cancel()
        event = self.pending.pop(sid, None)
        if event:
            await self.commit(event, False)

    async def close(self):
        for sid in list(self.pending):
            async with self.locks[sid]:
                await self._flush(sid)
