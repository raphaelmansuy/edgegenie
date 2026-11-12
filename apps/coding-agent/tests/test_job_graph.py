"""The task graph: one algorithm, two callers, one table.

`tools/job_graph.py` answers two questions — is this graph valid, and how is it drawn — and both are
asked by the tool server (before a create) and by the app (when it renders a job). This file is the guard
that keeps the two callers on one answer, in the shape spec 013's `test_fence_parity.py` established: a
table of shapes, asserted against both, with a failure that names the row.

The important half is the second: a graph the validator ACCEPTS must draw, and a graph it REFUSES must
not. A renderer that silently drops a cyclic task, or a validator that accepts a graph the renderer
cannot level, is the class of defect this repository keeps finding — two implementations of one rule that
each look right alone.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

GRAPH_MODULE = Path(__file__).resolve().parents[1] / "tools" / "job_graph.py"


def load_graph():
    """Import `tools/job_graph.py` by path: it is not on `sys.path` and must not be (the tool server is a
    separate process, and a shared import would hide the fact that it is duplicated)."""
    spec = importlib.util.spec_from_file_location("job_graph_under_test", GRAPH_MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


g = load_graph()


# ---------------------------------------------------------------------------------------------
# the shapes. One row per graph a model actually sends.
# ---------------------------------------------------------------------------------------------
def task(key: str, deps: list[str] | None = None, **extra) -> dict:
    body = {"task_key": key, "notebook_path": f"/Users/me/agent_scratch/{key}", "depends_on": deps or []}
    body.update(extra)
    return body


CHAIN = [task("silver"), task("gold", ["silver"])]
FAN_OUT = [task("ingest"), task("left", ["ingest"]), task("right", ["ingest"])]
FAN_IN = [task("a"), task("b"), task("join", ["a", "b"])]
DIAMOND = [task("a"), task("b", ["a"]), task("c", ["a"]), task("d", ["b", "c"])]
INDEPENDENT = [task("a"), task("b"), task("c")]
SELF = [task("a", ["a"])]
TWO_CYCLE = [task("a", ["b"]), task("b", ["a"])]
LONG_CYCLE = [task("a", ["c"]), task("b", ["a"]), task("c", ["b"]), task("lonely")]

VALID = [CHAIN, FAN_OUT, FAN_IN, DIAMOND, INDEPENDENT]
INVALID_CYCLES = [SELF, TWO_CYCLE, LONG_CYCLE]


@pytest.mark.parametrize("tasks", VALID)
def test_a_valid_graph_has_no_problems_and_draws(tasks):
    assert g.problems(tasks) == []
    drawn = g.levels(tasks)
    assert drawn, "a valid graph must draw"
    assert sorted(k for level in drawn for k in level) == sorted(t["task_key"] for t in tasks), (
        "levelling must place EVERY task exactly once — a dropped task is a graph that looks smaller")


@pytest.mark.parametrize("tasks", INVALID_CYCLES)
def test_a_cycle_is_refused_and_not_drawn(tasks):
    found = g.problems(tasks)
    assert any("cycle" in p for p in found), found
    assert g.levels(tasks) == [], "a cyclic graph must not render a partial picture"


# ---------------------------------------------------------------------------------------------
# the levelling itself
# ---------------------------------------------------------------------------------------------
def test_a_chain_is_one_task_per_level():
    assert g.levels(CHAIN) == [["silver"], ["gold"]]


def test_a_fan_out_puts_the_children_on_one_level():
    assert g.levels(FAN_OUT) == [["ingest"], ["left", "right"]]


def test_a_fan_in_puts_the_join_after_both_parents():
    """The assertion the wireframe F2 makes: `join` is below `a` AND `b`, not beside one of them."""
    drawn = g.levels(FAN_IN)
    assert drawn[-1] == ["join"]
    assert set(drawn[0]) == {"a", "b"}


def test_a_diamond_puts_the_join_after_both_branches():
    assert g.levels(DIAMOND) == [["a"], ["b", "c"], ["d"]]


def test_independent_tasks_are_one_level():
    assert g.levels(INDEPENDENT) == [["a", "b", "c"]]


def test_the_order_within_a_level_is_the_input_order():
    """Not sorted, not a set: a graph that reshuffles between renders reads as a live diagram when it is
    a static picture."""
    tasks = [task("zeta"), task("alpha"), task("mu")]
    assert g.levels(tasks) == [["zeta", "alpha", "mu"]]


def test_a_level_index_covers_every_key():
    index = g.task_level_index(DIAMOND)
    assert index == {"a": 0, "b": 1, "c": 1, "d": 2}


# ---------------------------------------------------------------------------------------------
# each rule, and the sentence it produces
# ---------------------------------------------------------------------------------------------
def test_no_tasks_is_refused_with_the_alternative():
    found = g.problems([])
    assert found and "at least one task" in found[0]


def test_a_missing_key_names_the_position():
    found = g.problems([{"notebook_path": "/Users/me/x"}])
    assert any("task 1 has no task_key" in p for p in found), found


def test_a_duplicate_key_is_named():
    found = g.problems([task("silver"), task("silver")])
    assert any("used twice" in p and "silver" in p for p in found), found


def test_a_bad_key_character_is_named():
    found = g.problems([task("bad key!")])
    assert any("letters, digits" in p for p in found), found


def test_two_task_types_is_refused():
    found = g.problems([task("both", pipeline_id="abc")])
    assert any("exactly one" in p for p in found), found


def test_no_task_type_names_the_options():
    found = g.problems([{"task_key": "empty"}])
    assert any("no task type" in p and "notebook_path" in p for p in found), found


def test_a_missing_dependency_is_named_with_its_near_miss():
    """[E-25] The commonest graph error: a renamed task and a forgotten dependency."""
    found = g.problems([task("silver"), task("gold", ["Silver"])])
    assert any("did you mean 'silver'" in p for p in found), found


def test_a_missing_dependency_with_no_near_miss_does_not_invent_one():
    found = g.problems([task("silver"), task("gold", ["platinum"])])
    assert any("'platinum'" in p for p in found), found
    assert not any("did you mean" in p for p in found), found


def test_every_problem_is_reported_not_only_the_first():
    """An agent that fixes one error per turn spends five turns on a graph it could fix in one."""
    found = g.problems([
        {"task_key": "a", "notebook_path": "/x"},                 # key 'a' ok, type ok
        {"task_key": "a", "notebook_path": "/x"},                 # duplicate
        {"task_key": "c"},                                        # no type
    ])
    assert len(found) >= 2, found


def test_a_cycle_is_named_as_a_path():
    """`a -> b -> a` is actionable; "a cycle exists" is not."""
    found = [p for p in g.problems(TWO_CYCLE) if "cycle" in p]
    assert found
    assert "\u2192" not in found[0]  # the sentence uses an ASCII arrow, not a glyph
    assert "a" in found[0] and "b" in found[0]


def test_a_long_cycle_names_the_tasks_in_it():
    found = [p for p in g.problems(LONG_CYCLE) if "cycle" in p][0]
    for key in ("a", "b", "c"):
        assert key in found, f"{key} is part of the cycle and must be named: {found}"
    assert "lonely" not in found, "a task outside the cycle must not be blamed for it"


def test_the_cycle_does_not_hang_on_a_large_graph():
    """`O(v + e)`: 500 tasks in a chain plus one edge closing it. A per-node scan would not finish."""
    tasks = [task(f"t{i}", [f"t{i - 1}"] if i else []) for i in range(500)]
    tasks.append(task("t0", ["t499"]))
    cycle = g.find_cycle(tasks)
    assert cycle and cycle[0] == cycle[-1]


def test_validate_raises_one_exception_carrying_every_sentence():
    with pytest.raises(g.TaskProblem) as caught:
        g.validate([task("a"), task("a")])
    message = str(caught.value)
    assert "used twice" in message


def test_validate_passes_a_valid_graph_silently():
    g.validate(DIAMOND)


def test_describe_reads_as_a_person_would_say_it():
    assert g.describe(CHAIN) == "2 tasks in 2 levels"
    assert g.describe(INDEPENDENT) == "3 tasks, all independent"
    assert g.describe([]) == "no tasks"
    assert "cycle" in g.describe(TWO_CYCLE)


def test_too_many_tasks_is_refused_by_the_platform_limit():
    tasks = [task(f"t{i}") for i in range(g.MAX_TASKS + 1)]
    found = g.problems(tasks)
    assert any("at most" in p for p in found), found


# ---------------------------------------------------------------------------------------------
# the parity: the app's copy and the tool's copy are the same rule
# ---------------------------------------------------------------------------------------------
def test_the_app_and_the_tool_agree_on_every_shape():
    """`api.domain.jobs` imports this module by path; this test is what stops a second copy appearing.

    If `api.domain.jobs` ever grows its own levelling, the assertions below still pass — but
    `test_jobs_domain.py::the_app_levels_what_the_tool_validated` fails, which is the guard that
    matters."""
    from api.domain import jobs as domain

    for tasks in VALID:
        assert domain.task_levels(tasks) == g.levels(tasks), tasks
        assert domain.task_graph_problem(tasks) is None, tasks
    for tasks in INVALID_CYCLES:
        assert domain.task_levels(tasks) == [], tasks
        assert domain.task_graph_problem(tasks), tasks
