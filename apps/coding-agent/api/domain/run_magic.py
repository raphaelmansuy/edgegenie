"""`%run ./other`: pull the cells of another notebook into the session.

The session never fetches code. The APP reads the other notebook with the USER's token (so a person can
only run what they can read, and the app's own authority is never used to fetch code) and sends the cells
to the session as ordinary, explicit cells. Pure: reading is a function the caller passes in.

Guards, each with a message that says what to do: a target that is not one path, a depth limit, a cycle,
a notebook that cannot be read, and a size limit.
"""

from __future__ import annotations

import posixpath
import shlex
from collections.abc import Awaitable, Callable
from typing import Any

from . import kernel

MAX_DEPTH = 3
MAX_CELLS = 200
MAX_CHARS = 500_000
MAX_NOTES = 20

#: Reads the cells of the notebook at an absolute path, or raises: PermissionError (not allowed), LookupError
#: (not there), ValueError (not a notebook), RuntimeError (the platform failed).
Reader = Callable[[str], Awaitable[list[Any]]]


class RunMagicError(Exception):
    """The `%run` cannot be done. The message is written for the person who wrote it."""


def target(notebook: str, ref: str) -> str:
    """The absolute workspace path `ref` names, from the notebook that wrote the `%run`."""
    try:
        parts = shlex.split(ref)
    except ValueError as exc:
        raise RunMagicError(f"could not read the notebook name after %run: {exc}") from exc
    if not parts:
        raise RunMagicError("%run needs a notebook, for example: %run ./helpers")
    if len(parts) > 1:
        raise RunMagicError("%run takes one notebook path and no arguments here. Set the values you need in a "
                            "variable before the %run, or in the other notebook.")
    path = parts[0]
    if any(ord(c) < 32 for c in path):
        raise RunMagicError("the notebook name after %run has a control character in it")
    joined = path if path.startswith("/") else posixpath.join(posixpath.dirname(notebook) or "/", path)
    resolved = posixpath.normpath(joined)
    if resolved.startswith("//"):
        resolved = "/" + resolved.lstrip("/")
    if not resolved.startswith("/") or resolved == "/":
        raise RunMagicError(f"{path!r} is not a notebook path")
    return resolved


async def expand(read: Reader, notebook: str, ref: str, *, max_depth: int = MAX_DEPTH) -> kernel.Command:
    """The `cells` command for `%run <ref>` written in `notebook`. Raises RunMagicError."""
    cells: list[dict[str, str]] = []
    notes: list[str] = []
    budget = {"chars": 0}
    await _add(read, notebook, ref, [notebook], max_depth, cells, notes, budget)
    if not cells:
        raise RunMagicError(f"{posixpath.basename(target(notebook, ref))} has no cell the session can run"
                            + (f" ({notes[0]})" if notes else ""))
    return kernel.Command("cells", "", tuple(cells), tuple(notes[:MAX_NOTES]))


async def _add(read: Reader, notebook: str, ref: str, stack: list[str], max_depth: int,
               cells: list[dict[str, str]], notes: list[str], budget: dict[str, int]) -> None:
    path = target(notebook, ref)
    if path in stack:
        raise RunMagicError("%run goes in a circle: " + " -> ".join(stack + [path]))
    if len(stack) > max_depth:
        raise RunMagicError(f"%run goes more than {max_depth} notebooks deep at {path}")
    try:
        found = await read(path)
    except PermissionError as exc:
        raise RunMagicError(f"you cannot read {path}, so it was not run ({exc})") from exc
    except LookupError as exc:
        raise RunMagicError(f"no notebook at {path} ({exc})") from exc
    except (ValueError, IsADirectoryError) as exc:
        raise RunMagicError(f"{path} cannot be run: {exc}") from exc
    except RuntimeError as exc:
        raise RunMagicError(f"{path} could not be read: {str(exc)[:200]}") from exc
    name = posixpath.basename(path)
    for cell in found:
        source = getattr(cell, "source", "") or ""
        if getattr(cell, "kind", "code") == "markdown" or not source.strip():
            continue
        label = f"{name}, cell {getattr(cell, 'index', 0) + 1}"
        if kernel.skipped(source):
            continue
        verdict = kernel.classify(getattr(cell, "language", ""), source)
        if isinstance(verdict, kernel.Refusal):
            notes.append(f"{label} was left out: {verdict.why}")
            continue
        if verdict.kind == "md":
            continue
        if verdict.kind == "run":
            await _add(read, path, verdict.source, stack + [path], max_depth, cells, notes, budget)
            continue
        budget["chars"] += len(verdict.source)
        if len(cells) >= MAX_CELLS or budget["chars"] > MAX_CHARS:
            raise RunMagicError(f"%run brings in too much code ({MAX_CELLS} cells or {MAX_CHARS // 1000} KB is the limit)")
        cells.append({"kind": verdict.kind, "source": verdict.source, "name": label})
