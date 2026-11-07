"""Serialize cells back to SOURCE format: the exact inverse of :func:`parse_source`.

This is the module that stands between a user and a silently-rewritten notebook, so its contract is
stated as a property rather than a promise:

    parse_source(serialize_source(parse_source(t)))  ==  parse_source(t)

for **every** text ``t``, and

    parse_source(serialize_source(cells))            ==  cells

for every cell list we can construct. Both are tested over a corpus (see
``tests/test_notebook_roundtrip.py``), because a violation means opening and saving a notebook
changes its bytes — the worst bug an editor can have.

## Why the round trip is "parse ∘ serialize", not "bytes in == bytes out"

``parse_source`` deliberately trims the blank lines that separators leave around each cell (it has
to: a separator is surrounded by blank lines, so a naive split yields a blank cell on each side).
That means information *between* cells is not representable in a `Cell`. Re-serializing inserts the
canonical spacing back. So byte-exactness cannot hold for arbitrary input, but **stability** must:

    serialize(parse(t))  produces  t'  such that  parse(t') == parse(t)  and  serialize(parse(t')) == t'

t' is the *canonical form* of t. The first save of a hand-written notebook may therefore normalize
its blank lines; every save after that is byte-identical. That is the strongest guarantee available
without inventing a cell field that means "how many blank lines preceded me", and the tests assert
it rather than leaving it implicit.
"""

from __future__ import annotations

from dataclasses import dataclass

from .notebook import MAGICS, Cell, _prefix, parse_source

#: Reverse of MAGICS: language -> the magic word that produced it. Markdown has its own path.
_MAGIC_FOR = {v: k for k, v in MAGICS.items()}

#: The magic each kind/language pair needs, or None when the cell is plain code in the notebook's
#: own language and needs no magic at all.
def _magic_for(kind: str, language: str, notebook_language: str) -> str | None:
    if kind == "markdown":
        return "md"
    lang = (language or "").lower()
    if not lang or lang == (notebook_language or "python").lower():
        return None
    # A cell that was a magic (sql/sh/pip/...) keeps its magic; anything unknown falls back to the
    # notebook's own language rather than inventing a magic that Databricks would not understand.
    return _MAGIC_FOR.get(lang)


@dataclass(frozen=True, slots=True)
class SerializeIssue:
    """Something the caller must not silently save."""

    kind: str      # "truncated" | "too_many" | "too_long"
    index: int
    detail: str


def _edge_blank(source: str) -> bool:
    """True when the source has a blank first or last line.

    Such a cell cannot be written as plain code: `parse_source` trims exactly those blank lines.
    It *may* still be writable in the MAGIC form, where every line carries the comment prefix.
    Whether it actually survives is decided by trying — see `check`.
    """
    lines = source.split("\n")
    return bool(lines) and (not lines[0].strip() or not lines[-1].strip())


def check(cells: list[Cell], notebook_language: str = "PYTHON") -> list[SerializeIssue]:
    """Everything that makes these cells unsafe to write back. Empty means safe.

    Two classes of problem, and the second is decided by **doing the round trip** rather than by
    reasoning about the format:

    1. *Structural*: a truncated cell (saving would drop the tail), too many cells, a cell too long.
       These are refused outright.
    2. *Unrepresentable*: a cell whose source cannot be written in SOURCE format and read back
       identically. The formats are lossy at the edges — plain code loses leading and trailing blank
       lines, and the MAGIC form loses a blank or leading-whitespace first line, because the parser
       strips the remainder of the magic line. Enumerating those cases by hand is how a corruption
       bug ships, so this re-parses what it would write and reports any cell that differs.

    The second check is the one that makes the guarantee honest: if `check` is empty, a save is
    provably a no-op on meaning.
    """
    from .notebook import MAX_CELLS, MAX_CELL_CHARS

    issues: list[SerializeIssue] = []
    if len(cells) > MAX_CELLS:
        issues.append(SerializeIssue("too_many", MAX_CELLS, f"{len(cells)} cells, limit {MAX_CELLS}"))
    for c in cells:
        if c.truncated:
            issues.append(SerializeIssue("truncated", c.index,
                                         "the reader truncated this cell; saving would drop the rest"))
        elif len(c.source) > MAX_CELL_CHARS:
            issues.append(SerializeIssue("too_long", c.index,
                                         f"{len(c.source)} chars, limit {MAX_CELL_CHARS}"))

    if issues:
        return issues          # structural problems make a round-trip check meaningless

    # Prove it: write, read back, compare. Cheap (<=400 small cells) and total.
    written = serialize_source(cells, notebook_language)
    back = parse_source(written, notebook_language)
    if len(back) != len(cells):
        issues.append(SerializeIssue("unencodable", 0,
                                     f"{len(cells)} cells would be read back as {len(back)}"))
        return issues
    for before, after in zip(cells, back):
        if (before.kind, before.language, before.source) != (after.kind, after.language, after.source):
            issues.append(SerializeIssue(
                "unencodable", before.index,
                "this cell's leading or trailing blank lines cannot be written and read back",
            ))
    return issues


def serialize_source(cells: list[Cell], language: str = "PYTHON") -> str:
    """Cells -> SOURCE text. Always ends with exactly one newline.

    Layout, matching what ``parse_source`` expects: the header line (comment prefix, then the
    words shown in ``_HEADER_TEXT`` below), then each cell, then a blank line, a separator line, and
    another blank line before the next cell. The literal is built at runtime rather than written
    here, because a source file containing that header at the start of a line would be turned into
    a notebook by the Databricks Apps deployment — see ``tests/test_packaging.py``.

    A magic cell writes its magic on the first line and the prefix on every line, which is the
    shape ``_cell`` in the parser reads back.
    """
    pre = _prefix(language)
    notebook_lang = (language or "PYTHON").lower()

    out: list[str] = [f"{pre} Databricks notebook source"]

    for i, cell in enumerate(cells):
        if i:
            out.append("")
            out.append(f"{pre} COMMAND ----------")
            out.append("")

        magic = _magic_for(cell.kind, cell.language, notebook_lang)
        # A cell with a TRAILING blank line cannot survive the plain form: the parser trims trailing
        # blanks from every block. The MAGIC form preserves them, because each line keeps its
        # prefix. So when the only problem is a trailing blank, switch to the MAGIC form.
        # (A *leading* blank line cannot be represented in the MAGIC form either — the parser reads
        # the magic from line 1 — so `check` refuses that case rather than corrupting it.)
        if magic is None and cell.source.endswith("\n"):
            magic = _MAGIC_FOR.get(notebook_lang) or notebook_lang
        if magic:
            # Every line of a magic cell carries the MAGIC prefix, and the first line names the
            # magic after a "%". This mirrors _cell() exactly.
            body = cell.source.split("\n")
            out.append(f"{pre} MAGIC %{magic} {body[0]}".rstrip() if body[0] else f"{pre} MAGIC %{magic}")
            for ln in body[1:]:
                out.append(f"{pre} MAGIC {ln}" if ln else f"{pre} MAGIC")
        else:
            for ln in cell.source.split("\n"):
                out.append(ln)

    return "\n".join(out) + "\n"
