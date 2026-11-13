"""Jobs lifecycle as the current user; scope-limited apps use reviewed bundle definitions."""

from .definition import DefinitionHandler
from ....domain.asset import WorkError


class JobHandler(DefinitionHandler):
    kind = "job"
    scope = "jobs"
    resource = "jobs"
    base = "/api/2.2/jobs"

    async def list_native(self, who, limit, query=""):
        data = await self.http.get(self.base + "/list", who.token, {"limit": min(limit, 100)})
        return [
            {
                "kind": self.kind,
                "id": str(r["job_id"]),
                "name": r.get("settings", {}).get("name", ""),
                "capped": bool(data.get("has_more")),
            }
            for r in data.get("jobs", [])
            if query.casefold() in r.get("settings", {}).get("name", "").casefold()
        ]

    async def get_native(self, id, who):
        if not str(id).isdigit():
            raise LookupError(id)
        row = await self.http.get(self.base + "/get", who.token, {"job_id": int(id)})
        if row.get("next_page_token"):
            raise WorkError(
                "This job definition is paged. Narrow the task before editing; a partial definition must never replace the whole job.",
                422,
            )
        return row["settings"]

    async def write_native(self, id, spec, old, who, *, create):
        spec = {**spec, "run_as": {"user_name": who.run_as}}
        if create:
            return (await self.http.post(self.base + "/create", who.token, spec))["job_id"]
        await self.http.post(self.base + "/reset", who.token, {"job_id": int(id), "new_settings": spec})
        return id

    async def delete_native(self, id, who):
        await self.http.post(self.base + "/delete", who.token, {"job_id": int(id)})

    async def submit(self, ref, params, who, key):
        if not self.api(who):
            raise PermissionError(
                "Jobs API scope is unavailable. Deploy the reviewed bundle yourself; it has not been deployed."
            )
        row = await self.http.get(self.base + "/get", who.token, {"job_id": int(ref.id)})
        if not self.name_inside(row.get("settings", {}).get("name", ""), who):
            raise WorkError("Job is outside the session prefix.", 403)
        if row.get("run_as_user_name") != who.run_as:
            raise PermissionError(
                "This job does not run as you. Agent code cannot run under another identity."
            )
        action = params.get("action", "run")
        if action == "repair":
            failed = params.get("rerun_tasks", [])
            if not failed:
                raise WorkError("Repair requires explicit failed task keys.", 422)
            original = await self.http.get(
                self.base + "/runs/get",
                who.token,
                {"run_id": int(params["run_id"]), "include_history": True},
            )
            if original.get("job_id") != int(ref.id):
                raise WorkError("The run does not belong to this job.", 403)
            permitted = {
                t["task_key"]
                for t in original.get("tasks", [])
                if t.get("state", {}).get("result_state") in ("FAILED", "TIMEDOUT", "UPSTREAM_FAILED")
            }
            if not set(failed) <= permitted:
                raise WorkError("Repair may rerun only tasks observed as failed.", 422)
            history = [
                r["id"]
                for r in original.get("repair_history", [])
                if r.get("type") == "REPAIR" and r.get("id") is not None
            ]
            result = await self.http.post(
                self.base + "/runs/repair",
                who.token,
                {
                    "run_id": int(params["run_id"]),
                    "rerun_tasks": failed,
                    **({"latest_repair_id": history[-1]} if history else {}),
                },
            )
            repair = result.get("repair_id")
            if repair is None:
                raise RuntimeError("The accepted repair did not return its repair ID.")
            return {"nativeId": f"{params['run_id']}:repair:{repair}", "repairId": repair, "runId": str(params["run_id"]), "tier": "api"}
        run = await self.http.post(
            self.base + "/run-now",
            who.token,
            {
                "job_id": int(ref.id),
                "job_parameters": params.get("parameters", {}),
                "idempotency_token": key,
            },
        )
        return {"nativeId": str(run["run_id"]), "tier": "api"}

    async def observe(self, native, who):
        run_id, _, repair_id = native.partition(":repair:")
        if not self.api(who):
            if self.observations is None:
                raise PermissionError(
                    "Jobs API scope is unavailable; native runs cannot be observed through this adapter."
                )
            return await self.observations.observe(run_id, who)
        row = await self.http.get(self.base + "/runs/get", who.token, {"run_id": int(run_id), **({"include_history": True} if repair_id else {})})
        status = row.get("state", {})
        if repair_id:
            repair = next((r for r in row.get("repair_history", []) if str(r.get("id")) == repair_id and r.get("type") == "REPAIR"), None)
            if repair is None:
                return {"state": "running", "reason": "Waiting for the accepted native repair to become observable.", "result": {"runId": run_id, "repairId": repair_id, "tasks": []}}
            status = repair.get("state", {})
        result = status.get("result_state", "")
        life = status.get("life_cycle_state", "")
        state = (
            ("succeeded" if result == "SUCCESS" else "cancelled" if result == "CANCELED" else "failed")
            if life in ("TERMINATED", "SKIPPED", "INTERNAL_ERROR")
            else "running"
        )
        tasks = []
        for task in row.get("tasks", [])[:100]:
            output = {}
            if task.get("run_id") and task.get("state", {}).get("life_cycle_state") == "TERMINATED":
                output = await self.http.get(
                    self.base + "/runs/get-output", who.token, {"run_id": task["run_id"]}
                )
            tasks.append({"key": task.get("task_key"), "state": task.get("state"), "output": output})
        return {
            "state": state,
            "result": {"tasks": tasks, "capped": bool(row.get("next_page_token")), **({"repairId": repair_id, "runId": run_id} if repair_id else {})},
            "reason": status.get("state_message", ""),
            "url": row.get("run_page_url", ""),
        }

    async def cancel(self, native, who):
        await self.http.post(self.base + "/runs/cancel", who.token, {"run_id": int(native.partition(":repair:")[0])})
