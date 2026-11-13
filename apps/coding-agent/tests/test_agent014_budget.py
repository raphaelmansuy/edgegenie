"""Budgets reject unknown units, unknown usage and inputs that cannot fit a pass."""

from dataclasses import replace
from unittest.mock import AsyncMock
import pytest
from api.adapters.durable.agent_ledgers import MemoryAgentLedgers
from api.domain.asset import Actor, WorkError
from api.domain.scope import Scope
from api.services.work_events import WorkEvents
from api.services.work_sessions import WorkSessions


@pytest.fixture
async def sessions():
    store = MemoryAgentLedgers()
    actor = Actor("s", "u", "t", Scope.for_session("s", "/scratch", None))
    caps = AsyncMock()
    caps.rows = lambda sid: [{"kind": "file"}]
    work = WorkSessions(
        store,
        WorkEvents(store, AsyncMock()),
        caps,
        lambda sid, tid: replace(actor, turn_id=tid),
        max_pass_cost=1,
    )
    await work.prepare("s")
    yield work
    await store.close()


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1, 0, True])
async def test_budget_rejects_nonfinite_and_nonpositive_limits(sessions, bad):
    with pytest.raises(WorkError):
        await sessions.budget("s", bad, "tokens")


async def test_budget_reserves_unicode_prompt_and_output_before_a_pass(sessions):
    await sessions.budget("s", 5000, "tokens")
    sessions.check_pass("s", "hello", 1000)
    with pytest.raises(WorkError, match="Budget reached"):
        sessions.check_pass("s", "界" * 1000, 1000)
    assert sessions.settings("s")["usedTokens"] == 0


async def test_unknown_usage_never_counts_as_a_free_turn(sessions):
    await sessions.record_pass("s", "t", {}, 1)
    with pytest.raises(WorkError, match="unknown"):
        await sessions.budget("s", 5000, "tokens")


async def test_changed_cost_units_cannot_be_combined_into_a_money_budget(sessions):
    await sessions.meter("s", {"cost": {"amount": 1, "currency": "USD"}}, "epoch")
    await sessions.meter("s", {"cost": {"amount": 2, "currency": "EUR"}}, "epoch")
    assert sessions.settings("s")["currency"] == ""
    with pytest.raises(WorkError, match="unit changed"):
        await sessions.budget("s", 5, "money")


@pytest.mark.parametrize("action", ["mode", "budget"])
async def test_setting_intent_and_audit_outbox_cannot_diverge_on_failed_commit(
    sessions, monkeypatch, action
):
    await sessions.prepare("s")
    monkeypatch.setattr(
        sessions.events, "commit", AsyncMock(side_effect=RuntimeError("storage unavailable before commit"))
    )
    with pytest.raises(RuntimeError):
        if action == "mode":
            await sessions.set_mode("s", "auto", "u")
        else:
            await sessions.budget("s", 1000, "tokens")
    stored = await sessions.store.get("session", "s")
    assert stored["mode"] == "review" and stored["budget"] is None
    assert sessions.settings("s")["mode"] == "review" and sessions.settings("s")["budget"] is None
