"""A workbook as CSV text, with no third-party dependency. Pure. `[R-21]`.

The gap this closes. Genie Code accepts `.xlsx` and `.xls`; this app's family table had image, text,
notebook, PDF and `OTHER`, so a user with a workbook had to export it first. An agent that cannot read the
file it was handed will describe what such a file *usually* contains.

**Why not `openpyxl`.** It is a large dependency for one attachment type, and this app's Python surface is
deliberately small: the tool server ships `mcp` and `httpx` and nothing else. An `.xlsx` is a ZIP of XML,
and the parts needed here are three files and one well-defined schema — small enough to read honestly in
~120 lines, with the format's own rules visible rather than hidden in a library.

**What is read, and what is deliberately not.**
  * `xl/workbook.xml`            the sheet names, in workbook order
  * `xl/sharedStrings.xml`       the shared string table (most cell text lives here)
  * `xl/worksheets/sheetN.xml`   the cells, addressed by `r="B7"`
Cells are addressed by their own reference rather than by position, because a worksheet omits empty cells
and counting would silently shift a column. A formula is reported as its **cached value**, which is what a
reader wants; the formula itself is not evaluated, and this module never pretends to.

**The bound is stated, not silent.** Every sheet is capped (`MAX_ROWS`, `MAX_COLS`, `MAX_CHARS`) and the
output says which cap was hit. A truncated workbook that looks whole is the defect `[R-3]` fixed for tool
results, applied to a person's own file.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from xml.etree import ElementTree as ET

#: Per sheet. A workbook with 100 000 rows is a database export, and the agent should be told to query
#: the table rather than be handed a paste of it.
MAX_ROWS = 200
MAX_COLS = 40
#: Across the whole workbook, in characters.
MAX_CHARS = 20_000

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

#: `B7` -> (row 7, col 2). One-based, as the format is.
_REF = re.compile(r"^([A-Z]+)(\d+)$")


def _col_index(letters: str) -> int:
    """`A` -> 1, `Z` -> 26, `AA` -> 27. Base-26 with no zero digit."""
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n


@dataclass(frozen=True, slots=True)
class Sheet:
    name: str
    rows: tuple[tuple[str, ...], ...]
    #: True when a cap cut this sheet. Reported so a reader knows the table is not all of it.
    truncated: bool
    total_rows: int = 0


def _shared_strings(zf: zipfile.ZipFile) -> list[str]:
    """The shared string table, in index order. Most cell TEXT is stored here and referenced by index."""
    try:
        raw = zf.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []
    out: list[str] = []
    for si in root.findall("m:si", _NS):
        # A string may be split across runs (`<r><t>a</t></r><r><t>b</t></r>`); join them in order.
        out.append("".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t")))
    return out


def _sheets(zf: zipfile.ZipFile) -> list[tuple[str, str]]:
    """`(name, part)` in workbook order. Falls back to the parts on disk when the workbook part is
    missing, so a slightly malformed file still yields something rather than nothing."""
    names: list[tuple[str, str]] = []
    try:
        root = ET.fromstring(zf.read("xl/workbook.xml"))
        rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        targets = {
            r.get("Id"): r.get("Target", "")
            for r in rels
        }
        for i, sh in enumerate(root.findall("m:sheets/m:sheet", _NS), start=1):
            name = sh.get("name") or f"sheet{i}"
            rid = sh.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            target = targets.get(rid or "", "")
            part = target.lstrip("/") if target else ""
            if not part.startswith("xl/"):
                part = f"xl/{part}" if part else f"xl/worksheets/sheet{i}.xml"
            names.append((name, part))
    except (KeyError, ET.ParseError):
        names = []
    if names:
        return names
    # No workbook part: read whatever worksheets exist, in name order.
    found = sorted(p for p in zf.namelist() if p.startswith("xl/worksheets/sheet"))
    return [(p.rsplit("/", 1)[-1].removesuffix(".xml"), p) for p in found]


def _rows(zf: zipfile.ZipFile, part: str, strings: list[str]) -> tuple[list[list[str]], bool, int]:
    try:
        root = ET.fromstring(zf.read(part))
    except (KeyError, ET.ParseError):
        return [], False, 0
    grid: list[list[str]] = []
    truncated = False
    for row in root.iter(f"{{{_NS['m']}}}row"):
        values: dict[int, str] = {}
        for c in row.findall("m:c", _NS):
            ref = c.get("r", "")
            m = _REF.match(ref)
            col = _col_index(m.group(1)) if m else len(values) + 1
            if col > MAX_COLS:
                truncated = True
                continue
            kind = c.get("t", "")
            if kind == "inlineStr":
                text = "".join(t.text or "" for t in c.iter(f"{{{_NS['m']}}}t"))
            else:
                v = c.find("m:v", _NS)
                raw = (v.text or "") if v is not None else ""
                if kind == "s":            # a shared string, by index
                    try:
                        text = strings[int(raw)]
                    except (ValueError, IndexError):
                        text = raw
                elif kind == "b":          # a boolean
                    text = "TRUE" if raw == "1" else "FALSE"
                else:
                    text = raw            # a number, or a cached formula result
            values[col] = text
        if not values:
            continue
        width = max(values)
        grid.append([values.get(i, "") for i in range(1, width + 1)])
        if len(grid) >= MAX_ROWS:
            truncated = True
            break
    return grid, truncated, len(grid)


def read(raw: bytes) -> tuple[list[Sheet], str]:
    """Every sheet, plus the note a reader needs about what was cut. Never raises.

    A workbook this reader cannot open (a legacy binary `.xls`, an encrypted file) returns no sheets and a
    sentence saying so — never an exception, because an attachment that fails must not fail the message.
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        return [], ("this file is not a readable workbook. A legacy binary .xls has to be saved as .xlsx "
                    "or .csv first; an encrypted workbook has to be unlocked.")
    with zf:
        if not any(n.startswith("xl/") for n in zf.namelist()):
            return [], "this file is a ZIP but not a workbook (it has no xl/ parts)."
        strings = _shared_strings(zf)
        out: list[Sheet] = []
        spent = 0
        for name, part in _sheets(zf):
            grid, cut, total = _rows(zf, part, strings)
            if not grid:
                continue
            body = "\n".join(",".join(_cell(v) for v in row) for row in grid)
            if spent + len(body) > MAX_CHARS:
                out.append(Sheet(name, tuple(tuple(r) for r in grid[:2]), True, total))
                break
            spent += len(body)
            out.append(Sheet(name, tuple(tuple(r) for r in grid), cut, total))
    notes = []
    for sh in out:
        if sh.truncated:
            notes.append(f"{sh.name}: first {len(sh.rows)} rows and {MAX_COLS} columns shown")
    return out, ("; ".join(notes) if notes else "")


def _cell(value: str) -> str:
    """CSV-safe: a value with a comma, a quote or a newline is quoted, with quotes doubled."""
    if any(ch in value for ch in (',', '"', "\n", "\r")):
        return '"' + value.replace('"', '""') + '"'
    return value


def as_text(raw: bytes) -> tuple[str, str]:
    """The workbook as one text block, plus an empty string or the reason there is none.

    The second value is the note, not an error: a workbook that opened is a success even when it was cut,
    and the caller reports the cut rather than refusing the file.
    """
    sheets, note = read(raw)
    if not sheets:
        return "", note
    parts = [f"# Sheet: {s.name}\n" + "\n".join(",".join(_cell(v) for v in row) for row in s.rows)
             for s in sheets]
    return "\n\n".join(parts), note
