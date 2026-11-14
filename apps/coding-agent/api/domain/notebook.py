"""Parse a Databricks notebook in SOURCE format into cells. Pure: text in, cells out.

SOURCE format is one text file per notebook, in the notebook's own language. In Python it is:

    line 1       the header: comment prefix + " Databricks notebook" + " source"
    cell bodies  separated by a line "# COMMAND ----------" (blank line on each side)
    magic cells  every line carries "# MAGIC ", the first one names the magic ("%md", "%sql")

(Do not write the header literally at the start of a line in this file: the Databricks Apps
deployment turns any source file that has one into a notebook and drops its ".py".)

The viewer needs cells, not a wall of text, so that a markdown cell renders as prose and a `%sql`
cell in a Python notebook is labelled as SQL. Anything we cannot classify stays a code cell in
the notebook's language: showing the source is always safe, guessing is not.
"""

from __future__ import annotations

import re

from dataclasses import asdict, dataclass

#: language -> single-line comment prefix used by the header, separators and MAGIC lines
PREFIX = {"PYTHON": "#", "R": "#", "SQL": "--", "SCALA": "//"}

#: magic keyword -> cell language ("md" is rendered as markdown, not as code)
MAGICS = {"md": "markdown", "sql": "sql", "python": "python", "scala": "scala", "r": "r",
          "sh": "shell", "fs": "fs", "pip": "pip", "run": "run"}

MAX_CELLS = 400
MAX_CELL_CHARS = 20_000


@dataclass(frozen=True, slots=True)
class Cell:
    index: int
    kind: str            # "code" | "markdown"
    language: str        # the language to label/highlight with
    source: str
    truncated: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _prefix(language: str) -> str:
    return PREFIX.get((language or "PYTHON").upper(), "#")


def parse_source(text: str, language: str = "PYTHON", *, max_cells: int = MAX_CELLS) -> list[Cell]:
    """Split SOURCE text into cells. Never raises on odd input."""
    lang = (language or "PYTHON").lower()
    pre = _prefix(language)
    lines = text.replace("\r\n", "\n").split("\n")

    # The header is provenance, not code. It is matched loosely (leading blank lines, any trailing
    # whitespace, an optional BOM) because a notebook written by an importer or by a person's editor
    # can carry it in several spellings — and when it was NOT stripped it became "cell 1", which then
    # got run as SQL and failed with a syntax error about '#'. That happened for real.
    header = f"{pre} Databricks notebook source"
    # The file's OWN comment prefix, which is not always the language we were asked to parse: a
    # notebook created as SQL but written with `#` lines (an importer, or an agent that assumed
    # Python) kept its header as "cell 1". Matching either prefix is the honest rule — the line is
    # a marker about the file, not code in a language.
    any_header = re.compile(r"^\ufeff?\s*(?:--|#)\s*Databricks notebook source\s*$")
    while lines and not lines[0].strip():
        lines = lines[1:]
    if lines and (lines[0].lstrip("\ufeff").strip() == header or any_header.match(lines[0])):
        lines = lines[1:]
    sep = f"{pre} COMMAND ----------"
    # A separator is a marker too, so the file's own prefix is honoured here for the same reason as
    # the header: a SQL notebook written with `#` lines uses `# COMMAND ----------`.
    any_sep = re.compile(r"^\ufeff?\s*(?:--|#)\s*COMMAND -{2,}\s*$")

    blocks: list[list[str]] = [[]]
    for ln in lines:
        if ln.strip() == sep or any_sep.match(ln):
            blocks.append([])
        else:
            blocks[-1].append(ln)

    cells: list[Cell] = []
    for block in blocks:
        # trim the blank lines the separators leave around a cell, keep inner blanks
        while block and not block[0].strip():
            block = block[1:]
        while block and not block[-1].strip():
            block = block[:-1]
        if not block:
            continue
        # A block that is only the header is not a cell (see above): a cell that is only provenance
        # is not executable, and offering a run control for it is the inert-button bug.
        if all(not ln.strip() or ln.strip() == header or any_header.match(ln) for ln in block):
            continue
        cells.append(_cell(len(cells), block, lang, pre))
        if len(cells) >= max_cells:
            break
    return cells


def read_completeness(text: str, language: str = "PYTHON") -> tuple[list[Cell], list[str]]:
    """One-cell lookahead detects a hidden tail without returning an unbounded cell list."""
    cells = parse_source(text, language, max_cells=MAX_CELLS + 1)
    reasons = []
    if len(cells) > MAX_CELLS:
        reasons.append("cell_count")
    visible = cells[:MAX_CELLS]
    if any(c.truncated for c in visible):
        reasons.append("cell_source")
    return visible, reasons


def _cell(index: int, block: list[str], lang: str, pre: str) -> Cell:
    magic = f"{pre} MAGIC"
    if all(ln.startswith(magic) or not ln.strip() for ln in block) and block[0].startswith(magic):
        body = [ln[len(magic):][1:] if ln[len(magic):].startswith(" ") else ln[len(magic):] for ln in block]
        first = body[0].strip() if body else ""
        if first.startswith("%"):
            word = first[1:].split()[0].lower() if first[1:].split() else ""
            # %skip is a run directive, not a language. Keep the line and the notebook's language.
            if word == "skip":
                return _make(index, "code", lang, "\n".join(body))
            # Everything after the magic token is content, and its leading whitespace is content
            # too: a markdown cell whose first line is "\tindented" is a different cell from one
            # whose first line is "indented". Drop the magic, the one separator space the writer is
            # required to emit, and nothing else. A bare `.strip()` here silently ate indentation,
            # which made the SOURCE round trip lossy.
            after = body[0].strip()[1 + len(word):]
            if after.startswith(" "):
                after = after[1:]
            rest = [after] + body[1:]
            rest = [r for i, r in enumerate(rest) if i or r]          # drop an empty remainder of line 1
            kind = "markdown" if word == "md" else "code"
            return _make(index, kind, MAGICS.get(word, word or lang), "\n".join(rest))
        return _make(index, "code", lang, "\n".join(body))
    return _make(index, "code", lang, "\n".join(block))


def _make(index: int, kind: str, language: str, source: str) -> Cell:
    if len(source) > MAX_CELL_CHARS:
        return Cell(index, kind, language, source[:MAX_CELL_CHARS], truncated=True)
    return Cell(index, kind, language, source)
