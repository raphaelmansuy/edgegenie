#!/usr/bin/env python3
"""Render the 006 wireframes on a strict character grid.

Why a generator: a box one character out of alignment reads as broken, and the defect is invisible in
a diff. Every screen here is a `Frame` with fixed column widths, and every cell is truncated or padded
to its own width before it is placed. The border positions are therefore a property of the frame, not
of the author's eye, and a long label cannot push a border sideways.

Run:  python3 tools/wireframes.py            # print, for review
      python3 tools/wireframes.py --write    # regenerate the block in 06-ux-wireframes.md
      python3 tools/wireframes.py --check     # exit 1 if any box does not close
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOC = HERE.parent / "06-ux-wireframes.md"
BEGIN = "<!-- BEGIN GENERATED WIREFRAMES -->"
END = "<!-- END GENERATED WIREFRAMES -->"

# No emoji anywhere in these screens. An emoji is often two code points (base + variation
# selector) and always two display columns, so it silently shifts every border to its right; the repo
# has the same rule for UI glyphs in `Icons.tsx` ("glyphs, not emoji", because an emoji ignores
# `color`). Text glyphs such as `*` and `x` keep the grid exact.
#
# Box drawing. Declared before anything that uses them as a default argument.
H, V = "─", "│"
TL, TR, BL, BR = "┌", "┐", "└", "┘"
LT, RT = "├", "┤"
XT, XB, XC = "┬", "┴", "┼"

# The three-pane shell: rail, document, assistant. Inner widths; 4 borders complete the line.
SHELL = (22, 40, 34)


def width(widths: tuple[int, ...]) -> int:
    """The total line width for a set of inner column widths."""
    return sum(widths) + len(widths) + 1


def fit(text: str, n: int) -> str:
    """Exactly `n` characters. Truncate with an ellipsis rather than push the next border."""
    t = text[:n] if len(text) <= n else text[: max(0, n - 1)] + "…"
    return t.ljust(n)


class Frame:
    """A bordered block. `widths` are the inner widths of its columns."""

    def __init__(self, widths: tuple[int, ...] = SHELL) -> None:
        self.widths = widths
        self.rows: list[str] = []

    @property
    def w(self) -> int:
        return width(self.widths)

    # -- rules
    def _rule(self, left: str, right: str, joint: str, spans: bool) -> str:
        if spans:
            return left + H * (self.w - 2) + right
        cells = H * self.widths[0]
        for n in self.widths[1:]:
            cells += joint + H * n
        return left + cells + right

    def top(self) -> "Frame":
        self.rows.append(self._rule(TL, TR, XT, False))
        return self

    def bottom(self) -> "Frame":
        self.rows.append(self._rule(BL, BR, XB, False))
        return self

    def divider(self) -> "Frame":
        self.rows.append(self._rule(LT, RT, XC, False))
        return self

    # -- content
    def full(self, text: str = "") -> "Frame":
        """One row spanning every column: the top bar, a caption inside the frame.

        A single leading space keeps the text off the border, which reads as a misalignment even when
        the geometry is exact. An empty row stays empty so a blank line does not become " ".
        """
        body = "" if not text else " " + fit(text, self.w - 3)
        self.rows.append(V + fit(body, self.w - 2) + V)
        return self

    def cells(self, *texts: str) -> "Frame":
        """One row, one entry per column. Extra texts are ignored; missing ones are blank.

        A single leading space is added to every non-empty cell: text that touches a border reads as
        a misalignment even when the geometry is exact.
        """
        parts = []
        for i, n in enumerate(self.widths):
            t = texts[i] if i < len(texts) else ""
            parts.append(" " + fit(t, n - 1) if t else fit("", n))
        return self._push(parts)

    def _push(self, parts: list[str]) -> "Frame":
        self.rows.append(V + V.join(parts) + V)
        return self

    def lines(self) -> list[str]:
        return self.rows


def nested(lines: list[str], width_in: int) -> list[str]:
    """A box of exactly `width_in` inner columns, for drawing inside a cell.

    Fixed width rather than measured content: a nested box that is one column too wide is silently
    truncated by the cell that holds it, which is how its right border disappears.
    """
    out = [TL + H * width_in + TR]
    for i, text in enumerate(lines):
        if text is None:  # type: ignore[comparison-overlap]
            out.append(LT + H * width_in + RT)
            continue
        out.append(V + " " + fit(text, width_in - 2) + " " + V)
    out.append(BL + H * width_in + BR)
    return out


def block(title: str, rows: list[str], note: str) -> str:
    return "\n".join([f"### {title}", "", "```text", *rows, "```", "", note, ""])


# ----------------------------------------------------------------------------- screens
RAIL_HEAD = "SESSIONS │ FILES  │ CATALOG"
TOPBAR = "◧ Databricks Coding Agents"


def topbar(meta: str) -> str:
    return TOPBAR + " " * max(1, width(SHELL) - 2 - len(TOPBAR) - len(meta) - 1) + meta


def s1_today() -> list[str]:
    """Today: the conversation is a TAB, so opening a file hides it."""
    f = Frame()
    f.top()
    f.full(topbar("⌘K   ▤   ◫   model ▾ gemini-3.8-flash   ready"))
    f.divider()
    f.cells("SESSIONS", "◫ Chat  e2e_outside_fence  display_tables", "")
    f.cells("FILES  │ CATALOG", "", "")
    f.cells("", "", "")
    box = nested([
        "display_unity_catalog_tables  PY ↗",
        None,
        "1 ▾ PY  # Display Tables in UC",
        '2 ▾ PY  spark.sql("SHOW SCHEMAS")',
        "3 ▾ PY  display(spark.sql(...))",
    ], 35)
    for i, line in enumerate(box):
        left = ["My home", "  ▸ Shared", "  ▸ Repos", "", "", "", "", ""][i]
        f.cells(left, " " + line, "")
    f.cells("", "  the conversation is a tab, so it is", "")
    f.cells("", "  not on screen while you read code", "")
    f.cells("", "", "")
    f.cells("", "  Ask ▾    Add to chat    Open in DBX ↗", "session FACTS only")
    f.divider()
    f.cells("no conversation here", "⌘I opens facts, not a place to talk", "")
    f.bottom()
    return f.lines()


def s2_target() -> list[str]:
    """Target: document in the centre, conversation on the right, both in context."""
    f = Frame()
    f.top()
    f.full(topbar("⌘K   ▤   ◫   model ▾ flash-3.8   ready"))
    f.divider()
    f.cells("FILES", "display_unity_catalog_tables  PY", "ASSISTANT        ＋  ⧉  ✕")
    f.cells("", "⟳   ↗   Ask ▾   ⤢", "")
    f.divider()
    f.cells("My home", "1 ▾ PY  # Display Tables in UC", "in context: display_unity_c…")
    f.cells("  ▸ Shared", "       Read samples with Spark.", "────────────────────────────")
    f.cells("  ▸ Repos", "", "you   show the schemas as a t…")
    f.cells("  * agent_scratch", "2 ▾ PY  for s in spark.sql(\"SHOW…", "")
    f.cells("", "", "agent  Reading samples…")
    f.cells("", "3 ▾ PY  display(spark.sql(f\"SEL…", " ▸ read_notebook 4.2s  done")
    f.cells("", "        samples.{s}.trips LIMIT 5", " ▸ run_python    1.8s  done")
    f.cells("", "", "────────────────────────────")
    f.cells("", "", "I found 6 schemas. The table:")
    f.cells("", "", "  [6 schemas × 2 columns]")
    f.cells("", "", "")
    f.cells("", "", "⏸ approval: write outside")
    f.cells("", "", "   ../../Shared/report")
    f.cells("", "", "")
    f.cells("", "", "┌──────────────────────────┐")
    f.cells("", "", "│ @ objects, / commands    │")
    f.cells("", "", "│                  Send ▾  │")
    f.cells("", "", "└──────────────────────────┘")
    f.cells("", "", "model ▾ flash-3.8    ⌘⇧M")
    f.bottom()
    return f.lines()


def s3_narrow() -> list[str]:
    """Narrow: the assistant is a drawer over the document, opened from the top bar."""
    f = Frame((92,))
    f.top()
    f.full(topbar("⌘K  ▤  ◫  ⌘J assistant"))
    f.divider()
    for line in [
        "display_unity_catalog_tables      PY   ⟳   ↗   Ask ▾      ⌘J ◫",
        "─" * 92,
        "1  ▾ PY   # Display Tables from Unity Catalog",
        "",
        "2  ▾ PY   for s in spark.sql(\"SHOW SCHEMAS IN samples\"):",
        "             print(s.schemaName)",
        "",
        "3  ▾ PY   display(spark.sql(f\"SELECT * FROM samples.{s}.trips\"))",
        "",
        "the assistant is closed at this width: opened, it would cover the code.",
        "⌘J toggles it, and the key is on the bar, so it is always recoverable.",
    ]:
        f.full(line)
    f.bottom()
    return f.lines()


def s4_states() -> list[str]:
    """The assistant pane's four states, side by side."""
    cols = (24, 24, 24, 24)
    titles = ("EMPTY (NO SESSION)", "STREAMING", "WAITING FOR YOU", "FAILED")
    bodies = [
        ("no session yet", "↵ in the document asks", "about it", "", "▸ what does this do?",
         "▸ find the bug in cell 2", "▸ document this notebook"),
        ("you   show the schemas", "agent Reading samples…", "▸ read_nb 4.2s done", "▸ run_py 1.8s done",
         "──────────────────", "I found 6 schemas.", "▮"),
        ("⏸ approval required", "write outside folder", "../../Shared/report", "", "[Allow once]",
         "[Allow session]", "[Deny]", "recorded in the audit"),
        ("✕ the provider refused", "google-vertex said:", "403 PERMISSION_DENIED", "", "[Retry]",
         "[Change model]", "the turn kept its pin", ""),
    ]
    f = Frame(cols)
    f.top()
    f.cells(*titles)
    f.divider()
    for i in range(8):
        f.cells(*[(b[i] if i < len(b) else "") for b in bodies])
    f.bottom()
    return f.lines()


def s5_model() -> list[str]:
    """The model control: in the composer, and the one popover it opens."""
    head = Frame((94,))
    head.top()
    head.full(topbar("⌘K   ▤   ◫   model ▾ flash-3.8   ready"))
    head.divider()
    for line in [
        "",
        " display_unity_catalog_tables                              PY   ⟳  ↗",
        " ────────────────────────────────────────────────────────────────────",
        " 1  ▾ PY  for s in spark.sql(\"SHOW SCHEMAS IN samples\"):",
        " 2  ▾ PY  display(spark.sql(f\"SELECT * FROM samples.{s}.trips\"))",
        "",
        " ┌──────────────────────────────────────────────────────────────────┐",
        " │ @ objects   / commands        model ▾ flash-3.8     Send ▾       │",
        " └──────────────────────────────────────────────────────────────────┘",
    ]:
        head.full(line)
    head.bottom()

    pop = Frame((78,))
    pop.top()
    pop.full("SEARCH                       current: gemini-3.8-flash")
    pop.divider()
    pop.full("▾ THIS SESSION                                    3 of 3")
    pop.full("✓ gemini-3.8-flash      vertex · 1M ctx · 64k out · key ✓")
    pop.full("○ claude-sonnet-5       gateway · 200k · 32k out · on")
    pop.full("○ gpt-5.6-sol           gateway · 400k · 32k out · on")
    pop.divider()
    pop.full("▾ YOUR PROVIDERS                                  1 of 2")
    pop.full("○ gpt-4.1               openai · key expired 2h ago")
    pop.full("✕ kimi-k3-max           no key · add one")
    pop.divider()
    pop.full("▸ NOT AVAILABLE HERE (2)")
    pop.divider()
    pop.full("↑↓ move   ⏎ pin for the next turn   ⌘⏎ keep open   esc")
    pop.full("a switch never retargets a turn that is already running")
    pop.bottom()
    return head.lines() + [""] + pop.lines()


def s6_files() -> list[str]:
    """The Files pane as a list, with the metadata Databricks shows."""
    f = Frame((42, 52))
    f.top()
    f.full(topbar("⌘K   ▤   ◫   model ▾ flash-3.8"))
    f.divider()
    f.cells(" FILES      ⌕ search   ⟳ ⇪ ＋", " Workspace › Users › me          ▤ list")
    f.cells(" Tree view: ON", " ────────────────────────────────────────────")
    f.cells(" ▾ My home", " Name                 Type      Owner  Upd")
    f.cells("   ▸ agent_scratch", " ▸ agent_scratch      Folder    me     now")
    f.cells("   ▸ e2e_outside_fence", " ▸ e2e_outside_fence  Notebook  me     2h")
    f.cells(" ▾ Repos", " ▸ display_unity_cat  Notebook  me     1d")
    f.cells("   ▾ edgedata", " ▸ demo              Folder    me     3d")
    f.cells("     demo.py", " ▸ edgedata          Repo      me     5d")
    f.cells(" ▸ Shared", "")
    f.cells("", " 5 items · sorted by name · filter: all")
    f.cells(" * Favorites", "")
    f.cells("   agent_scratch", " drop a file anywhere here to import it")
    f.cells(" x Trash", "")
    f.bottom()
    return f.lines()


def s7_nav_map() -> list[str]:
    """Navigation: five doors, one document.

    One box, one connector column. Five boxes side by side would be a truer picture and a worse
    diagram: at this size the eye cannot follow five vertical joins, and the alignment checker cannot
    tell a neighbour's border from text that overflows.
    """
    doors = [
        ("Files", "tree / list", "┐", ""),
        ("Catalog", "tree", "┤", ""),
        ("⌘K palette", "any object", "┼", "one Doc"),
        ("a tool call", "inside a turn", "┤", "kind + ref + rev"),
        ("@-mention", "in the composer", "┘", ""),
    ]
    inner = 66
    joint = 40          # the column every connector lands on

    def row(text: str) -> str:
        return V + " " + fit(text, inner - 2) + " " + V

    out = [TL + H * inner + TR, row("FIVE DOORS, ONE DOCUMENT"), LT + H * inner + RT, row("")]
    for i, (name, sub, glyph, right) in enumerate(doors):
        lead = f"{name:<14}{sub}"
        # dashes run from the end of the label to the connector column, so the join is always vertical
        dashes = H * max(1, joint - 2 - len(lead))
        line = f"  {lead}{dashes}{glyph}"
        if right:
            line = f"{line}{H * 2}▶ {right}"
        out.append(row(line))
    out.append(row(""))
    out.append(LT + H * inner + RT)
    out.append(row("  Files and the palette OPEN a document; a tool call and an"))
    out.append(row("  @-mention ADD one to the conversation. All five produce the"))
    out.append(row("  same Doc, so the tab strip, the tree selection and the dock"))
    out.append(row("  cannot disagree about what is open."))
    out.append(BL + H * inner + BR)
    return out


SCREENS = [
    ("1 · Today: the conversation is a tab", s1_today,
     "Opening a file replaces the transcript. The inspector on the right is read-only metadata, so\n"
     "there is nowhere to type while you are looking at code."),
    ("2 · Target: the conversation is a pane beside the document", s2_target,
     "The document keeps the centre and the conversation keeps the right, and both are about the same\n"
     "object. `in context:` is the binding, not decoration: it changes when you change focus."),
    ("3 · Narrow: one zone at a time", s3_narrow,
     "Below 1180 px the assistant is a drawer over the document, opened by `⌘J`. It never opens by\n"
     "itself: an overlay that appears unasked hides the code."),
    ("4 · The four states of the assistant pane", s4_states,
     "Every state names a next action. A failure keeps the turn's model pin and offers the only two\n"
     "things that can help: retry, or a different model."),
    ("5 · The model, always one control away", s5_model,
     "The picker is in the composer as well as in the top bar, so choosing a model does not depend on a\n"
     "shortcut. It is one component, so the two triggers cannot disagree about the current model."),
    ("6 · Files: a list with the metadata that decides what to open", s6_files,
     "A tree answers *where*; a list answers *which*. Databricks offers both, as does this: the same\n"
     "rail, one toggle, and Favorites and Trash anchored where they do not move."),
    ("7 · Navigation: five doors, one document", s7_nav_map,
     "Every entry point produces the same `Doc`, so the tab strip, the tree selection and the assistant\n"
     "binding cannot disagree about what is open."),
]


def render() -> str:
    return "\n".join(block(t, fn(), note) for t, fn, note in SCREENS)


def check() -> int:
    """The same rules `verify-spec-ascii.mjs` applies, so --check needs no node."""
    problems = 0
    for title, fn, _note in SCREENS:
        rows = fn()
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                if ch != TL:
                    continue
                right = row.find(TR, x + 1)
                if right < 0:
                    print(f"UNCLOSED {title}:{y + 1} box at column {x}")
                    problems += 1
                    continue
                close = next((j for j in range(y + 1, len(rows))
                              if len(rows[j]) > right and rows[j][x] == BL and rows[j][right] == BR), -1)
                if close < 0:
                    print(f"UNCLOSED {title}:{y + 1} box at column {x} (width {right - x + 1})")
                    problems += 1
                    continue
                for j in range(y + 1, close):
                    r = rows[j]
                    left_ch = r[x] if x < len(r) else ""
                    right_ch = r[right] if right < len(r) else ""
                    if left_ch not in "│├┌└┬┴┼▼▲▶◀":
                        print(f"LEFT     {title}:{j + 1} expected a border at {x}, found {left_ch!r}")
                        problems += 1
                    if right_ch not in "│┤┐┘┬┴┼▼▲▶◀":
                        print(f"RIGHT    {title}:{j + 1} expected a border at {right}, found {right_ch!r}")
                        problems += 1
    print(f"{len(SCREENS)} screens · {problems} problem(s)")
    return problems


def main(argv: list[str]) -> int:
    if "--check" in argv:
        return 1 if check() else 0
    body = render()
    if "--write" not in argv:
        print(body)
        return 0
    text = DOC.read_text()
    if BEGIN not in text or END not in text:
        print(f"{DOC} has no marker pair", file=sys.stderr)
        return 2
    head, rest = text.split(BEGIN, 1)
    _old, tail = rest.split(END, 1)
    DOC.write_text(f"{head}{BEGIN}\n\n{body}\n{END}{tail}")
    print(f"wrote {DOC.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
