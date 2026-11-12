"""Two implementations of one fence rule, held to one table.

The tool server is a separate process: it cannot import `api.domain.scope`, so the rule exists twice
(spec 013 [RB-5]). Duplication with no guard is drift, so this file is the guard: one table of cases,
asserted against both sides. If either side changes alone, a row here fails and names which.

`api.domain.scope` answers `Verdict.ALLOW | ASK | DENY`.
The tool server answers by raising `PermissionError` or returning normally.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.domain import scope as server_scope          # the app's implementation

SERVER = Path(__file__).resolve().parents[1] / "tools" / "databricks_notebook_mcp.py"

FOLDER = "/Users/me/agent_scratch"
SCHEMA = "main.agent_scratch"
JOB = "job-prefix-"
INSTANCE = "inst-prefix-"
APP = "app-prefix-"


@pytest.fixture(scope="module")
def tools():
    """The tool server, loaded once with the same scope the app's `Scope` describes."""
    saved = dict(os.environ)
    os.environ.update({
        "NBMCP_ALLOW_WRITES": "1",
        "NBMCP_WRITE_PATHS": FOLDER.rstrip("/") + "/",
        "NBMCP_WRITE_SCHEMAS": SCHEMA,
        "NBMCP_WRITE_JOB_PREFIX": JOB,
        "NBMCP_WRITE_INSTANCE_PREFIX": INSTANCE,
        "NBMCP_WRITE_APP_PREFIX": APP,
        "DATABRICKS_HOST": "https://example.invalid",
        "DATABRICKS_TOKEN": "t",
    })
    spec = importlib.util.spec_from_file_location("nbmcp_parity", SERVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    os.environ.clear()
    os.environ.update(saved)
    return module


@pytest.fixture(scope="module")
def scope():
    return server_scope.Scope.for_session("abcdef12-0000-0000", FOLDER, SCHEMA)


def _allows(verdict) -> bool:
    """The one bridge between the two shapes. `ASK` is not `ALLOW`: the tool refuses, the app asks a
    human, and for "is this inside the fence" both are 'no'."""
    return verdict is server_scope.Verdict.ALLOW


# -- paths -------------------------------------------------------------------------------------
PATH_CASES = [
    (f"{FOLDER}/x.py", True),
    (f"{FOLDER}/nested/x.py", True),
    (f"{FOLDER}/../other/x.py", False),      # the escape a prefix test misses (spec 013 [E-27])
    (f"{FOLDER}/a/../../etc/passwd", False),
    ("/Shared/x.py", False),
    ("/Users/someone_else/x.py", False),
    (f"{FOLDER}/", True),
]


@pytest.mark.parametrize("path,allowed", PATH_CASES)
def test_path_fence_agrees(tools, scope, path, allowed):
    app_side = _allows(server_scope.check_path(scope, path).verdict)
    try:
        tools._check_path_scope(path)
        tool_side = True
    except PermissionError:
        tool_side = False
    assert app_side is allowed, f"the app's check_path disagrees with the table for {path}"
    assert tool_side is allowed, f"the tool server's _check_path_scope disagrees for {path}"


# -- SQL write targets -------------------------------------------------------------------------
# The table now includes the statements that used to fall through to ALLOW. A parity test that
# accepts "ALLOW or ASK" accepts every verdict except DENY, so it could not fail on the bug where a
# write with no readable target was ALLOWed. Each row states the answer the fence must give, and both
# sides are held to it.
#: The two sides answer slightly different questions, and the difference is deliberate:
#:
#:   `expected`        what the APP decides, including the human check for a destructive statement
#:   `tool_scope`      what the TOOL SERVER decides about scope alone — it has no approval flow, so
#:                     it cannot ask a human; a destructive statement inside the fence is "in scope"
#:
#: Writing both columns is what makes the difference a recorded decision instead of a test that
#: passes because it accepts any answer. The rule is: the app is never LOOSER than the tool. Where the
#: app says `allow`, the tool must say in-scope; where the tool says out-of-scope, the app must not
#: say `allow`.
SQL_CASES = [
    # (statement, app verdict, tool says in scope?)
    (f"CREATE TABLE {SCHEMA}.t (x INT)", "allow", True),
    ("CREATE TABLE main.other.t (x INT)", "ask", False),
    ("INSERT INTO main.other.t VALUES (1)", "ask", False),
    (f"INSERT INTO {SCHEMA}.t SELECT * FROM main.other.s", "allow", True),
    (f"MERGE INTO {SCHEMA}.t USING s ON 1=1 WHEN MATCHED THEN DELETE", "allow", True),
    ("MERGE INTO main.other.t USING s ON 1=1 WHEN MATCHED THEN UPDATE SET x=1", "ask", False),
    ("DROP TABLE main.other.t", "ask", False),
    # destructive inside the fence: the tool has no human to ask, so it is merely in scope; the app
    # asks. This is the one row where the two columns disagree on purpose.
    ("DROP TABLE main.agent_scratch.t", "ask", True),
    ("OPTIMIZE main.other.t", "ask", False),             # was ALLOW before the fix
    ("OPTIMIZE main.agent_scratch.t", "allow", True),
    ("VACUUM main.other.t", "ask", False),               # was ALLOW before the fix
    ("VACUUM main.agent_scratch.t", "allow", True),
    ("COMMENT ON TABLE main.other.t IS 'x'", "ask", False),   # was READ, never reached the fence
    ("COMMENT ON TABLE main.agent_scratch.t IS 'x'", "allow", True),
    ("INSERT INTO t VALUES (1)", "ask", False),          # unplaceable, so unprovable
]


@pytest.mark.parametrize("sql,expected,tool_scope", SQL_CASES)
def test_sql_fence_agrees(tools, scope, sql, expected, tool_scope):
    tool_in_scope = tools._check_sql_scope(sql) is None
    app_verdict = server_scope.check_sql(scope, sql).verdict
    assert tool_in_scope is tool_scope, (
        f"the tool server says in-scope={tool_in_scope} for {sql!r}, the table says {tool_scope}")
    assert (app_verdict is server_scope.Verdict.ALLOW) is (expected == "allow"), (
        f"the app says {app_verdict.value} for {sql!r}, the table says {expected}")
    # The invariant, independent of the table: the app may be stricter, never looser.
    if app_verdict is server_scope.Verdict.ALLOW:
        assert tool_in_scope, (
            f"the app ALLOWED {sql!r} while the tool server refuses it out of scope")


@pytest.mark.parametrize("sql", [
    "OPTIMIZE main.other.t", "VACUUM main.other.t", "DROP TABLE main.other.t",
    "COMMENT ON TABLE main.other.t IS 'x'", "INSERT INTO main.other.t VALUES (1)",
])
def test_the_app_is_never_looser_than_the_tool(tools, scope, sql):
    """The property, stated once and swept: if the tool refuses for scope, the app must not allow.

    This is the bug that existed. `check_sql` answered ALLOW for `OPTIMIZE main.other.t` because it
    could not read the target; the tool server refused the same statement. A parity test that allowed
    "ALLOW or ASK" could not see the disagreement, so it passed on a broken fence.
    """
    app_allows = server_scope.check_sql(scope, sql).verdict is server_scope.Verdict.ALLOW
    tool_in_scope = tools._check_sql_scope(sql) is None
    assert not (app_allows and not tool_in_scope), (
        f"{sql!r}: the app allowed a statement the tool server refuses as out of scope")


def test_a_destructive_statement_always_needs_a_human_on_the_app_side(tools, scope):
    """The one place the two sides deliberately differ, asserted so the difference is a decision."""
    decision = server_scope.check_sql(scope, f"DROP TABLE {SCHEMA}.t")
    assert decision.verdict is server_scope.Verdict.ASK
    assert decision.reason == "destructive SQL always needs a human"
    # the tool server's helper answers only the scope question, not the human one
    assert tools._check_sql_scope(f"DROP TABLE {SCHEMA}.t") is None


# -- name prefixes -----------------------------------------------------------------------------
# The names are built from the SCOPE's own prefixes, not from constants: `Scope.for_session` derives
# them from the session id, and a table written against invented strings would test nothing.
def prefix_cases(scope):
    cases = [
        ("job", f"{scope.job_prefix}daily", True),
        ("job", f"{scope.instance_prefix}daily", False),
        ("instance", f"{scope.instance_prefix}db", True),
        ("app", f"{scope.app_prefix}tickets", True),
        ("app", "tickets", False),
    ]
    # A cross-kind row is only meaningful when the two prefixes DIFFER. `Scope.for_session` currently
    # derives the same string for an app and an instance (`agent-<id>-`), so "an instance name checked
    # as an app" cannot be a distinguishing case here — and pretending otherwise would be a test that
    # passes for the wrong reason. `test_tools_fence.py` covers it with five distinct prefixes, which
    # is where the coincidence is broken on purpose ([E-6]).
    if scope.app_prefix != scope.instance_prefix:
        cases += [
            ("instance", f"{scope.app_prefix}db", False),
            ("app", f"{scope.instance_prefix}tickets", False),
        ]
    return cases


def test_name_prefix_fence_is_per_kind(tools, scope):
    """Both sides classify the SAME object: `check_app`/`check_job`/`check_instance` and the tool's
    `_check_prefix` with the matching prefix.

    The tool server's prefixes are set to the scope's, which is what `registry.start` does; if that
    wiring ever drops one, the row it feeds fails here.
    """
    tools.JOB_PREFIX = scope.job_prefix
    tools.INSTANCE_PREFIX = scope.instance_prefix
    tools.APP_PREFIX = scope.app_prefix
    app_check = {"job": server_scope.check_job, "instance": server_scope.check_instance,
                 "app": server_scope.check_app}
    tool_prefix = {"job": tools.JOB_PREFIX, "instance": tools.INSTANCE_PREFIX,
                   "app": tools.APP_PREFIX}
    failures = []
    for kind, name, allowed in prefix_cases(scope):
        app_side = _allows(app_check[kind](scope, name).verdict)
        try:
            tools._check_prefix(kind, name, tool_prefix[kind])
            tool_side = True
        except PermissionError:
            tool_side = False
        if app_side is not allowed:
            failures.append(f"app check_{kind}({name!r}) said {app_side}, table says {allowed}")
        if tool_side is not allowed:
            failures.append(f"tool prefix[{kind}] ({name!r}) said {tool_side}, table says {allowed}")
    assert not failures, "the two fences disagree:\n  " + "\n  ".join(failures)


def test_a_scope_would_distinguish_the_two_prefixes_if_it_ever_needs_to(scope):
    """[E-6] The app and instance prefixes are equal today *by construction* (`agent-<id>-`), which is
    why the defect in [F3] was invisible. This records the coincidence as a fact of `Scope`, so the
    cross-kind case above is skipped knowingly rather than accidentally."""
    assert scope.app_prefix == f"agent-{scope.app_prefix.split('-')[1]}-"
    assert scope.job_prefix != scope.app_prefix


def test_the_scope_and_the_environment_describe_the_same_fence(tools, scope):
    """`Scope.for_session` produces the values `registry.start` passes as environment. If the two
    derivations ever diverge, both sides 'work' and enforce different fences ([RB-5])."""
    assert tools.WRITE_PATHS == [scope.folder], (tools.WRITE_PATHS, scope.folder)
    assert tools.WRITE_SCHEMAS == [(scope.schema or "").lower()], (tools.WRITE_SCHEMAS, scope.schema)


# -- the UNSET case: the one the table above never had -------------------------------------------
# `[R-1]`, `[R-2]`. Every dimension of a fence can be unset, and until these rows existed the two
# runtimes disagreed about what that means: the app answered ASK and the tool server answered *allow*.
# Measured before the fix: `_check_path_scope("/Users/victim/x.py")` returned None (in scope) for a
# session created with `folder="/"`, and `_check_sql_scope` returned None for any statement when no
# schema was configured. A fence that opens when a field is omitted is not a fence.
#
# The table is the specification: row = (dimension, spelling of "unset"). Both sides must REFUSE.

UNSET_FOLDERS = [None, "", " ", "/", "//", "///", " . ", "`/`"]
UNSET_SCHEMAS = [None, "", " ", "sales", "main.", ".sales", "` `"]

#: A path that must be refused, and a statement that must be refused, for every unset spelling.
FOREIGN_PATH = "/Users/someone_else/agent_scratch/x.py"
FOREIGN_SQL = "DROP TABLE main.production.sales"


def _tools_with(paths: str, schemas: str):
    """Load the tool server with a specific scope environment. A fresh module per case, because the
    scope is read once at import (`WRITE_PATHS`/`WRITE_SCHEMAS` are module constants)."""
    from api.domain.fence_rules import writable_folder, writable_schema

    saved = dict(os.environ)
    os.environ.update({
        "NBMCP_ALLOW_WRITES": "1",
        "NBMCP_WRITE_PATHS": paths,
        "NBMCP_WRITE_SCHEMAS": schemas,
        "NBMCP_WRITE_JOB_PREFIX": JOB,
        "NBMCP_WRITE_INSTANCE_PREFIX": INSTANCE,
        "NBMCP_WRITE_APP_PREFIX": APP,
        "DATABRICKS_HOST": "https://example.invalid",
        "DATABRICKS_TOKEN": "t",
    })
    try:
        spec = importlib.util.spec_from_file_location("nbmcp_unset", SERVER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        os.environ.clear()
        os.environ.update(saved)
    # `registry.start` no longer builds these strings itself: it asks `fence_rules`. So the test drives
    # the SAME derivation the app uses, which is the only way the row proves the real seam.
    module.WRITE_PATHS = [p for p in writable_folder(paths).split(",") if p]
    module.WRITE_SCHEMAS = [s for s in writable_schema(schemas).split(",") if s]
    return module


@pytest.mark.parametrize("folder", UNSET_FOLDERS)
def test_an_unset_folder_refuses_every_path_on_both_sides(folder):
    """`folder` unset in any spelling → the app ASKs and the tool server REFUSES the same path."""
    scope = server_scope.Scope.for_session("abcdef12-0000", folder or "", None)
    app_allows = _allows(server_scope.check_path(scope, FOREIGN_PATH).verdict)
    tools = _tools_with(folder or "", "")
    try:
        tools._check_path_scope(FOREIGN_PATH)
        tool_allows = True
    except PermissionError:
        tool_allows = False
    assert not app_allows, f"the app allowed {FOREIGN_PATH} for folder={folder!r}"
    assert not tool_allows, f"the tool server allowed {FOREIGN_PATH} for folder={folder!r}"


@pytest.mark.parametrize("schema", UNSET_SCHEMAS)
def test_an_unset_schema_refuses_every_write_on_both_sides(schema):
    """`schema` unset (or unplaceable) → the app ASKs and the tool server REFUSES the same statement."""
    scope = server_scope.Scope.for_session("abcdef12-0000", FOLDER, schema)
    app_allows = _allows(server_scope.check_sql(scope, FOREIGN_SQL).verdict)
    tools = _tools_with(FOLDER, schema or "")
    tool_err = tools._check_sql_scope(FOREIGN_SQL)
    assert not app_allows, f"the app allowed {FOREIGN_SQL} for schema={schema!r}"
    assert tool_err, f"the tool server allowed {FOREIGN_SQL} for schema={schema!r}"


def test_a_root_folder_never_becomes_a_wildcard_through_the_registry():
    """The exact arithmetic that produced the wildcard: `"/".rstrip("/") + "/"` is `"/"`.

    This asserts the DERIVATION, not a behaviour, because the bug lived in the derivation and the
    behaviour was correct in the one place somebody looked.
    """
    from api.domain.fence_rules import writable_folder
    from api.domain.scope import Scope

    for spelling in ("/", "", "//", "   "):
        assert writable_folder(spelling) == "", f"{spelling!r} produced a writable folder"
        assert Scope.for_session("abcdef12", spelling, None).folder == ""
    assert writable_folder("/Users/me/x") == "/Users/me/x/"


def test_the_refusal_names_which_dimension_is_missing():
    """A refusal that says "not allowed" without saying WHAT is unset is the least useful state in the
    product. `[R-1]` requires the sentence to name the missing dimension and the remedy."""
    from api.domain.fence_rules import refuse_reason

    assert "schema" in refuse_reason("schema")
    assert "folder" in refuse_reason("folder")
    for dimension in ("schema", "folder"):
        sentence = refuse_reason(dimension)
        assert "write blocked" in sentence
        assert "conversation" in sentence   # the remedy
