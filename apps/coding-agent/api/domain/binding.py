"""A binding is a reference to what a conversation is about. Pure: no I/O here.

Spec 006 FX-3/FX-5. Two jobs:

  1. **Canonicalise** a cell reference (`/path/to/nb#3`) into `(path, index)` and refuse anything
     malformed loudly rather than guessing — a binding that points at the wrong cell is the most
     damaging failure in this feature, because the agent then edits code the user did not mean.
  2. **Render** the one cell, with a staleness check. A cell index is positional: the file may have
     changed since the user selected it, so a binding carries the content hash it was taken at. If
     the hash no longer matches, the rendered context says so *and* includes the current text, so the
     agent works on what exists instead of on what was described (E-04).
"""

from __future__ import annotations

import hashlib
import re

CELL_KINDS = ("cell",)
_CELL_REF = re.compile(r"^(/.+)#(\d+)$")


class BindingError(ValueError):
    """A binding the server will not act on. Maps to HTTP 422."""


def parse_cell_ref(ref: str) -> tuple[str, int]:
    """`'/a/b#3'` -> `('/a/b', 3)`. 1-based, like the notebook UI's cell numbers."""
    m = _CELL_REF.match((ref or "").strip())
    if not m:
        raise BindingError(f"a cell is attached as <path>#<index>, got {ref!r}")
    index = int(m.group(2))
    if index < 1:
        raise BindingError("a cell index starts at 1")
    path = m.group(1)
    if ".." in path.split("/"):
        raise BindingError(f"not a workspace path: {path!r}")
    return path, index


def content_sha(text: str) -> str:
    """A short, stable hash of one cell's source. Short on purpose: it is rendered into the prompt."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:4]


def cell_text(cells, index: int) -> tuple[str, str]:
    """The source and the language of cell `index` (1-based). Raises when it does not exist.

    Absence is an error, not an empty attachment: silently sending nothing would let the agent answer
    about a cell it never saw.
    """
    if index < 1 or index > len(cells):
        raise BindingError(f"that cell is no longer in this notebook ({len(cells)} cells)")
    cell = cells[index - 1]
    return cell.source, (cell.language or "")


def render_cell(path: str, index: int, source: str, language: str, *, sha: str, seen_sha: str) -> str:
    """The context block for one cell, including a notice when the cell changed since it was bound."""
    head = f"cell {index} of {path}"
    if language:
        head += f" ({language.lower()})"
    head += f" — sha {sha}"
    if seen_sha and seen_sha != sha:
        notice = (
            f"NOTE: this cell changed after the user selected it (was sha {seen_sha}, now sha {sha}). "
            "The text below is the CURRENT content. Work on this, and say that it changed."
        )
        return f"{head}\n{notice}\n{source}"
    return f"{head}\n{source}"
