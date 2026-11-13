"""Opt-in native SELECT-only fault injection. Run with the repository venv and user CLI profile.

Drops one successful submit acknowledgement, restarts both local ledgers, then proves the
original statement is observed. Does not run a model, modify tables, or retry submission.
"""

import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.adapters.databricks.http import DbxHttp
from api.adapters.databricks.queries import DatabricksQueries
from api.adapters.databricks.handlers.sql import StatementHandler
from api.adapters.durable.agent_ledgers import SqliteAgentLedgers
from api.adapters.durable.query_sqlite import SqliteQueryStore
from api.domain.asset import Actor, AssetRef
from api.domain.asset_registry import AssetRegistry, Registration
from api.domain.scope import Scope
from api.services.operations import OperationService
from api.services.sql_service import SqlService
from api.services.work_events import WorkEvents


async def main():
    profile = os.environ.get("EXAM_DATABRICKS_PROFILE", "opengenie-dev")

    def cli(*args):
        return json.loads(
            subprocess.check_output(["databricks", *args, "--profile", profile, "-o", "json"])
        )

    me = cli("current-user", "me")
    host = "https://dbc-cb61f1e1-bd8e.cloud.databricks.com"
    assert me["userName"] == "raphael.mansuy@gmail.com"
    token = cli("auth", "token")["access_token"]
    http = DbxHttp(host, lambda: None, max_response_bytes=4 * 1024 * 1024)
    who = Actor(
        "sql-recovery-" + uuid4().hex[:8],
        str(me["id"]),
        "turn",
        Scope.for_session("sql-recovery", "/Users/" + me["userName"] + "/agent_scratch", None),
        workspace=host,
        token=token,
        username=me["userName"],
    )
    scratch = Path(tempfile.mkdtemp(prefix="agent014-sql-recovery-"))

    class LostAcknowledgement(DatabricksQueries):
        submits = 0
        actual_id = ""

        async def submit(self, actor, payload):
            self.submits += 1
            response = await super().submit(actor, payload)
            self.actual_id = response["statement_id"]
            raise TimeoutError("Injected lost submit acknowledgement")

    provider = LostAcknowledgement(http)

    class LostOperationHandle(StatementHandler):
        async def submit(self, *args):
            await super().submit(*args)
            raise TimeoutError("Injected loss before the operation ledger stored its local SQL handle")

    emitted = []

    async def emit(event):
        emitted.append(event.to_dict())

    async def wake(row):
        raise AssertionError("No automatic continuation was armed")

    def build():
        sql_store = SqliteQueryStore(str(scratch / "sql.db"))
        service = SqlService(provider, sql_store, run_enabled=True)
        store = SqliteAgentLedgers(str(scratch / "agent.db"))
        registry = AssetRegistry(
            [
                Registration(
                    "statement", "SQL statements", "sql", LostOperationHandle(service), "Recovery fixture"
                )
            ]
        )
        events = WorkEvents(store, emit)
        operations = OperationService(registry, store, events, lambda *args: who, wake, interval=300)
        return operations, store, sql_store

    operations, store, sql_store = build()
    try:
        warehouses = await provider.warehouses(
            StatementHandler(SqlService(provider, sql_store)).sql_actor(who)
        )
        chosen = next((w for w in warehouses if w["state"] == "RUNNING"), warehouses[0])
        canary = uuid4().hex
        submitted = await operations.submit(
            who.session_id,
            who.turn_id,
            "dbx_run",
            AssetRef("statement", "recovery-probe"),
            {"sql": "SELECT '" + canary + "' AS recovery_probe", "warehouse_id": chosen["id"]},
        )
        assert submitted["state"] == "unknown" and provider.submits == 1 and provider.actual_id
        assert not submitted["nativeId"]
        await operations.close()
        await store.close()
        sql_store.close()
        operations, store, sql_store = build()
        await operations.recover()
        deadline = time.monotonic() + 180
        while True:
            observed = await operations.observe(who.session_id, submitted["id"])
            if observed["state"] == "succeeded":
                break
            assert observed["state"] not in {"failed", "rejected", "cancelled"}, observed
            if time.monotonic() >= deadline:
                raise TimeoutError("History has not exposed the original statement; never resubmit")
            await asyncio.sleep(2)
        assert observed["statementId"] == provider.actual_id
        assert observed["result"]["rows"] == [[canary]] and provider.submits == 1
        repeated = await operations.submit(
            who.session_id,
            who.turn_id,
            "dbx_run",
            AssetRef("statement", "recovery-probe"),
            {"sql": "SELECT '" + canary + "' AS recovery_probe", "warehouse_id": chosen["id"]},
        )
        assert repeated["id"] == submitted["id"] and provider.submits == 1
        result = {
            "pass": True,
            "workspace": host,
            "identity": me["userName"],
            "owner": str(me["id"]),
            "statementId": provider.actual_id,
            "operationId": observed["id"],
            "submitCount": provider.submits,
            "checks": {
                "lostAcknowledgement": True,
                "lostOperationHandle": True,
                "bothStoresReopened": True,
                "sameNativeStatement": True,
                "actualResultVerified": True,
                "repeatReturnedOriginal": True,
                "noTableMutation": True,
            },
            "fixtureStorage": str(scratch),
            "scope": "Native backend fault injection; not a browser or model exam",
        }
        destination = (
            Path(__file__).resolve().parents[3] / "specs/014-improve-agent/e2e/sql-recovery-live-02.json"
        )
        destination.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result))
    finally:
        await operations.close()
        await store.close()
        sql_store.close()
        await http.close()


asyncio.run(main())
