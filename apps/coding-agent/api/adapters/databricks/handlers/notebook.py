"""Notebook editing plus isolated user-owned Jobs runs; no app-identity execution fallback."""

from .workspace import WorkspaceHandler
from .job import JobHandler
from ....domain.asset import WorkError


class NotebookHandler(WorkspaceHandler):
    def __init__(self, workspace, http):
        super().__init__(workspace, "notebook")
        self.jobs = JobHandler(http, workspace)

    async def probe(self, who):
        result = await super().probe(who)
        if self.jobs.api(who):
            try:
                await self.jobs.list_native(who, 1)
                return {
                    **result,
                    "run": True,
                    "reason": "Notebook runs use an ephemeral Jobs submission that runs as you.",
                }
            except PermissionError:
                pass
        return result

    async def submit(self, ref, params, who, key):
        if not self.jobs.api(who):
            raise PermissionError(
                "Notebook execution needs your Jobs API scope. No code will run as the app identity."
            )
        if not self.inside(ref, who):
            raise WorkError("Notebook run is outside the working folder.", 403)
        await self.read(ref, who)
        task = {
            "task_key": "agent_notebook",
            "notebook_task": {"notebook_path": ref.id, "base_parameters": params.get("parameters", {})},
        }
        # Native runs/submit defaults to the authenticated caller, with no app service principal.
        row = await self.jobs.http.post(
            self.jobs.base + "/runs/submit",
            who.token,
            {"run_name": who.scope.job_prefix + "notebook", "tasks": [task], "idempotency_token": key},
        )
        return {"nativeId": str(row["run_id"]), "tier": "api"}

    async def observe(self, native, who):
        return await self.jobs.observe(native, who)

    async def cancel(self, native, who):
        return await self.jobs.cancel(native, who)
