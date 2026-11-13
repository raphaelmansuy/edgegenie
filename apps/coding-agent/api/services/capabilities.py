"""Probe the actual session identity. Only explicit permission errors downgrade capabilities."""

import asyncio
import time
from ..domain.asset import WorkError


class CapabilityService:
    def __init__(self, registry, store, events, actor, *, operations=True):
        self.registry, self.store, self.events, self.actor = registry, store, events, actor
        self._matrix = {}
        self.operations = operations

    async def probe(self, sid):
        who = self.actor(sid, "")

        async def one(entry):
            try:
                result = await asyncio.wait_for(entry.handler.probe(who), 10)
                return {
                    "kind": entry.kind,
                    "label": entry.label,
                    "description": entry.description,
                    **result,
                }
            except PermissionError as exc:
                return {
                    "kind": entry.kind,
                    "label": entry.label,
                    "read": False,
                    "change": False,
                    "run": False,
                    "tier": "unavailable",
                    "reason": str(exc),
                }
            except Exception as exc:
                old = next((r for r in self._matrix.get(sid, []) if r["kind"] == entry.kind), {})
                return {
                    **old,
                    "kind": entry.kind,
                    "label": entry.label,
                    "read": old.get("read", False),
                    "change": old.get("change", False),
                    "run": old.get("run", False),
                    "tier": old.get("tier", "unknown"),
                    "reason": "Could not verify capability: " + str(exc)[:160],
                }

        rows = await asyncio.gather(*(one(e) for e in self.registry.entries()))
        if not self.operations:
            rows = [{**r, "run": False} for r in rows]
        self._matrix[sid] = rows
        await self.events.commit(
            [],
            sid,
            None,
            "capabilities.reported",
            {"capabilities": rows, "checkedAt": time.time()},
            who.user_id,
        )
        return {"items": rows, "checkedAt": time.time(), "identity": who.user_id}

    def rows(self, sid):
        return self._matrix.get(sid, [])

    def forget(self, sid):
        self._matrix.pop(sid, None)

    def allows(self, sid, kind, verb):
        return bool(next((r.get(verb) for r in self.rows(sid) if r["kind"] == kind), False))

    async def downgrade(self, sid, kind, reason, verb=None):
        rows = [
            {
                **r,
                **(
                    {verb: False}
                    if verb
                    else {"read": False, "change": False, "run": False, "tier": "unavailable"}
                ),
                "reason": reason,
            }
            if r["kind"] == kind
            else r
            for r in self.rows(sid)
        ]
        self._matrix[sid] = rows
        who = self.actor(sid, "")
        await self.events.commit(
            [],
            sid,
            None,
            "capabilities.reported",
            {"capabilities": rows, "checkedAt": time.time()},
            who.user_id,
        )
