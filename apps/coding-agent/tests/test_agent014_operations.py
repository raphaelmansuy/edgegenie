import asyncio
import time
from dataclasses import replace
import pytest
from api.adapters.durable.agent_ledgers import MemoryAgentLedgers
from api.adapters.fake.workspace import DemoWorkspace
from api.adapters.fake.notebook import DemoNotebookHandler
from api.domain.asset import Actor, AssetRef, WorkError
from api.domain.asset_registry import AssetRegistry, Registration
from api.domain.scope import Scope
from api.domain.invocation_evidence import grade
from api.domain.events import Event
from api.services.operations import OperationService
from api.services.work_events import WorkEvents
from api.services.journal_writer import JournalWriter


@pytest.fixture
async def rig():
    store = MemoryAgentLedgers()
    ws = DemoWorkspace(store)
    handler = DemoNotebookHandler(ws, store)
    who = Actor("sid", "u", "tid", Scope.for_session("sid", "/scratch", None))
    actor = lambda sid, tid: replace(who, turn_id=tid)
    registry = AssetRegistry([Registration("notebook", "Notebooks", "", handler, "")])
    emitted = []
    wakes = []

    async def emit(e):
        emitted.append(e)

    async def wake(r):
        wakes.append(r)

    events = WorkEvents(store, emit)
    ops = OperationService(registry, store, events, actor, wake, interval=0.02)
    await ws.seed("/scratch")
    yield store, ops, wakes, handler, who
    await ops.close()
    await store.close()


async def test_repeat_submit_is_one_native_run_and_observer_needs_no_browser(rig):
    store, ops, wakes, handler, who = rig
    ref = AssetRef("notebook", "/scratch/revenue")
    a, b = await asyncio.gather(
        ops.submit("sid", "tid", "run", ref, {"seconds": 0.2}),
        ops.submit("sid", "tid", "run", ref, {"seconds": 0.2}),
    )
    assert a["id"] == b["id"]
    assert len((await store.page("fake_run"))["items"]) == 1
    await ops.set_wakeup("sid", a["id"], "continue")
    await asyncio.sleep(0.45)
    assert (await ops.get("sid", a["id"]))["state"] == "succeeded"
    assert len(wakes) == 1
    await ops.observe("sid", a["id"])
    assert len(wakes) == 1


async def test_cancel_reaches_native_run(rig):
    store, ops, wakes, handler, who = rig
    row = await ops.submit("sid", "tid", "run", AssetRef("notebook", "/scratch/revenue"), {"seconds": 10})
    result = await ops.cancel("sid", row["id"])
    assert result["state"] == "cancelled"
    assert (await store.get("fake_run", row["nativeId"]))["state"] == "cancelled"


async def test_lost_submit_response_never_resubmits(rig):
    store, ops, wakes, handler, who = rig
    actual = handler.submit
    count = 0

    async def lost(*args):
        nonlocal count
        count += 1
        await actual(*args)
        raise TimeoutError()

    handler.submit = lost
    a = await ops.submit("sid", "tid", "run", AssetRef("notebook", "/scratch/revenue"), {})
    b = await ops.submit("sid", "tid", "run", AssetRef("notebook", "/scratch/revenue"), {})
    assert a["state"] == "unknown" and b["id"] == a["id"] and count == 1


async def test_expired_credential_retains_last_native_handle(rig):
    store, ops, wakes, handler, who = rig
    a = await ops.submit("sid", "tid", "run", AssetRef("notebook", "/scratch/revenue"), {"seconds": 10})
    ops.actor = lambda sid, tid: replace(who, expires_at=time.time() - 1)
    row = await ops.observe("sid", a["id"])
    assert row["state"] == "unobserved" and row["nativeId"] == a["nativeId"]


@pytest.mark.parametrize("claim,expected", [("42", "verified"), ("99", "contradicted"), ("", "supported")])
def test_evidence_grades_actual_result_values(claim, expected):
    answer = f"| requirement | tool | summary |\n|---|---|---|\n| Count trips | inv_1 | {claim} |"
    row = grade(
        answer,
        [
            {
                "id": "inv_1",
                "tool": "dbx_read",
                "state": "completed",
                "resultTokens": ["42"],
                "resultSummary": "42 trips",
            }
        ],
    )[0]
    assert row["grade"] == expected


def test_evidence_never_joins_a_programmatic_name_or_another_turn():
    answer = "| requirement | tool | summary |\n|---|---|---|\n| Count trips | dbx_read | 42 |"
    assert (
        grade(answer, [{"id": "inv_1", "tool": "dbx_read", "state": "completed", "resultTokens": ["42"]}])[
            0
        ]["grade"]
        == "unverified"
    )


async def test_journal_coalesces_and_flushes_before_transition():
    rows = []

    async def commit(event, snapshot):
        rows.append((event, snapshot))
        return event

    writer = JournalWriter(commit, window=0.02)
    for _ in range(100):
        await writer.emit(Event("sid", "message.delta", {"text": "x"}, turn_id="tid"))
    await writer.emit(Event("sid", "turn.completed", {}, turn_id="tid"))
    assert len(rows) == 2 and rows[0][0].payload["text"] == "x" * 100
    assert [r[1] for r in rows] == [False, True]
    await writer.close()


async def test_journal_flush_window_without_another_event():
    rows = []

    async def commit(event, snapshot):
        rows.append(event)
        return event

    writer = JournalWriter(commit, window=0.02)
    await writer.emit(Event("sid", "message.delta", {"text": "saved"}))
    await asyncio.sleep(0.04)
    assert rows[0].payload["text"] == "saved"
    await writer.close()


async def test_notebook_pages_reuse_one_export_per_revision_and_turn(rig):
    store, ops, wakes, handler, who = rig
    original = handler.workspace.export_content
    count = 0

    async def counted(*args):
        nonlocal count
        count += 1
        return await original(*args)

    handler.workspace.export_content = counted
    for _ in range(5):
        await handler.read(AssetRef("notebook", "/scratch/revenue"), who)
    assert count == 1
    await handler.read(AssetRef("notebook", "/scratch/revenue"), replace(who, turn_id="next"))
    assert count == 2


def test_unobserved_prose_is_supported_never_verified():
    answer = "| requirement | tool | summary |\n|---|---|---|\n| Verify | inv_1 | Every user was deleted |"
    assert (
        grade(
            answer,
            [{"id": "inv_1", "tool": "dbx_read", "state": "completed", "resultTokens": ["unchanged"]}],
        )[0]["grade"]
        == "supported"
    )


def test_failed_result_cannot_verify_even_matching_value():
    answer = "| requirement | tool | summary |\n|---|---|---|\n| Verify | inv_1 | 42 |"
    assert (
        grade(answer, [{"id": "inv_1", "tool": "dbx_read", "state": "failed", "resultTokens": ["42"]}])[0][
            "grade"
        ]
        == "unverified"
    )


def test_truncated_results_do_not_prove_contradictions():
    answer = "| requirement | tool | summary |\n|---|---|---|\n| Verify | inv_1 | 99 |"
    assert (
        grade(
            answer,
            [
                {
                    "id": "inv_1",
                    "tool": "dbx_read",
                    "state": "completed",
                    "resultTokens": ["42"],
                    "resultTruncated": True,
                }
            ],
        )[0]["grade"]
        == "unverified"
    )


async def test_repeated_unchanged_observation_does_not_rewrite_the_journal(rig):
    store, ops, wakes, handler, who = rig
    row = await ops.submit("sid", "tid", "run", AssetRef("notebook", "/scratch/revenue"), {"seconds": 10})
    first = await ops.observe("sid", row["id"])
    for _ in range(5):
        repeated = await ops.observe("sid", row["id"])
        assert repeated["version"] == first["version"]


def test_explicit_wrapped_invocation_and_corrected_claim_are_not_legacy_name_joins():
    inv = "inv_" + "a" * 20
    answer = f"| requirement | tool | summary |\n|---|---|---|\n| Count | {inv} | 99 |\n| Count | dbx_read({inv}) | 42 |"
    rows = grade(answer, [{"id": inv, "tool": "dbx_read", "state": "completed", "resultTokens": ["42"]}])
    assert len(rows) == 1 and rows[0]["grade"] == "verified" and rows[0]["toolCallId"] == inv


def test_matching_number_does_not_verify_unobserved_prose():
    answer = "| requirement | tool | summary |\n|---|---|---|\n| Verify | inv_1 | Deleted 42 users |"
    assert (
        grade(
            answer,
            [{"id": "inv_1", "tool": "dbx_read", "state": "completed", "resultTokens": ["42", "trips"]}],
        )[0]["grade"]
        == "supported"
    )


def test_latest_audit_evidence_replaces_earlier_invalid_citations():
    inv = "inv_" + "b" * 20
    answer = f"Evidence\n| requirement | tool | summary |\n|---|---|---|\n| old wording | dbx_read | 99 |\n\n**Evidence**\n| requirement | tool | summary |\n|---|---|---|\n| Count trips | {inv} | Read back the count: 42 |"
    rows = grade(
        answer, [{"id": inv, "tool": "dbx_read", "state": "completed", "resultTokens": ["count", "42"]}]
    )
    assert len(rows) == 1 and rows[0]["grade"] == "verified"


def test_negation_and_quantifiers_are_never_ignored_by_evidence_matching():
    call = {
        "id": "inv_1",
        "tool": "dbx_read",
        "state": "completed",
        "resultTokens": ["users", "deleted", "42"],
    }
    for summary in ("No users deleted 42", "All users deleted 42"):
        answer = f"| requirement | tool | summary |\n|---|---|---|\n| Count | inv_1 | {summary} |"
        assert grade(answer, [call])[0]["grade"] == "supported"


def test_explicit_id_after_a_tool_name_is_preserved_before_grading():
    inv = "inv_" + "c" * 20
    answer = f"| requirement | tool | summary |\n|---|---|---|\n| Count | dbx_read **{inv}** | 42 |"
    assert grade(answer, [{"id": inv, "tool": "dbx_read", "state": "completed", "resultTokens": ["42"]}])[
        0
    ]["verified"]


def test_result_words_come_from_decoded_values_and_not_json_escape_sequences():
    from api.domain.invocation_evidence import result_lexicon

    tokens, truncated = result_lexicon(
        {"source": '# CELL 37\nprint("cell-37-FIXED")', "revision": "revisionhash"}
    )
    assert "print" in tokens and not truncated
    answer = '| requirement | tool | summary |\n|---|---|---|\n| Verify | inv_1 | Revision = revisionhash; cell 37 source is print("cell-37-FIXED") |'
    assert grade(
        answer, [{"id": "inv_1", "tool": "dbx_read", "state": "completed", "resultTokens": tokens}]
    )[0]["verified"]


async def test_all_native_operations_share_the_bounded_admission_pool(rig):
    store, ops, wakes, handler, who = rig
    ops._native_slots = asyncio.Semaphore(2)
    active, maximum = 0, 0
    actual = handler.submit

    async def measured(*args):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        try:
            await asyncio.sleep(0.03)
            return await actual(*args)
        finally:
            active -= 1

    handler.submit = measured
    rows = await asyncio.gather(
        *[
            ops.submit(
                "sid", "tid", "run", AssetRef("notebook", "/scratch/revenue"), {"seconds": 10, "fixture": i}
            )
            for i in range(7)
        ]
    )
    assert maximum == 2
    assert all(r["nativeId"] for r in rows)
    assert len({r["nativeId"] for r in rows}) == 7


async def test_unknown_submission_lookup_failure_keeps_observer_recoverable(rig):
    store, ops, wakes, handler, who = rig

    async def uncertain(*args):
        raise TimeoutError("response lost")

    handler.submit = uncertain
    row = await ops.submit("sid", "tid", "run", AssetRef("notebook", "/scratch/revenue"), {})

    async def unavailable(*args):
        raise TimeoutError("lookup unavailable")

    handler.lookup = unavailable
    result = await ops.observe("sid", row["id"])
    assert result["state"] == "unknown" and not result["nativeId"]

    async def found(*args):
        return "found-native-id"

    handler.lookup = found
    result = await ops.observe("sid", row["id"])
    assert result["state"] == "running" and result["nativeId"] == "found-native-id"


def test_no_execution_constraint_never_exempts_a_requested_source_edit_from_proof():
    from api.domain.evidence import says_no_tools, extract_requirements
    from api.domain.supervisor import decide, State, Verdict

    prompt = "- Fix the literal BROKEN in cell 37 of /Users/u/agent/long_notebook.\nDo not run code or SQL."
    assert not says_no_tools(prompt)
    assert says_no_tools("Explain this source without running code.")
    assert says_no_tools("Just explain the fix. Do not use tools.")
    state = State(
        extract_requirements(prompt), [], "dbx_edit(kind=notebook, ...)", proof_floor=True, evidence_rows=()
    )
    assert decide(state).verdict is Verdict.AUDIT


@pytest.mark.parametrize("observed,verdict", [(False, "audit"), (True, "done")])
def test_supported_prose_can_finish_for_review_only_after_the_native_effect_is_observed(observed, verdict):
    from api.domain.evidence import Requirement
    from api.domain.supervisor import decide, State

    rows = (
        {
            "requirement": "修改笔记本",
            "toolCallId": "inv_1",
            "tool": "dbx_read",
            "summary": "Descriptive supported prose",
            "verified": False,
            "grade": "supported",
        },
    )
    decision = decide(
        State(
            [Requirement("修改笔记本")],
            [],
            "Descriptive supported prose",
            evidence_rows=rows,
            proof_floor=True,
            observed_effects=observed,
        )
    )
    assert decision.verdict.value == verdict
    assert decision.evidence[0]["verified"] is False


def test_contradicted_claim_still_blocks_completion_after_a_verified_effect():
    from api.domain.evidence import Requirement
    from api.domain.supervisor import decide, State, Verdict

    rows = (
        {
            "requirement": "Fix cell",
            "toolCallId": "inv_1",
            "tool": "dbx_read",
            "summary": "99",
            "verified": False,
            "grade": "contradicted",
        },
    )
    decision = decide(
        State(
            [Requirement("Fix cell")],
            [],
            "99",
            evidence_rows=rows,
            proof_floor=True,
            observed_effects=True,
            audits=2,
        )
    )
    assert decision.verdict is Verdict.BLOCKED


async def test_pruned_wakeup_cannot_rearm_or_repeat_a_consumed_continuation(rig):
    store, ops, wakes, handler, who = rig
    row = await ops.submit("sid", "tid", "run", AssetRef("notebook", "/scratch/revenue"), {"seconds": 0.1})
    await ops.set_wakeup("sid", row["id"], "continue")
    await asyncio.sleep(0.3)
    assert len(wakes) == 1
    assert (await ops.get("sid", row["id"]))["wakeFiredAt"]
    assert await store.prune_wakeups() == 1
    with pytest.raises(WorkError, match="already fired"):
        await ops.set_wakeup("sid", row["id"], "continue")
    await ops.observe("sid", row["id"])
    assert len(wakes) == 1


async def test_sql_wait_compatibility_is_explicitly_clamped_without_changing_effect_identity():
    from api.services.toolbox import Toolbox
    from unittest.mock import AsyncMock
    toolbox = object.__new__(Toolbox)
    toolbox.actor = lambda *args: None
    toolbox.run = AsyncMock(return_value={"id": "same-operation", "state": "running"})
    first = await toolbox._execute("s", "t", "dbx_run_sql", {"sql":"SELECT 1", "wait_seconds":300}, "inv")
    second = await toolbox._execute("s", "t", "dbx_run_sql", {"sql":"SELECT 1", "wait_seconds":100}, "inv2")
    assert first["effectiveWaitSeconds"] == 0 and first["requestedWaitSeconds"] == 300 and first["waitClamped"]
    assert "dbx_operation" in first["waitMessage"] and second["id"] == first["id"]
    assert toolbox.run.call_args_list[0].args[-2:] == toolbox.run.call_args_list[1].args[-2:]
    assert toolbox.run.call_args.args[-1] == {"sql":"SELECT 1"}


async def test_invalid_wait_is_refused_before_sql_can_submit():
    from api.services.toolbox import Toolbox
    from api.domain.asset import WorkError
    from unittest.mock import AsyncMock
    toolbox = object.__new__(Toolbox)
    toolbox.actor = lambda *args: None
    toolbox.run = AsyncMock()
    with pytest.raises(WorkError):
        await toolbox._execute("s", "t", "dbx_run_sql", {"sql":"SELECT 1", "wait_seconds":True}, "inv")
    toolbox.run.assert_not_awaited()
