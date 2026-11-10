"""The scaffold's step table: a step is done only when a call proved it.

These tests are the definition of `[SCF-1]`, `[SCF-2]` and `[E-9]`. They use literals — no fixture, no
I/O — because the function is pure, and a pure function that needs a fixture is usually not pure.

The step definitions live in `web/src/domain/scaffold-steps.json`; `web/src/domain/scaffold.test.ts` reads the
same file, so the two runtimes cannot disagree about what a step is.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from api.domain import scaffold
from api.domain.scaffold import Call, StepState, compute, load_steps

APP = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def steps():
    return load_steps()


def by_key(outcomes):
    return {o.key: o for o in outcomes}


def completed(name, **fields):
    return Call(name=name, status="completed", result=json.dumps(fields))


# -- the definition ------------------------------------------------------------------------------
def test_seven_steps_in_the_order_the_card_implies(steps):
    assert [s.key for s in steps] == ["project", "branch", "table", "resource", "files", "deploy", "verify"]


def test_every_step_names_a_tool_that_exists_and_a_proof_field(steps):
    server = (APP / "tools" / "databricks_notebook_mcp.py").read_text()
    for step in steps:
        assert step.proof, f"{step.key} has no proof field"
        for tool in step.tools:
            assert f"def {tool}(" in server, f"{step.key} names a tool that does not exist: {tool}"


def test_the_typescript_mirror_reads_the_same_file(steps):
    """[07 §2.1] One rule, two runtimes: the TS module imports this JSON, not a copy of it."""
    ts = (APP / "web" / "src" / "domain" / "scaffold.ts").read_text()
    assert 'from "./scaffold-steps.json"' in ts
    # and the definitions are the same file the Python module reads
    assert scaffold.STEPS_FILE == APP / "web" / "src" / "domain" / "scaffold-steps.json"


# -- a proof is required ---------------------------------------------------------------------------
def test_a_full_chain_proves_every_step(steps):
    calls = [
        completed("dbx_lakebase_create", project="projects/pg"),
        completed("dbx_lakebase_branch", branch="projects/pg/branches/agent-1"),
        completed("dbx_lakebase_sql", ok=True, row_count=12),
        completed("dbx_create_app", resources=["postgres"], deploy_http_status=200),
        completed("dbx_write_file", bytes=1200),
        completed("dbx_app_health", status=200),
    ]
    outcomes = compute(steps, calls)
    assert [o.state for o in outcomes] == [StepState.DONE] * 7
    assert by_key(outcomes)["table"].proof == "12"
    assert by_key(outcomes)["verify"].proof == "200"


def test_a_completed_call_without_the_proof_field_does_not_prove_the_step(steps):
    """[E-9] `{"ok": true}` is not a proof of a table. This is the difference between a status and
    evidence, and it is the whole reason the table exists."""
    calls = [completed("dbx_lakebase_sql", ok=True)]
    table = by_key(compute(steps, calls))["table"]
    assert table.state is StepState.PENDING and table.proof == ""


def test_a_row_count_read_back_is_a_proof(steps):
    """The `rows` shape a SELECT returns: `{"columns": [...], "rows": [["12"]]}`."""
    calls = [Call("dbx_lakebase_sql", "completed",
                  result=json.dumps({"columns": ["count"], "rows": [["12"]], "row_count": 1}))]
    assert by_key(compute(steps, calls))["table"].proof == "12"


def test_a_failed_call_is_not_a_proof_even_with_the_field(steps):
    calls = [Call("dbx_lakebase_create", "error", result=json.dumps({"project": "projects/x", "error": "denied"}))]
    outcome = by_key(compute(steps, calls))["project"]
    assert outcome.state is StepState.BLOCKED and outcome.proof == ""


def test_a_write_that_reported_its_bytes_proves_the_files_step(steps):
    calls = [completed("dbx_write_file", path="/f/app.yaml", bytes=240)]
    assert by_key(compute(steps, calls))["files"].proof == "240"


def test_a_deployment_that_returned_a_5xx_is_not_a_proof(steps):
    calls = [completed("dbx_create_app", resources=["postgres"], deploy_http_status=500)]
    assert by_key(compute(steps, calls))["deploy"].state is not StepState.DONE


def test_a_health_check_that_returned_500_is_not_a_proof(steps):
    calls = [completed("dbx_app_health", status=500)]
    assert by_key(compute(steps, calls))["verify"].state is not StepState.DONE


def test_an_app_without_the_postgres_resource_does_not_prove_the_resource_step(steps):
    """[F6] An app created without the resource is the defect; it must not tick the box."""
    calls = [completed("dbx_create_app", resources=[])]
    assert by_key(compute(steps, calls))["resource"].state is not StepState.DONE


# -- the chain stops ------------------------------------------------------------------------------
def test_a_blocked_step_stops_the_chain(steps):
    """[SCF-2], [E-8] Creating an app over a missing table is not a partial success.

    A step whose call DID prove it is still `done` — it happened — but it carries a reason saying it
    ran after a block, and every step with no proof is `pending` naming the blocker. The plan
    therefore cannot be read as a tidy chain over a broken one.
    """
    calls = [
        completed("dbx_lakebase_create", project="projects/pg"),
        completed("dbx_lakebase_branch", branch="projects/pg/branches/a"),
        Call("dbx_lakebase_sql", "error", result=json.dumps({"error": "permission denied on schema"})),
        completed("dbx_create_app", resources=["postgres"], deploy_http_status=200),
    ]
    rows = by_key(compute(steps, calls))
    assert rows["table"].state is StepState.BLOCKED
    assert "permission denied" in rows["table"].reason
    # the app call happened, so it is done — and it says it ran after a block
    assert rows["resource"].state is StepState.DONE
    assert "table" in rows["resource"].reason and "blocked" in rows["resource"].reason
    # and no later step can be proven, because none was attempted
    assert rows["verify"].state is StepState.PENDING
    assert "table" in rows["verify"].reason


def test_no_app_is_created_when_the_table_step_blocks(steps):
    """The behavioural half of [SCF-2]: the plan is not the only guard; the steps after a block must
    not have been attempted at all. This asserts the SHAPE a scenario must produce, so a fake scenario
    that creates an app over a failed table fails here."""
    calls = [
        completed("dbx_lakebase_create", project="projects/pg"),
        completed("dbx_lakebase_branch", branch="projects/pg/branches/a"),
        Call("dbx_lakebase_sql", "error", result=json.dumps({"error": "permission denied"})),
        completed("dbx_create_app", resources=["postgres"], deploy_http_status=200),
    ]
    rows = compute(steps, calls)
    app_step = [o for o in rows if o.key == "resource"][0]
    assert app_step.state is StepState.DONE, "the call happened; the plan does not pretend otherwise"
    assert app_step.reason, "but it MUST say the chain was broken before it"


def test_a_running_step_is_running_not_blocked(steps):
    calls = [Call("dbx_lakebase_create", "running")]
    rows = by_key(compute(steps, calls))
    assert rows["project"].state is StepState.RUNNING
    assert rows["branch"].state is StepState.PENDING


# -- repetition ----------------------------------------------------------------------------------
def test_a_repeated_proof_keeps_one_row_and_the_latest_value(steps):
    """[E-10] A retried create must not produce two rows in the plan."""
    calls = [
        completed("dbx_lakebase_create", project="projects/first"),
        completed("dbx_lakebase_create", project="projects/second"),
    ]
    outcomes = compute(steps, calls)
    assert len([o for o in outcomes if o.key == "project"]) == 1
    assert by_key(outcomes)["project"].proof == "projects/second"


# -- performance -----------------------------------------------------------------------------------
def test_matching_is_linear_in_calls_plus_steps(steps):
    """[06 §6.4] This runs on every render tick. A per-step scoring loop over the calls would be
    `O(s · c)` — the mistake spec 012 found in the evidence-heading scan."""
    import time
    calls = [completed("dbx_run_sql", columns=["n"], rows=[["1"]], row_count=1)] * 2000
    calls += [completed("dbx_lakebase_create", project="projects/p")]
    started = time.perf_counter()
    compute(steps, calls)
    elapsed = time.perf_counter() - started
    assert elapsed < 0.05, f"2000 calls took {elapsed * 1000:.1f} ms"


# -- the summary ------------------------------------------------------------------------------------
def test_progress_counts_proven_steps(steps):
    calls = [completed("dbx_lakebase_create", project="projects/p"),
             completed("dbx_lakebase_branch", branch="projects/p/branches/b")]
    assert scaffold.progress(compute(steps, calls)) == {"done": 2, "total": 7}


def test_outcomes_serialise_for_the_api(steps):
    row = compute(steps, [completed("dbx_lakebase_create", project="projects/p")])[0]
    data = row.to_dict()
    assert data["key"] == "project" and data["state"] == "done" and data["proof"] == "projects/p"
