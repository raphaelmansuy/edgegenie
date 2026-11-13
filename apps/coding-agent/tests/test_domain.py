"""Domain tests: pure logic, exhaustive, fast. No I/O, no model."""

from __future__ import annotations

import pytest

from api.domain.evidence import (
    Requirement,
    ToolCall,
    extract_requirements,
    gaps,
    parse_evidence_block,
    verify,
)
from api.domain.scope import (
    Action,
    Scope,
    Verdict,
    check_app,
    check_job,
    check_path,
    check_sql,
    classify_sql,
)
from api.domain.session import DomainError, Session, SessionStatus, Turn, TurnStatus
from api.domain.supervisor import MAX_AUDITS, State, decide
from api.domain.supervisor import Verdict as SVerdict


# ---------------------------------------------------------------- evidence
def test_extracts_numbered_requirements():
    prompt = "Build a notebook.\n1. Read samples.nyctaxi.trips\n2. Chart fare by hour\n3. Exit with the hour count"
    reqs = extract_requirements(prompt)
    assert [r.text for r in reqs] == [
        "Read samples.nyctaxi.trips",
        "Chart fare by hour",
        "Exit with the hour count",
    ]


def test_extracts_bullets_and_falls_back_to_sentences():
    assert len(extract_requirements("- make a table\n- run it")) == 2
    assert len(extract_requirements("Rank the zips by revenue and show a running share.")) == 1


def test_a_demo_marker_is_not_a_requirement():
    """Regression: the demo marker was parsed as an unfulfillable requirement, so every demo turn
    ended blocked."""
    reqs = extract_requirements("Build a notebook and run it. [[scenario:notebook]]")
    assert all("scenario:" not in r.text for r in reqs)


def test_a_failed_turn_always_has_a_reason():
    from api.domain.events import turn_ended
    for kind in ("cancelled", "interrupted", "failed"):
        ev = turn_ended("s", "t", kind)
        assert ev.payload["reason"].strip(), f"{kind} produced an empty reason"
    ev = turn_ended("s", "t", "failed", "the model or agent failed: free daily limit")
    assert "free daily limit" in ev.payload["reason"]


def test_parse_evidence_prefers_json_block():
    text = 'EVIDENCE\n```json\n[{"requirement":"a","tool":"dbx_run_sql","summary":"3 rows"}]\n```'
    rows = parse_evidence_block(text)
    assert rows[0]["tool"] == "dbx_run_sql"


def test_parse_evidence_reads_a_markdown_table():
    text = "| requirement | tool | summary |\n|---|---|---|\n| create it | dbx_write_notebook | 5 cells |"
    rows = parse_evidence_block(text)
    assert rows == [{"requirement": "create it", "tool": "dbx_write_notebook", "summary": "5 cells"}]


def test_verify_rejects_a_citation_to_a_call_that_never_happened():
    """The failure we care about most: a confident report citing work that was not done."""
    rows = verify([{"requirement": "create the notebook", "tool": "dbx_write_notebook"}], [])
    assert rows[0].verified is False


def test_verify_requires_completed_status():
    calls = [ToolCall("c1", "dbx_run_sql", status="error")]
    assert verify([{"requirement": "x", "tool": "dbx_run_sql"}], calls)[0].verified is False
    calls = [ToolCall("c1", "dbx_run_sql", status="completed")]
    assert verify([{"requirement": "x", "tool": "dbx_run_sql"}], calls)[0].verified is True


def test_verify_tolerates_a_dropped_server_prefix():
    calls = [ToolCall("c1", "dbx_run_sql", status="completed")]
    assert verify([{"requirement": "x", "tool": "run_sql"}], calls)[0].verified is True


def test_gaps_lists_only_uncovered_requirements():
    reqs = [Requirement("run the notebook"), Requirement("write documentation")]
    rows = verify(
        [{"requirement": "run the notebook", "tool": "dbx_run_notebook"}],
        [ToolCall("c1", "dbx_run_notebook", status="completed")],
    )
    assert gaps(reqs, rows) == ["write documentation"]


def test_duplicate_claims_collapse_to_one_row():
    """Regression: the agent repeats its evidence table on every audit pass, which showed as
    "9 of 9 requirements proven" on a session with 3 requirements."""
    from api.domain.evidence import dedupe

    calls = [ToolCall("c1", "dbx_run_sql", status="completed")]
    claim = [{"requirement": "count the rows", "tool": "dbx_run_sql"}] * 3
    assert len(dedupe(verify(claim, calls))) == 1


def test_evidence_is_ordered_by_requirement_and_keeps_proven_rows():
    from api.domain.evidence import limit_to

    calls = [
        ToolCall("c1", "dbx_write_notebook", status="completed"),
        ToolCall("c2", "dbx_run_notebook", status="completed"),
    ]
    rows = verify(
        [
            {"requirement": "run the notebook", "tool": "dbx_run_notebook"},
            {"requirement": "write the notebook", "tool": "dbx_write_notebook"},
        ],
        calls,
    )
    reqs = [Requirement("write the notebook"), Requirement("run the notebook")]
    ordered = limit_to(reqs, rows)
    assert [r.tool_name for r in ordered] == ["dbx_write_notebook", "dbx_run_notebook"]


# ---------------------------------------------------------------- supervisor
def _state(answer="", calls=None, reqs=None, continuations=0, audits=0):
    return State(
        requirements=reqs or [],
        calls=calls or [],
        answer=answer,
        continuations=continuations,
        audits=audits,
    )


def test_empty_answer_continues_then_gives_up():
    assert decide(_state()).verdict is SVerdict.CONTINUE
    assert decide(_state(continuations=5)).verdict is SVerdict.BLOCKED


def test_answer_without_evidence_triggers_an_audit():
    d = decide(_state(answer="Done! Created the table.", reqs=[Requirement("create the table")]))
    assert d.verdict is SVerdict.AUDIT
    assert d.missing


def test_audit_is_capped():
    d = decide(
        _state(answer="Done! Created the table.", reqs=[Requirement("create the table")], audits=MAX_AUDITS)
    )
    assert d.verdict is SVerdict.BLOCKED


def test_verified_evidence_completes_the_turn():
    call = ToolCall("c1", "dbx_write_notebook", status="completed")
    answer = (
        "EVIDENCE\n| requirement | tool | summary |\n|---|---|---|\n"
        "| create the table | dbx_write_notebook | 5 cells |"
    )
    d = decide(_state(answer=answer, calls=[call], reqs=[Requirement("create the notebook")]))
    assert d.verdict is SVerdict.DONE
    assert d.evidence[0]["verified"] is True


def test_agent_admitting_it_cannot_proceed_is_blocked_not_done():
    d = decide(_state(answer="I cannot continue: permission denied on samples.nyctaxi.trips."))
    assert d.verdict is SVerdict.BLOCKED
    assert "cannot proceed" in d.message


# ---------------------------------------------------------------- scope / fence
def _scope():
    return Scope.for_session("abcdef1234567890", "/Users/me/agent_scratch", "workspace.agent_scratch")


def test_scope_prefixes_derive_from_the_session():
    s = _scope()
    assert s.job_prefix == "agent_abcdef12_" and s.app_prefix == "agent-abcdef12-"


@pytest.mark.parametrize(
    "sql,expected",
    [
        ("select * from t", Action.READ),
        ("CREATE OR REPLACE TABLE workspace.agent_scratch.t AS SELECT 1", Action.DESTRUCTIVE),
        ("drop table workspace.agent_scratch.t", Action.DESTRUCTIVE),
        ("DELETE FROM t", Action.DESTRUCTIVE),
        ("truncate table t", Action.DESTRUCTIVE),
    ],
)
def test_classifies_sql(sql, expected):
    assert classify_sql(sql) is expected


def test_write_inside_the_schema_is_allowed():
    d = check_sql(_scope(), "create table workspace.agent_scratch.t as select 1")
    assert d.verdict is Verdict.ALLOW


def test_human_sql_outside_the_schema_requires_a_decision_and_agent_sql_is_denied():
    from api.domain.policy.sql import check_scope
    sql = "create table workspace.default.t as select 1"
    assert check_sql(_scope(), sql).verdict is Verdict.ASK
    assert check_scope(sql, [_scope().schema])


def test_destructive_sql_always_asks_even_inside_the_schema():
    d = check_sql(_scope(), "drop table workspace.agent_scratch.t")
    assert d.verdict is Verdict.ASK and d.action is Action.DESTRUCTIVE


def test_path_traversal_is_never_inside():
    assert check_path(_scope(), "/Users/me/agent_scratch/../other/x.py").verdict is Verdict.ASK
    assert check_path(_scope(), "/Users/me/agent_scratch/x.py").verdict is Verdict.ALLOW


def test_job_and_app_names_must_carry_the_session_prefix():
    s = _scope()
    assert check_job(s, "agent_abcdef12_daily").verdict is Verdict.ALLOW
    assert check_job(s, "someone_elses_job").verdict is Verdict.ASK
    assert check_app(s, "agent-abcdef12-app").verdict is Verdict.ALLOW
    assert check_app(s, "edgequake").verdict is Verdict.ASK


# ---------------------------------------------------------------- session machine
def test_session_cannot_skip_from_provisioning_to_streaming():
    s = Session(id="1", user_id="u", folder="/f", schema=None, model="m")
    with pytest.raises(DomainError):
        s.transition(SessionStatus.STREAMING)
    assert s.transition(SessionStatus.READY).status is SessionStatus.READY


def test_archived_is_terminal():
    s = Session(
        id="1", user_id="u", folder="/f", schema=None, model="m", status=SessionStatus.READY
    ).transition(SessionStatus.ARCHIVED)
    with pytest.raises(DomainError):
        s.transition(SessionStatus.READY)


def test_turn_finish_records_usage():
    t = Turn(id="t", session_id="s", index=1, prompt="p", model="m").start()
    done = t.finish(
        TurnStatus.COMPLETED, "end_turn", {"inputTokens": 10, "outputTokens": 2, "cachedReadTokens": 5}
    )
    assert (done.input_tokens, done.output_tokens, done.cached_tokens) == (10, 2, 5)


def test_turn_cannot_finish_in_a_non_terminal_state():
    with pytest.raises(DomainError):
        Turn(id="t", session_id="s", index=1, prompt="p", model="m").finish(TurnStatus.RUNNING)


# -- an explicit "no tools" is honoured: the answer is the deliverable ------------------------
@pytest.mark.parametrize("prompt", [
    "In one sentence, what is the capital of France? Answer without using tools.",
    "Just explain how a left join works.",
    "Don't run any code, tell me what this error means.",
    "No tools please: what is a medallion architecture?",
    "Do not use the tools. Why is the sky blue?",
    "What does this do? Explain it without running any queries.",
])
def test_an_explicit_no_tools_instruction_is_detected(prompt):
    from api.domain.evidence import says_no_tools

    assert says_no_tools(prompt)


@pytest.mark.parametrize("prompt", [
    "Run SELECT 6 * 7 and tell me the result.",
    "Create a notebook that profiles samples.nyctaxi.trips.",
    "Why is my job failing? Use the tools to check the last run.",
    "What are the top 5 pickup zones?",
    "Explain the schema of the trips table.",       # needs a lookup: not an opt-out
])
def test_ordinary_requests_are_not_mistaken_for_an_opt_out(prompt):
    from api.domain.evidence import says_no_tools

    assert not says_no_tools(prompt)


def test_a_no_tools_answer_is_done_without_an_audit_pass():
    """The measured regression: the audit forced `SELECT 'Paris'` after 'answer without using tools'."""
    from api.domain import supervisor
    from api.domain.evidence import extract_requirements, says_no_tools

    prompt = "In one sentence, what is the capital of France? Answer without using tools."
    state = supervisor.State(requirements=extract_requirements(prompt), calls=[],
                             answer="The capital of France is Paris.",
                             read_only=says_no_tools(prompt))
    assert supervisor.decide(state).verdict is supervisor.Verdict.DONE
    # Same answer, no opt-out: the audit still demands evidence. The rule is unchanged for real work.
    plain = supervisor.State(requirements=extract_requirements(prompt), calls=[],
                             answer="The capital of France is Paris.", read_only=False)
    assert supervisor.decide(plain).verdict is supervisor.Verdict.AUDIT
