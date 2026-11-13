"""Pipeline definitions use native conditional writes and user-owned updates."""

from urllib.parse import quote
from .definition import DefinitionHandler
from ....domain.asset import WorkError


class PipelineHandler(DefinitionHandler):
    kind = "pipeline"
    scope = "pipelines"
    resource = "pipelines"
    base = "/api/2.0/pipelines"

    def path(self, id):
        return self.base + "/" + quote(str(id), safe="")

    async def list_native(self, who, limit, query=""):
        data = await self.http.get(self.base, who.token, {"max_results": min(limit, 100)})
        return [
            {
                "kind": self.kind,
                "id": r["pipeline_id"],
                "name": r.get("name", ""),
                "capped": bool(data.get("next_page_token")),
            }
            for r in data.get("statuses", [])
            if query.casefold() in r.get("name", "").casefold()
        ]

    async def get_native(self, id, who):
        row = await self.http.get(self.path(id), who.token)
        return {
            **row["spec"],
            "_last_modified": row.get("last_modified"),
            "_run_as": row.get("run_as_user_name"),
        }

    async def write_native(self, id, spec, old, who, *, create):
        body = {k: v for k, v in spec.items() if not k.startswith("_")}
        body["run_as"] = {"user_name": who.run_as}
        if create:
            return (await self.http.post(self.base, who.token, body))["pipeline_id"]
        if old.get("_last_modified") is None:
            raise WorkError("Pipeline did not expose its conditional-write revision.", 422)
        await self.http.request(
            "PUT", self.path(id), who.token, body={**body, "expected_last_modified": old["_last_modified"]}
        )
        return id

    async def delete_native(self, id, who):
        await self.http.request("DELETE", self.path(id), who.token)

    def requires_review(self, params):
        return bool(params.get("full_refresh") or params.get("full_refresh_selection"))

    async def submit(self, ref, params, who, key):
        if not self.api(who):
            raise PermissionError("No pipeline API scope. This definition is not deployed.")
        spec = await self.get_native(ref.id, who)
        if not self.name_inside(spec.get("name", ""), who):
            raise WorkError("Pipeline is outside the session prefix.", 403)
        if spec.get("_run_as") != who.run_as:
            raise PermissionError("The pipeline must run as you before the agent can start it.")
        result = await self.http.post(
            self.path(ref.id) + "/updates",
            who.token,
            {
                k: v
                for k, v in params.items()
                if k in ("full_refresh", "full_refresh_selection", "refresh_selection", "validate_only")
            },
        )
        return {"nativeId": ref.id + ":" + result["update_id"], "tier": "api"}

    async def observe(self, native, who):
        if not self.api(who):
            if self.observations is None:
                raise PermissionError("Pipelines API scope is unavailable.")
            return await self.observations.observe(native.split(":", 1)[-1], who)
        pipeline, update = native.split(":", 1)
        row = (await self.http.get(self.path(pipeline) + "/updates/" + quote(update, safe=""), who.token))[
            "update"
        ]
        state = {"COMPLETED": "succeeded", "FAILED": "failed", "CANCELED": "cancelled"}.get(
            row.get("state"), "running"
        )
        events = await self.http.get(self.path(pipeline) + "/events", who.token, {"max_results": 25})
        return {
            "state": state,
            "result": {
                "update": row,
                "events": [
                    e for e in events.get("events", []) if e.get("origin", {}).get("update_id") == update
                ],
                "capped": bool(events.get("next_page_token")),
            },
        }

    async def cancel(self, native, who):
        await self.http.post(self.path(native.split(":", 1)[0]) + "/stop", who.token, {})
