"""The round-trip properties: a save must never silently rewrite a notebook.

Two properties, and one stability property that makes the second meaningful:

  P1  parse(serialize(cells)) == cells
  P2  parse(serialize(parse(t))) == parse(t)
  P3  serialize(parse(serialize(parse(t)))) == serialize(parse(t))   (idempotent canonical form)

P1 is the one that matters for editing: whatever the user's cells are, saving and re-reading gives
the same cells. P2 says an untouched notebook keeps its meaning. P3 says the *first* save may
normalize spacing but every save after that is byte-identical — see notebook_write.py for why
byte-equality with arbitrary input is not achievable.

These are property tests with generated input, not examples, because the failure mode is an unusual
notebook and examples never contain the unusual case.
"""

from __future__ import annotations

import itertools
import random

import pytest

from api.domain.notebook import MAGICS, Cell, parse_source
from api.domain.notebook_write import check, serialize_source

LANGS = ["PYTHON", "SQL", "SCALA", "R"]
PREFIX = {"PYTHON": "#", "SQL": "--", "SCALA": "//", "R": "#"}


# ---------------------------------------------------------------- fixtures
def notebook_text(lang: str, cells: list[tuple[str, str]]) -> str:
    """Build a SOURCE document the way Databricks writes one."""
    p = PREFIX[lang]
    out = [f"{p} Databricks notebook source"]
    for i, (kind, source) in enumerate(cells):
        if i:
            out += ["", f"{p} COMMAND ----------", ""]
        if kind == "markdown":
            for ln in source.split("\n"):
                out.append(f"{p} MAGIC %md {ln}" if ln else f"{p} MAGIC")
        elif kind not in ("", lang.lower()):
            word = {"sql": "sql", "shell": "sh", "pip": "pip", "fs": "fs", "r": "r", "scala": "scala"}.get(kind, kind)
            for ln in source.split("\n"):
                out.append(f"{p} MAGIC %{word} {ln}" if ln else f"{p} MAGIC")
        else:
            out += source.split("\n")
    return "\n".join(out) + "\n"


CORPUS = [
    ("PYTHON", [("", "print(1)")]),
    ("PYTHON", [("", "print(1)"), ("", "print(2)")]),
    ("PYTHON", [("markdown", "# Title"), ("", "x = 1")]),
    ("PYTHON", [("", "x = 1"), ("sql", "select * from samples.nyctaxi.trips")]),
    ("PYTHON", [("markdown", "# A\n\nSome prose.\n\n- one\n- two"), ("", "df = spark.table('t')")]),
    ("SCALA", [("", "val x = 1"), ("", "println(x)")]),
    ("SQL", [("", "select 1"), ("", "select 2")]),
    ("R", [("", "x <- 1")]),
    ("PYTHON", [("", "a\n\nb\n\n\nc")]),                       # inner blank lines
    ("PYTHON", [("", "  indented\n    deeper")]),              # leading whitespace
    ("PYTHON", [("shell", "%sh\necho hi"), ("", "y = 2")]),
    ("PYTHON", [("pip", "pip install pandas")]),
]


@pytest.mark.parametrize("lang,cells", CORPUS)
def test_parse_serialize_is_identity(lang, cells):
    """P1 — the cells a user has are the cells they get back."""
    text = notebook_text(lang, cells)
    parsed = parse_source(text, lang)
    again = parse_source(serialize_source(parsed, lang), lang)
    assert [(c.kind, c.language, c.source) for c in again] == [(c.kind, c.language, c.source) for c in parsed]


@pytest.mark.parametrize("lang,cells", CORPUS)
def test_canonical_form_is_stable(lang, cells):
    """P3 — after one save, further saves are byte-identical."""
    text = notebook_text(lang, cells)
    once = serialize_source(parse_source(text, lang), lang)
    twice = serialize_source(parse_source(once, lang), lang)
    assert once == twice


def test_empty_notebook_round_trips():
    assert parse_source(serialize_source([], "PYTHON"), "PYTHON") == []


def test_header_only_document():
    """A notebook with no cells is a header and a newline, and parses to no cells."""
    assert serialize_source([], "PYTHON") == "# Databricks notebook source\n"


def test_first_save_normalises_spacing_but_keeps_cells():
    """The documented, deliberate normalisation: blank lines between cells become canonical."""
    messy = "# Databricks notebook source\n\n\nprint(1)\n\n\n# COMMAND ----------\n\n\nprint(2)\n\n\n"
    cells = parse_source(messy, "PYTHON")
    canonical = serialize_source(cells, "PYTHON")
    assert parse_source(canonical, "PYTHON") == cells
    assert serialize_source(parse_source(canonical, "PYTHON"), "PYTHON") == canonical


# ---------------------------------------------------------------- generated
def random_source(rng: random.Random) -> str:
    """Source text that stresses the things a hand-written fixture would miss.

    Deliberately not starting with a blank line: `parse_source` trims leading blanks from every
    block, so a cell with a leading blank line cannot be produced by reading a notebook. Generating
    one would test a state that cannot exist and inflate the refusal count with fiction.
    """
    atoms = [
        "x = 1", "  indented()", "", "# a comment", "s = 'quote'", 'd = "double"',
        "triple = '''a\nb'''", "sql = 'select 1'", "\ttabbed", "emoji = '🚀'",
        "_ = 'a#b'", "y = '--'", "z = '//'", "back `tick`", "trailing space   ",
    ]
    body = [rng.choice(atoms) for _ in range(rng.randint(1, 6))]
    while body and not body[0].strip():
        body.pop(0)
    return "\n".join(body or ["pass"])


def test_generated_cells_round_trip_or_are_refused():
    """P1 over 2000 generated cell lists: **every** input either round-trips exactly or is refused.

    This is the contract that matters. A cell either survives a save byte-for-byte, or `check()`
    says it cannot and no save happens. What must never occur is the third outcome — accepted, and
    silently changed.
    """
    rng = random.Random(20261107)
    kinds = [("code", "python"), ("markdown", "markdown"), ("code", "sql"), ("code", "shell")]
    round_tripped = 0
    refused = 0
    for _ in range(2000):
        lang = rng.choice(LANGS)
        cells = [
            Cell(index=i, kind=k, language=l, source=random_source(rng))
            for i, (k, l) in enumerate(rng.choice(kinds) for _ in range(rng.randint(0, 5)))
        ]
        issues = check(cells, lang)
        if issues:
            refused += 1
            assert all(i.kind == "unencodable" for i in issues), (issues, cells)
            continue
        round_tripped += 1
        back = parse_source(serialize_source(cells, lang), lang)
        assert [(c.kind, c.source) for c in back] == [(c.kind, c.source) for c in cells], (lang, cells)

    # The vast majority must round-trip; refusal is the rare exception, not the norm.
    assert round_tripped > refused * 3, (round_tripped, refused)


def test_generated_documents_parse_identically():
    """P2 over 2000 generated SOURCE documents: parsing is a function of meaning, not of spacing."""
    rng = random.Random(7)
    refused = 0
    for _ in range(2000):
        lang = rng.choice(LANGS)
        n = rng.randint(0, 4)
        cells = [(rng.choice(["", "markdown", "sql"]), random_source(rng)) for _ in range(n)]
        text = notebook_text(lang, cells)
        a = parse_source(text, lang)
        if check(a, lang):
            refused += 1
            continue
        b = parse_source(serialize_source(a, lang), lang)
        assert [(c.kind, c.language, c.source) for c in a] == [(c.kind, c.language, c.source) for c in b]
    assert refused < 400, refused       # refusal is the exception, not the rule


# ---------------------------------------------------------------- refusals
def test_truncated_cell_is_refused():
    """Saving a truncated document would destroy the tail — it must be refused, not saved."""
    cells = [Cell(index=0, kind="code", language="python", source="x", truncated=True)]
    issues = check(cells)
    assert [i.kind for i in issues] == ["truncated"]
    assert "truncated" in issues[0].detail


def test_too_many_cells_is_refused():
    from api.domain.notebook import MAX_CELLS
    cells = [Cell(index=i, kind="code", language="python", source="x") for i in range(MAX_CELLS + 1)]
    assert [i.kind for i in check(cells)] == ["too_many"]


def test_clean_cells_pass():
    assert check([Cell(index=0, kind="code", language="python", source="x")]) == []


# ---------------------------------------------------------------- the magic table
def test_every_magic_language_round_trips():
    """Every entry in MAGICS must survive a save, not just the two we happen to test elsewhere."""
    for word, lang in sorted(MAGICS.items()):
        cell = Cell(index=0, kind="markdown" if word == "md" else "code",
                    language=lang, source="body line 1\nbody line 2")
        out = serialize_source([cell], "PYTHON")
        back = parse_source(out, "PYTHON")
        assert len(back) == 1, (word, out)
        assert back[0].source == "body line 1\nbody line 2", (word, out)
        assert (back[0].kind, back[0].language) == (cell.kind, cell.language), (word, out)


def test_magic_word_survives_an_unknown_language():
    """An unknown language falls back rather than inventing a magic Databricks would reject."""
    cell = Cell(index=0, kind="code", language="brainfuck", source="+++")
    out = serialize_source([cell], "PYTHON")
    back = parse_source(out, "PYTHON")
    assert back[0].source == "+++"
    assert "MAGIC" not in out


def test_skip_is_kept_as_a_directive_in_the_notebook_language():
    text = "# Databricks notebook source\n# MAGIC %skip\n# MAGIC select 1\n"
    cells = parse_source(text, "PYTHON")
    assert len(cells) == 1
    assert cells[0].language == "python"
    assert cells[0].source == "%skip\nselect 1"
