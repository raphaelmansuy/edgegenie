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

#: A SQL cell may run for ten minutes. The request that starts it returns at once and the client polls
#: (`services/sql_run_service.py`), so no single HTTP request is held open. Past this a query belongs in a
#: job, and the result says so rather than leaving a spinner forever.
MAX_RUN_SECONDS = 600.0
#: Databricks' own `display()` shows the first 1,000 rows and says so; so does this.
MAX_ROWS = 1000
#: An engine error carries line and position pointers that are the whole point of the message. Four
#: hundred characters cut those off; four thousand keeps a stack of Spark analysis errors whole.
MAX_ERROR_CHARS = 4000


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
    #: One type name per column, lower case ("int", "string", "decimal"), for alignment and the header.
    types: list[str] = field(default_factory=list)
    #: The full type text per column ("ARRAY<INT>", "STRUCT<x: INT, y: STRING>"). Only kept when some column
    #: is an array, map or struct: it is what lets the UI show their values as values.
    type_texts: list[str] = field(default_factory=list)
    #: What the cell produced, in the order it produced it: `text` (stdout/stderr), `table`, `image`, `html`.
    #: Present for Python. The flat fields above stay filled so a client that predates this still works.
    outputs: list[dict[str, Any]] = field(default_factory=list)
    #: The widgets the session has after this cell ran. None: this run did not say (SQL, or a one-shot run).
    #: An empty list is a statement: there are none.
    widgets: list[dict[str, Any]] | None = None
    #: When it finished (UTC, ISO 8601) and who asked: Databricks prints both under the cell.
    finished_at: str = ""
    ran_by: str = ""

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"state": self.state.value, "seconds": round(self.seconds, 2)}
        # With ordered `outputs` the flat fields would repeat the same rows and the same PNGs, and the
        # response would be twice as large for nothing. A client reads one or the other.
        flat = not self.outputs
        if flat and self.columns:
            out["columns"] = self.columns
            out["rows"] = self.rows
            out["truncated"] = self.truncated
            if self.types:
                out["types"] = self.types
            if self.type_texts:
                out["typeTexts"] = self.type_texts
        if flat and self.total_rows is not None:
            out["totalRows"] = self.total_rows
        if self.error:
            out["error"] = self.error
        if self.statement:
            out["statement"] = self.statement
        if self.warehouse:
            out["warehouse"] = self.warehouse
        if flat and self.output:
            out["output"] = self.output
        if flat and self.images:
            out["images"] = self.images
        if self.outputs:
            out["outputs"] = self.outputs
        if self.widgets is not None:
            out["widgets"] = self.widgets
        if self.finished_at:
            out["finishedAt"] = self.finished_at
        if self.ran_by:
            out["ranBy"] = self.ran_by
        return out


#: Languages this app can actually execute. A Python cell needs a cluster and a runtime; a SQL cell
#: needs a warehouse, which every workspace has. Pretending otherwise is the inert-control bug.
RUNNABLE_LANGUAGES = frozenset({"sql"})
#: Column types whose values are shown as nested values.
NESTED_TYPES = frozenset({"array", "map", "struct"})

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


_SQL_MAGIC = re.compile(r"^[ \t]*%sql\b[ \t]*\n?", re.IGNORECASE)


def sql_statement(source: str) -> str:
    """The SQL to send: the cell without its `%skip` and `%sql` directive lines.

    `%sql` in a Python notebook is a *marker*, not SQL. `is_runnable` accepts it, so it must also be
    removed before the text reaches the warehouse; otherwise the engine answers with a syntax error at
    `%sql` for a cell that was fine.
    """
    _, body = without_skip(source or "")
    body = body.lstrip("\n")
    return _SQL_MAGIC.sub("", body, count=1).strip()


def split_statements(text: str) -> list[str]:
    """Split a SQL cell into its statements at top-level `;`.

    A `;` inside a quoted string, a backtick name, a `--` comment or a `/* */` comment is not a
    separator. A Databricks SQL script (`BEGIN ... END`) is one statement whose body holds its own `;`,
    so it is not split. Pieces with nothing but comments or blanks are dropped.
    """
    text = text or ""
    if re.match(r"\s*begin\b", text, re.IGNORECASE):
        return [text.strip()] if text.strip() else []
    out: list[str] = []
    buf: list[str] = []
    has_code = False
    quote = ""
    i, n = 0, len(text)

    def flush() -> None:
        nonlocal buf, has_code
        piece = "".join(buf).strip()
        if piece and has_code:
            out.append(piece)
        buf, has_code = [], False

    while i < n:
        c = text[i]
        if quote:
            buf.append(c)
            if c == "\\" and quote != "`" and i + 1 < n:
                buf.append(text[i + 1])
                i += 2
                continue
            if c == quote:
                quote = ""
            i += 1
            continue
        if c in "'\"`":
            quote = c
            has_code = True
            buf.append(c)
        elif text.startswith("--", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            buf.append(text[i:j])
            i = j
            continue
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            buf.append(text[i:j])
            i = j
            continue
        elif c == ";":
            flush()
        else:
            if not c.isspace():
                has_code = True
            buf.append(c)
        i += 1
    flush()
    return out


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
    schema = (manifest.get("schema") or {}).get("columns", [])
    columns = [c.get("name", "") for c in schema]
    types = [str(c.get("type_name") or "").lower() for c in schema]
    nested = any(t in NESTED_TYPES for t in types)
    type_texts = [str(c.get("type_text") or "") for c in schema] if nested else []
    data = result.get("data_array") or []
    total = result.get("row_count") or manifest.get("total_row_count")
    statement = payload.get("statement") or ""

    if state == "SUCCEEDED":
        # The engine's own `truncated` flag wins: `row_limit` cuts the result and the total may not say so.
        cut = bool(manifest.get("truncated")) or bool(total is not None and len(data) < int(total))
        return RunResult(
            state=RunState.SUCCEEDED, seconds=waited, columns=columns, types=types if any(types) else [],
            type_texts=type_texts,
            rows=[[(None if v is None else str(v)) for v in row] for row in data],
            truncated=cut, statement=statement,
            total_rows=int(total) if total is not None else len(data),
            # A statement with no result set (CREATE, USE, SET) is "OK" in Databricks.
            # Without this the cell said "done" and showed nothing, which reads as "did it run?".
            output="" if columns else "OK",
        )
    if state in {"PENDING", "QUEUED", "RUNNING"}:
        # `QUEUED` belongs here ([R-29], `[F-15]`). A statement spends real time queued on a busy
        # warehouse — that is the normal case for a large query on a shared SQL endpoint — and it used
        # to fall through to the failure branch, so the user saw a red failure whose "reason" was
        # "the warehouse reported QUEUED": a state that means *not yet*.
        return RunResult(
            state=RunState.RUNNING, seconds=waited, statement=statement,
            error=(
                f"still running after {waited:.0f}s. It was cancelled at the app's "
                f"{MAX_RUN_SECONDS / 60:.0f}-minute limit; run it as a job for anything longer."
            ),
        )
    if state == "CANCELED" or state == "CANCELLED":
        return RunResult(state=RunState.CANCELLED, seconds=waited, statement=statement,
                         error="cancelled before it finished")
    if state == "FAILED":
        message = ((status.get("error") or {}).get("message") or "").strip()
        return RunResult(
            state=RunState.FAILED, seconds=waited, statement=statement,
            error=message[:MAX_ERROR_CHARS] or "the warehouse reported FAILED without a message",
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


def sql_params(statement: str) -> list[str]:
    """The named parameters (`:name`) a statement uses, in order, each once.

    A marker is a colon followed by a name, not preceded by a word character or another colon (so `a::int` and
    JSON paths like `col:field` are not parameters), and not inside a string, a quoted name, or a comment.
    """
    names: list[str] = []
    i, n = 0, len(statement)
    while i < n:
        c = statement[i]
        if c in "'\"`":
            q, i = c, i + 1
            while i < n:
                if statement[i] == "\\" and q != "`":
                    i += 2
                    continue
                if statement[i] == q:
                    if i + 1 < n and statement[i + 1] == q:    # a doubled quote is a quote
                        i += 2
                        continue
                    break
                i += 1
            i += 1
        elif statement.startswith("--", i):
            i = statement.find("\n", i)
            i = n if i < 0 else i
        elif statement.startswith("/*", i):
            end = statement.find("*/", i + 2)
            i = n if end < 0 else end + 2
        elif c == ":" and i + 1 < n and (statement[i + 1].isalpha() or statement[i + 1] == "_") \
                and not (i > 0 and (statement[i - 1].isalnum() or statement[i - 1] in "_:")):
            j = i + 1
            while j < n and (statement[j].isalnum() or statement[j] == "_"):
                j += 1
            if statement[i + 1:j] not in names:
                names.append(statement[i + 1:j])
            i = j
        else:
            i += 1
    return names
