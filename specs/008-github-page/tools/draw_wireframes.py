#!/usr/bin/env python3
"""Draw the wireframes in `04-wireframes.md` on an exact character grid.

A wireframe typed by hand drifts: one character lost in an edit and every box below it is a pixel out.
This script owns the geometry instead, and the geometry has one rule: **every interior row is exactly
the interior width**. Rows are composed from cells and padded or clipped to the millimetre, so a border
can never be overwritten and a text run can never escape.

The grammar is the checker the repository already trusts
(`apps/coding-agent/web/scripts/verify-spec-ascii.mjs`), which parses each `┌` and requires that:

  - the top border is only `─` and `┬` between `┌` and `┐` — so no title sits on a border;
  - some later line closes the box with `└` and `┘` at the same columns;
  - every line between has a border at both columns, and nothing but drawing characters to the right.

    python3 specs/008-github-page/tools/draw_wireframes.py          # rewrite 04-wireframes.md
    python3 specs/008-github-page/tools/draw_wireframes.py --check  # exit 1 if the file is stale
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = HERE.parent
ROOT = SPEC.parent.parent
TARGET = SPEC / "04-wireframes.md"

DESKTOP = 98  # drawing width in characters, about 11 px each
PHONE = 46  # the narrowest supported viewport, rounded to a grid
DRAWING = set("│┤┐┘┬┴┼─┌└├ ")


# ----------------------------------------------------------------------------------- composition
def cell(text: str, width: int) -> str:
    """Exactly `width` characters: padded right, or clipped. The single source of alignment."""
    if width <= 0:
        return ""
    return text[:width].ljust(width)


class Rule:
    """A full-width horizontal rule inside a frame: `├───┴───┤`.

    Kept as a marker rather than as text, so `frame()` can paint it across the frame's own borders
    instead of nesting it one character inside them.
    """

    def __init__(self, left: str = "├", mid: str = "┼", right: str = "┤", stops: list[int] | None = None):
        self.left, self.mid, self.right, self.stops = left, mid, right, stops or []


def draw_rule(width: int, *, left: str, mid: str, right: str, stops: list[int]) -> str:
    """`width` characters wide, with `mid` at each stop column (0-based, including the borders)."""
    out = []
    for i in range(width):
        if i == 0:
            out.append(left)
        elif i == width - 1:
            out.append(right)
        elif i in stops:
            out.append(mid)
        else:
            out.append("─")
    return "".join(out)


def frame(rows: list[str | Rule], width: int = DESKTOP) -> str:
    """Close a list of interior rows in a box whose total width is `width`."""
    inner = width - 2
    body: list[str] = []
    for row in rows:
        if isinstance(row, Rule):
            body.append(draw_rule(width, left=row.left, mid=row.mid, right=row.right,
                                  stops=[s + 1 for s in row.stops]))
        else:
            body.append("│" + cell(row, inner) + "│")
    top = "┌" + "─" * inner + "┐"
    bottom = "└" + "─" * inner + "┘"
    return "\n".join([top, *body, bottom])


def columns(cells: list[tuple[str, int]]) -> str:
    """Interior cells side by side, each at an exact width, joined by nothing.

    A cell of width 1 is used as a divider, so `columns([(a, 20), ("│", 1), (b, 40)])` draws a rule
    between two panes without a second box.
    """
    return "".join(cell(text, w) for text, w in cells)


def split(avail: int, n: int) -> list[int]:
    """`n` pane widths that sum to exactly `avail`.

    Dividers and borders are *not* counted here: a box of total width `w` with `n` panes has
    `w - 2 - (n - 1)` columns left for content, so callers pass that.
    """
    base, extra = divmod(avail, n)
    return [base + (1 if i < extra else 0) for i in range(n)]


def bars(pairs: list[tuple[str, int]], width: int = 34) -> list[str]:
    """A small horizontal bar chart as text rows: label, a bar, a value."""
    out = []
    longest = max(len(label) for label, _ in pairs)
    for label, value in pairs:
        filled = round(width * value / 100)
        out.append(f" {label.ljust(longest)}   {'█' * filled}{'░' * (width - filled)}   {value}%")
    return out


# ------------------------------------------------------------------------------------- screens
def screen_route_order() -> str:
    rows = [
        ("1", "/", "Home", "what it is, why it exists, the three claims, the first look"),
        ("2", "/tour/", "Tour", "17 screenshots of the running app, captioned by width"),
        ("3", "/tutorial/", "Tutorial", "the 30-minute setup, rendered from docs/tutorial.md"),
        ("4", "/evidence/", "Evidence", "the exam results, with denominator and caveat"),
        ("5", "/install/", "Install", "the three ways to run it, and what each needs"),
        ("6", "/reference/", "Reference", "the docs and the five specifications, verbatim"),
        ("7", "/about/", "About", "who built it, why, and what else he builds"),
        ("-", "/404.html", "404", "the seven routes, in the site's own design"),
    ]
    inner = []
    for n, route, name, desc in rows:
        inner.append(columns([(f" {n:>2}  {route:<12}{name:<11}{desc}", DESKTOP - 2)]))
    return frame(inner)


def screen_home_first_screen() -> str:
    W = DESKTOP
    inner_w = W - 2
    nav_left = "  ◕ OpenGenie     Tour   Tutorial   Evidence   Install   Reference"
    nav_right = "[◐][◑][●]   GitHub"

    shot_w = inner_w - 6
    rows: list[str] = []
    rows.append(columns([(nav_left, inner_w - len(nav_right)), (nav_right, len(nav_right))]))
    rows.append(Rule())
    rows.append("")
    rows.append("   Apache-2.0   ·   Databricks App   ·   any model you can reach")
    rows.append("")
    rows.append("   Genie Code gives you one model.")
    rows.append("   You cannot choose it, and you cannot see the bill coming.")
    rows.append("")
    rows.append("   OpenGenie is a Databricks App that does the same work with the model")
    rows.append("   you pick, writes only inside the folder you name, and proves what it")
    rows.append("   did before it says done.")
    rows.append("")
    # two actions, side by side, as one divided strip rather than two boxes
    rows.append("   ┌────────────────────────┬──────────────────────────┐")
    rows.append("   │     Read the tour      │       Install it         │")
    rows.append("   └────────────────────────┴──────────────────────────┘")
    rows.append("      filled primary                outline")
    rows.append("")
    rows.append("   ┌" + "─" * shot_w + "┐")
    rows.append("   │" + cell("       the app at 1440 px: sessions and files · notebook · assistant dock", shot_w) + "│")
    rows.append("   │" + cell("       a real screenshot, not an illustration of one", shot_w) + "│")
    rows.append("   │" + cell("", shot_w) + "│")
    rows.append("   └" + "─" * shot_w + "┘")
    rows.append('   caption: "The three-pane shell at 1440 px. The dock is bound to the notebook."')
    rows.append("")
    return frame(rows)


def screen_home_claims() -> str:
    """Three equal panes inside one frame, divided by `┬`/`│`/`┴` — never a box inside a box."""
    W = DESKTOP
    inner_w = W - 2
    # a box of total width `pane_w` with 3 panes leaves pane_w - 2 - 2 content columns
    pane_w = inner_w - 2
    widths = split(pane_w - 4, 3)

    panes = [
        [
            "",
            " 1 · The model is yours",
            "",
            " 16 models from 4 providers,",
            " plus whatever the gateway",
            " serves, discovered live.",
            "",
            " seed/llm_models.yaml  →",
        ],
        [
            "",
            " 2 · The fence is real",
            "",
            " A write is allowed only in",
            " the folder and the schema",
            " you named. Anything else",
            " is ask, or deny.",
            "",
            " api/domain/scope.py  →",
        ],
        [
            "",
            " 3 · Proof, not promises",
            "",
            " A requirement counts as done",
            " only when a tool call proves",
            " it. A citation to a call that",
            " never happened is a verdict.",
            "",
            " api/domain/evidence.py  →",
        ],
    ]
    h = max(len(p) for p in panes)
    pane_w = inner_w - 2
    stops = []
    cursor = 0
    for w in widths[:-1]:
        cursor += w
        stops.append(cursor)
        cursor += 1

    rows = [" " + draw_rule(pane_w, left="┌", mid="┬", right="┐", stops=[s+1 for s in stops]) + " "]
    for r in range(h):
        rows.append(" │" + columns([
            (panes[0][r] if r < len(panes[0]) else "", widths[0]),
            ("│", 1),
            (panes[1][r] if r < len(panes[1]) else "", widths[1]),
            ("│", 1),
            (panes[2][r] if r < len(panes[2]) else "", widths[2]),
        ]) + "│ ")
    rows.append(" " + draw_rule(pane_w, left="└", mid="┴", right="┘", stops=[s+1 for s in stops]) + " ")
    rows.append("")
    rows.append(" Same tools, same rules, two models. 8 development tasks (M1-M8), one run each:")
    rows.append("")
    rows.extend(bars([("gpt-oss-120b", 39), ("Gemini 3.8 Flash", 86)], width=44))
    rows.append("")
    rows.append(" The caveat is on the card, not in a footnote: one run per model, and M2 has the")
    rows.append(" widest natural spread of the eight. Source, and the command that regenerates this,")
    rows.append(" are one link away on /evidence/.")
    return frame(rows)


def screen_home_honesty() -> str:
    rows = [
        "",
        " What this is not",
        "",
        " · Not a replacement for Genie's business-term understanding. Our exams named the tables.",
        " · Not a cost comparison. We measured tokens, not money, and hold no Genie usage history.",
        " · Not a hosted demo. The app needs your workspace token, so there is nothing to click.",
        " · Not a guarantee. One run per setup, small clean data, well-specified tasks.",
        "",
        " →  Every number above, with its source and the command that regenerates it.  [Evidence]",
        "",
        " ┌───────────────────────────────────────────────────────────────────────────────────────┐",
        " │ footer                                                                                │",
        " │  ◕ OpenGenie · Apache-2.0 · built 8 Nov 2026 from commit 39eeb2f                      │",
        " │  Pages: Tour · Tutorial · Evidence · Install · Reference · About                      │",
        " │  Elsewhere: GitHub · LinkedIn · EdgePii · EdgeQuake · the book                        │",
        " └───────────────────────────────────────────────────────────────────────────────────────┘",
    ]
    return frame(rows)


def screen_doc_page() -> str:
    """One frame divided into a 22-character rail and the content column."""
    W = DESKTOP
    inner_w = W - 2
    rail = 22
    gap = 1
    content = inner_w - rail - gap
    shot_w = content - 4

    left = [
        " On this page",
        " ─────────────",
        " The shell",
        "   The notebook",
        "   The dock",
        "   The picker",
        " The widths",
        "   1440",
        "   1100",
        "   800",
        " Themes",
        "",
        " ─────────────",
        " ← Evidence",
        " Tutorial →",
        "",
        " 200 px rail",
    ]
    right = [
        " Tour",
        " What the app looks like, at four widths, in both themes.",
        "",
        " ┌" + "─" * (shot_w - 2) + "┐",
        " │" + cell(" 1440 px · light", shot_w - 2) + "│",
        " │" + cell("", shot_w - 2) + "│",
        " │" + cell("   the screenshot, downscaled to the column", shot_w - 2) + "│",
        " │" + cell("", shot_w - 2) + "│",
        " └" + "─" * (shot_w - 2) + "┘",
        " Sessions and files on the left, the notebook in the centre, the",
        " assistant docked right and saying what it is bound to.",
        "",
        " ┌" + "─" * (shot_w - 2) + "┐",
        " │" + cell(" 1100 px · dark", shot_w - 2) + "│",
        " │" + cell("", shot_w - 2) + "│",
        " │" + cell("   ...", shot_w - 2) + "│",
        " │" + cell("", shot_w - 2) + "│",
        " └" + "─" * (shot_w - 2) + "┘",
        " 72 characters of measure, no rail, no advertising.",
    ]

    nav_left = "  ◕ OpenGenie    Tour  Tutorial  Evidence  Install  Reference"
    nav_right = "[◐][◑][●]  GitHub"
    rows = [columns([(nav_left, inner_w - len(nav_right)), (nav_right, len(nav_right))])]
    rows.append(Rule(stops=[rail]))
    body_h = max(len(left), len(right))
    for i in range(body_h):
        rows.append(columns([
            (left[i] if i < len(left) else "", rail),
            ("│", gap),
            (right[i] if i < len(right) else "", content),
        ]))
    rows.append(Rule(mid="┴", stops=[rail]))
    # the previous/next band spans the whole width: it belongs to the page, not to a pane, so no divider
    rows.append(" ← Evidence" + " " * (inner_w - 24) + "Tutorial →  ")
    return frame(rows)


def screen_tablet() -> str:
    W = 76
    inner_w = W - 2
    rows = [
        columns([("  ◕ OpenGenie", inner_w - 34), ("[☰ Menu]   [◐][◑][●]   GitHub", 34)]),
        Rule(),
        "",
        "  Tour",
        "  What the app looks like, at four widths, in both themes.",
        "",
        "  ┌" + "─" * (inner_w - 6) + "┐",
        "  │" + cell("       the screenshot, scaled to the column", inner_w - 6) + "│",
        "  └" + "─" * (inner_w - 6) + "┘",
        "",
        "  after pressing [☰ Menu]:",
        "",
        "  ┌" + "─" * (inner_w - 6) + "┐",
        "  │" + cell("   Home", inner_w - 6) + "│",
        "  │" + cell("   Tour          ← current", inner_w - 6) + "│",
        "  │" + cell("   Tutorial", inner_w - 6) + "│",
        "  │" + cell("   Evidence", inner_w - 6) + "│",
        "  │" + cell("   Install", inner_w - 6) + "│",
        "  │" + cell("   Reference", inner_w - 6) + "│",
        "  │" + cell("   About", inner_w - 6) + "│",
        "  └" + "─" * (inner_w - 6) + "┘",
        "",
        "  44 px rows, focus trapped, Escape closes. A sheet, not a squeezed row.",
    ]
    return frame(rows, W)


def screen_phone() -> str:
    W = PHONE
    inner_w = W - 2
    shot_w = inner_w - 6
    rows = [
        columns([("  ◕ OpenGenie", inner_w - 16), ("[☰] [◐][◑][●]", 16)]),
        Rule(),
        "",
        "  Tour",
        "  What the app looks like.",
        "",
        "  ┌" + "─" * shot_w + "┐",
        "  │" + cell(" 1440 px · light", shot_w) + "│",
        "  │" + cell(" ───────────────", shot_w) + "│",
        "  │" + cell("  swipe to pan", shot_w) + "│",
        "  │" + cell(" ───────────────", shot_w) + "│",
        "  └" + "─" * shot_w + "┘",
        "",
        "  The three-pane shell at 1440 px:",
        "  the notebook in the centre, the",
        "  assistant docked on the right.",
        "",
        Rule(),
        columns([("  ← Evidence", inner_w - 14), ("Tutorial →  ", 14)]),
    ]
    return frame(rows, W)


def screen_claim_card() -> str:
    W = DESKTOP - 8
    inner_w = W - 2
    rows = [
        columns([("  CL-3", inner_w - 22), ("value   86%", 22)]),
        "  " + "─" * (inner_w - 4),
        "  The model matters more than the tooling",
        "",
        "  Same agent, same tools, same rules, two models.",
        "",
    ]
    rows.extend(bars([("gpt-oss-120b", 39), ("Gemini 3.8 Flash", 86)], width=40))
    rows.extend([
        "",
        "  " + "─" * (inner_w - 4),
        "  how it was measured     8 development tasks (M1-M8), one run per model,",
        "                         scored on the live workspace: 60/152 and 130/152",
        "  what it does not prove  one run each; M2 has the widest natural spread",
        "  source                  exams/results/v5_gptoss/ · v5_gemini/",
        "  regenerate              python3 exams/make_tables.py",
    ])
    return frame(rows, W)


def screen_state_theme() -> str:
    return "\n".join([
        "",
        "   system ──press──► light ──press──► dark ──press──► system",
        "      │                │                │                 │",
        "      ▼                ▼                ▼                 ▼",
        "   follows OS       data-theme=light  data-theme=dark   attribute removed,",
        "   (no attribute)                                       follows OS again",
        "",
        '   first paint: <html data-theme="dark">, set by a nine-line inline script in <head>',
        "   no stylesheet-dependent flash, and no transition on the document element",
        "",
    ])


def screen_state_menu() -> str:
    rows = [
        "",
        "  open with Enter or Space",
        "         │",
        "         ▼",
        "  focus moves to the first item, and Tab stays inside",
        "         │",
        "         ├── Escape ──────────► close, focus returns to the button",
        "         ├── click outside ───► close, focus does not move",
        "         ├── choose an item ──► navigate, the button keeps :focus",
        "         └── resize ≥ 860px ──► close silently, no focus change",
        "",
        "  one event, one meaning.",
    ]
    return frame(rows, 76)


def screen_404() -> str:
    W = DESKTOP
    inner_w = W - 2
    nav_left = "  ◕ OpenGenie    Tour  Tutorial  Evidence  Install  Reference"
    nav_right = "[◐][◑][●]  GitHub"
    pad = "  "
    strip_w = inner_w - 4
    n1 = 4
    a = (strip_w - (n1 - 1) - 2) // n1
    w1 = [a] * (n1 - 1)
    w1.append(strip_w - 2 - (n1 - 1) - sum(w1))
    n2 = 3
    b = (strip_w - (n2 - 1) - 2) // n2
    w2 = [b, b, strip_w - 2 - (n2 - 1) - 2 * b]

    def buttons(widths: list[int], labels: list[str]) -> list[str]:
        top = pad + "┌" + "┬".join("─" * w for w in widths) + "┐"
        mid = pad + "│" + "│".join(cell(f" {lab}", w) for lab, w in zip(labels, widths)) + "│"
        bot = pad + "└" + "┴".join("─" * w for w in widths) + "┘"
        return [top, mid, bot]

    rows = [
        columns([(nav_left, inner_w - len(nav_right)), (nav_right, len(nav_right))]),
        Rule(),
        "",
        "  404",
        "  That page is not here. Nothing was lost; the link was wrong.",
        "",
    ]
    rows.extend(buttons(w1, ["Home", "Tour", "Tutorial", "Evidence"]))
    rows.extend(buttons(w2, ["Install", "Reference", "About"]))
    rows.append("")
    return frame(rows)


SCREENS: list[tuple[str, str, str]] = [
    (
        "## Route order",
        "The reading order. It drives the header, the footer, and the previous/next links (`[NAV-7]`).",
        screen_route_order(),
    ),
    (
        "## Screen 1. Home, desktop 1100 to 1600 px",
        "The first two viewports are the whole argument: identity, the problem, two actions, and one real "
        "screenshot of the product (`[PG-1]`, `[PG-3]`).",
        screen_home_first_screen(),
    ),
    (
        "## Screen 2. Home, continued: the three claims",
        "Each cell is a claim, a one-line reason, and a path to the file that implements it (`[PG-2]`), "
        "followed by the one measurement that motivates the page — with its caveat attached (`[CPT-2]`).",
        screen_home_claims(),
    ),
    (
        "## Screen 3. Home, continued: what it is not, and the footer",
        "The honesty block. It exists because the study's own limits are the page's credibility "
        "(`[PG-15]`, `[PG-16]`).",
        screen_home_honesty(),
    ),
    (
        "## Screen 4. Any document page (`/tour/`, `/tutorial/` and so on), desktop",
        "One frame divided into a 22-character contents rail and the content column. The rail exists only "
        "above 1100 px, and the measure never exceeds 72 characters (`[NAV-6]`).",
        screen_doc_page(),
    ),
    (
        "## Screen 5. Tablet, 860 px, the navigation collapses",
        "`[NAV-4]`. The contents rail is gone, the content takes the full width, and the header keeps "
        "identity and one menu button. The menu is a sheet of 44 px rows.",
        screen_tablet(),
    ),
    (
        "## Screen 6. Phone, 320 to 430 px",
        "`[AX-7]`. One column and no horizontal scroll on the page. A wide screenshot scrolls inside its "
        "own frame instead of being squashed to illegibility.",
        screen_phone(),
    ),
    (
        "## Screen 7. The evidence page, one claim card, annotated",
        "The most important component on the site "
        "([P3](01-five-whys.md#p3-two-glances-about-the-same-thing-cannot-share-a-slot)): the six facts a "
        "suspicious reader needs, and the caveat *inside* the card rather than after the table.",
        screen_claim_card(),
    ),
    (
        "## Screen 8. State: the theme, and the no-flash rule",
        "`[NAV-3]`. One attribute on `<html>`, set before first paint by an inline script that reads the "
        "same key the control writes.",
        screen_state_theme(),
    ),
    (
        "## Screen 9. State: the navigation menu, and one escape order",
        "`[NAV-4]`. One ordered meaning for Escape, the same discipline as "
        "[007 `KB-8`](../007-ux-ui-improve/03-requirements.md).",
        screen_state_menu(),
    ),
    (
        "## Screen 10. The 404",
        "`[PG-18]`. A real page: identity, the seven routes, and no apology longer than one line.",
        screen_404(),
    ),
]

HEADER = """# 04 · Wireframes (ASCII)

[Index](README.md) · prev: [03 Requirements](03-requirements.md) · next: [05 Diagrams](05-diagrams.md)

Every drawing below is **generated** on an exact character grid by
[`tools/draw_wireframes.py`](tools/draw_wireframes.py): one primitive composes each interior row to an
exact width, so a box cannot drift a character out in an edit. Then the drawings are verified
independently by the repository's own checker, which parses each box rather than comparing line lengths:

```bash
python3 specs/008-github-page/tools/draw_wireframes.py --check
cd apps/coding-agent/web && node scripts/verify-spec-ascii.mjs ../../../specs/008-github-page
```

The design widths behind the drawings are content `1100` px, the navigation breakpoint `860` px, and the
narrowest supported viewport `320` px. On the desktop drawings one character is about 11 px of the real
page.

---

"""

FOOTER = """
---

## What the drawings decided

| Drawing | The decision it fixes | Requirement |
|---|---|---|
| Screens 1–3 | The product screenshot sits above the second viewport, not after the findings | `PG-3` |
| Screen 2 | Three claims, each with a path to the code that implements it | `PG-2` |
| Screen 2 | The one measurement appears on the home page **with** its caveat | `CPT-2` |
| Screen 3 | The limits are a section of the home page, not a footnote on another one | `PG-15` |
| Screen 4 | One frame, two panes: the contents rail is a division, not a second box | `NAV-6` |
| Screen 5 | One button below 860 px, and a sheet of 44 px rows rather than a squeezed row | `NAV-4` |
| Screen 6 | A wide screenshot scrolls inside its frame; the page never scrolls sideways | `AX-7` |
| Screen 7 | Value, denominator, run count, model, caveat and command in one card | `CPT-2` |
| Screens 8–9 | Two state machines, each with one meaning per event | `NAV-3`, `NAV-4` |
| Screen 10 | A wrong link costs the reader one click, not a dead end | `PG-18` |
"""


def build() -> str:
    parts = [HEADER]
    for heading, blurb, art in SCREENS:
        parts.append(f"{heading}\n\n{blurb}\n\n```text\n{art}\n```\n\n")
    parts.append(FOOTER)
    return "".join(parts)


def main() -> int:
    text = build()
    if "--check" in sys.argv:
        current = TARGET.read_text(encoding="utf-8") if TARGET.is_file() else ""
        if current != text:
            print(f"stale: {TARGET.relative_to(ROOT)} — run the generator", file=sys.stderr)
            return 1
        print("04-wireframes.md is up to date")
        return 0
    TARGET.write_text(text, encoding="utf-8")
    print(f"wrote {TARGET.relative_to(ROOT)} ({len(text.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
