"""The supervisor: done means proven, and proven does not mean tabulated. `[R-31]`, `[F-17]`.

The defect: a turn where the agent completed `dbx_write_notebook` and `dbx_run_notebook` and then wrote
a correct prose answer **without** an EVIDENCE table became `blocked` after two audit passes — measured,
with both calls in the transcript. The product's strongest promise punished a compliant agent for
omitting a formatting step.

The fix is a closed mapping (`api/domain/evidence_map.py`) that may only **add** a row from a
**completed** call, and the tests below are mostly negative: the cheap version of this fix is "any call
proves anything", and each negative here fails that.

`[E-6]` remains open on purpose: a real call carrying a *fabricated summary* still verifies, because
checking it needs a result diff and a wrong diff produces false `blocked` turns — this same failure
inverted. That is asserted, so the limitation is recorded rather than discovered.
"""

from __future__ import annotations

import pytest

from api.domain.evidence import Requirement, ToolCall
from api.domain.evidence_map import derive
from api.domain.supervisor import MAX_AUDITS, MAX_CONTINUATIONS, State, Verdict, decide

WRITE = Requirement("write the notebook")
RUN = Requirement("run it and quote the result")
REQS = [WRITE, RUN]

DONE_CALLS = [
    ToolCall("c1", "dbx_write_notebook", "completed", "wrote /Users/me/x"),
    ToolCall("c2", "dbx_run_notebook", "completed", "5 rows"),
]
PROSE = "Done. I wrote the notebook and ran it; it returned 5 rows."


def _decide(**kw) -> object:
    base = dict(requirements=REQS, calls=DONE_CALLS, answer=PROSE, continuations=0, audits=0,
                read_only=False)
    base.update(kw)
    return decide(State(**base))


# ============================================================== the fix
def test_completed_work_without_a_table_is_not_blocked():
    """The exact scenario that used to end `blocked` at every audit count."""
    for audits in (0, 1, MAX_AUDITS):
        d = _decide(audits=audits)
        assert d.verdict is Verdict.DONE, f"still blocked at audits={audits}"
        assert len(d.evidence) == 2


def test_a_derived_row_says_it_is_derived():
    """A derived row is weaker than a reported one and must be able to say so, or a reader cannot
    tell "the agent tabulated this" from "this call exists"."""
    d = _decide()
    derived = [r for r in d.evidence if r.get("derived")]
    assert derived, "no row was marked derived"
    assert all(r["verified"] for r in derived)


def test_the_table_still_wins_when_it_is_present():
    """The reported path is unchanged: a tabulated answer verifies exactly as before."""
    table = """Done.

| requirement | tool | summary |
|---|---|---|
| write the notebook | dbx_write_notebook | ok |
| run it and quote the result | dbx_run_notebook | 5 rows |"""
    d = _decide(answer=table)
    assert d.verdict is Verdict.DONE
    assert all(not r.get("derived") for r in d.evidence)


# ============================================================== the negatives
def test_an_incomplete_call_still_blocks():
    """A call that is still running proves nothing. Without this the fix would be "any call counts"."""
    calls = [ToolCall("c1", "dbx_write_notebook", "running")]
    for audits in (0, MAX_AUDITS):
        d = _decide(calls=calls, answer="Done.", audits=audits)
        assert d.verdict is not Verdict.DONE
    assert _decide(calls=calls, answer="Done.", audits=MAX_AUDITS).verdict is Verdict.BLOCKED


def test_a_failed_call_still_blocks():
    calls = [ToolCall("c1", "dbx_write_notebook", "error", "permission denied")]
    d = _decide(calls=calls, answer="Done.", audits=MAX_AUDITS)
    assert d.verdict is Verdict.BLOCKED


def test_an_agent_that_admits_it_cannot_proceed_stays_blocked():
    """The derived path must not rescue a turn where the agent said it failed."""
    d = _decide(answer="I cannot continue: permission denied on samples.")
    assert d.verdict is Verdict.BLOCKED


def test_an_unrelated_tool_proves_nothing():
    """The mapping is CLOSED. A `dbx_whoami` call is not evidence that a notebook was written."""
    calls = [ToolCall("c1", "dbx_whoami", "completed", "me")]
    d = _decide(calls=calls, answer="Done.", audits=MAX_AUDITS)
    assert d.verdict is Verdict.BLOCKED


def test_a_requirement_a_tool_cannot_prove_still_blocks():
    """A requirement with no mapped tool is a gap, whatever calls exist.

    `migrate` is an action verb (`needs_evidence` is true), so the turn cannot complete on prose — and
    no completed call in this turn maps to migration work. It must stay a gap.
    """
    d = decide(State(
        requirements=[Requirement("migrate the SQL dialects")],
        calls=DONE_CALLS, answer="Migrated.", audits=MAX_AUDITS))
    assert d.verdict is Verdict.BLOCKED
    assert list(d.missing) == ["migrate the SQL dialects"]


def test_one_call_cannot_prove_two_requirements():
    """A derived row consumes its call, so two requirements cannot both cite the notebook write."""
    found = derive(REQS, [ToolCall("c1", "dbx_write_notebook", "completed", "x")], already=set())
    assert len(found) <= 1


def test_a_requirement_already_reported_is_not_derived_again():
    found = derive(REQS, DONE_CALLS, already={WRITE.text})
    assert all(f.requirement != WRITE.text for f in found)


# ============================================================== the recorded limitation
def test_a_fabricated_summary_on_a_real_call_still_verifies():
    """`[E-6]`, asserted so it is a known limit rather than a surprise.

    The supervisor checks that a completed call of that NAME exists, not that its output matches the
    claim. Tightening it needs a diff of the tool's own result against the summary, and a wrong diff
    produces false `blocked` turns — the same failure inverted. Left open, on purpose.

    The table covers **both** requirements here so the only thing under test is whether the summary is
    read. With one row the verdict is `AUDIT` for the uncovered requirement, which would hide it.
    """
    table = """Done.

| requirement | tool | summary |
|---|---|---|
| write the notebook | dbx_write_notebook | I wrote 400 pages of poetry |
| run it and quote the result | dbx_run_notebook | I never ran it at all |"""
    d = _decide(answer=table)
    assert d.verdict is Verdict.DONE, "the name-based check does not read the summary"
    assert len(d.evidence) == 2


# ============================================================== the other verdicts are untouched
def test_an_empty_answer_continues_then_blocks():
    assert decide(State(requirements=REQS, calls=[], answer="", continuations=0)).verdict is Verdict.CONTINUE
    d = decide(State(requirements=REQS, calls=[], answer="", continuations=MAX_CONTINUATIONS))
    assert d.verdict is Verdict.BLOCKED


def test_a_read_only_request_is_done_without_evidence():
    """Asking about attached context: the answer IS the deliverable."""
    d = decide(State(requirements=[Requirement("what does this table contain?")],
                     calls=[], answer="It holds one row per trip.", read_only=True))
    assert d.verdict is Verdict.DONE


def test_a_purely_conversational_request_needs_no_evidence():
    d = decide(State(requirements=[Requirement("remember that I prefer SQL")],
                     calls=[], answer="Noted."))
    assert d.verdict is Verdict.DONE


@pytest.mark.parametrize("audits", [0, 1, MAX_AUDITS])
def test_only_the_audit_boundary_changes_the_verdict_shape(audits):
    """Whatever the count, the verdict is one of the four and `missing` is consistent with it."""
    d = _decide(calls=[], answer="Done.", audits=audits)
    assert d.verdict in (Verdict.AUDIT, Verdict.BLOCKED)
    assert (d.verdict is Verdict.BLOCKED) == (audits >= MAX_AUDITS)
