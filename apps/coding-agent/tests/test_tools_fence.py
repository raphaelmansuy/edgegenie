"""The fence for the two objects the agent can create, with prefixes that are all DIFFERENT.

Why this file exists. `dbx_create_app` compared an app name against `INSTANCE_PREFIX`, and no test
could see it because the two prefixes are the same string today (spec 013 [F3]). So every test here
uses five *different* prefixes: a mix-up cannot pass by coincidence, which is the only way to prove
this class of fix.

Each test loads the tool server as a module (no network, no MCP transport) and calls the guard the
tool itself calls.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

SERVER = Path(__file__).resolve().parents[1] / "tools" / "databricks_notebook_mcp.py"

PREFIXES = {
    "NBMCP_WRITE_PATHS": "/Users/me/agent_scratch/",
    "NBMCP_WRITE_SCHEMAS": "main.agent_scratch",
    "NBMCP_WRITE_JOB_PREFIX": "job-prefix-",
    "NBMCP_WRITE_INSTANCE_PREFIX": "inst-prefix-",
    "NBMCP_WRITE_APP_PREFIX": "app-prefix-",
}


def load(monkeypatch, **overrides):
    """Load a fresh copy of the tool server with its own environment."""
    env = {**PREFIXES, **overrides}
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    # A host and token keep `_client()` from raising before a test reaches the guard.
    monkeypatch.setenv("DATABRICKS_HOST", "https://example.invalid")
    monkeypatch.setenv("DATABRICKS_TOKEN", "t")
    monkeypatch.setenv("NBMCP_ALLOW_WRITES", "1")
    spec = importlib.util.spec_from_file_location(f"nbmcp_fence_{os.urandom(4).hex()}", SERVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# -- the defect this file exists for ---------------------------------------------------------
def test_the_five_prefixes_are_five_different_strings(monkeypatch):
    """If this ever passes trivially, the suite below stops proving anything."""
    m = load(monkeypatch)
    values = {m.JOB_PREFIX, m.INSTANCE_PREFIX, m.APP_PREFIX}
    assert len(values) == 3, "job, instance and app prefixes must be distinct in this test"


def test_an_app_name_is_checked_against_the_app_prefix_not_the_instance_prefix(monkeypatch):
    """[E-6] The exact defect: a name matching the INSTANCE prefix must be refused as an APP name."""
    m = load(monkeypatch)
    with pytest.raises(PermissionError, match="app-prefix-"):
        m.dbx_create_app("inst-prefix-tickets")
    # and the right prefix passes the guard (the call itself never happens: no host)
    m._check_prefix("app", "app-prefix-tickets", m.APP_PREFIX)


def test_an_instance_name_is_checked_against_the_instance_prefix(monkeypatch):
    m = load(monkeypatch)
    m._check_prefix("instance", "inst-prefix-db", m.INSTANCE_PREFIX)
    with pytest.raises(PermissionError, match="inst-prefix-"):
        m._check_prefix("instance", "app-prefix-db", m.INSTANCE_PREFIX)


def test_a_job_name_is_checked_against_the_job_prefix(monkeypatch):
    m = load(monkeypatch)
    m._check_prefix("job", "job-prefix-daily", m.JOB_PREFIX)
    with pytest.raises(PermissionError, match="job-prefix-"):
        m._check_prefix("job", "inst-prefix-daily", m.JOB_PREFIX)


# -- refusals say what to do, and offer no retry ----------------------------------------------
def test_a_prefix_refusal_names_the_prefix_and_forbids_a_second_guess(monkeypatch):
    """[E-5] A model that reads a bare "denied" tries another name. The message must stop that."""
    m = load(monkeypatch)
    with pytest.raises(PermissionError) as caught:
        m.dbx_create_app("tickets-app")
    message = str(caught.value)
    assert "app-prefix-" in message
    assert "tickets-app" in message


def test_an_app_name_the_platform_would_reject_is_refused_before_the_call(monkeypatch):
    """[E-7] Local validation: zero HTTP calls for a name the platform's pattern excludes."""
    m = load(monkeypatch)

    def no_call(*a, **k):  # pragma: no cover - it must never run
        raise AssertionError("the platform must not be called for an invalid name")

    monkeypatch.setattr(m, "_client", no_call)
    out = m.dbx_create_app("app-prefix-Bad_Name")
    assert "lowercase" in out and "30" in out


def test_a_postgres_resource_without_a_branch_is_refused_locally(monkeypatch):
    """[AP-1] An app with a postgres resource but no branch is the F6 defect arriving from the side."""
    m = load(monkeypatch)
    out = m.dbx_create_app("app-prefix-tickets", project="inst-prefix-db")
    assert "branch" in out
    assert "production" in out, "the refusal must say not to use production"


# -- the path and SQL fences, unchanged, held to the same table ------------------------------
@pytest.mark.parametrize("path,allowed", [
    ("/Users/me/agent_scratch/a.py", True),
    ("/Users/me/agent_scratch/../other/a.py", False),
    ("/Users/me/other/a.py", False),
    ("/Shared/a.py", False),
])
def test_the_path_fence_still_refuses_an_escape(monkeypatch, path, allowed):
    m = load(monkeypatch)
    if allowed:
        m._check_path_scope(path)
    else:
        with pytest.raises(PermissionError):
            m._check_path_scope(path)


@pytest.mark.parametrize("sql,blocked", [
    ("CREATE TABLE main.agent_scratch.t (x INT)", False),
    ("CREATE TABLE main.other.t (x INT)", True),
    ("INSERT INTO main.other.t VALUES (1)", True),
    ("MERGE INTO main.other.t USING s ON 1=1 WHEN MATCHED THEN DELETE", True),
    ("not sql at all", True),        # fail closed: a write we cannot read is not a write we allow
])
def test_the_sql_fence_still_refuses_a_write_outside_the_schema(monkeypatch, sql, blocked):
    """The helper's contract is about WRITES: `dbx_run_sql` sends a read straight through and calls
    this only for a statement whose head is not SELECT/SHOW/DESCRIBE/EXPLAIN. So a `SELECT` is not
    this function's business, and an unparseable write is refused rather than allowed."""
    m = load(monkeypatch)
    error = m._check_sql_scope(sql)
    assert (error is not None) is blocked


def test_a_read_is_never_offered_to_the_write_checker(monkeypatch):
    """The guarantee is in the caller: a read head skips the check. This asserts the caller's rule,
    because the helper fails closed by design and would refuse an unparseable statement."""
    m = load(monkeypatch)
    import inspect
    src = inspect.getsource(m.dbx_run_sql)
    assert '("SELECT", "SHOW", "DESCRIBE", "DESC", "EXPLAIN"' in src
    assert "_check_sql_scope(sql)" in src


# -- the capacity rules are checked before the platform is asked -----------------------------
@pytest.mark.parametrize("low,high,expected", [
    (0, 0, None),            # no range given: the platform's default
    (0.5, 4, None),
    (8, 24, None),           # exactly 16 apart
    (0.5, 32, "16"),         # 31.5 apart
    (2, 66, "64"),
    (0.4, 1, "0.5"),
    (8, 4, "below"),
])
def test_the_autoscaling_range_is_checked_locally(monkeypatch, low, high, expected):
    """[LB-4], [E-7] The rule is the platform's; the sentence is ours."""
    m = load(monkeypatch)
    problem = m._capacity_problem(low, high)
    if expected is None:
        assert problem is None
    else:
        assert problem is not None and expected in problem


# -- identity normalisation ------------------------------------------------------------------
def test_a_project_name_and_its_full_path_are_one_object(monkeypatch):
    """[LB-5], [E-24] Two spellings, one key: the notebook equivalent is `canonicalPath`."""
    m = load(monkeypatch)
    assert m._lakebase_project("pg_tickets") == m._lakebase_project("projects/pg_tickets")
    assert m._lakebase_project("/projects/pg_tickets/") == "projects/pg_tickets"


def test_an_endpoint_path_is_built_in_one_place(monkeypatch):
    m = load(monkeypatch)
    assert (m._lakebase_endpoint("pg_tickets", "agent-1")
            == "projects/pg_tickets/branches/agent-1/endpoints/primary")
    assert (m._lakebase_endpoint("projects/pg_tickets", "production", "replica")
            == "projects/pg_tickets/branches/production/endpoints/replica")


def test_a_branch_given_as_a_full_path_is_accepted(monkeypatch):
    """A model that copies a branch path from a previous answer must not be punished for it."""
    m = load(monkeypatch)
    assert (m._lakebase_endpoint("pg_tickets", "projects/pg_tickets/branches/agent-9")
            == "projects/pg_tickets/branches/agent-9/endpoints/primary")


# -- identifiers -------------------------------------------------------------------------------
@pytest.mark.parametrize("bad", ['app"; DROP DATABASE x; --', "app'name", "app name", "1table", ""])
def test_an_identifier_that_needs_escaping_is_refused(monkeypatch, bad):
    """[E-19] An identifier that needs escaping is not an identifier."""
    m = load(monkeypatch)
    with pytest.raises(ValueError, match="identifier"):
        m._pg_identifier(bad, "database")


@pytest.mark.parametrize("good", ["app", "databricks_postgres", "_x", "a1$b"])
def test_a_plain_identifier_is_accepted(monkeypatch, good):
    m = load(monkeypatch)
    assert m._pg_identifier(good, "database") == good


# -- the tool surface is a budget, not a wish list --------------------------------------------
#: The `core` budget, raised from 25 to 28 by spec 014. The raise is a recorded decision with a
#: compensating removal and three assertions, not an edited number: `07 §6` of spec 014 carries the
#: arithmetic and the two merges that were considered and rejected. Every MCP tool is advertised on every
#: request, so this count is a cost paid on every turn of every session.
CORE_BUDGET = 28

#: The tools that LEFT `core` in spec 014. Each must still be discoverable, which here means named by a
#: skill: a tool that left `core` and is named by no skill is a tool the agent can no longer reach.
DEPARTED = {"dbx_lakebase_database", "dbx_lakebase_role", "dbx_lakebase_tables"}

#: A skill body names a tool when it mentions it in a `code span`. Checked below.
SKILLS = Path(__file__).resolve().parents[1] / "tools" / "skills"


def test_the_core_profile_stays_within_its_budget(monkeypatch):
    """[TOOL-1] The count is asserted so growth is a decision rather than a drift."""
    m = load(monkeypatch)
    assert len(m._CORE) <= CORE_BUDGET, (
        f"_CORE has {len(m._CORE)} tools, over the budget of {CORE_BUDGET}. Adding one means removing "
        f"one, or raising the budget with a reason in spec 014 [07 §6].")


def test_every_core_tool_is_reachable_from_a_flow(monkeypatch):
    """A tool in `core` that no page reads and no skill requires is context spent on nothing."""
    m = load(monkeypatch)
    text = "\n".join(p.read_text() for p in SKILLS.glob("*.md"))
    undocumented = []
    for name in sorted(m._CORE):
        # Reachable means: a skill names it, or it is one of the calls the product's own pages read
        # (the infra and job tools), which are enumerated here rather than inferred.
        if name in text or _has_a_page(name):
            continue
        undocumented.append(name)
    assert not undocumented, f"no page reads these and no skill names them: {undocumented}"


def _has_a_page(name: str) -> bool:
    """The tools whose result a page in this app renders. One list, because "reachable" is a claim about
    the product and this is where the claim is checked."""
    return name in {
        "dbx_whoami",                    # the account menu
        "dbx_list_tables", "dbx_describe_table", "dbx_search_tables",   # the Catalog tab
        "dbx_run_sql",                   # a SQL cell's result
        "dbx_list_notebooks", "dbx_read_notebook", "dbx_write_notebook", "dbx_write_file",
        "dbx_run_notebook", "dbx_run_notebook_status", "dbx_grep_notebook",   # Files tab and editor
        "dbx_list_jobs", "dbx_create_job", "dbx_run_job", "dbx_job_run_status",
        "dbx_job_failure_context",       # the Data tab, the job page, the run page
        "dbx_create_pipeline", "dbx_pipeline_status", "dbx_start_pipeline",
        "dbx_stop_pipeline",             # the Data tab, the pipeline page
        "dbx_lakebase_create", "dbx_lakebase_status", "dbx_lakebase_branch", "dbx_lakebase_sql",
        "dbx_create_app", "dbx_app_health",                              # the Data tab, spec 013 pages
        "dbx_skill",                     # the mechanism itself
    }


def test_every_tool_that_left_core_is_named_by_a_skill(monkeypatch):
    """[E-28] The removal's only real risk: a scaffold that used to work loses three calls and the agent
    has no way to learn they exist."""
    m = load(monkeypatch)
    text = "\n".join(p.read_text() for p in SKILLS.glob("*.md"))
    missing = sorted(DEPARTED - {n for n in DEPARTED if n in text})
    assert not missing, (
        f"{missing} left `core` and no skill names them, so nothing can tell the agent they exist")
    still_registered = {n for n in DEPARTED if hasattr(m, n)}
    assert still_registered == DEPARTED, (
        f"these were meant to leave `core` but stay registered in `full`: {DEPARTED - still_registered}")


def test_every_tool_a_core_tool_names_in_its_next_hint_exists(monkeypatch):
    """A `next` hint that names a renamed tool is worse than no hint: it teaches a dead call."""
    m = load(monkeypatch)
    import re
    missing = []
    for name in m._CORE:
        fn = getattr(m, name, None)
        if fn is None:
            missing.append(name)
            continue
        doc = (fn.__doc__ or "") + " "
        for hinted in re.findall(r"dbx_[a-z_]+", doc):
            if not hasattr(m, hinted):
                missing.append(f"{name} -> {hinted}")
    assert not missing, f"a hint names a tool that does not exist: {missing}"


# -- the label the UI shows must be the set the server advertises ---------------------------------
def test_the_tool_count_the_ui_shows_is_the_real_core_size(monkeypatch):
    """`TOOL_COUNT_CORE` is a LABEL — the dock's "N tools" — and a label that disagrees with reality is a
    lie in a variable. Before spec 014 it said 19 while `_CORE` had 25, so the app under-reported its own
    surface by six tools for as long as both existed.

    This test exists because a comment in `orchestrator.py` claimed one did. A claim about a test is worth
    nothing without the test, which is the same defect as a policy function with no caller (013 [F4])."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from api.services.orchestrator import TOOL_COUNT_CORE

    m = load(monkeypatch)
    assert TOOL_COUNT_CORE == len(m._CORE), (
        f"the UI shows {TOOL_COUNT_CORE} core tools but the server advertises {len(m._CORE)}")
