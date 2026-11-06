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


def parse_source(text: str, language: str = "PYTHON") -> list[Cell]:
    """Split SOURCE text into cells. Never raises on odd input."""
    lang = (language or "PYTHON").lower()
    pre = _prefix(language)
    lines = text.replace("\r\n", "\n").split("\n")

    header = f"{pre} Databricks notebook" + " source"
    if lines and lines[0].strip() == header:
        lines = lines[1:]
    sep = f"{pre} COMMAND ----------"

    blocks: list[list[str]] = [[]]
    for ln in lines:
        if ln.strip() == sep:
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
        cells.append(_cell(len(cells), block, lang, pre))
        if len(cells) >= MAX_CELLS:
            break
    return cells


def _cell(index: int, block: list[str], lang: str, pre: str) -> Cell:
    magic = f"{pre} MAGIC"
    if all(ln.startswith(magic) or not ln.strip() for ln in block) and block[0].startswith(magic):
        body = [ln[len(magic):][1:] if ln[len(magic):].startswith(" ") else ln[len(magic):] for ln in block]
        first = body[0].strip() if body else ""
        if first.startswith("%"):
            word = first[1:].split()[0].lower() if first[1:].split() else ""
            rest = [first[1 + len(word):].strip()] + body[1:]
            rest = [r for i, r in enumerate(rest) if i or r]          # drop an empty remainder of line 1
            kind = "markdown" if word == "md" else "code"
            return _make(index, kind, MAGICS.get(word, word or lang), "\n".join(rest))
        return _make(index, "code", lang, "\n".join(body))
    return _make(index, "code", lang, "\n".join(block))


def _make(index: int, kind: str, language: str, source: str) -> Cell:
    if len(source) > MAX_CELL_CHARS:
        return Cell(index, kind, language, source[:MAX_CELL_CHARS], truncated=True)
    return Cell(index, kind, language, source)
