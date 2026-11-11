"""The vocabulary of a scheduled object, and the graph it runs. Pure and total. No I/O, no async, no SDK.

Four things live here because they are *rules*, not plumbing:

* **the state words** — what `TERMINATED` + `FAILED` means to a person, and why `TERMINATED` alone is not
  an answer. A job run carries `life_cycle_state` (always present) and `result_state` (present only when
  terminal), and only the pair distinguishes success from failure. A pipeline carries its own `state`
  (`IDLE`) and a list of updates with their own (`COMPLETED`, `FAILED`) — and `IDLE` means both "never
  run" and "the last run failed". Reading the convenient field is the defect 013 recorded as [RB-12] for
  Lakebase; this is the same rule for two more object types (spec 014 [PIPE-5], [UI-8]).
* **which states are active** — the six words for which a Cancel control must exist, and the terminal
  words after which a Repair becomes possible. One predicate, so a component cannot invent a seventh.
* **the duration arithmetic** — from two timestamps, with a missing one returning None rather than 0.
  A zero duration reads as "instant" and a queued task was not instant (spec 014 [E-12]).
* **the graph** — imported from `tools/job_graph.py` rather than re-implemented, so the page draws what
  the tool validated (`[RB-5]`).

`web/src/domain/jobs.ts` mirrors the tables, and `web/src/domain/jobs-table.json` holds the cases both are
tested against. `tests/test_jobs_domain.py` reads that fixture, so a word changed on one side alone fails
one test that names the row.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

#: The Jobs API's `life_cycle_state`, verbatim. Every value is a position in the machine, not a verdict.
RUN_LIFE_CYCLE: tuple[str, ...] = (
    "PENDING", "QUEUED", "RUNNING", "TERMINATING", "TERMINATED",
    "SKIPPED", "INTERNAL_ERROR", "BLOCKED", "WAITING_FOR_RETRY",
)

#: `result_state`, which the platform documents as *only* available in a terminal lifecycle state.
RUN_RESULT: tuple[str, ...] = (
    "SUCCESS", "FAILED", "TIMEDOUT", "CANCELED", "MAXIMUM_CONCURRENT_RUNS_REACHED",
    "UPSTREAM_CANCELED", "UPSTREAM_FAILED", "EXCLUDED", "SUCCESS_WITH_FAILURES", "DISABLED",
)

#: A pipeline's own state. `IDLE` is ambiguous on purpose and that is the whole problem: it means both
#: "nothing is running" and "the last update failed".
PIPELINE_STATE: tuple[str, ...] = (
    "DEPLOYING", "STARTING", "RUNNING", "STOPPING", "DELETED", "RECOVERING", "FAILED",
    "RESETTING", "IDLE",
)

#: An update's state. This is the one that answers "did the last run work?".
UPDATE_STATE: tuple[str, ...] = (
    "QUEUED", "WAITING_FOR_RESOURCES", "INITIALIZING", "RESETTING", "CREATING_FLOW",
    "RUNNING", "IDLE", "COMPLETED", "FAILED", "CANCELED",
)

#: Life cycle states in which a run is doing something, and for which Cancel must be offered.
#: `BLOCKED` and `WAITING_FOR_RETRY` are included deliberately: a run waiting on a dependency is still
#: holding a slot the user may want back.
ACTIVE: frozenset[str] = frozenset({
    "PENDING", "QUEUED", "RUNNING", "TERMINATING", "BLOCKED", "WAITING_FOR_RETRY",
})

#: States after which nothing will change, so a Repair is possible and a poll can stop.
TERMINAL: frozenset[str] = frozenset({"TERMINATED", "SKIPPED", "INTERNAL_ERROR"})

#: results that mean "the work the user asked for did not happen". `SUCCESS_WITH_FAILURES` is here on
#: purpose: a job whose child runs failed is not a success for a person reading a dashboard.
FAILED_RESULTS: frozenset[str] = frozenset({
    "FAILED", "TIMEDOUT", "CANCELED", "MAXIMUM_CONCURRENT_RUNS_REACHED",
    "UPSTREAM_CANCELED", "UPSTREAM_FAILED", "EXCLUDED", "DISABLED", "SUCCESS_WITH_FAILURES",
})

#: An update in progress, for which Stop must be offered.
ACTIVE_UPDATE: frozenset[str] = frozenset({
    "QUEUED", "WAITING_FOR_RESOURCES", "INITIALIZING", "RESETTING", "CREATING_FLOW", "RUNNING",
})

#: The words a page may show. An unknown value is returned verbatim and lowercased, never mapped to a
#: synonym: a plausible paraphrase of a state nobody has seen is worse than the platform's own word.
RUN_WORDS: dict[str, str] = {
    "SUCCESS": "succeeded",
    "FAILED": "failed",
    "TIMEDOUT": "timed out",
    "CANCELED": "canceled",
    "UPSTREAM_FAILED": "upstream failed",
    "UPSTREAM_CANCELED": "upstream canceled",
    "MAXIMUM_CONCURRENT_RUNS_REACHED": "busy",
    "SUCCESS_WITH_FAILURES": "succeeded with failures",
    "EXCLUDED": "excluded",
    "DISABLED": "disabled",
    "PENDING": "pending",
    "QUEUED": "queued",
    "RUNNING": "running",
    "TERMINATING": "finishing",
    "BLOCKED": "blocked",
    "WAITING_FOR_RETRY": "waiting to retry",
    "SKIPPED": "skipped",
    "INTERNAL_ERROR": "platform error",
    "TERMINATED": "finished",
}

UPDATE_WORDS: dict[str, str] = {
    "QUEUED": "queued",
    "WAITING_FOR_RESOURCES": "waiting for compute",
    "INITIALIZING": "starting",
    "RESETTING": "resetting",
    "CREATING_FLOW": "creating flows",
    "RUNNING": "running",
    "IDLE": "idle",
    "COMPLETED": "succeeded",
    "FAILED": "failed",
    "CANCELED": "canceled",
}

PIPELINE_WORDS: dict[str, str] = {
    "DEPLOYING": "deploying",
    "STARTING": "starting",
    "RUNNING": "running",
    "STOPPING": "stopping",
    "DELETED": "deleted",
    "RECOVERING": "recovering",
    "FAILED": "failed",
    "RESETTING": "resetting",
    "IDLE": "idle",
}

#: The tone a page paints, from the same word. `good`/`busy`/`bad`/`quiet`.
RUN_TONES: dict[str, str] = {
    "succeeded": "good",
    "running": "busy",
    "pending": "busy",
    "queued": "busy",
    "finishing": "busy",
    "waiting to retry": "busy",
    "blocked": "busy",
    "starting": "busy",
    "failed": "bad",
    "timed out": "bad",
    "upstream failed": "bad",
    "platform error": "bad",
    "succeeded with failures": "bad",
    "canceled": "quiet",
    "upstream canceled": "quiet",
    "skipped": "quiet",
    "excluded": "quiet",
    "disabled": "quiet",
    "finished": "quiet",
    "busy": "busy",
}


class JobError(ValueError):
    """A malformed reference or a rule the platform would refuse. Maps to HTTP 422."""


# ---------------------------------------------------------------------------------------------
# identity
# ---------------------------------------------------------------------------------------------
def job_id(value: object) -> int:
    """A job or run id, as the platform's integer.

    The API answers with a JSON number, a URL carries a string, and a tool result may carry either. One
    function so a tab opened from a link and a tab opened from a transcript are the same tab
    (spec 014 [JOB-1]): `"812345678901"` and `812345678901` are one object.
    """
    if isinstance(value, bool):
        raise JobError("a job id is a number, not a boolean")
    if isinstance(value, int):
        if value <= 0:
            raise JobError(f"a job id is a positive number; got {value}")
        return value
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            number = int(text)
            if number > 0:
                return number
        raise JobError(f"a job id is a number; got {value!r}. "
                       "A job's name is not its id — open the job from the Data tab.")
    raise JobError(f"a job id is a number; got {type(value).__name__}")


def pipeline_id(value: object) -> str:
    """A pipeline id, which is a UUID. A *name* is refused with the alternative, because a `404` for a
    name reads as a permission problem (spec 014 [E-17], the class 013's [RB-12] recorded)."""
    text = str(value or "").strip()
    if not text:
        raise JobError("a pipeline is named by its id, for example 'f0e1c4a2-…-9a2b'")
    if _looks_like_name(text):
        raise JobError(
            f"{text!r} looks like a pipeline name; a pipeline is identified by its UUID. "
            "Call dbx_list_pipelines to find the id.")
    return text


def _looks_like_name(text: str) -> bool:
    """A UUID is 36 characters of hex and hyphens; anything else is treated as a name."""
    if len(text) == 36 and text.count("-") == 4:
        return False
    return not all(c in "0123456789abcdef-" for c in text.lower())


# ---------------------------------------------------------------------------------------------
# the words
# ---------------------------------------------------------------------------------------------
def run_word(life_cycle: str | None, result: str | None = None) -> str:
    """The one word a page shows for a run.

    **While the life cycle is active, the LIFE CYCLE decides** ([R-28], `[F-14]`). `result_state` is
    documented as terminal-only, but the API does send it on `TERMINATING`, and reading it whenever it
    is present produced 24 of 60 `ACTIVE × RESULT` combinations showing a finished word — `succeeded`,
    `failed`, `timed out`, `canceled` — while `can_cancel()` was simultaneously true. A page then showed
    a green "succeeded" *and* an enabled Cancel for one run.

    Once the run is terminal, `result` is the answer, because only it distinguishes a success from a
    failure inside `TERMINATED` (`SKIPPED` and `INTERNAL_ERROR` carry their own meaning).

    An unknown value comes back **verbatim, lowercased**. A state nobody has seen is a fact; a cheerful
    synonym for it is a guess.
    """
    life = (life_cycle or "").upper()
    res = (result or "").upper()
    if life and life in ACTIVE:
        # A live run: the life cycle is the only honest field. `result` may be stale, may be the
        # previous attempt's, and may simply be early.
        return RUN_WORDS.get(life) or life.lower()
    if res:
        return RUN_WORDS.get(res) or res.lower()
    if life:
        return RUN_WORDS.get(life) or life.lower()
    return "unknown"


def update_word(state: str | None) -> str:
    if not state:
        return "unknown"
    return UPDATE_WORDS.get(state.upper(), str(state).lower())


def pipeline_word(state: str | None, last_update: str | None = None) -> str:
    """The one word a pipeline page shows, and the reason this function exists.

    A pipeline's own `state` is `IDLE` both when it has never run and when its last update **failed**.
    So the last update decides, and the pipeline's state is the fallback only when there is no update at
    all (spec 014 [PIPE-5]).
    """
    if last_update:
        return update_word(last_update)
    if state:
        return PIPELINE_WORDS.get(state.upper(), str(state).lower())
    return "unknown"


def tone(word: str) -> str:
    """A word's colour, from the same table the word came from."""
    return RUN_TONES.get(word, "quiet")


def is_active(life_cycle: str | None) -> bool:
    return (life_cycle or "").upper() in ACTIVE


def is_terminal(life_cycle: str | None) -> bool:
    return (life_cycle or "").upper() in TERMINAL


def is_failed(result: str | None) -> bool:
    return (result or "").upper() in FAILED_RESULTS


def update_is_active(state: str | None) -> bool:
    return (state or "").upper() in ACTIVE_UPDATE


def can_cancel(life_cycle: str | None) -> bool:
    """Whether a Cancel control belongs on screen. The platform documents cancellation as asynchronous,
    so this answers "is there something to cancel", not "will it stop now" (spec 014 [RUN-2], [E-8])."""
    return is_active(life_cycle)


def can_repair(result: str | None, life_cycle: str | None) -> bool:
    """Repair re-runs failed tasks of a FINISHED run. `rerun_tasks` on a live run is a `400`.

    Only `TERMINATED` qualifies ([E-26]). `SKIPPED` and `INTERNAL_ERROR` are terminal but the run never
    started, so a Repair button beside them offers to re-run nothing — measured before this guard:
    `SKIPPED + FAILED → can_repair == True`.
    """
    life = (life_cycle or "").upper()
    return life == "TERMINATED" and (result or "").upper() in ("FAILED", "TIMEDOUT")


# ---------------------------------------------------------------------------------------------
# time
# ---------------------------------------------------------------------------------------------
def duration_seconds(start_ms: int | None, end_ms: int | None, now_ms: int | None = None) -> int | None:
    """A duration in seconds, or None when it cannot be known.

    Three cases, and the third is the one that matters: an active run's duration is `now - start`, and a
    run with no start is **not** zero seconds (spec 014 [E-12]). The platform reports epoch milliseconds.
    """
    if end_ms and start_ms:
        return max(0, int((end_ms - start_ms) / 1000))
    if start_ms and now_ms and now_ms >= start_ms:
        return max(0, int((now_ms - start_ms) / 1000))
    return None


def describe_duration(seconds: int | None) -> str:
    """`1 m 42 s`, `38 s`, `—`. Never `0 s` for an unknown value."""
    if seconds is None:
        return "—"
    if seconds < 60:
        return f"{seconds} s"
    minutes, rest = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} m {rest:02d} s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes:02d} m"


# ---------------------------------------------------------------------------------------------
# the graph: imported, not re-implemented
# ---------------------------------------------------------------------------------------------
_GRAPH_FILE = Path(__file__).resolve().parents[2] / "tools" / "job_graph.py"

#: One module instance per process. Populated on first use so importing this package never touches a
#: file at import time (a test that only wants a word table pays nothing).
_GRAPH = None


def _graph():
    """`tools/job_graph.py`, imported by path.

    The tool server cannot import this package, and this package must not import the tool server's
    environment — so the module is loaded from its file, once, and both sides use the same code. Spec
    014's [RB-5] explains why a third top-level package is the worse answer.
    """
    global _GRAPH
    if _GRAPH is None:
        spec = importlib.util.spec_from_file_location("job_graph", _GRAPH_FILE)
        _GRAPH = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_GRAPH)
    return _GRAPH


def task_graph_problem(tasks: list[dict] | None) -> str | None:
    """The graph's problems as one sentence, or None. One string because it is shown in one place."""
    found = _graph().problems(tasks)
    return "; ".join(found) if found else None


def task_levels(tasks: list[dict]) -> list[list[str]]:
    """The tasks by dependency depth. `[]` for a cyclic graph: a partial picture reads as a small job."""
    return _graph().levels(tasks)


def validate_task_graph(tasks: list[dict] | None) -> None:
    """Raise `JobError` naming every problem, for a route that returns 422."""
    problem = task_graph_problem(tasks)
    if problem:
        raise JobError(problem)


# ---------------------------------------------------------------------------------------------
# what a tool result names, for the transcript
# ---------------------------------------------------------------------------------------------
def job_from_tool(name: str, args: str | None, result: str | None) -> int | None:
    """A job id from a tool call, or None.

    In the **result** first, because a create's identity is something the platform granted and the
    arguments only asked for a name. This is the same ordering 013's `touched()` uses for a Lakebase
    project, and for the same reason.
    """
    if not name.startswith("dbx_"):
        return None
    for text in (result, args):
        found = _json_field(text, "job_id")
        if found is not None:
            try:
                return job_id(found)
            except JobError:
                return None
    return None


def run_from_tool(name: str, args: str | None, result: str | None) -> int | None:
    if not name.startswith("dbx_"):
        return None
    for text in (result, args):
        found = _json_field(text, "run_id")
        if found is not None:
            try:
                return job_id(found)
            except JobError:
                return None
    return None


def pipeline_from_tool(name: str, args: str | None, result: str | None) -> str | None:
    if not name.startswith("dbx_"):
        return None
    for text in (result, args):
        found = _json_field(text, "pipeline_id")
        if isinstance(found, str) and found:
            return found
    return None


def _json_field(text: str | None, field: str) -> object | None:
    """One field of a possibly-truncated JSON object, without a full parse when it cannot succeed.

    A tool result is capped (spec 001), so a truncated blob must still yield its first field: the id is
    written before the payload by every tool in this server.
    """
    if not text:
        return None
    import json
    import re

    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        match = re.search(rf'"{field}"\s*:\s*"?([A-Za-z0-9_-]+)"?', text)
        return match.group(1) if match else None
    if isinstance(data, dict):
        return data.get(field)
    return None
