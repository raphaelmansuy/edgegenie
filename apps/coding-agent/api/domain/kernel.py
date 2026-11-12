"""A Python session on serverless compute: the app's half of the protocol. Pure; no network, no SDK.

`kernel_runtime.py` is the half that runs on the compute. This module builds the notebook that starts it,
decides what a cell is (Python, a shell command, a library install), writes a command, and reads a result
back as a `RunResult`. The service (`services/kernel_service.py`) moves the files; the adapter
(`adapters/databricks/session_store.py`) reaches the volume. Neither knows what is in them.

Why a session at all: a variable made by one cell exists in the next only if one process stays alive
between them. Re-running the cells above (the one-shot mode) cannot give that and repeats their side
effects. See specs/010-notebook for the measurements that decided it.
"""

from __future__ import annotations

import dataclasses
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import kernel_runtime, pyrun
from .cellrun import RunResult, RunState, without_skip

#: Shown on every result: this ran in a session, as the app.
WHERE = "Serverless session · as the app"

#: A Databricks job cannot run forever; this is the longest one session may live, whatever else is true.
MAX_SESSION_SECONDS = 4 * 3600
DEFAULT_IDLE_SECONDS = 20 * 60
DEFAULT_LEASE_SECONDS = 180
#: How long a cell may keep running after the user pressed Stop before the whole session is ended.
INTERRUPT_GRACE_SECONDS = 10.0
#: The session did not report in this long: it is treated as gone.
HEARTBEAT_STALE_SECONDS = 45.0
#: Starting serverless compute can take a while on a busy day; past this it did not start.
START_TIMEOUT_SECONDS = 300.0


def runtime_source() -> str:
    """The text of `kernel_runtime.py`: the code that runs on the compute is the code the tests ran."""
    return Path(kernel_runtime.__file__).read_text(encoding="utf-8")


def kernel_notebook(root: str, session_id: str, *, idle_seconds: float = DEFAULT_IDLE_SECONDS,
                    lease_seconds: float = DEFAULT_LEASE_SECONDS,
                    limits: dict[str, int] | None = None) -> str:
    """The notebook that becomes the session, in Databricks source format.

    Everything that varies travels as a JSON literal, so nothing in it can change the code around it.
    """
    config = json.dumps({"root": root, "session_id": session_id, "idle_seconds": idle_seconds,
                         "lease_seconds": lease_seconds, "limits": limits or {}})
    return (
        "# Databricks notebook source\n"
        + runtime_source()
        + "\n\n# COMMAND ----------\n"
        + "_config = json.loads(" + json.dumps(config) + ")\n"
        + "_names = globals()\n"
        + "_kernel = Kernel(\n"
        + "    _config['root'],\n"
        + "    namespace={k: _names[k] for k in ('spark', 'dbutils', 'sc') if k in _names},\n"
        + "    limits=_config['limits'], idle_seconds=_config['idle_seconds'],\n"
        + "    lease_seconds=_config['lease_seconds'], session_id=_config['session_id'])\n"
        + "_reason = _kernel.serve()\n"
        + "dbutils.notebook.exit(_reason)\n"
    )


@dataclass(frozen=True, slots=True)
class Command:
    """What to send to the session for one cell."""

    kind: str          # "python" | "sh" | "pip" | "md" | "run" (the app expands it) | "cells"
    source: str
    #: For "cells": the cells of the notebook a `%run` named, as {"kind", "source", "name"}, and what was left out.
    cells: tuple[dict[str, str], ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Refusal:
    why: str


_FIRST_MAGIC = re.compile(r"^[ \t]*%(\w+)[ \t]*(.*)$")
#: The cell languages a notebook file gives these magics when it is read (`# MAGIC %sh` -> "shell").
_LANGUAGE_KIND = {"pip": "pip", "shell": "sh", "sh": "sh", "run": "run", "markdown": "md", "md": "md"}
_MAGIC_KIND = {"pip": "pip", "sh": "sh", "run": "run", "md": "md"}


def classify(language: str, source: str) -> Command | Refusal:
    """What this cell is, to a session: Python, a shell command, a library install, markdown, or a `%run`.

    A magic on the first line says what the cell is, whatever the notebook's language. A cell read from a
    notebook file has had its magic taken off and carries it as its language instead ("shell", "pip", "run").
    Anything a session cannot run is refused with the reason in words (`%sql` runs on a warehouse, so the
    caller never sends it here).
    """
    skipped, rest = without_skip(source or "")
    text = (rest if skipped else (source or "")).strip("\n")
    if not text.strip():
        return Refusal("this cell is only a %skip" if skipped else "this cell is empty")
    lines = text.lstrip().splitlines()
    magic = _FIRST_MAGIC.match(lines[0])
    if magic and magic.group(1).lower() in _MAGIC_KIND:
        kind = _MAGIC_KIND[magic.group(1).lower()]
        body = "\n".join([magic.group(2)] + lines[1:]).strip("\n")
        return _command(kind, body)
    kind = _LANGUAGE_KIND.get((language or "").lower())
    if kind and not magic:
        return _command(kind, text)
    body, why = pyrun.python_source(language, source)
    if body is None:
        return Refusal(why)
    return Command("python", body)


def _command(kind: str, body: str) -> Command | Refusal:
    if not body.strip():
        return Refusal({"pip": "%pip needs a command, for example: %pip install pandas",
                        "sh": "%sh needs a command to run",
                        "run": "%run needs a notebook, for example: %run ./helpers",
                        "md": "this markdown cell is empty"}[kind])
    if kind == "pip":
        body = " ".join(body.split())   # a pip command is one line; a continuation is still the same command
    if kind == "run":
        body = body.strip().splitlines()[0].strip()
    return Command(kind, body)


def command_doc(seq: int, command_id: str, command: Command, *, index: int | None = None,
                widgets: dict[str, str] | None = None) -> dict[str, Any]:
    doc: dict[str, Any] = {"protocol": kernel_runtime.PROTOCOL, "seq": seq, "id": command_id,
                           "kind": command.kind, "source": command.source}
    if command.kind == "cells":
        doc["cells"] = list(command.cells)
        doc["notes"] = list(command.notes)
    if index is not None:
        doc["index"] = index
    if widgets:
        doc["widgets"] = widgets
    return doc


def skipped(source: str) -> bool:
    """A cell marked %skip is not run by Run all; asking for it by itself still runs it."""
    return without_skip(source or "")[0]


@dataclass(frozen=True, slots=True)
class Progress:
    """What the session said about a command, read from its out file."""

    final: bool
    beat: int
    seconds: float
    result: RunResult | None       # set when final
    outputs: list[dict[str, Any]]  # set while running: what has been printed so far


def read_out(doc: Any, *, command_id: str | None = None) -> Progress | None:
    """A session's out file as progress, or None when it is not a file we understand.

    The file was written by compute the app does not control, so every field is checked, not trusted:
    a result for a different command, a wrong type, or an unknown protocol is ignored rather than drawn.
    """
    if not isinstance(doc, dict) or doc.get("protocol") != kernel_runtime.PROTOCOL:
        return None
    if command_id is not None and doc.get("id") not in (None, command_id) and doc.get("final"):
        return None
    seconds = doc.get("seconds")
    seconds = float(seconds) if isinstance(seconds, (int, float)) else 0.0
    beat = doc.get("n")
    beat = int(beat) if isinstance(beat, int) else 0
    outputs = pyrun.clean_outputs(doc.get("outputs"))
    if not doc.get("final"):
        return Progress(False, beat, seconds, None, outputs)
    result = result_of(doc, seconds)
    return Progress(True, beat, seconds, result, outputs)


MAX_WIDGETS = 40


def clean_widgets(raw: Any) -> list[dict[str, Any]]:
    """The widgets a session reports, reduced to what the UI can draw. The document came from compute the app does
    not control, so a malformed declaration is dropped, not drawn."""
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for w in raw[:MAX_WIDGETS]:
        if not isinstance(w, dict):
            continue
        kind, name, default = w.get("type"), w.get("name"), w.get("default")
        if kind not in kernel_runtime.WIDGET_TYPES or not isinstance(name, str) or not name or len(name) > 64 \
                or not isinstance(default, str) or len(default) > 2000:
            continue
        choices = [c[:200] for c in (w.get("choices") or []) if isinstance(c, str)][:200] if isinstance(w.get("choices"), list) else []
        label = w.get("label") if isinstance(w.get("label"), str) and w.get("label") else name
        value = w.get("value") if isinstance(w.get("value"), str) else default
        out.append({"name": name, "type": kind, "default": default, "label": label[:120], "choices": choices,
                    "value": value[:2000]})
    return out


def result_of(doc: dict[str, Any], seconds: float) -> RunResult:
    """The final out file as a result the UI draws. A cell that was interrupted is cancelled, not failed."""
    cell = {"ok": bool(doc.get("ok", False)), "outputs": doc.get("outputs") or [], "error": doc.get("error", "")}
    base = pyrun.cell_result(cell, seconds)
    if "widgets" in doc:
        base = dataclasses.replace(base, widgets=clean_widgets(doc.get("widgets")))
    if doc.get("interrupted"):
        return RunResult(state=RunState.CANCELLED, seconds=seconds, error=str(doc.get("error") or "Interrupted"),
                         warehouse=WHERE, output=base.output, images=base.images, outputs=base.outputs,
                         columns=base.columns, rows=base.rows, types=base.types, widgets=base.widgets)
    return _where(base)


def _where(r: RunResult) -> RunResult:
    import dataclasses

    return dataclasses.replace(r, warehouse=WHERE)
