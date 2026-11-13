"""Journal acceptance and normalized state share one commit, including failure and migration."""

import base64
import os
import time

import pytest

from api.adapters.durable.agent_ledgers import SqliteAgentLedgers
from api.adapters.durable.sqlite import SqliteSessionStore
from api.adapters.memory.store import MemoryEventStore
from api.domain.asset import WorkError
from api.domain.events import Event
from api.services.agent_work import AgentWork


@pytest.fixture(params=["memory", "sqlite", "postgres"])
async def pair(request, tmp_path):
    if request.param == "postgres":
        dsn = os.environ.get("TEST_AGENT_PG_DSN")
        if not dsn:
            pytest.skip("set TEST_AGENT_PG_DSN to disposable agent014 database")
        from api.adapters.durable.postgres import PostgresSessionStore
        from api.adapters.durable.agent_postgres import PostgresAgentLedgers
        from api.config import Settings

        journal = PostgresSessionStore(Settings(session_database_url=dsn))
        await journal.open()
        store = PostgresAgentLedgers(journal, base64.urlsafe_b64encode(b"t" * 32).decode())
    else:
        journal = (
            MemoryEventStore()
            if request.param == "memory"
            else SqliteSessionStore(str(tmp_path / "journal.db"))
        )
        store = SqliteAgentLedgers(
            str(tmp_path / "ledger.db") if request.param == "sqlite" else "", journal=journal
        )
    yield journal, store
    await store.close()
    close = getattr(journal, "close", None)
    if close:
        result = close()
        if hasattr(result, "__await__"):
            await result


async def test_turn_and_retry_key_never_commit_without_journal_acceptance(pair, monkeypatch):
    from uuid import uuid4

    journal, store = pair
    sid, tid = "atomic-" + uuid4().hex, "turn-" + uuid4().hex
    snapshot = {"version": 1, "session": {"id": sid, "user_id": "u", "status": "ready"}, "turns": []}
    await journal.commit(Event(sid, "session.created", {}), snapshot)
    original = journal.commit

    async def fail(event, snapshot, *, participant=None):
        async def injected(connection):
            await participant(connection)
            raise RuntimeError("fault after normalized row before event")

        return await original(event, snapshot, participant=injected)

    monkeypatch.setattr(journal, "commit", fail)
    turn = {
        "id": tid,
        "sessionId": sid,
        "owner": "u",
        "state": "queued",
        "request_key": "retry",
        "createdAt": time.time(),
    }
    with pytest.raises(RuntimeError, match="fault after normalized"):
        await store.commit_transition(
            journal, Event(sid, "turn.started", {}, turn_id=tid), {**snapshot, "turns": [turn]}, turn
        )
    assert await journal.latest_seq(sid) == 1
    assert (await journal.snapshot(sid))["turns"] == []
    with pytest.raises(WorkError):
        await store.get("turn", tid)
    monkeypatch.setattr(journal, "commit", original)
    await store.commit_transition(
        journal, Event(sid, "turn.started", {}, turn_id=tid), {**snapshot, "turns": [turn]}, turn
    )
    assert await journal.latest_seq(sid) == 2
    assert (await store.get("turn", tid))["request_key"] == "retry"
    assert (await journal.snapshot(sid))["turns"][0]["id"] == tid


async def test_legacy_sqlite_ledger_import_is_lossless_and_not_replayed(tmp_path):
    path = str(tmp_path / "legacy.agent")
    old = SqliteAgentLedgers(path)
    await old.reserve(
        "change",
        "dedup",
        {
            "id": "change",
            "sessionId": "s",
            "owner": "u",
            "state": "applied",
            "createdAt": 1,
            "_before": "private source",
        },
    )
    await old.close()
    original = (tmp_path / "legacy.agent").read_bytes()
    journal = SqliteSessionStore(str(tmp_path / "journal.db"))
    paired = SqliteAgentLedgers(path, journal=journal)
    saved = await paired.get("change", "change")
    assert saved["_before"] == "private source"
    await paired.put("change", {**saved, "state": "verified"}, saved["version"])
    await paired.close()
    journal.close()
    journal = SqliteSessionStore(str(tmp_path / "journal.db"))
    paired = SqliteAgentLedgers(path, journal=journal)
    saved, fresh = await paired.reserve("change", "dedup", {"id": "ignored"})
    assert not fresh and saved["state"] == "verified" and saved["_before"] == "private source"
    assert (tmp_path / "legacy.agent").read_bytes() == original
    await paired.close()
    journal.close()


async def test_continuation_limit_survives_pruning_and_pages_past_recent_operations():
    store = SqliteAgentLedgers()
    work = AgentWork(None, None, None, None, None, None, store, None, None)
    await store.batch(
        [
            (
                "operation",
                {
                    "id": str(i),
                    "sessionId": "s",
                    "owner": "u",
                    "state": "succeeded",
                    "createdAt": i + 1,
                    **({"wakeFiredAt": 1} if i < 5 else {}),
                },
                None,
            )
            for i in range(110)
        ]
    )
    for i in range(5):
        await store.put(
            "wakeup", {"id": str(i), "sessionId": "s", "owner": "u", "state": "fired", "createdAt": 1}
        )
    assert await work.continuation_count("s") == 5
    assert await store.prune_wakeups() == 5
    assert await work.continuation_count("s") == 5
    assert await work.continuation_count("another") == 0
    await store.close()


async def test_storage_and_session_cascade_are_owner_isolated_and_remove_request_receipts(pair):
    from uuid import uuid4

    journal, store = pair
    sid, other = "purge-" + uuid4().hex, "keep-" + uuid4().hex
    for session in (sid, other):
        await journal.commit(
            Event(session, "session.created", {}),
            {"session": {"id": session, "user_id": "u", "status": "archived"}, "turns": []},
        )
        for kind in (
            "turn",
            "previous_content",
            "invocation",
            "change",
            "approval",
            "operation",
            "wakeup",
            "resource",
            "evidence",
            "usage_pass",
            "outbox",
            "session",
        ):
            await store.reserve(
                kind,
                session + kind,
                {
                    "id": session + kind,
                    "sessionId": session,
                    "owner": "u",
                    "createdAt": 1,
                    "state": "retained",
                    "_private": "secret source",
                },
            )
    report = await journal.storage(sid)
    sizes = await store.storage(sid)
    assert report["eventRows"] == 1 and report["eventPayloadBytes"] > 0
    assert sizes["previous_content"]["rows"] == 1 and sizes["previous_content"]["payloadBytes"] > 0
    assert "secret source" not in str(sizes)
    await store.purge_session(journal, sid)
    assert (await journal.storage(sid))["eventRows"] == 0
    assert all(r["rows"] == 0 for r in (await store.storage(sid)).values())
    assert (await journal.storage(other))["eventRows"] == 1
    assert (await store.get("previous_content", other + "previous_content"))["_private"] == "secret source"
    _, fresh = await store.reserve(
        "change",
        sid + "change",
        {"id": "replacement-" + sid, "sessionId": sid, "owner": "u", "createdAt": 2},
    )
    assert fresh


def test_history_api_requires_owner_admin_archive_and_exact_confirmation(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from api.main import build
    from api.config import Settings

    monkeypatch.delenv("DATABRICKS_HOST", raising=False)
    cfg = Settings(
        agent_mode="fake",
        tool_mode="none",
        allowed_models=["fake/model-a"],
        default_model="fake/model-a",
        dev_user="alice",
        llm_admins="alice",
        changes=True,
        journal_v2=True,
        agent_workspace_demo=True,
        session_db_path=str(tmp_path / "session.db"),
    )
    with TestClient(build(cfg)) as client:
        sid = client.post("/api/sessions", json={"folder": "/Users/alice/agent_scratch"}).json()["id"]
        url = f"/api/sessions/{sid}/history"
        body = {"confirmSessionId": sid}
        assert client.get(f"/api/sessions/{sid}/storage").json()["journal"]["eventRows"] > 0
        assert (
            client.get(f"/api/sessions/{sid}/storage", headers={"x-forwarded-user": "bob"}).status_code
            == 404
        )
        assert client.request("DELETE", url, json={"confirmSessionId": "wrong"}).status_code == 422
        assert client.request("DELETE", url, json=body).status_code == 409
        assert client.delete(f"/api/sessions/{sid}").status_code == 204
        client.app.state.settings.llm_admins = ""
        assert client.request("DELETE", url, json=body).status_code == 403
        client.app.state.settings.llm_admins = "alice"
        assert client.request("DELETE", url, json=body).status_code == 200
        assert client.get(f"/api/sessions/{sid}").status_code == 404
        assert client.get(f"/api/sessions/{sid}/storage").status_code == 404


async def test_purge_failure_rolls_back_ledger_and_journal_together(pair, monkeypatch):
    from uuid import uuid4

    journal, store = pair
    sid = "purge-fault-" + uuid4().hex
    await journal.commit(
        Event(sid, "session.created", {}), {"session": {"id": sid, "user_id": "u", "status": "archived"}}
    )
    await store.put(
        "previous_content",
        {
            "id": sid,
            "sessionId": sid,
            "owner": "u",
            "state": "retained",
            "createdAt": 1,
            "_private": "keep",
        },
    )
    original = journal.purge_session

    async def fail(sid, *, participant=None):
        async def injected(connection):
            await participant(connection)
            raise RuntimeError("fault before purge commit")

        return await original(sid, participant=injected)

    monkeypatch.setattr(journal, "purge_session", fail)
    with pytest.raises(RuntimeError, match="fault before purge"):
        await store.purge_session(journal, sid)
    assert (await journal.storage(sid))["eventRows"] == 1
    assert (await store.get("previous_content", sid))["_private"] == "keep"


@pytest.mark.parametrize(
    "kind,state",
    [("operation", "unknown"), ("operation", "running"), ("resource", "present"), ("resource", "unknown")],
)
async def test_purge_preflight_keeps_unsettled_work_and_resources(kind, state):
    from unittest.mock import AsyncMock

    store = SqliteAgentLedgers()
    work = AgentWork(None, None, None, None, None, None, store, None, None)
    await store.put(kind, {"id": "keep", "sessionId": "s", "owner": "u", "state": state, "createdAt": 1})
    erase = AsyncMock()
    with pytest.raises(WorkError):
        await work.purge_session(None, "s", erase_local=erase)
    erase.assert_not_called()
    assert (await store.get(kind, "keep"))["state"] == state
    await store.close()


def test_mode_snapshot_and_ledger_agree_after_process_restart(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from api.main import build
    from api.config import Settings

    monkeypatch.delenv("DATABRICKS_HOST", raising=False)
    cfg = Settings(
        agent_mode="fake",
        tool_mode="none",
        allowed_models=["fake/model-a"],
        default_model="fake/model-a",
        dev_user="alice",
        changes=True,
        journal_v2=True,
        agent_workspace_demo=True,
        session_db_path=str(tmp_path / "mode.db"),
    )
    with TestClient(build(cfg)) as client:
        sid = client.post("/api/sessions", json={"folder": "/Users/alice/agent_scratch"}).json()["id"]
        assert client.post(f"/api/sessions/{sid}/mode", json={"mode": "auto"}).status_code == 200
        assert client.get(f"/api/sessions/{sid}").json()["mode"] == "auto"
    with TestClient(build(cfg)) as client:
        assert client.get(f"/api/sessions/{sid}").json()["mode"] == "auto"
        assert client.get(f"/api/sessions/{sid}/work").json()["mode"] == "auto"
