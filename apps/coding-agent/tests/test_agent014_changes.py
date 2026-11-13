"""Contract and fault tests for revisioned writes, review, undo and encrypted durable state."""

import asyncio
import time
import os
import base64
from pathlib import Path
import pytest
from api.adapters.durable.agent_ledgers import SqliteAgentLedgers, MemoryAgentLedgers
from api.adapters.fake.workspace import DemoWorkspace
from api.adapters.databricks.handlers.workspace import WorkspaceHandler
from api.domain.asset import Actor, AssetRef, WorkError, digest
from api.domain.asset_registry import AssetRegistry, Registration
from api.domain.scope import Scope
from api.domain.edits import cells
from api.services.changes import ChangeService
from api.services.work_events import WorkEvents


@pytest.fixture(params=["memory", "sqlite", "postgres"])
async def ledger(request, tmp_path):
    journal = None
    if request.param == "postgres":
        dsn = os.environ.get("TEST_AGENT_PG_DSN")
        if not dsn:
            pytest.skip("set TEST_AGENT_PG_DSN to a disposable local agent014 database")
        from api.config import Settings
        from api.adapters.durable.postgres import PostgresSessionStore
        from api.adapters.durable.agent_postgres import PostgresAgentLedgers, table
        from api.adapters.durable.agent_ledgers import KINDS

        journal = PostgresSessionStore(Settings(session_database_url=dsn))
        await journal.open()
        async with journal.transaction() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT current_database()")
                assert (await cur.fetchone())[0].startswith("agent014"), (
                    "Agent ledger tests require a disposable agent014 database"
                )
                await cur.execute("DELETE FROM agent.request")
                for kind in KINDS:
                    await cur.execute("DELETE FROM " + table(kind))
        store = PostgresAgentLedgers(journal, base64.urlsafe_b64encode(b"t" * 32).decode())
    else:
        store = (
            MemoryAgentLedgers()
            if request.param == "memory"
            else SqliteAgentLedgers(str(tmp_path / "ledger.sqlite"))
        )
    try:
        yield store
    finally:
        await store.close()
        if journal:
            await journal.close()


async def fixture(store, mode="review"):
    ws = DemoWorkspace(store)
    path = await ws.seed("/Users/u/agent")
    ref = AssetRef("notebook", path)
    actor = Actor("s", "u", "t", Scope.for_session("s", "/Users/u/agent", "main.agent"))
    handler = WorkspaceHandler(ws, "notebook")
    registry = AssetRegistry([Registration("notebook", "Notebooks", "workspace.workspace", handler, "")])
    recorded = []

    async def emit(e):
        recorded.append(e)

    events = WorkEvents(store, emit)
    service = ChangeService(registry, store, events, lambda sid, tid: actor, lambda sid: mode)
    return ws, ref, actor, handler, service, recorded


async def test_review_preserves_other_59_cells_and_undo_is_byte_identical(ledger):
    ws, ref, actor, h, service, events = await fixture(ledger)
    before = await h.read(ref, actor)
    _, parts, _ = cells(before.content)
    row = await service.propose(
        "s",
        "t",
        "inv",
        ref,
        before.revision,
        [{"op": "replace_cell", "index": 3, "sha": digest(parts[3]), "source": "print(300)\n\n"}],
    )
    assert row["state"] == "awaiting_review"
    assert (await h.read(ref, actor)).content == before.content
    applied = await service.decide("s", row["id"], "apply", "decision-1", "u")
    assert applied["state"] == "applied"
    after = await h.read(ref, actor)
    _, new, _ = cells(after.content)
    assert len(new) == 60 and all(new[i] == parts[i] for i in range(60) if i != 3)
    reverted = await service.undo("s", row["id"], "u")
    assert reverted["state"] == "reverted" and (await h.read(ref, actor)).content == before.content


async def test_rejection_is_final_and_first_decision_wins(ledger):
    _, ref, a, h, s, _ = await fixture(ledger)
    before = await h.read(ref, a)
    _, parts, _ = cells(before.content)
    row = await s.propose(
        "s", "t", "inv", ref, before.revision, [{"op": "delete_cell", "index": 2, "sha": digest(parts[2])}]
    )
    rejected = await s.decide("s", row["id"], "reject", "first", "u")
    assert rejected["state"] == "rejected"
    assert (await s.decide("s", row["id"], "reject", "first", "u"))["version"] == rejected["version"]
    with pytest.raises(WorkError):
        await s.decide("s", row["id"], "apply", "second", "u")
    assert (await h.read(ref, a)).content == before.content


async def test_stale_revision_is_conflicted_not_merged(ledger):
    ws, ref, a, h, s, _ = await fixture(ledger)
    before = await h.read(ref, a)
    _, parts, _ = cells(before.content)
    row = await s.propose(
        "s",
        "t",
        "inv",
        ref,
        before.revision,
        [{"op": "replace_cell", "index": 0, "sha": digest(parts[0]), "source": "print(100)\n"}],
    )
    human = before.content + "\n# human edit\n"
    await ws.import_content(
        ref.id, human.encode(), None, format="SOURCE", language="PYTHON", overwrite=True
    )
    result = await s.decide("s", row["id"], "apply", "a", "u")
    assert result["state"] == "conflicted" and result["currentRevision"]
    assert (await h.read(ref, a)).content == human


async def test_create_is_ledgered_and_outside_fence_never_applies(ledger):
    ws, ref, a, h, s, _ = await fixture(ledger, mode="auto")
    created = await s.propose(
        "s",
        "t",
        "inv",
        AssetRef("notebook", "/Users/u/agent/new"),
        "",
        [],
        content="# Databricks notebook source\nprint(1)",
    )
    assert created["state"] == "applied"
    assert len((await ledger.page("resource", session_id="s"))["items"]) == 1
    outside = await s.propose(
        "s", "t", "inv2", AssetRef("notebook", "/Shared/outside"), "", [], content="print(2)"
    )
    assert outside["state"] == "refused"
    with pytest.raises(LookupError):
        await ws.status("/Shared/outside", None)


async def test_store_compare_and_swap_and_reserve_are_atomic(ledger):
    body = {"id": "x", "owner": "u", "sessionId": "s", "state": "running", "createdAt": time.time()}
    row, fresh = await ledger.reserve("operation", "same", body)
    duplicate, new = await ledger.reserve("operation", "same", {**body, "id": "other"})
    assert fresh and not new and duplicate["id"] == "x"
    results = await asyncio.gather(
        ledger.put("operation", {**row, "state": "succeeded"}, row["version"]),
        ledger.put("operation", {**row, "state": "failed"}, row["version"]),
        return_exceptions=True,
    )
    assert sum(isinstance(r, WorkError) for r in results) == 1


async def test_ledger_cursor_does_not_skip_equal_timestamps(ledger):
    for i in range(5):
        await ledger.put(
            "change", {"id": str(i), "owner": "u", "sessionId": "s", "state": "applied", "createdAt": 1}
        )
    rows = []
    cursor = ""
    while True:
        page = await ledger.page("change", session_id="s", cursor=cursor, limit=2)
        rows.extend(r["id"] for r in page["items"])
        cursor = page["nextCursor"]
        if not cursor:
            break
    assert rows == ["4", "3", "2", "1", "0"]


async def test_encrypted_previous_content_survives_restart(tmp_path):
    path = tmp_path / "encrypted.sqlite"
    store = SqliteAgentLedgers(str(path))
    row = await store.put(
        "change",
        {
            "id": "secret",
            "sessionId": "s",
            "owner": "u",
            "createdAt": 1,
            "_before": "PRIVATE_NOTEBOOK_SOURCE",
        },
    )
    await store.close()
    assert b"PRIVATE_NOTEBOOK_SOURCE" not in path.read_bytes()
    reopened = SqliteAgentLedgers(str(path))
    assert (await reopened.get("change", "secret"))["_before"] == "PRIVATE_NOTEBOOK_SOURCE"
    await reopened.close()


async def test_retention_prunes_only_expired_undo_content_in_bounded_batches(ledger):
    before = time.time() - 30 * 86400
    rows = [
        (
            "previous_content",
            {
                "id": str(i),
                "sessionId": "s",
                "owner": "u",
                "state": "retained",
                "createdAt": before - 1,
                "_content": "expired sensitive source",
            },
            None,
        )
        for i in range(3)
    ]
    rows += [
        (
            "previous_content",
            {
                "id": "fresh",
                "sessionId": "s",
                "owner": "u",
                "state": "retained",
                "createdAt": before + 1,
                "_content": "fresh source",
            },
            None,
        ),
        (
            "resource",
            {"id": "keep", "sessionId": "s", "owner": "u", "state": "present", "createdAt": 1},
            None,
        ),
    ]
    await ledger.batch(rows)
    assert await ledger.prune_previous(before, limit=2) == 2
    assert await ledger.prune_previous(before, limit=2) == 1
    assert await ledger.prune_previous(before) == 0
    assert (await ledger.get("previous_content", "fresh"))["_content"] == "fresh source"
    assert (await ledger.get("resource", "keep"))["state"] == "present"


async def test_expired_read_snapshot_can_be_reserved_again_after_retention(ledger):
    row = {
        "id": "snapshot",
        "sessionId": "s",
        "owner": "u",
        "state": "observed",
        "createdAt": 1,
        "_content": "old source",
    }
    await ledger.reserve("previous_content", "same-revision-key", row)
    assert await ledger.prune_previous(2) == 1
    saved, fresh = await ledger.reserve("previous_content", "same-revision-key", {**row, "createdAt": 3})
    assert fresh and saved["createdAt"] == 3


async def test_finished_wakeup_retention_preserves_armed_work_and_legacy_deduplication(ledger):
    for key, state in [("fired", "fired"), ("cancelled", "cancelled"), ("armed", "armed")]:
        await ledger.put(
            "operation",
            {
                "id": key,
                "sessionId": "sid",
                "owner": "u",
                "state": "succeeded",
                "wakeup": "continue",
                "createdAt": 1,
            },
        )
        await ledger.put(
            "wakeup", {"id": key, "sessionId": "sid", "owner": "u", "state": state, "createdAt": 1}
        )
    assert await ledger.prune_wakeups(limit=1) == 1
    assert await ledger.prune_wakeups(limit=1) == 1
    assert await ledger.prune_wakeups(limit=1) == 0
    assert (await ledger.get("wakeup", "armed"))["state"] == "armed"
    assert (await ledger.get("operation", "fired"))["wakeFiredAt"]
    assert (await ledger.get("operation", "fired"))["wakeup"] == "none"
    assert (await ledger.get("operation", "cancelled"))["state"] == "succeeded"
