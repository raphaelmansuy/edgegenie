"""App deployment lifecycle. Deployment requires a human review in every autonomy mode."""

from urllib.parse import quote
from .definition import DefinitionHandler
from ..app_logs import AppLogFailure
from ....domain.asset import WorkError
from ....domain.policy.paths import inside


class AppHandler(DefinitionHandler):
    kind = "app"
    scope = "apps"
    resource = "apps"
    base = "/api/2.0/apps"

    def __init__(self, http, workspace, *, logs=None):
        super().__init__(http, workspace)
        self.logs = logs

    async def describe(self, ref, who):
        result = await super().describe(ref, who)
        if not ref.id.startswith("/"):
            if self.logs is None:
                result["logs"] = {
                    "state": "unavailable",
                    "reason": "Native app log access is not configured.",
                }
            else:
                try:
                    result["logs"] = await self.logs.read(ref.id, who)
                except AppLogFailure as exc:
                    result["logs"] = {"state": exc.state, "reason": str(exc), "code": exc.code,
                                      **({"httpStatus": exc.http_status} if exc.http_status is not None else {})}
                except PermissionError as exc:
                    result["logs"] = {"state": "unreadable", "reason": str(exc)}
                except TimeoutError:
                    result["logs"] = {
                        "state": "unobserved",
                        "reason": "The log stream reached its bounded deadline. Refresh to observe again.",
                    }
        return result

    def path(self, id):
        return self.base + "/" + quote(id, safe="")

    def name_inside(self, name, who):
        return bool(name and name.startswith(who.scope.app_prefix))

    async def list_native(self, who, limit, query=""):
        row = await self.http.get(self.base, who.token, {"page_size": min(limit, 100)})
        return [
            {
                "kind": self.kind,
                "id": r["name"],
                "name": r["name"],
                "capped": bool(row.get("next_page_token")),
            }
            for r in row.get("apps", [])
            if query.casefold() in r["name"].casefold()
        ]

    async def get_native(self, id, who):
        return await self.http.get(self.path(id), who.token)

    def validate(self, spec, who):
        super().validate(spec, who)
        if spec.get("resources"):
            raise WorkError("Agent-created apps cannot attach secret or database resources.", 403)

    async def write_native(self, id, spec, old, who, *, create):
        if not create:
            raise WorkError(
                "App configuration updates are unavailable; use reviewed source edits and a reviewed deployment.",
                422,
            )
        await self.http.post(
            self.base, who.token, {k: v for k, v in spec.items() if k in ("name", "description")}
        )
        return spec["name"]

    async def delete_native(self, id, who):
        await self.http.request("DELETE", self.path(id), who.token)

    def requires_review(self, params):
        return True

    async def submit(self, ref, params, who, key):
        if not self.name_inside(ref.id, who):
            raise WorkError("App is outside the session prefix.", 403)
        if params.get("action") == "stop":
            await self.http.post(self.path(ref.id) + "/stop", who.token, {})
            return {"nativeId": ref.id + ":stop", "tier": "api"}
        source = params.get("source_code_path", "")
        if not inside(source, who.scope.folder):
            raise WorkError("App deployment source must be inside the working folder.", 403)
        row = await self.http.get(self.path(ref.id), who.token)
        if row.get("resources"):
            raise PermissionError(
                "This app has attached resources. Model-written code cannot be deployed into an identity that can access app secrets or databases."
            )
        result = await self.http.post(
            self.path(ref.id) + "/deployments", who.token, {"source_code_path": source, "mode": "SNAPSHOT"}
        )
        return {"nativeId": ref.id + ":" + result["deployment_id"], "tier": "api"}

    async def observe(self, native, who):
        app, deployment = native.split(":", 1)
        row = await self.http.get(
            self.path(app)
            if deployment == "stop"
            else self.path(app) + "/deployments/" + quote(deployment, safe=""),
            who.token,
        )
        status = row.get("compute_status" if deployment == "stop" else "status", {})
        state = (
            {"STOPPED": "succeeded", "ERROR": "failed"}
            if deployment == "stop"
            else {"SUCCEEDED": "succeeded", "FAILED": "failed", "CANCELLED": "cancelled"}
        ).get(status.get("state"), "running")
        return {"state": state, "result": row, "reason": status.get("message", "")}

    async def cancel(self, native, who):
        await self.http.post(self.path(native.split(":", 1)[0]) + "/stop", who.token, {})
