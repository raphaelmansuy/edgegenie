"""Skills from three sources (`[R-18]`) and workbooks as attachments (`[R-21]`).

Both are parity items with Genie Code, and both are tested from the case a user would hit:

  * a skill written by a team must be findable, and a workspace skill must SHADOW a built-in of the same
    name — a team's rule should win over ours;
  * a real `.xlsx` must be readable without a third-party dependency, and a file that only LOOKS like a
    workbook must be refused with a sentence rather than a crash.
"""

from __future__ import annotations

import importlib.util
import io
import os
import zipfile
from pathlib import Path

import pytest

from api.domain import sheet
from api.domain.blob import Family, _family_of, _is_xlsx

SERVER = Path(__file__).resolve().parents[1] / "tools" / "databricks_notebook_mcp.py"


# ============================================================== [R-18] three skill sources
def _skill_server(tmp_path: Path, *, user: str = "", workspace: str = ""):
    saved = dict(os.environ)
    os.environ.update({
        "NBMCP_ALLOW_WRITES": "0", "NBMCP_PROFILE": "core", "NBMCP_WRITE_MODE": "fenced",
        "DATABRICKS_HOST": "https://example.invalid", "DATABRICKS_TOKEN": "t",
        "NBMCP_SKILLS_DIR": str(Path(SERVER).parent / "skills"),
        **({"NBMCP_SKILLS_USER_DIR": user} if user else {}),
        **({"NBMCP_SKILLS_WORKSPACE_DIR": workspace} if workspace else {}),
    })
    try:
        spec = importlib.util.spec_from_file_location("nbmcp_skills", SERVER)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
    finally:
        os.environ.clear()
        os.environ.update(saved)
    return m


def _write(dir_: Path, name: str, body: str) -> Path:
    dir_.mkdir(parents=True, exist_ok=True)
    p = dir_ / f"{name}.md"
    p.write_text(body)
    return p


def test_the_built_in_four_are_still_listed(tmp_path):
    m = _skill_server(tmp_path)
    listing = m.dbx_skill()
    for name in ("notebook-authoring", "etl-pipelines", "lakebase-postgres", "databricks-apps"):
        assert name in listing, f"{name} disappeared from the index"


def test_a_user_skill_is_listed_and_labelled(tmp_path):
    user = tmp_path / "user"
    _write(user, "revenue", "# My revenue rules\nuse gold.")
    m = _skill_server(tmp_path, user=str(user))
    assert '"revenue": "user"' in m.dbx_skill()
    body = m.dbx_skill("revenue")
    assert "My revenue rules" in body
    assert "source: user" in body, "a skill's body must say where it came from"


def test_a_workspace_skill_is_listed_and_labelled(tmp_path):
    ws = tmp_path / "ws"
    _write(ws, "naming", "# Team naming\nsnake_case.")
    m = _skill_server(tmp_path, workspace=str(ws))
    assert "Team naming" in m.dbx_skill("naming")
    assert "source: workspace" in m.dbx_skill("naming")


def test_a_workspace_skill_shadows_a_built_in_of_the_same_name(tmp_path):
    """A team's rule must win over ours: the order builtin -> user -> workspace decides the winner."""
    ws = tmp_path / "ws"
    _write(ws, "notebook-authoring", "# OUR team's notebook rules\nuse our template")
    m = _skill_server(tmp_path, workspace=str(ws))
    body = m.dbx_skill("notebook-authoring")
    assert "OUR team's notebook rules" in body
    assert "source: workspace" in body


def test_a_user_skill_shadows_a_built_in_but_not_a_workspace_skill(tmp_path):
    user, ws = tmp_path / "user", tmp_path / "ws"
    _write(user, "etl-pipelines", "# mine")
    _write(ws, "etl-pipelines", "# the team's")
    m = _skill_server(tmp_path, user=str(user), workspace=str(ws))
    assert "the team's" in m.dbx_skill("etl-pipelines")


def test_an_unknown_skill_says_so_and_lists_what_exists(tmp_path):
    m = _skill_server(tmp_path)
    out = m.dbx_skill("does-not-exist")
    assert "unknown skill" in out
    assert "notebook-authoring" in out, "a refusal must still help the caller find a real one"


def test_no_configured_directories_is_not_an_error(tmp_path):
    """A laptop has no workspace. The built-in four must still work."""
    m = _skill_server(tmp_path, user="", workspace="")
    assert "notebook-authoring" in m.dbx_skill()


def test_an_unreadable_skill_file_is_skipped_not_fatal(tmp_path):
    user = tmp_path / "user"
    user.mkdir(parents=True)
    (user / "broken.md").write_bytes(b"\xff\xfe\x00 not utf-8")
    _write(user, "good", "# Good one\nfine.")
    m = _skill_server(tmp_path, user=str(user))
    listing = m.dbx_skill()
    assert "good" in listing


# ============================================================== [R-21] workbooks
def build_xlsx(rows: list[tuple[str, str]], sheet_name: str = "Revenue") -> bytes:
    """A minimal but REAL .xlsx: workbook part, rels, shared strings, one worksheet."""
    wb = ('<?xml version="1.0"?><workbook '
          'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
          'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
          f'<sheets><sheet name="{sheet_name}" sheetId="1" r:id="rId1"/></sheets></workbook>')
    rels = ('<?xml version="1.0"?><Relationships '
            'xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            'Target="worksheets/sheet1.xml"/></Relationships>')
    texts = sorted({t for pair in rows for t in pair})
    sst = ('<?xml version="1.0"?><sst '
           'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
           + "".join(f"<si><t>{t}</t></si>" for t in texts) + "</sst>")
    cells = []
    for r, (a, b) in enumerate(rows, start=1):
        ia, ib = texts.index(a), texts.index(b)
        cells.append(f'<row r="{r}"><c r="A{r}" t="s"><v>{ia}</v></c>'
                     f'<c r="B{r}" t="s"><v>{ib}</v></c></row>')
    ws = ('<?xml version="1.0"?><worksheet '
          'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
          f'<sheetData>{"".join(cells)}</sheetData></worksheet>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr("xl/workbook.xml", wb)
        z.writestr("xl/_rels/workbook.xml.rels", rels)
        z.writestr("xl/sharedStrings.xml", sst)
        z.writestr("xl/worksheets/sheet1.xml", ws)
    return buf.getvalue()


def test_a_real_workbook_is_detected_from_its_bytes_not_its_name():
    raw = build_xlsx([("month", "revenue")])
    assert _is_xlsx(raw)
    assert _family_of("application/zip", "anything.bin", raw) is Family.SHEET


def test_an_ipynb_is_still_a_notebook_not_a_sheet():
    """Both are ZIPs. The archive's own parts decide, which is why the name is not consulted."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("nb.ipynb", "{}")
    raw = buf.getvalue()
    assert not _is_xlsx(raw)
    assert _family_of("application/zip", "nb.ipynb", raw) is Family.NOTEBOOK


def test_every_sheet_is_read_in_workbook_order():
    raw = build_xlsx([("month", "jan"), ("revenue", "1000")])
    sheets, note = sheet.read(raw)
    assert len(sheets) == 1
    assert sheets[0].name == "Revenue"
    assert sheets[0].rows[0] == ("month", "jan")
    assert note == ""


def test_cells_are_addressed_by_reference_not_by_position():
    """A worksheet omits empty cells, so counting would silently shift a column."""
    ws = ('<?xml version="1.0"?><worksheet '
          'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
          '<row r="1"><c r="A1" t="inlineStr"><is><t>a</t></is></c>'
          '<c r="C1" t="inlineStr"><is><t>c</t></is></c></row>'
          '</sheetData></worksheet>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/workbook.xml",
                   '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                   '<sheets><sheet name="S" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="x" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml", ws)
    sheets, _ = sheet.read(buf.getvalue())
    assert sheets[0].rows[0] == ("a", "", "c"), "an empty B1 must leave a hole, not shift C into B"


def test_the_note_says_when_a_sheet_was_cut():
    rows = [(f"r{i}", str(i)) for i in range(sheet.MAX_ROWS + 50)]
    raw = build_xlsx(rows)
    sheets, note = sheet.read(raw)
    assert sheets[0].truncated
    assert "rows" in note and str(sheet.MAX_ROWS) in note


def test_a_legacy_or_encrypted_workbook_is_refused_with_a_sentence():
    text, note = sheet.as_text(b"not a zip at all")
    assert text == ""
    assert "not a readable workbook" in note
    assert ".csv" in note, "the sentence must say what would work"


def test_a_zip_that_is_not_a_workbook_says_which():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("readme.txt", "hello")
    text, note = sheet.as_text(buf.getvalue())
    assert text == ""
    assert "not a workbook" in note


def test_a_value_with_a_comma_is_quoted_so_the_csv_is_one_row():
    raw = build_xlsx([("month", "a,b")])
    text, _ = sheet.as_text(raw)
    assert '"a,b"' in text


def test_a_quote_is_doubled():
    raw = build_xlsx([('say "hi"', "x")])
    text, _ = sheet.as_text(raw)
    assert '"say ""hi"""' in text
