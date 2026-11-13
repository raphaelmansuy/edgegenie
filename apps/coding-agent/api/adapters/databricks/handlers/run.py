"""Read-only native run attachment with an explicit system-table tier when API scopes are absent."""

import json
from ....domain.asset import AssetContent, WorkError, digest


class RunHandler:
    def __init__(self, parent, observations):
        self.parent, self.observations = parent, observations

    async def probe(self, who):
        if self.parent.api(who):
            await self.parent.list_native(who, 1)
            return {
                "read": True,
                "change": False,
                "run": False,
                "tier": "api",
                "reason": "Read run state and task results as you.",
            }
        return await self.observations.probe(who)

    async def read(self, ref, who):
        if not self.parent.api(who):
            return await self.observations.read(ref, who)
        row = await self.parent.observe(ref.id, who)
        return AssetContent(ref, digest(row), json.dumps(row, ensure_ascii=False, indent=2), metadata=row)

    async def describe(self, ref, who):
        value = await self.read(ref, who)
        return {"asset": ref.to_dict(), "revision": value.revision, **value.metadata}

    async def find(self, query, who, limit):
        if self.parent.api(who):
            raise WorkError("Attach a native run ID to read its tasks and result.", 422)
        return await self.observations.find(query, who, limit)
