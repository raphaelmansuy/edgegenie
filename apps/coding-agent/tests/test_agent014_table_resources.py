"""SQL effects are accounted from durable intent and native identity/data-version observations."""

from dataclasses import replace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from api.adapters.databricks.handlers.table import TableHandler
from api.adapters.databricks.handlers.sql import StatementHandler
from api.adapters.durable.agent_ledgers import MemoryAgentLedgers
from api.adapters.durable.query_sqlite import SqliteQueryStore
from api.domain.asset import Actor, AssetRef, WorkError
from api.domain.asset_registry import AssetRegistry, Registration
from api.domain.scope import Scope
from api.services.agent_work import AgentWork
from api.services.operations import OperationService
from api.services.sql_service import SqlService
from api.services.work_events import WorkEvents


class Catalog:
    row = None
    version = 0
    deletes = 0

    async def table(self, name, token):
        if self.row is None:
            raise LookupError("not found")
        return dict(self.row)

    async def run_sql(self, source, token, **kwargs):
        assert source == "DESCRIBE HISTORY `main`.`agent`.`created` LIMIT 1"
        return {
            "status": {"state": "SUCCEEDED"},
            "manifest": {"schema": {"columns": [{"name": "version"}]}},
            "result": {"data_array": [[str(self.version)]]},
        }, "warehouse"

    async def remove_table(self, name, token):
        self.deletes += 1
        self.row = None


@pytest.fixture
async def rig():
    catalog = Catalog()

    class Provider:
        demo = True
        dialect = None
        submits = 0
        lost = False
        sid = str(uuid4())

        async def warehouses(self, actor):
            return [{"id": "warehouse", "state": "RUNNING"}]

        async def submit(self, actor, payload):
            self.submits += 1
            if "CREATE TABLE" in payload["statement"]:
                catalog.row = {
                    "fullName": "main.agent.created",
                    "owner": "alice",
                    "format": "DELTA",
                    "tableId": "table-identity",
                    "columns": [{"name": "id", "type": "BIGINT"}],
                }
            elif "DROP TABLE" in payload["statement"]:
                catalog.row = None
            if self.lost:
                raise TimeoutError("accepted, acknowledgement lost")
            return {"statement_id": self.sid}

        async def lookup_statement(self, *args):
            return self.sid

        async def status(self, *args):
            return {"status": {"state": "SUCCEEDED"}}

    provider = Provider()
    sql_store = SqliteQueryStore()
    sql = SqlService(provider, sql_store)
    table = TableHandler(catalog, sql)
    statement = StatementHandler(sql, table)
    store = MemoryAgentLedgers()
    events = WorkEvents(store, AsyncMock())
    who = Actor(
        "s", "opaque-owner", "t", Scope.for_session("s", "/scratch", "main.agent"), username="alice"
    )
    registry = AssetRegistry(
        [
            Registration("table", "Tables", "", table, ""),
            Registration("statement", "SQL statements", "", statement, ""),
        ]
    )
    ops = OperationService(registry, store, events, lambda *args: who, AsyncMock(), interval=1000)
    work = AgentWork(None, None, None, ops, None, registry, store, events, lambda *args: who)
    yield work, ops, table, catalog, provider, who
    await ops.close()
    await store.close()
    sql_store.close()


@pytest.mark.parametrize("lost", [False, True])
async def test_native_table_create_has_one_resource_and_reviewed_version_guarded_cleanup(rig, lost):
    work, ops, table, catalog, provider, who = rig
    provider.lost = lost
    row = await ops.submit(
        "s",
        "t",
        "dbx_run_sql",
        AssetRef("statement", "source"),
        {"sql": "CREATE TABLE main.agent.created (id BIGINT)"},
    )
    observed = await ops.observe("s", row["id"])
    assert observed["state"] == "succeeded" and observed["undoAvailable"] is False
    resources = (await work.store.page("resource", session_id="s"))["items"]
    assert len(resources) == 1 and resources[0]["asset"] == {"kind": "table", "id": "main.agent.created"}
    assert resources[0]["operationId"] == row["id"] and resources[0]["undoAvailable"] is False
    await ops.observe("s", row["id"])
    assert len((await work.store.page("resource", session_id="s"))["items"]) == 1 and provider.submits == 1
    review = await work.propose_cleanup("s", resources[0]["id"])
    assert review["state"] == "cleanup_pending" and catalog.deletes == 0
    deleted = await work.cleanup("s", review["id"], True)
    assert deleted["state"] == "deleted" and catalog.deletes == 1


@pytest.mark.parametrize("change", ["data", "identity", "owner", "schema"])
async def test_cleanup_refuses_data_edits_recreated_identity_and_moved_scope(rig, change):
    work, ops, table, catalog, provider, who = rig
    row = await ops.submit(
        "s",
        "t",
        "dbx_run_sql",
        AssetRef("statement", "source"),
        {"sql": "CREATE TABLE main.agent.created (id BIGINT)"},
    )
    await ops.observe("s", row["id"])
    resource = (await work.store.page("resource", session_id="s"))["items"][0]
    if change == "data":
        catalog.version = 1
    if change == "identity":
        catalog.row["tableId"] = "different-table"
    if change == "owner":
        catalog.row["owner"] = "bob"
    if change == "schema":
        moved = {**resource, "asset": {"kind": "table", "id": "main.outside.created"}}
        await work.store.put("resource", moved, resource["version"])
    with pytest.raises(WorkError):
        await work.propose_cleanup("s", resource["id"])
    assert catalog.deletes == 0


async def test_existing_create_if_not_exists_never_claims_a_preexisting_table(rig):
    work, ops, table, catalog, provider, who = rig
    catalog.row = {
        "fullName": "main.agent.created",
        "tableId": "preexisting",
        "owner": "alice",
        "format": "DELTA",
    }
    assert (
        await table.creation_candidates("CREATE TABLE IF NOT EXISTS main.agent.created (id BIGINT)", who)
        == []
    )


async def test_delegated_cleanup_uses_sql_scope_before_any_native_delete_attempt(rig):
    work, ops, table, catalog, provider, who = rig
    await provider.submit(None, {"statement": "CREATE TABLE"})
    ref = AssetRef("table", "main.agent.created")
    current = await table.cleanup_snapshot(ref, who)
    await table.remove(
        ref, current.revision, replace(who, delegated=True, scopes=("sql", "catalog.tables:read"))
    )
    assert catalog.deletes == 0 and catalog.row is None


async def test_uncertain_cleanup_absence_is_honest_and_can_be_acknowledged_without_deletion(rig):
    work, ops, table, catalog, provider, who = rig
    await work.store.put(
        "resource",
        {
            "id": "r",
            "sessionId": "s",
            "owner": who.user_id,
            "asset": {"kind": "table", "id": "main.agent.created"},
            "state": "unknown",
            "revision": "r",
            "createdAt": 1,
        },
    )
    observed = await work.reconcile_cleanup("s", "r")
    assert observed["state"] == "absent" and "may have been moved" in observed["reason"]
    acknowledged = await work.acknowledge_resource("s", "r")
    assert acknowledged["state"] == "acknowledged" and catalog.deletes == 0


def test_quoted_databricks_identifiers_use_the_same_fail_closed_scope_classifier():
    from api.domain.policy.sql import classify, mutation_parameters
    from api.domain.sqlquery import SqlError

    assert classify("CREATE TABLE `main`.`agent`.`created` (id BIGINT)").created_tables == (
        "main.agent.created",
    )
    assert mutation_parameters("DROP TABLE `main`.`agent`.`created`", [], schema="main.agent") == []
    with pytest.raises(SqlError):
        mutation_parameters("DROP TABLE `main`.`agentX`.`created`", [], schema="main.agent")


async def test_sql_scope_refusal_is_rejected_before_any_native_effect(rig):
    work, ops, table, catalog, provider, who = rig
    row = await ops.submit(
        "s",
        "t",
        "dbx_run_sql",
        AssetRef("statement", "source"),
        {"sql": "CREATE TABLE main.outside.created (id BIGINT)"},
    )
    assert row["state"] == "rejected" and provider.submits == 0 and catalog.row is None
