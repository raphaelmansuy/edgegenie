"""Deterministic durable native-run double for full app/ACP/MCP operation tests."""

import time
from uuid import uuid4
from ..databricks.handlers.workspace import WorkspaceHandler
from ...domain.asset import WorkError


class DemoNotebookHandler(WorkspaceHandler):
    def __init__(self, workspace, store):
        super().__init__(workspace, "notebook")
        self.store = store

    async def probe(self, who):
        await self.workspace.seed(who.scope.folder)
        return {
            **await super().probe(who),
            "run": True,
            "reason": "Local deterministic workspace and native-run fixture.",
        }

    async def submit(self, ref, params, who, key):
        await self.read(ref, who)
        row, fresh = await self.store.reserve(
            "fake_run",
            key,
            {
                "id": "native_" + uuid4().hex[:16],
                "sessionId": who.session_id,
                "owner": who.user_id,
                "state": "running",
                "createdAt": time.time(),
                "finishAfter": max(0.2, min(float(params.get("seconds", 1)), 600)),
                "result": {"columns": ["value"], "rows": [["300"]], "totalRows": 1},
            },
        )
        return {"nativeId": row["id"], "tier": "api"}

    async def observe(self, native, who):
        row = await self.store.get("fake_run", native)
        if row["state"] == "running" and time.time() - row["createdAt"] >= row["finishAfter"]:
            row = await self.store.put("fake_run", {**row, "state": "succeeded"}, row["version"])
        return {
            "state": row["state"],
            "result": row["result"] if row["state"] == "succeeded" else {},
            "stateVersion": row["version"],
        }

    async def cancel(self, native, who):
        row = await self.store.get("fake_run", native)
        if row["state"] == "running":
            await self.store.put("fake_run", {**row, "state": "cancelled"}, row["version"])
