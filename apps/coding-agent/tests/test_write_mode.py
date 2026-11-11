"""The write mode, enforced by the process that actually mutates. `[R-9]`, `[F-8]`.

The pure grid is in `test_phase2.py`. This file proves the **other runtime**: `NBMCP_WRITE_MODE` in the
tool server's environment changes what a mutating tool does, and the `ask` mode returns the structured
needs-human payload rather than raising — because an exception reads as a failure and this is not one.

The defect these close: `NBMCP_ALLOW_WRITES=1` was a constant for every session, so the tool server's own
docstring (*"mirrors Genie Code's approval modes but is enforced by the server"*) described a mode the
product never used, and a SQL write inside the schema executed with no human gate.
"""

from __future__ import annotations

import ast
import importlib.util
import inspect
import json
import os
import textwrap
from pathlib import Path

import pytest

SERVER = Path(__file__).resolve().parents[1] / "tools" / "databricks_notebook_mcp.py"
FOLDER = "/Users/me/agent_scratch"
SCHEMA = "main.agent_scratch"


def load(mode: str):
    """The tool server as a fresh module, with one mode. A module per case because the mode is read once
    at import, the same way the write scope is."""
    saved = dict(os.environ)
    os.environ.update({
        "NBMCP_ALLOW_WRITES": "1",
        "NBMCP_WRITE_MODE": mode,
        "NBMCP_WRITE_PATHS": FOLDER.rstrip("/") + "/",
        "NBMCP_WRITE_SCHEMAS": SCHEMA,
        "NBMCP_WRITE_JOB_PREFIX": "agent_abcdef12_",
        "NBMCP_WRITE_APP_PREFIX": "agent-abcdef12-",
        "NBMCP_WRITE_INSTANCE_PREFIX": "agent-abcdef12-",
        "DATABRICKS_HOST": "https://example.invalid",
        "DATABRICKS_TOKEN": "t",
        "NBMCP_PROFILE": "core",
    })
    try:
        spec = importlib.util.spec_from_file_location(f"nbmcp_mode_{mode.replace('-', '_')}", SERVER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        os.environ.clear()
        os.environ.update(saved)
    return module


# ============================================================== read-only
def test_read_only_refuses_every_mutation_and_names_the_mode():
    m = load("read-only")
    with pytest.raises(PermissionError) as e:
        m._need_writes("write a notebook")
    text = str(e.value)
    assert "read-only" in text, "the refusal must name the mode, not just the folder"
    assert "write a notebook" in text


def test_read_only_refuses_even_inside_the_fence():
    """The mode outranks placement: a read-only session says no to a target it was allowed to reach."""
    m = load("read-only")
    with pytest.raises(PermissionError, match="read-only"):
        m._need_writes("create a table")


def test_fenced_allows_the_gate_and_still_enforces_the_fence():
    m = load("fenced")
    m._need_writes("write a notebook")          # the mode gate passes
    assert m._check_sql_scope(f"CREATE TABLE {SCHEMA}.t (x INT)") is None
    assert m._check_sql_scope("CREATE TABLE main.other.t (x INT)") is not None


# ============================================================== ask
def test_ask_returns_a_needs_human_payload_from_a_mutating_tool():
    """`ask` does not raise: it returns a value the app turns into an approval. An exception here would
    be read as a failure by every caller, and asking is not one."""
    m = load("ask")
    out = m.dbx_write_file(f"{FOLDER}/a.txt", "hello")
    payload = json.loads(out)
    assert payload["needsHuman"] is True
    assert payload["tool"] == "dbx_write_file"
    assert payload["mode"] == "ask"
    assert "Approve" in payload["note"]


def test_ask_does_not_touch_the_workspace():
    """A needs-human result must not have performed the write it is asking about."""
    m = load("ask")
    out = json.loads(m.dbx_write_file(f"{FOLDER}/a.txt", "hello"))
    assert "error" not in out or out.get("needsHuman")
    assert out["needsHuman"] is True


def test_ask_leaves_reads_alone():
    """The wrapper fires only for `_MUTATING`; a read in `ask` mode is untouched."""
    m = load("ask")
    assert "dbx_describe_table" not in m._MUTATING
    assert "dbx_list_tables" not in m._MUTATING


def test_fenced_calls_the_tool_rather_than_asking():
    """In `fenced`, the same tool reaches the workspace layer — proven by the error being about the
    CONNECTION (there is no real host in a unit test), not about approval.

    Any exception type is accepted here, and the assertion is on what the exception is NOT: a `fenced`
    session that returned a needs-human payload, or one whose message mentions approval, would mean the
    mode leaked into a mode that should not ask.
    """
    m = load("fenced")
    with pytest.raises(Exception) as e:
        m.dbx_write_file(f"{FOLDER}/a.txt", "hello")
    message = str(e.value).lower()
    assert "needshuman" not in message
    assert "approv" not in message
    assert isinstance(e.value, Exception) and not isinstance(e.value, SystemExit)


# ============================================================== the set itself
def test_every_tool_that_calls_the_write_gate_is_in_the_ask_set():
    """`_MUTATING` and the `_need_writes()` call sites must name the same tools.

    This is the guard against a new mutating tool that `ask` mode silently lets through: the mode is
    applied by the decorator, which consults `_MUTATING`, while the operator switch is applied by
    `_need_writes()`. Two lists that must agree is exactly the drift `test_fence_parity.py` exists for.
    """
    m = load("full")
    named = set(m._MUTATING)
    assert len(named) >= 15, f"only {len(named)} mutating tools found"

    # …and the set must match the tools that actually call the gate. Read from the RUNTIME, not the
    # source text: a substring search matches the docstring that *describes* the gate, which is how the
    # first version of this check reported a tool that no longer called it.
    gated = set()
    for name in (n for n in dir(m) if n.startswith("dbx_")):
        fn = getattr(m, name)
        if not callable(fn):
            continue
        body = inspect.getsource(fn)
        # Strip the docstring, then look for a real call.
        tree = ast.parse(textwrap.dedent(body))
        calls = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        if "_need_writes" in calls:
            gated.add(name)
    assert named == gated, (
        f"the ask set and the write gate disagree — "
        f"in the set only: {sorted(named - gated)}; calls the gate only: {sorted(gated - named)}")

    # Every name in the set must be a real tool.
    for name in named:
        assert hasattr(m, name), f"{name} is in _MUTATING but is not a tool"


def test_the_mode_is_read_from_the_environment_and_defaults_to_fenced():
    m = load("fenced")
    assert m.WRITE_MODE == "fenced"
    m2 = load("")
    assert m2.WRITE_MODE == "fenced", "an unset mode must be the narrow default, never unrestricted"


@pytest.mark.parametrize("alias", ["read_only", "readonly", "RO"])
def test_the_read_only_aliases_all_refuse(alias):
    m = load(alias)
    with pytest.raises(PermissionError, match="read-only"):
        m._need_writes("change something")
