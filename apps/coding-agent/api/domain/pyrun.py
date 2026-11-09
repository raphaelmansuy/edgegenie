"""Running Python cells on serverless compute. Pure: what to run, and what a run's output means.

A Databricks App cannot run Python *as the signed-in user*: Apps user authorization has no jobs or
compute scope, so there is no token the app may hold that submits a run in the user's name. The only
thing the app can do is run it as **its own service principal**. That is a different identity with
different permissions, and it is the one fact this module is built around:

  - the plan runs ONLY cells the caller listed, never anything fetched from the workspace;
  - the result says, in words, where it ran and as whom (`WHERE`), so nobody mistakes it for their own;
  - who may ask is decided elsewhere (administrators only, `routers/api.py`), not here.

How a cell runs: a notebook cannot be handed source and return stdout, so one wrapper notebook is
generated. It executes the cells in order in one namespace (so a variable made by cell 2 exists in
cell 5), captures each cell's stdout, its last expression and any `display(df)` table, and returns one
JSON document through `dbutils.notebook.exit`. This module builds that notebook and reads that
document back; it never touches the network.
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass, field
from typing import Any

from .cellrun import RunResult, RunState, without_skip

#: Shown on every Python result. It is the whole point of the labelling: this did not run as you.
WHERE = "Serverless · as the app"

MAX_CELLS = 200
MAX_ROWS = 200
#: Per cell. A cell that prints a million lines gets its first and last lines, not a frozen page.
MAX_OUTPUT_CHARS = 20_000

_MAGIC = re.compile(r"^\s*%(\w+)[ \t]*(.*)$")
_PYTHON_MAGICS = frozenset({"python", "py"})


@dataclass(frozen=True, slots=True)
class PyCell:
    """One cell as the client holds it. `index` is its 0-based position in the notebook."""

    index: int
    language: str
    source: str


@dataclass(frozen=True, slots=True)
class Plan:
    """What to execute, and what to say about the cells that will not be."""

    #: (notebook index, python source) in notebook order: everything up to and including the target.
    steps: tuple[tuple[int, str], ...]
    #: Indexes whose output the caller asked for. The rest only run, to leave their variables behind.
    show: frozenset[int]
    #: Cells asked for that cannot run, with the reason in words.
    refused: dict[int, str] = field(default_factory=dict)


def python_source(language: str, source: str) -> tuple[str | None, str]:
    """The Python this cell contains, or (None, why not).

    A `%python` line makes a cell Python whatever the notebook's language is. Any other magic is the
    author saying what the cell is, so it is respected: `%sql` is a SQL cell (it runs on a warehouse,
    not here) and `%pip`/`%sh` cannot be run by `exec`.
    """
    skipped, rest = without_skip(source or "")
    text = (rest if skipped else (source or "")).strip("\n")
    if not text.strip():
        return None, "this cell is only a %skip" if skipped else "this cell is empty"
    first = text.lstrip().splitlines()[0]
    magic = _MAGIC.match(first)
    if magic:
        name = magic.group(1).lower()
        if name in _PYTHON_MAGICS:
            rest = text.lstrip().split("\n", 1)
            body = (magic.group(2) + ("\n" + rest[1] if len(rest) > 1 else "")).strip("\n")
            return (body, "") if body.strip() else (None, "this cell is empty")
        if name == "sql":
            return None, "this is a SQL cell; it runs on a SQL warehouse, not as Python"
        return None, (f"%{name} cells cannot run here. Install libraries in the notebook's own "
                      "environment, or ask the agent")
    if (language or "").lower() not in {"python", "py", ""}:
        return None, f"{language} cells do not run as Python"
    return text, ""


def plan(cells: list[PyCell], *, upto: int | None, show: set[int] | None = None) -> Plan:
    """Which cells to execute for a request.

    `upto` is the last cell to run (0-based); None means every cell. `show` is the cells whose output
    is wanted; None means all of the Python cells that run. Cells above the target that are not Python
    are skipped silently (they are another engine's, and `%pip` above is the author's own business);
    a *requested* cell that cannot run is refused with its reason.
    """
    last = len(cells) - 1 if upto is None else min(upto, len(cells) - 1)
    steps: list[tuple[int, str]] = []
    refused: dict[int, str] = {}
    for cell in cells:
        if cell.index > last:
            break
        skipped, _rest = without_skip(cell.source)
        # A %skip cell runs only when this request asked for it. In a batch it is omitted, and it
        # does not leave variables behind — that is what "skip" means.
        if skipped and not (show is not None and cell.index in show):
            continue
        body, why = python_source(cell.language, cell.source)
        if body is None:
            if show is not None and cell.index in show:
                refused[cell.index] = why
            continue
        steps.append((cell.index, body))
    shown = frozenset(i for i, _ in steps) if show is None else frozenset(show) - frozenset(refused)
    return Plan(steps=tuple(steps), show=shown, refused=refused)


# -- the wrapper notebook -----------------------------------------------------------------------

_WRAPPER = r'''# Databricks notebook source
import ast, base64, contextlib, io, json, traceback

_STEPS = json.loads(base64.b64decode("__STEPS__").decode("utf-8"))
_SHOW = set(json.loads(base64.b64decode("__SHOW__").decode("utf-8")))
_MAX_ROWS = __MAX_ROWS__
_MAX_CHARS = __MAX_CHARS__
_tables = []


def _clip(text):
    if len(text) <= _MAX_CHARS:
        return text
    half = _MAX_CHARS // 2
    return text[:half] + "\n... [%d characters not shown] ...\n" % (len(text) - _MAX_CHARS) + text[-half:]


def _as_table(value):
    """A Spark or pandas DataFrame as {columns, rows, total}, or None for anything else."""
    kind = type(value).__module__
    if hasattr(value, "collect") and hasattr(value, "columns") and hasattr(value, "limit"):
        rows = value.limit(_MAX_ROWS + 1).collect()
        cols = list(value.columns)
        data = [["" if v is None else str(v) for v in r] for r in rows[:_MAX_ROWS]]
        return {"columns": cols, "rows": data, "truncated": len(rows) > _MAX_ROWS}
    if kind.startswith("pandas") and hasattr(value, "head") and hasattr(value, "columns"):
        head = value.head(_MAX_ROWS)
        cols = [str(c) for c in head.columns]
        data = [["" if v is None else str(v) for v in row] for row in head.itertuples(index=False, name=None)]
        return {"columns": cols, "rows": data, "truncated": len(value) > _MAX_ROWS}
    return None


def display(value=None, *args, **kwargs):
    table = _as_table(value)
    if table is not None:
        _tables.append(table)
    elif value is not None:
        print(value if isinstance(value, str) else repr(value))


def displayHTML(html=None, *args, **kwargs):
    print("[HTML output is not shown here; open the notebook in Databricks to see it]")


def _frames(exc):
    """The traceback, from the user's cells only: the wrapper's own frames are noise."""
    lines = []
    for f in traceback.extract_tb(exc.__traceback__):
        if f.filename.startswith("<cell"):
            lines.append("  %s, line %d" % (f.filename.strip("<>"), f.lineno))
    return ("Traceback (cells only):\n" + "\n".join(lines) + "\n" if lines else "") + "".join(
        traceback.format_exception_only(type(exc), exc)).strip()


_results = []
_g = globals()
for _step in _STEPS:
    _i, _src = _step["i"], _step["src"]
    _tables.clear()
    _out = io.StringIO()
    _value = None
    _error = ""
    _name = "<cell %d>" % (_i + 1)
    try:
        _tree = ast.parse(_src, _name)
        _last = ast.Expression(_tree.body.pop().value) if _tree.body and isinstance(_tree.body[-1], ast.Expr) else None
        with contextlib.redirect_stdout(_out), contextlib.redirect_stderr(_out):
            exec(compile(_tree, _name, "exec"), _g)
            if _last is not None:
                _v = eval(compile(_last, _name, "eval"), _g)
                _t = _as_table(_v)
                if _t is not None:
                    _tables.append(_t)
                elif _v is not None:
                    _value = repr(_v)
    except BaseException as _exc:  # a cell may raise anything, including SystemExit
        _error = _frames(_exc)
    _entry = {"i": _i, "ok": not _error}
    if _error:
        _entry["error"] = _clip(_error)
    if _i in _SHOW:
        _entry["stdout"] = _clip(_out.getvalue())
        if _value is not None:
            _entry["value"] = _clip(_value)
        if _tables:
            _entry["table"] = _tables[0]
            _entry["tables"] = len(_tables)
    _results.append(_entry)
    if _error:
        break

dbutils.notebook.exit(json.dumps({"v": 1, "cells": _results}))
'''


def wrapper_notebook(p: Plan) -> str:
    """The generated notebook, in Databricks source format. The user's code travels as base64 data, so
    nothing in a cell can end the string it is in or change the wrapper around it."""
    steps = [{"i": i, "src": src} for i, src in p.steps]
    b64 = lambda obj: base64.b64encode(json.dumps(obj).encode("utf-8")).decode("ascii")  # noqa: E731
    return (_WRAPPER.replace("__STEPS__", b64(steps)).replace("__SHOW__", b64(sorted(p.show)))
            .replace("__MAX_ROWS__", str(MAX_ROWS)).replace("__MAX_CHARS__", str(MAX_OUTPUT_CHARS)))


# -- reading a run back -------------------------------------------------------------------------

_LIVE = {"PENDING", "QUEUED", "RUNNING", "TERMINATING", "BLOCKED", "WAITING_FOR_RETRY"}


def results_from_run(p: Plan, *, life_cycle: str, result_state: str, message: str, output: str | None,
                     error: str, seconds: float) -> tuple[bool, dict[int, RunResult]]:
    """(finished, results by cell index) from what the Jobs API said about a run.

    While the run is live the answer is (False, {}). Once it has ended, every cell that was asked for
    has a result: its own, or the reason there is none (an earlier cell failed; the run was cancelled;
    the compute could not start). Nothing is left "running" forever.
    """
    life, result = (life_cycle or "").upper(), (result_state or "").upper()
    if life in _LIVE:
        return False, {}
    out: dict[int, RunResult] = {i: RunResult(state=RunState.REFUSED, error=why, warehouse="")
                                 for i, why in p.refused.items()}

    def everything(state: RunState, why: str) -> dict[int, RunResult]:
        for i in p.show:
            out[i] = RunResult(state=state, seconds=seconds, error=why, warehouse=WHERE)
        return out

    if result in {"CANCELED", "CANCELLED"} or life == "SKIPPED":
        return True, everything(RunState.CANCELLED, "cancelled before it finished")
    doc: dict[str, Any] | None = None
    if output:
        try:
            parsed = json.loads(output)
            doc = parsed if isinstance(parsed, dict) and "cells" in parsed else None
        except ValueError:
            doc = None
    if doc is None:
        # The wrapper never reported: the compute could not start, was refused, or the run timed out.
        detail = (error or message or "").strip()
        return True, everything(RunState.FAILED, detail[:600] or (
            f"the run ended as {result or life or 'unknown'} without reporting a result"))

    seen = {int(c["i"]): c for c in doc["cells"] if "i" in c}
    for index in sorted(p.show):
        cell = seen.get(index)
        if cell is None:
            # Never reached: an earlier cell failed (possibly one that only ran to leave variables).
            earlier = next((c for c in doc["cells"] if not c.get("ok", True)), None)
            if earlier is None:
                out[index] = RunResult(state=RunState.REFUSED, error="not run", warehouse=WHERE)
            else:
                n = int(earlier["i"]) + 1
                out[index] = RunResult(
                    state=RunState.FAILED, seconds=seconds, warehouse=WHERE,
                    error=f"cell {n} failed before this one ran: {str(earlier.get('error', ''))[:500]}")
            continue
        out[index] = _cell_result(cell, seconds)
    return True, out


def _cell_result(cell: dict[str, Any], seconds: float) -> RunResult:
    table = cell.get("table") or {}
    text = cell.get("stdout", "") or ""
    value = cell.get("value", "") or ""
    shown = text + (("" if not text or text.endswith("\n") else "\n") + value if value else "")
    if not cell.get("ok", True):
        return RunResult(state=RunState.FAILED, seconds=seconds, warehouse=WHERE, output=shown,
                         error=str(cell.get("error", "the cell failed"))[:2000])
    return RunResult(
        state=RunState.SUCCEEDED, seconds=seconds, warehouse=WHERE, output=shown,
        columns=list(table.get("columns", [])), rows=list(table.get("rows", [])),
        truncated=bool(table.get("truncated", False)),
        total_rows=len(table.get("rows", [])) if table else None,
    )
