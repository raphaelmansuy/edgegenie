#!/usr/bin/env python3
"""The task graph: validation and levelling, pure and total. No I/O, no SDK, no environment.

Two questions, one algorithm each, and both are asked twice — by the tool server before it calls the
platform (spec 014 [TOOL-3]) and by the app when it renders a job (spec 014 [JOB-3]). The tool server is
a separate process and cannot import `api.domain`, so the rule lives here, in a module that imports
nothing but the standard library, and `tests/test_job_graph.py` holds both callers to one table of
shapes (`[RB-5]`).

Why this is a module and not three functions inside the 1 815-line tool server: a module can be imported
by a test without importing `mcp`, starting no transport and reading no environment. That is what makes
the table below possible.

The rules, each of which the platform enforces later with a `400` that says much less:

  1. at least one task
  2. a task_key is present, well-formed and UNIQUE
  3. every depends_on names a task in the same list
  4. exactly one task type per task
  5. no cycle

Rules 1-4 are local facts. Rule 5 is the one that needs the graph, so it is `O(v + e)` by Kahn's
algorithm rather than a scan per node — the same function is called on whatever a model sent, and a model
that sends 500 tasks is not hypothetical (spec 014 [06 §6]).

This file is duplicated in no other language: `api/domain/jobs.py` imports it by path for its own copy of
`task_levels`, so the page and the validator cannot disagree about what "level 2" means.
"""
from __future__ import annotations

import re

#: The task types a job tool may build. Each is a KEY in a task body, and exactly one may be present.
#: `spark_python_task` is deliberately absent: this product writes notebooks, and a `.py` file with a
#: notebook header deploys as a notebook (spec 013's packaging test proved that the hard way).
TASK_TYPES: tuple[str, ...] = ("notebook_path", "python_file", "sql_file", "pipeline_id", "job_id")

#: How a task type becomes the platform's field. `notebook_path` is nested inside `notebook_task`, which
#: is why a "task type" here is not simply a key of the task body.
TASK_TYPE_FIELD: dict[str, str] = {
    "notebook_path": "notebook_task.notebook_path",
    "python_file": "spark_python_task.python_file",
    "sql_file": "sql_task.file.path",
    "pipeline_id": "pipeline_task.pipeline_id",
    "job_id": "run_job_task.job_id",
}

#: The platform's own limit for a task_key's characters is looser than this; a key that needs escaping in
#: a URL or a log line is not a key an agent should be allowed to invent.
TASK_KEY = re.compile(r"^[A-Za-z0-9_-]{1,100}$")

MAX_TASKS = 100


class TaskProblem(ValueError):
    """A graph the platform would refuse, with a sentence that says what to change.

    It is a `ValueError` so that a router maps it to 422 without a second table, and so that the tool
    server's `except ValueError` path already catches it.
    """


def _key_of(task: dict, index: int) -> str:
    """The key as the model meant it, or a placeholder that names the position.

    Never raises: a missing key is reported by `problems()` as a sentence, and a placeholder lets every
    other check still run so a model gets ALL its mistakes in one turn rather than one per turn.
    """
    raw = task.get("task_key")
    return raw if isinstance(raw, str) and raw else f"<task {index + 1}>"


def _type_of(task: dict) -> str:
    """The one task type present, or '' when none/many. `problems()` explains which."""
    present = [t for t in TASK_TYPES if task.get(t)]
    return present[0] if len(present) == 1 else ""


def problems(tasks: list[dict] | None) -> list[str]:
    """Every problem with this graph, as sentences. Empty means the platform will accept it.

    **All** problems, not the first: an agent that fixes one error per turn spends five turns on a graph
    it could have fixed in one. The order is the order a person would check them.
    """
    out: list[str] = []
    if not tasks:
        return ["no tasks given: a job needs at least one task"]

    if len(tasks) > MAX_TASKS:
        out.append(f"a job has at most {MAX_TASKS} tasks; this one has {len(tasks)}")

    keys: list[str] = []
    for i, task in enumerate(tasks):
        if not isinstance(task, dict):
            out.append(f"task {i + 1} is not an object; each task is "
                       "{'task_key': ..., 'notebook_path': ...}")
            continue
        key = _key_of(task, i)
        keys.append(key)
        raw = task.get("task_key")
        if not isinstance(raw, str) or not raw:
            out.append(f"task {i + 1} has no task_key; every task needs one, and it is how other "
                       "tasks depend on it")
        elif not TASK_KEY.match(raw):
            out.append(f"task_key {raw!r} must be letters, digits, underscores or hyphens (1-100 "
                       "characters)")

        present = [t for t in TASK_TYPES if task.get(t)]
        if not present:
            out.append(f"task {key!r} has no task type; give exactly one of "
                       f"{', '.join(TASK_TYPES)}")
        elif len(present) > 1:
            out.append(f"task {key!r} has {len(present)} task types ({', '.join(present)}); "
                       "the platform accepts exactly one")

    seen: set[str] = set()
    for key in keys:
        if key in seen:
            out.append(f"task_key {key!r} is used twice; task keys must be unique within a job")
        seen.add(key)

    known = set(keys)
    for task in tasks:
        if not isinstance(task, dict):
            continue
        key = _key_of(task, 0)
        deps = task.get("depends_on") or []
        if not isinstance(deps, list):
            out.append(f"task {key!r}: depends_on must be a list of task keys")
            continue
        for dep in deps:
            if dep in known:
                continue
            # A near-miss is the commonest graph error: a model renames a task and forgets a dependency,
            # or capitalises one. Naming the candidate fixes it in the same turn (spec 014 [E-25]).
            match = _case_insensitive(dep, known)
            out.append(f"task {key!r} depends on {dep!r}, which is not a task"
                       + (f"; did you mean {match!r}?" if match else ""))

    cycle = find_cycle(tasks)
    if cycle:
        out.append("the dependencies form a cycle: " + " -> ".join(cycle)
                   + "; a job cannot wait for itself")
    return out


def _case_insensitive(needle: object, haystack: set[str]) -> str | None:
    if not isinstance(needle, str):
        return None
    low = needle.lower()
    matches = [h for h in haystack if h.lower() == low]
    return matches[0] if len(matches) == 1 else None


def validate(tasks: list[dict] | None) -> None:
    """Raise `TaskProblem` naming every problem, or return.

    One exception carrying every sentence, rather than one per problem, because the caller is a tool
    that returns one string to a model and the model fixes it best with all of it.
    """
    found = problems(tasks)
    if found:
        raise TaskProblem("; ".join(found))


# ---------------------------------------------------------------------------------------------
# the graph
# ---------------------------------------------------------------------------------------------
def _edges(tasks: list[dict]) -> tuple[list[str], dict[str, list[str]]]:
    """(keys in input order, adjacency key -> [dependency keys]). Dangling keys are dropped: `problems()`
    has already reported them, and levelling must not crash on a graph it is about to refuse."""
    keys: list[str] = []
    deps: dict[str, list[str]] = {}
    for i, task in enumerate(tasks):
        if not isinstance(task, dict):
            continue
        key = _key_of(task, i)
        keys.append(key)
        deps[key] = [d for d in (task.get("depends_on") or []) if isinstance(d, str)]
    return keys, deps


def find_cycle(tasks: list[dict]) -> list[str]:
    """One cycle, as the path that closes it, or []. `O(v + e)`.

    Depth-first with a colour map, which is the cheapest way to name the cycle rather than only detect
    it — and naming it is the whole point: "a cycle exists" leaves a model guessing which edge to remove.
    """
    keys, deps = _edges(tasks)
    WHITE, GREY, BLACK = 0, 1, 2
    colour = dict.fromkeys(keys, WHITE)
    stack: list[str] = []

    def visit(key: str) -> list[str]:
        colour[key] = GREY
        stack.append(key)
        for dep in deps.get(key, ()):
            if dep not in colour:
                continue                      # dangling: reported elsewhere
            if colour[dep] == GREY:
                at = stack.index(dep)
                return stack[at:] + [dep]     # the cycle, starting and ending at the same task
            if colour[dep] == WHITE:
                found = visit(dep)
                if found:
                    return found
        stack.pop()
        colour[key] = BLACK
        return []

    for key in keys:
        if colour.get(key) == WHITE:
            found = visit(key)
            if found:
                return found
    return []


def levels(tasks: list[dict]) -> list[list[str]]:
    """The tasks grouped by dependency depth: level 0 has no dependencies, level n depends only on
    levels < n. `O(v + e)` by Kahn's algorithm.

    **A cycle returns `[]`**, never a partial graph: rendering four of five tasks of a cyclic job would
    look like a job that is merely small. `problems()` is what reports the cycle; this function is what
    draws, and a drawing of an invalid graph is worse than none (spec 014 [JOB-3]).

    Order within a level is the input's order, so a graph does not shuffle between renders.
    """
    keys, deps = _edges(tasks)
    if not keys:
        return []
    remaining = {k: [d for d in deps.get(k, []) if d in deps] for k in keys}
    out: list[list[str]] = []
    done: set[str] = set()
    while len(done) < len(keys):
        ready = [k for k in keys if k not in done and all(d in done for d in remaining[k])]
        if not ready:
            return []                          # a cycle: nothing is ready and nothing is done
        out.append(ready)
        done.update(ready)
    return out


def task_level_index(tasks: list[dict]) -> dict[str, int]:
    """task_key -> its level. `O(v + e)`, and total: every key of a valid graph appears."""
    index: dict[str, int] = {}
    for depth, keys in enumerate(levels(tasks)):
        for key in keys:
            index[key] = depth
    return index


def describe(tasks: list[dict]) -> str:
    """One line a person reads: `3 tasks in 2 levels`. For a tool result and a block's note."""
    if not tasks:
        return "no tasks"
    found = levels(tasks)
    if not found:
        return f"{len(tasks)} tasks, with a cycle"
    noun = "task" if len(tasks) == 1 else "tasks"
    if len(found) == 1:
        return f"{len(tasks)} {noun}, all independent"
    return f"{len(tasks)} {noun} in {len(found)} levels"
