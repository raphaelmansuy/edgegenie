"""Lakebase instance metadata and creation. Database credentials never enter tool results."""

from urllib.parse import quote
from .definition import DefinitionHandler
from ....domain.asset import WorkError


class InstanceHandler(DefinitionHandler):
    kind = "instance"
    scope = "postgres"
    resource = "database_instances"
    base = "/api/2.0/database/instances"

    def path(self, id):
        return self.base + "/" + quote(id, safe="")

    def name_inside(self, name, who):
        return bool(name and name.startswith(who.scope.instance_prefix))

    async def probe(self, who):
        if not self.api(who):
            return {
                "read": False,
                "change": False,
                "run": False,
                "tier": "unavailable",
                "reason": "The app was not granted postgres user scope.",
            }
        await self.list_native(who, 1)
        return {
            "read": True,
            "change": True,
            "run": True,
            "tier": "api",
            "reason": "Creating an instance incurs ongoing cost and always requires review.",
        }

    async def list_native(self, who, limit, query=""):
        data = await self.http.get(self.base, who.token, {"page_size": min(limit, 100)})
        return [
            {
                "kind": self.kind,
                "id": r["name"],
                "name": r["name"],
                "capped": bool(data.get("next_page_token")),
            }
            for r in data.get("database_instances", [])
            if query.casefold() in r["name"].casefold()
        ]

    async def get_native(self, id, who):
        return await self.http.get(self.path(id), who.token)

    def validate(self, spec, who):
        if set(spec) - {"name", "capacity"}:
            raise WorkError("Instance definitions accept only name and capacity.", 422)
        if spec.get("capacity") not in ("CU_1", "CU_2", "CU_4", "CU_8"):
            raise WorkError("Choose an explicit supported instance capacity.", 422)

    async def plan(self, *args, **kwargs):
        from dataclasses import replace
        from ....domain.policy.verdict import ActionClass

        return replace(
            await super().plan(*args, **kwargs), action=ActionClass.IRREVERSIBLE, undo_available=False
        )

    async def write_native(self, id, spec, old, who, *, create):
        if not create:
            raise WorkError("Instance configuration updates are not offered by this handler.", 422)
        await self.http.post(self.base, who.token, spec)
        return spec["name"]

    async def delete_native(self, id, who):
        await self.http.request("DELETE", self.path(id), who.token)

    def requires_review(self, params):
        return True

    async def submit(self, ref, params, who, key):
        # Creation is a reviewed change. Following readiness is a separate durable operation.
        if not self.name_inside(ref.id, who):
            raise WorkError("Instance is outside the session prefix.", 403)
        await self.get_native(ref.id, who)
        return {"nativeId": ref.id, "tier": "api"}

    async def observe(self, native, who):
        row = await self.get_native(native, who)
        state = {"AVAILABLE": "succeeded", "FAILED": "failed", "DELETED": "cancelled"}.get(
            row.get("state"), "running"
        )
        return {"state": state, "result": row}

    async def cancel(self, native, who):
        raise WorkError(
            "Instance creation cannot be cancelled here. Review cleanup once its outcome is known.", 422
        )
