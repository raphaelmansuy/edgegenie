"""Run a cell and hand back its result. Pure: the shape of a run, not the running of it.

Spec 006 X1–X4. The largest gap against Databricks was that a notebook had no output: a cell could
not be run and had nowhere to put a result. This module defines what a run *is*, so the adapter can
be thin and the UI can render every outcome from one union instead of guessing.

Three rules, each learned from what a notebook user actually needs:
  - **a run is a value, not a side effect**: state, duration, row count, and either data or a reason;
  - **failure is a first-class outcome**, with the engine's own words — never "something went wrong";
  - **only what can be executed is executable**: a Python cell in this app cannot be run on a
    warehouse, and claiming it can would be the inert button all over again (00 P4).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

#: A cell run is bounded so the request cannot hang. A longer query belongs in a job, and the UI says
#: so rather than leaving a spinner forever.
MAX_WAIT_SECONDS = 50.0
MAX_ROWS = 200


class RunState(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RUNNING = "running"
    CANCELLED = "cancelled"
    REFUSED = "refused"      # we declined to run it at all, and said why
    #: The warehouse reported a state this build does not know. Distinct from `failed` on purpose: the
    #: engine never said it failed, so saying so would be a claim we cannot support ([R-29]).
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class RunResult:
    """One cell's execution. `columns`/`rows` are present only when there is data to show."""

    state: RunState
    seconds: float = 0.0
    columns: list[str] = field(default_factory=list)
    rows: list[list[str | None]] = field(default_factory=list)
    truncated: bool = False
    #: The engine's own message on failure, or our reason on a refusal. Never a generic sentence.
    error: str = ""
    #: For SQL, the statement that ran, so the user can copy it (a result without its query is a rumour).
    statement: str = ""
    #: Where it ran: a SQL warehouse's name, or (for Python) the compute and the identity it ran as.
    warehouse: str = ""
    #: Text a Python cell printed, plus its last expression's value. SQL has none.
    output: str = ""
    #: PNG plots as base64 (no `data:` prefix). Matplotlib figures the cell left open.
    images: list[str] = field(default_factory=list)
    #: Rows the engine reports having produced, when it says so and we only show the first page.
    total_rows: int | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"state": self.state.value, "seconds": round(self.seconds, 2)}
        if self.columns:
            out["columns"] = self.columns
            out["rows"] = self.rows
            out["truncated"] = self.truncated
        if self.total_rows is not None:
            out["totalRows"] = self.total_rows
        if self.error:
            out["error"] = self.error
        if self.statement:
            out["statement"] = self.statement
        if self.warehouse:
            out["warehouse"] = self.warehouse
        if self.output:
            out["output"] = self.output
        if self.images:
            out["images"] = self.images
        return out


#: Languages this app can actually execute. A Python cell needs a cluster and a runtime; a SQL cell
#: needs a warehouse, which every workspace has. Pretending otherwise is the inert-control bug.
RUNNABLE_LANGUAGES = frozenset({"sql"})

_LEADING_MAGIC = re.compile(r"^\s*%(\w+)\s*", re.MULTILINE)
_SKIP = re.compile(r"^\s*%skip\b[^\n]*\n?", re.IGNORECASE)


def without_skip(source: str) -> tuple[bool, str]:
    """Drop a leading `%skip` line. The flag is true when the directive was there.

    `%skip` leaves a cell out of Run all, Run above and Run below. Running the cell on its own
    executes what follows the directive, so the line must not be sent to the warehouse.
    """
    text = source or ""
    match = _SKIP.match(text)
    if not match:
        return False, text
    return True, text[match.end():]


def is_runnable(language: str, source: str) -> tuple[bool, str]:
    """Can this cell be executed here? Returns (yes, reason-if-no).

    The reason is written to be shown to a user: it names what would work instead.
    """
    skipped, body = without_skip(source or "")
    text = body.strip()
    if not text:
        return False, "this cell is only a %skip" if skipped else "this cell is empty"
    # A magic is the author's explicit statement of what the cell is, so it is read FIRST: `%sql` in a
    # Python notebook is the common Databricks spelling of a SQL cell, and answering "python needs a
    # cluster" to it would be both wrong and unhelpful.
    magic = _LEADING_MAGIC.search(text)
    if magic:
        if magic.group(1).lower() == "sql":
            return True, ""
        return False, f"%{magic.group(1)} cells need a cluster; only SQL runs on a warehouse here"
    lang = (language or "").lower()
    if lang not in RUNNABLE_LANGUAGES:
        return False, (
            f"{lang or 'this'} cells need a cluster. Ask the agent to run it, or write the query as "
            "SQL to run it here."
        )
    return True, ""


def result_from_statement(payload: dict[str, Any], *, waited: float) -> RunResult:
    """Turn a SQL Statement API response into a RunResult. The one place that knows that shape.

    Every branch names something a user can act on. A cancellation is not an error, an empty result
    is not a failure, and a long query says how long it ran rather than "timed out".
    """
    status = payload.get("status") or {}
    state = str(status.get("state") or "").upper()
    manifest = payload.get("manifest") or {}
    result = payload.get("result") or {}
    columns = [c.get("name", "") for c in (manifest.get("schema") or {}).get("columns", [])]
    data = result.get("data_array") or []
    total = result.get("row_count") or manifest.get("total_row_count")
    statement = payload.get("statement") or ""

    if state == "SUCCEEDED":
        return RunResult(
            state=RunState.SUCCEEDED, seconds=waited, columns=columns,
            rows=[[("" if v is None else str(v)) for v in row] for row in data],
            truncated=bool(total is not None and len(data) < int(total)),
            statement=statement, total_rows=int(total) if total is not None else len(data),
        )
    if state in {"PENDING", "QUEUED", "RUNNING"}:
        # `QUEUED` belongs here ([R-29], `[F-15]`). A statement spends real time queued on a busy
        # warehouse — that is the normal case for a large query on a shared SQL endpoint — and it used
        # to fall through to the failure branch, so the user saw a red failure whose "reason" was
        # "the warehouse reported QUEUED": a state that means *not yet*.
        return RunResult(
            state=RunState.RUNNING, seconds=waited, statement=statement,
            error=(
                f"still running after {waited:.0f}s. It was cancelled so the page stays responsive; "
                "run it as a job for anything longer."
            ),
        )
    if state == "CANCELED" or state == "CANCELLED":
        return RunResult(state=RunState.CANCELLED, seconds=waited, statement=statement,
                         error="cancelled before it finished")
    if state == "FAILED":
        message = ((status.get("error") or {}).get("message") or "").strip()
        return RunResult(
            state=RunState.FAILED, seconds=waited, statement=statement,
            error=message[:400] or "the warehouse reported FAILED without a message",
        )
    # A state this app does not know. NOT a failure: the engine never told us it failed, and reporting
    # one is a claim we cannot support ([R-29]). `UNRESOLVED` says what is true — the outcome is not
    # known to this build — and carries the platform's own word so a reader can look it up.
    return RunResult(
        state=RunState.UNRESOLVED, seconds=waited, statement=statement,
        error=(f"the warehouse reported {state or 'no state'}, which this version of the app does not "
               "know. The statement may have run; check it in the SQL editor before retrying."),
    )


def refused(reason: str) -> RunResult:
    """A cell we will not run. Not an error state: a state with a reason the user can act on."""
    return RunResult(state=RunState.REFUSED, error=reason)


class Clock:
    """A monotonic clock, injectable so a duration is testable without sleeping."""

    def __init__(self, now=time.monotonic) -> None:
        self._now = now

    def start(self) -> float:
        return self._now()

    def since(self, at: float) -> float:
        return max(0.0, self._now() - at)
