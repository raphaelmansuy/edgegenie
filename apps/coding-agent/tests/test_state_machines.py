"""The state machines, at their edges. `[R-26]`–`[R-30]`, `F-12`–`F-17`.

Each test here exists because a transition was **enumerated** and found to be wrong, not because a
function needed coverage. The shape is deliberate: every matrix is the PRODUCT of the machine's axes,
because that is what found the six defects — the existing tests sampled the diagonal.
"""

from __future__ import annotations

import pytest

from api.domain.cellrun import RunState, result_from_statement
from api.domain.jobs import (
    ACTIVE, can_cancel, can_repair, is_active, is_terminal, run_word, tone,
    RUN_LIFE_CYCLE, RUN_RESULT,
)
from api.domain.retention import Candidate, Disposition, retention
from api.domain.session import DomainError, TERMINAL, Turn, TurnStatus


def _turn(status: TurnStatus = TurnStatus.QUEUED) -> Turn:
    return Turn(id="t1", session_id="s1", index=1, prompt="p", model="m", status=status)


# ============================================================== [R-26] a terminal turn is final
@pytest.mark.parametrize("start", list(TurnStatus))
@pytest.mark.parametrize("target", [s for s in TurnStatus if s in TERMINAL])
def test_a_terminal_turn_cannot_change(start, target):
    """The 8 x 5 matrix. Before `[R-26]`, `finish()` guarded only its TARGET, so all eight statuses
    could finish as any of the five terminals — measured: a `COMPLETED` turn became `INTERRUPTED`."""
    turn = _turn(start)
    if start in TERMINAL:
        with pytest.raises(DomainError, match="already finished"):
            turn.finish(target)
    elif start is TurnStatus.AUDITING:
        # An auditing turn is legitimately finished by the supervisor.
        assert turn.finish(target).status is target
    else:
        assert turn.finish(target).status is target


def test_the_timeout_handler_cannot_rewrite_a_finished_turn():
    """The reachable path: `orchestrator.py:947` finishes a turn by id after unwinding, so a
    settle/timeout race on the same tick used to rewrite a completed turn as interrupted."""
    settled = _turn(TurnStatus.RUNNING).finish(TurnStatus.COMPLETED)
    with pytest.raises(DomainError):
        settled.finish(TurnStatus.INTERRUPTED, error="the runtime limit was reached")


def test_finishing_a_settled_turn_the_same_way_is_also_refused():
    """Idempotence is tempting and wrong: a second `turn.completed` in the journal is a second record
    of a moment that happened once, and the reducer would paint it again."""
    settled = _turn(TurnStatus.RUNNING).finish(TurnStatus.COMPLETED)
    with pytest.raises(DomainError):
        settled.finish(TurnStatus.COMPLETED)


def test_finish_still_refuses_a_non_terminal_target():
    """The guard that already existed must survive: `finish(RUNNING)` is not a finish."""
    with pytest.raises(DomainError, match="terminal"):
        _turn(TurnStatus.RUNNING).finish(TurnStatus.RUNNING)


def test_start_still_refuses_a_settled_turn():
    with pytest.raises(DomainError, match="cannot start"):
        _turn(TurnStatus.COMPLETED).start()


# ============================================================== [R-28] an active run reads active
@pytest.mark.parametrize("life", sorted(ACTIVE))
@pytest.mark.parametrize("result", list(RUN_RESULT))
def test_an_active_run_never_reads_as_finished(life, result):
    """The 6 x 10 grid. `result_state` is documented as terminal-only but arrives on `TERMINATING`,
    so 24 of 60 cells used to show `succeeded`/`failed`/`timed out` beside an enabled Cancel."""
    word = run_word(life, result)
    assert word not in ("succeeded", "failed", "timed out", "canceled"), (
        f"{life} + {result} read as {word!r} while the run is active")
    # …and the control agrees with the word: a live run is cancellable.
    assert can_cancel(life) is True


@pytest.mark.parametrize("result,word", [
    ("SUCCESS", "succeeded"), ("FAILED", "failed"), ("TIMEDOUT", "timed out"),
    ("CANCELED", "canceled"), ("UPSTREAM_FAILED", "upstream failed"),
    ("SUCCESS_WITH_FAILURES", "succeeded with failures"),
])
def test_a_terminal_run_reads_its_result(result, word):
    """Only `result_state` distinguishes success from failure inside TERMINATED."""
    assert run_word("TERMINATED", result) == word


def test_a_terminated_run_with_no_result_reads_finished():
    assert run_word("TERMINATED") == "finished"


def test_an_unknown_state_is_quoted_verbatim():
    """A state nobody has seen is a fact; a cheerful synonym for it is a guess."""
    assert run_word("TERMINATED", "A_NEW_RESULT") == "a_new_result"
    assert run_word("A_NEW_LIFE_CYCLE") == "a_new_life_cycle"


# ============================================================== [E-26] repair is not offered falsely
@pytest.mark.parametrize("life", ["SKIPPED", "INTERNAL_ERROR"])
@pytest.mark.parametrize("result", ["FAILED", "TIMEDOUT"])
def test_a_run_that_never_ran_offers_no_repair(life, result):
    """`SKIPPED` means the platform never started it; there is nothing to re-run."""
    assert can_repair(result, life) is False


@pytest.mark.parametrize("result,expected", [
    ("FAILED", True), ("TIMEDOUT", True), ("SUCCESS", False), ("CANCELED", False),
])
def test_repair_belongs_only_on_a_terminated_failure(result, expected):
    assert can_repair(result, "TERMINATED") is expected


def test_a_live_run_is_never_repairable():
    for life in ACTIVE:
        assert can_repair("FAILED", life) is False


def test_no_active_run_offers_a_terminal_word_and_cancel_together():
    """The invariant the grid above asserts, stated once as the contradiction it was."""
    contradictions = [
        (life, result) for life in ACTIVE for result in RUN_RESULT
        if run_word(life, result) in ("succeeded", "failed", "canceled", "timed out")
        and can_cancel(life)
    ]
    assert contradictions == []


# ============================================================== [R-29] QUEUED waits
@pytest.mark.parametrize("state", ["PENDING", "QUEUED", "RUNNING"])
def test_a_waiting_statement_is_running_not_failed(state):
    r = result_from_statement({"statement": "select 1", "status": {"state": state}}, waited=2.0)
    assert r.state is RunState.RUNNING
    assert "still running" in r.error


def test_queued_is_not_reported_as_a_failure_with_the_state_as_its_reason():
    """The exact defect: `failed` with the error text "the warehouse reported QUEUED"."""
    r = result_from_statement({"statement": "s", "status": {"state": "QUEUED"}}, waited=1.0)
    assert r.state is not RunState.FAILED
    assert "the warehouse reported QUEUED" not in r.error


@pytest.mark.parametrize("state", ["", "SOMETHING_NEW", "BRAND_NEW_STATE"])
def test_an_unknown_state_is_unresolved_and_names_itself(state):
    r = result_from_statement({"statement": "s", "status": {"state": state}}, waited=1.0)
    assert r.state is RunState.UNRESOLVED
    assert state or "no state" in r.error
    if state:
        assert state in r.error


def test_a_failure_with_no_message_says_so_rather_than_nothing():
    r = result_from_statement({"statement": "s", "status": {"state": "FAILED"}}, waited=1.0)
    assert r.state is RunState.FAILED
    assert r.error == "the warehouse reported FAILED without a message"


def test_a_failure_keeps_the_engines_own_words():
    payload = {"statement": "s", "status": {"state": "FAILED",
                                            "error": {"message": "TABLE_OR_VIEW_NOT_FOUND"}}}
    r = result_from_statement(payload, waited=1.0)
    assert r.state is RunState.FAILED
    assert "TABLE_OR_VIEW_NOT_FOUND" in r.error


# ============================================================== [R-30] the reason is the reason
@pytest.mark.parametrize("refcount", [0, 1, 5])
def test_an_unknown_state_is_kept_for_being_unknown_at_every_refcount(refcount):
    """Before `[R-30]` the refcount was checked first, so an unknown state with a reference reported
    `KEPT_REFERENCED` — a reason a test could not distinguish from "protected by a turn"."""
    d = retention(Candidate("b", "a-future-state", 0.0, refcount), now=1e9)
    assert d is Disposition.KEPT_UNKNOWN_STATE


@pytest.mark.parametrize("refcount", [1, 5])
def test_a_referenced_blob_is_never_swept_at_any_age(refcount):
    for state in ("pending", "ready", "attached"):
        d = retention(Candidate("b", state, 0.0, refcount), now=1e9)
        assert d is Disposition.KEPT_REFERENCED
