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
cell 5), captures each cell's stdout, its last expression, any `display(df)` table, and any
matplotlib figures left open (PNG, base64), and returns one JSON document through
`dbutils.notebook.exit`. This module builds that notebook and reads that document back; it never
touches the network.
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .cellrun import RunResult, RunState, without_skip

#: Shown on every Python result. It is the whole point of the labelling: this did not run as you.
WHERE = "Serverless · as the app"

MAX_CELLS = 200
MAX_ROWS = 1000
#: Per cell. A cell that prints a million lines gets its first and last lines, not a frozen page.
MAX_OUTPUT_CHARS = 20_000
#: Per cell. A KPI grid is one figure; a cell that opens dozens still returns a readable page.
MAX_IMAGES = 8
#: Base64 length. ~1 MB of PNG is plenty for a notebook plot; the exit payload has to stay small.
MAX_IMAGE_B64 = 1_500_000
#: One HTML output (`displayHTML`, a styled table). Larger is replaced by a sentence.
MAX_HTML = 1_000_000
#: Everything the notebook returns must fit the Jobs API's 5 MB `notebook.exit` limit. Outputs share this
#: budget in notebook order; the hard limit is the check that runs once the document is built.
TOTAL_BUDGET = 3_500_000
HARD_LIMIT = 4_800_000

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
        if (language or "").lower() == "sql":
            return None, "this is a SQL cell; it runs on a SQL warehouse, not as Python"
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

# The code that runs the cells is `kernel_runtime.py`, embedded as text: the one-shot run and the session
# produce the same outputs because they are the same code. Only the loop below is the one-shot's own.
_WRAPPER_TAIL = r'''
# COMMAND ----------
_STEPS = json.loads(base64.b64decode("__STEPS__").decode("utf-8"))
_SHOW = set(json.loads(base64.b64decode("__SHOW__").decode("utf-8")))
_HARD_LIMIT = __HARD_LIMIT__
_rt = CellRuntime(json.loads("__LIMITS__"))
_g = globals()
_g.update(_rt.builtins())
_results = []
for _step in _STEPS:
    _entry = _rt.run(_step["i"], _step["src"], _g, keep_outputs=_step["i"] in _SHOW)
    _entry.pop("interrupted", None)
    _results.append(_entry)
    if not _entry["ok"]:
        break

_doc = json.dumps({"v": 2, "cells": _results})
if len(_doc) > _HARD_LIMIT:
    # Last resort: the budget counts what it can see, and a very wide table can still push past the
    # cap. Keep every cell's words and say what went.
    for _e in _results:
        _kept = [o for o in _e.get("outputs", []) if o["type"] == "text"]
        if len(_kept) != len(_e.get("outputs", [])):
            _kept.append({"type": "text", "stream": "notice",
                          "text": "tables, plots and HTML were not shown: the result was too large"})
        _e["outputs"] = _kept
    _doc = json.dumps({"v": 2, "cells": _results})
dbutils.notebook.exit(_doc)
'''


def wrapper_notebook(p: Plan) -> str:
    """The generated notebook, in Databricks source format. The user's code travels as base64 data, so
    nothing in a cell can end the string it is in or change the wrapper around it."""
    from . import kernel_runtime

    steps = [{"i": i, "src": src} for i, src in p.steps]
    b64 = lambda obj: base64.b64encode(json.dumps(obj).encode("utf-8")).decode("ascii")  # noqa: E731
    limits = json.dumps({"max_rows": MAX_ROWS, "max_chars": MAX_OUTPUT_CHARS, "max_images": MAX_IMAGES,
                         "max_image_b64": MAX_IMAGE_B64, "max_html": MAX_HTML, "budget": TOTAL_BUDGET})
    tail = (_WRAPPER_TAIL.replace("__STEPS__", b64(steps)).replace("__SHOW__", b64(sorted(p.show)))
            .replace("__LIMITS__", limits.replace('"', '\\"')).replace("__HARD_LIMIT__", str(HARD_LIMIT)))
    return "# Databricks notebook source\n" + Path(kernel_runtime.__file__).read_text(encoding="utf-8") + tail


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
    unreadable = False
    if output:
        try:
            parsed = json.loads(output)
            doc = parsed if isinstance(parsed, dict) and "cells" in parsed else None
        except ValueError:
            doc = None
        unreadable = doc is None
    if doc is None:
        # The wrapper never reported: the compute could not start, was refused, or the run timed out.
        # Output that is there but is not JSON is the other case, and it is a different sentence: the
        # Jobs API returns only the first 5 MB of a notebook's exit value, and a cut document is no document.
        if unreadable:
            return True, everything(RunState.FAILED, (
                "the notebook finished, but its result could not be read. It was probably cut at the "
                "5 MB the Jobs API returns. Show less per cell (fewer rows, smaller plots), or run fewer "
                "cells at once."))
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


def _cell_images(cell: dict[str, Any]) -> list[str]:
    """PNG base64 strings the wrapper put on the cell. Anything that is not a string is dropped."""
    raw = cell.get("images") or []
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, str) and item and len(item) <= MAX_IMAGE_B64:
            out.append(item)
        if len(out) >= MAX_IMAGES:
            break
    return out


_STREAMS = frozenset({"stdout", "stderr", "result", "notice"})


def clean_outputs(raw: Any) -> list[dict[str, Any]]:
    """The ordered outputs a cell reported, reduced to what the UI can draw and what is within bounds.

    The document comes back from compute the app does not control, so every item is checked rather than
    trusted: an unknown type, a non-string PNG or a table whose rows are not lists is dropped, not drawn.
    """
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    images = 0
    for item in raw:
        if not isinstance(item, dict):
            continue
        kind = item.get("type")
        if kind == "text" and isinstance(item.get("text"), str) and item["text"]:
            stream = item.get("stream") if item.get("stream") in _STREAMS else "stdout"
            out.append({"type": "text", "stream": stream, "text": item["text"][: 4 * MAX_OUTPUT_CHARS]})
        elif kind == "table" and isinstance(item.get("columns"), list) and isinstance(item.get("rows"), list):
            cols = [str(c) for c in item["columns"]]
            rows = [[(None if v is None else str(v)) for v in r] for r in item["rows"][:MAX_ROWS]
                    if isinstance(r, list)]
            types = [str(t) for t in item["types"]] if isinstance(item.get("types"), list) else []
            table: dict[str, Any] = {"type": "table", "columns": cols, "rows": rows,
                                     "truncated": bool(item.get("truncated", False))}
            if types and len(types) == len(cols):
                table["types"] = types
            texts = [str(t)[:2000] for t in item["typeTexts"]] if isinstance(item.get("typeTexts"), list) else []
            if texts and len(texts) == len(cols):
                table["typeTexts"] = texts
            out.append(table)
        elif kind == "image" and isinstance(item.get("png"), str) and item["png"]:
            if len(item["png"]) <= MAX_IMAGE_B64 and images < MAX_IMAGES:
                out.append({"type": "image", "png": item["png"]})
                images += 1
        elif kind == "html" and isinstance(item.get("html"), str) and item["html"]:
            if len(item["html"]) <= MAX_HTML:
                out.append({"type": "html", "html": item["html"]})
        elif kind == "markdown" and isinstance(item.get("text"), str) and item["text"].strip():
            out.append({"type": "markdown", "text": item["text"][:MAX_HTML]})
    return out


def _flat_text(outputs: list[dict[str, Any]]) -> str:
    """The text outputs as one string, the way an older client reads `output`."""
    parts: list[str] = []
    for o in outputs:
        if o["type"] != "text":
            continue
        if parts and not parts[-1].endswith("\n"):
            parts.append("\n")
        parts.append(o["text"])
    return "".join(parts)


def _cell_result(cell: dict[str, Any], seconds: float) -> RunResult:
    outputs = clean_outputs(cell.get("outputs")) if "outputs" in cell else []
    if outputs or "outputs" in cell:
        first = next((o for o in outputs if o["type"] == "table"), None)
        shown = _flat_text(outputs)
        images = [o["png"] for o in outputs if o["type"] == "image"]
        flat: dict[str, Any] = dict(
            output=shown, images=images, outputs=outputs,
            columns=list(first["columns"]) if first else [], rows=list(first["rows"]) if first else [],
            types=list(first.get("types", [])) if first else [],
            truncated=bool(first and first["truncated"]),
            total_rows=len(first["rows"]) if first else None)
    else:
        table = cell.get("table") or {}
        text = cell.get("stdout", "") or ""
        value = cell.get("value", "") or ""
        shown = text + (("" if not text or text.endswith("\n") else "\n") + value if value else "")
        flat = dict(
            output=shown, images=_cell_images(cell),
            columns=list(table.get("columns", [])), rows=list(table.get("rows", [])),
            truncated=bool(table.get("truncated", False)),
            total_rows=len(table.get("rows", [])) if table else None)
    if not cell.get("ok", True):
        return RunResult(state=RunState.FAILED, seconds=seconds, warehouse=WHERE,
                         error=str(cell.get("error", "the cell failed"))[:4000], **flat)
    return RunResult(state=RunState.SUCCEEDED, seconds=seconds, warehouse=WHERE, **flat)


#: One cell of a run document as a result. Public because a session reads the same shape.
cell_result = _cell_result
