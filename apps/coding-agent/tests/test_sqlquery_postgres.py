"""Real Postgres contracts: encryption, isolation, CAS, reservation and restart recovery.

Every test creates its own new database on the explicitly configured local test server.
No existing tables or databases are deleted. Native execution is covered separately in dev E2E.
"""

import asyncio
import os
import time
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet, InvalidToken

from api.adapters.durable.postgres import PostgresSessionStore
from api.adapters.durable.query_postgres import PostgresQueryStore
from api.config import Settings
from api.domain.sqlquery import SqlActor, SqlError
from api.services.sql_service import SqlService


@pytest.fixture
async def pg():
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import make_conninfo

    dsn = os.environ.get("TEST_SQL_PG_DSN")
    if not dsn:
        pytest.skip("TEST_SQL_PG_DSN must name the isolated SQL test server")
    name = "sqltest_" + uuid4().hex
    async with await psycopg.AsyncConnection.connect(dsn, autocommit=True) as admin:
        await admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    dsn = make_conninfo(dsn, dbname=name)
    journal = PostgresSessionStore(Settings(session_database_url=dsn))
    await journal.open()
    key = Fernet.generate_key().decode()
    store = PostgresQueryStore(journal.run_operation, key)
    try:
        yield store, journal, key, dsn
    finally:
        await journal.close()


def attempt(**extra):
    return {"id": str(uuid4()), "state": "submitting", "createdAt": time.time(), **extra}


async def test_atomic_reservation_encryption_and_restart(pg):
    store, journal, key, dsn = pg
    row = attempt(text="private SQL canary", sourceRef="source")
    results = await asyncio.gather(*(store.reserve("alice", "run:key", "same", row) for _ in range(8)))
    assert sum(fresh for _, fresh in results) == 1
    assert len({saved["id"] for saved, _ in results}) == 1

    async def encrypted(conn):
        cur = await conn.execute("SELECT body FROM agent.sql_item WHERE scope='alice'")
        return bytes((await cur.fetchone())[0])

    assert b"private SQL canary" not in await journal.run_operation(encrypted)
    await journal.close()
    reopened = PostgresSessionStore(Settings(session_database_url=dsn))
    try:
        await reopened.open()
        recovered = PostgresQueryStore(reopened.run_operation, key)
        assert (await recovered.get("alice", "run", row["id"]))["text"] == row["text"]
        saved, fresh = await recovered.reserve("alice", "run:key", "same", row)
        assert not fresh and saved["id"] == row["id"]
    finally:
        await reopened.close()


async def test_cas_and_owner_isolation(pg):
    store, *_ = pg
    one = await store.put("alice", "draft", "draft", attempt(text="one"))
    results = await asyncio.gather(*(store.put("alice", "draft", "draft", {**one, "text": str(i)},
                                             one["version"]) for i in range(8)), return_exceptions=True)
    assert sum(isinstance(row, dict) for row in results) == 1
    assert all(isinstance(row, (dict, SqlError)) for row in results)
    with pytest.raises(SqlError, match="unavailable"):
        await store.get("bob", "draft", "draft")
    assert (await store.get("alice", "draft", "draft"))["version"] == 2


async def test_identity_bound_ciphertext_cannot_move_between_owners(pg):
    store, journal, *_ = pg
    await store.put("alice", "draft", "id", attempt(text="secret"))
    await store.put("bob", "draft", "id", attempt(text="public"))

    async def swap(conn):
        await conn.execute("UPDATE agent.sql_item SET body=(SELECT body FROM agent.sql_item "
                           "WHERE scope='alice') WHERE scope='bob'")

    await journal.run_operation(swap)
    with pytest.raises(SqlError, match="authenticated"):
        await store.get("bob", "draft", "id")


async def test_operation_conflict_expiry_and_recent_order(pg):
    store, journal, *_ = pg
    row, _ = await store.reserve("alice", "key", "same", attempt())
    with pytest.raises(SqlError, match="different"):
        await store.reserve("alice", "key", "changed", attempt())

    async def expire(conn):
        await conn.execute("UPDATE agent.sql_operation SET created=%s", (time.time() - 90000,))

    await journal.run_operation(expire)
    with pytest.raises(SqlError, match="expired"):
        await store.reserve("alice", "key", "same", row)
    for i in range(3):
        await store.put("alice", "draft", str(i), attempt(id=str(i), createdAt=100 + i))
    assert [r["id"] for r in await store.list("alice", "draft", before=102, limit=2)] == ["1", "0"]


async def test_concurrency_source_user_and_global_limits(pg):
    store, *_ = pg
    await store.reserve("alice", "a", "a", attempt(sourceRef="same"))
    with pytest.raises(SqlError, match="active"):
        await store.reserve("alice", "b", "b", attempt(sourceRef="same"))
    for i in range(3):
        await store.reserve("alice", str(i), str(i), attempt())
    with pytest.raises(SqlError, match="active"):
        await store.reserve("alice", "fifth", "fifth", attempt())
    for i in range(28):
        await store.reserve(f"user{i}", "key", "key", attempt())
    with pytest.raises(SqlError, match="active"):
        await store.reserve("last", "key", "key", attempt())


async def test_run_recovery_keeps_statement_handle_without_resubmit(pg):
    from api.adapters.databricks.queries import DemoQueries

    store, journal, key, dsn = pg
    actor = SqlActor("workspace", "alice", "user-token")
    service = SqlService(DemoQueries(store), store)
    source = await service.draft(actor, {"text": "SELECT 1 AS result"})
    body = {"draftId": source["id"], "version": source["version"], "warehouseId": "demo-warehouse"}
    run = await service.run(actor, body, "once")
    await journal.close()
    reopened = PostgresSessionStore(Settings(session_database_url=dsn))
    try:
        await reopened.open()
        recovered = PostgresQueryStore(reopened.run_operation, key)
        provider = DemoQueries(recovered)

        async def forbidden(*_):
            raise AssertionError("A recovered intent must not submit twice")

        provider.submit = forbidden
        service = SqlService(provider, recovered)
        replay = await service.run(actor, body, "once")
        assert replay["id"] == run["id"] and replay["statementId"] == run["statementId"]
        assert (await service.observe(actor, run["id"], cancel=True))["state"] == "canceled"
    finally:
        await reopened.close()


def test_key_derivation_is_stable_separate_and_requires_a_key():
    shared = Fernet.generate_key().decode()
    first = PostgresQueryStore(None, shared_key=shared)
    second = PostgresQueryStore(None, shared_key=shared)
    encoded = first._encode("a", "draft", "id", {"text": "SELECT 1"})
    assert second._decode("a", "draft", "id", encoded)["text"] == "SELECT 1"
    with pytest.raises(InvalidToken):
        Fernet(shared.encode()).decrypt(encoded)
    with pytest.raises(ValueError):
        PostgresQueryStore(None)


async def test_native_stopped_warehouse_submits_on_demand_without_a_start_call(pg):
    from api.adapters.databricks.queries import DatabricksQueries

    store, *_ = pg

    class Http:
        calls = []

        async def get(self, path, token, params=None):
            self.calls.append(("GET", path, token, params))
            return {"warehouses": [{"id": "stopped", "name": "Serverless", "state": "STOPPED"}]}

        async def post(self, path, token, body=None):
            self.calls.append(("POST", path, token, body))
            return {"statement_id": str(uuid4()), "status": {"state": "PENDING"}}

    http = Http()
    service = SqlService(DatabricksQueries(http), store, run_enabled=True)
    actor = SqlActor("workspace", "alice", "user-token")
    source = await service.draft(actor, {"text": "SELECT 1 AS result"})
    body = {"draftId": source["id"], "version": source["version"], "warehouseId": "stopped"}
    one = await service.run(actor, body, "once")
    two = await service.run(actor, body, "once")
    posts = [call for call in http.calls if call[0] == "POST"]
    assert one["state"] == "pending" and one["id"] == two["id"]
    assert len(posts) == 1 and posts[0][1:3] == ("/api/2.0/sql/statements", "user-token")
    assert posts[0][3]["wait_timeout"] == "0s"


async def test_http_composition_uses_the_durable_shared_journal(pg, monkeypatch):
    from fastapi.testclient import TestClient

    from api.main import build

    _, journal, key, dsn = pg
    await journal.close()
    monkeypatch.delenv("DATABRICKS_HOST", raising=False)
    cfg = Settings(session_database_url=dsn, sql_key=key, sql_run=True,
                   allowed_models=["fake/model-a"], default_model="fake/model-a")
    app = build(cfg)
    assert isinstance(app.state.sql.store, PostgresQueryStore)
    with TestClient(app) as client:
        assert client.get("/api/sql/capabilities").json()["durable"]
        source = client.post("/api/sql/drafts", json={"text": "SELECT 1"}).json()
        run = client.post("/api/sql/runs", headers={"Idempotency-Key": "once"}, json={
            "draftId": source["id"], "version": source["version"], "warehouseId": "demo-warehouse",
        })
        assert run.status_code == 202 and run.json()["statementId"]
