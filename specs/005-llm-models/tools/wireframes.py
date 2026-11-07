#!/usr/bin/env python3
"""Render the 005 wireframes on a strict character grid.

Why a generator instead of hand-drawn ASCII: a box that is one character out of alignment looks
broken, and the defect is invisible in a diff. Every box here measures its own content, so a border
cannot drift — alignment becomes a property of the construction, not of the author's eye.

Run:  python3 tools/wireframes.py --write    # regenerate the block inside the marker pair
      python3 tools/wireframes.py --check    # exit 1 if a rendered box does not close
      python3 tools/wireframes.py            # print, for review
"""
from __future__ import annotations

import sys
from pathlib import Path

H, V = "─", "│"
TL, TR, BL, BR = "┌", "┐", "└", "┘"
LT, RT, TT, BT = "├", "┤", "┬", "┴"

TOP_X = 34      # the chip's x in the topbar; every popover hangs from here
GAP = "  "      # between the glyph column and the name column
NAME_W = 22     # the name column, so facts line up down the list


def cell(s: str) -> int:
    """Display width. ASCII art here is deliberately ASCII + box drawing + a few symbols, all
    single-cell, so `len` is the width. Asserted rather than assumed."""
    return len(s)


class Box:
    """A box that measures its content. `inner` is the widest line placed in it."""

    def __init__(self, title: str = "", right: str = "", pad: int = 2) -> None:
        self.title, self.right, self.pad = title, right, pad
        self.lines: list[str] = []

    def line(self, text: str = "") -> "Box":
        self.lines.append(text)
        return self

    def rule(self) -> "Box":
        self.lines.append(None)  # type: ignore[arg-type]
        return self

    @property
    def inner(self) -> int:
        body = max([cell(x) for x in self.lines if x is not None] + [0])
        head = 0
        if self.title:
            head += cell(f" {self.title} ") + 2
        if self.right:
            head += cell(f" {self.right} ") + 1
        if self.title and self.right:
            head += 4
        return max(body + self.pad * 2, head + 2, 24)

    def render(self, indent: int = 0) -> list[str]:
        w, pad = self.inner, self.pad
        pre = " " * indent
        out = [pre + TL + H * w + TR]
        if self.title or self.right:
            left = f" {self.title} " if self.title else ""
            right = f" {self.right} " if self.right else ""
            gap = w - cell(left) - cell(right)
            out.append(pre + V + left + " " * max(gap, 0) + right + V)
            out.append(pre + LT + H * w + RT)
        for line in self.lines:
            if line is None:
                out.append(pre + LT + H * w + RT)
                continue
            body = " " * pad + line
            out.append(pre + V + body + " " * max(w - cell(body), 0) + V)
        out.append(pre + BL + H * w + BR)
        return out


def topbar(model: str, state: str) -> list[str]:
    """The real topbar width (96) so the popover's hang point reads true."""
    w = 96
    row = [" "] * w
    row[0], row[1] = TL, TR
    for i in range(1, w - 1):
        row[i] = H
    row[0], row[w - 1] = TL, TR
    inner = "".join(row)

    def put(line: list[str], x: int, text: str) -> None:
        for i, ch in enumerate(text):
            if 0 <= x + i < w - 1:
                line[x + i] = ch

    mid = [" "] * w
    mid[0], mid[w - 1] = V, V
    put(mid, 2, "◧ Databricks Coding Agents")
    put(mid, TOP_X, f"model ▾ {model}")
    x_state = TOP_X + cell(f"model ▾ {model}") + 2
    put(mid, x_state, state)
    put(mid, w - 17, "⌘K   ▤   ◫")
    bottom = list(inner)
    bottom[0], bottom[w - 1] = BL, BR
    return [inner, "".join(mid), "".join(bottom)]


def model_rows() -> Box:
    rows = [
        ("✓", "llama-4-maverick", "128k ctx · 8k out · measured"),
        ("○", "gpt-oss-120b", "128k ctx · 24k out · measured"),
        ("○", "qwen3-next-80b", "128k ctx · 10k out · measured"),
        ("○", "meta-llama-3-3-70b", "128k ctx · 8k out · measured"),
        ("◌", "claude-sonnet-4-5", "not enabled · ask an admin"),
    ]
    b = Box()
    b.line("▾ DATABRICKS · AI GATEWAY" + " " * 24 + "5 of 5")
    for glyph, name, facts in rows:
        b.line(f"{glyph} {name:<{NAME_W}}{facts}")
    b.rule()
    b.line("▾ YOUR PROVIDERS" + " " * 35 + "2 of 3")
    b.line("○ gemini-3.8-flash".ljust(2 + 1 + NAME_W) + "vertex · 1M ctx · key …7f3a")
    b.line("⚠ gpt-4.1".ljust(2 + 1 + NAME_W) + "openai · key expired 2h ago")
    b.line("✕ claude-sonnet-4-5".ljust(2 + 1 + NAME_W) + "anthropic · no key · add one")
    b.rule()
    b.line("▸ NOT AVAILABLE HERE (1)")
    return b


def picker() -> list[str]:
    b = Box(title="", pad=2)
    b.line("SEARCH".ljust(44) + "current: llama-4-maverick")
    b.rule()
    inner = model_rows()
    for line in inner.lines:
        b.lines.append(line)
    b.rule()
    b.line("↑↓ move  ⏎ select  ⌘⏎ keep open  esc close")
    b.line("source: workspace · keys: 2 · updated 12s ago")
    return b.render(indent=TOP_X)


def filtered() -> list[str]:
    b = Box(pad=2)
    b.line("gemin▏".ljust(50) + "3 matches")
    b.rule()
    b.line("▾ YOUR PROVIDERS")
    b.line("▸○ ".ljust(2) + f"{'gemini-3.8-flash':<{NAME_W}}" + "vertex · 1M ctx · key …7f3a")
    b.line(" ○ ".ljust(2) + f"{'gemini-3.8-pro':<{NAME_W}}" + "vertex · 1M ctx · key …7f3a")
    b.rule()
    b.line("▾ DATABRICKS · AI GATEWAY — 1 match")
    b.line(" ○ ".ljust(2) + f"{'gemma-3-12b':<{NAME_W}}" + "not served here")
    b.rule()
    b.line("↑↓ move  ⏎ select  ⌘⏎ keep open  esc close")
    b.line("gemini · matched name · 2 selectable · 1 unavailable")
    return b.render(indent=TOP_X)


def inspector() -> list[str]:
    b = Box(title="INSPECTOR", right="⌘I")
    b.line("MODEL")
    b.line("  gemini-3.8-flash".ljust(46) + "○ available")
    b.line("  google_vertex / google/gemini-3.8-flash")
    b.line()
    b.line("  Provider     Google Vertex AI (your key)")
    b.line("  Wire         vertex_native")
    b.line("  Endpoint     …/locations/global/endpoints/openapi")
    b.line("  Context      1,000,000        documented")
    b.line("  Max output      30,000        documented")
    b.line("  Tools        yes · signature round-trip required")
    b.line("  Key          …7f3a · yours · project mobioos-506015")
    b.line()
    b.line("  THIS SESSION")
    b.line("  4 turns · 2 on llama-4-maverick · 2 on gemini-3.8-flash")
    b.line("  ▲ the switch was at turn 3. Earlier turns are not")
    b.line("    retargeted.")
    b.line()
    b.line("  WHAT THIS DOES NOT CHANGE")
    b.line("  The agent still writes only to /Users/me/agent_scratch")
    b.line("  and schema main.agent_ab12ef34.")
    b.line()
    b.line("  [ Change model ]  [ Test connection ]  [ Manage keys ]")
    return b.render()


def providers() -> list[str]:
    b = Box(title="Providers and keys", right="⌘,   esc")

    def section(head: str, state: str, rows: list[str]) -> None:
        b.line(head.ljust(51) + state)
        b.rule()
        for r in rows:
            b.line("  " + r)
        b.line()

    section("Databricks AI Gateway", "workspace token · managed", [
        "Available here   5 models · claude-sonnet-4-5 not enabled",
        "Credential       your Databricks session (no key to manage)",
        "Last discovery   12 seconds ago             [ Refresh ]",
    ])
    section("Google Vertex AI", "● connected", [
        "Key          service account · project mobioos-506015 · …7f3a",
        "Added        2 November 2026 by raphael.mansuy@…",
        "Last used    3 minutes ago · 2 sessions",
        "Models (3)   gemini-3.8-flash  gemini-3.8-pro  gemini-3.5-flash",
        "                            [ Test ] [ Rotate ] [ Revoke ]",
    ])
    section("OpenAI", "⚠ key expired", [
        "Key          …9c41 · expired 2 hours ago (per the provider)",
        "Effect       gpt-4.1 and 2 other models unavailable to you",
        "                            [ Test ] [ Replace key ]",
    ])
    section("Anthropic", "✕ no key", [
        "Nothing configured. 4 models would become available.",
        "                            [ Add a key ]",
    ])
    b.rule()
    b.line("source: database · keys encrypted with kek-2026-11 · 2 of 4 usable")
    return b.render()


def add_key() -> list[str]:
    b = Box(title="Add a key · Google Vertex AI", right="esc")
    b.line("Paste the service-account JSON, or drop the .json file here.")
    b.line("It is encrypted before it is stored, and never shown again.")
    b.rule()
    inner = Box(pad=2)
    for t in [
        "{",
        '  "type": "service_account",',
        '  "project_id": "mobioos-506015",',
        '  "client_email": "vertex-express@mobioos-506015.iam.gserviceaccount.com",',
        '  "private_key": "-----BEGIN PRIVATE KEY-----\\n••••••\\n-----END …",',
        '  "token_uri": "https://oauth2.googleapis.com/token"',
        "}",
    ]:
        inner.line(t)
    for line in inner.render(indent=2):
        b.lines.append(line[2:].rstrip())
    b.rule()
    b.line("✓ type is service_account")
    b.line("✓ project_id mobioos-506015")
    b.line("✓ private_key parses as RSA" + " " * 18 + "[ masked ]")
    b.line()
    b.line("Which models should this key enable?")
    b.line("☑ gemini-3.8-flash    ☑ gemini-3.8-pro    ☐ gemini-3.5-flash")
    b.rule()
    b.line("Prompts and tool results leave your workspace: Google's")
    b.line("terms apply, not Unity Catalog.")
    b.rule()
    b.line("[ Test connection ]".rjust(40) + "   [ Save key ]")
    return b.render()


def degraded() -> list[str]:
    b = Box(title="SEARCH", right="⚠", pad=2)
    n = Box(pad=1)
    n.line("Keys cannot be saved: the model database is unreachable.")
    n.line("Databricks models work. External models need a key.")
    for line in n.render(indent=0):
        b.lines.append(line)
    b.rule()
    b.line("▾ DATABRICKS · AI GATEWAY".ljust(44) + "5 of 5")
    b.line("✓ llama-4-maverick    128k ctx · 8k out · measured")
    b.line("○ gpt-oss-120b        128k ctx · 24k out · measured")
    b.rule()
    b.line("▸ EXTERNAL — unavailable without a key store")
    b.rule()
    b.line("source: seed only · keys: not available")
    return b.render(indent=TOP_X)


def degraded_row() -> list[str]:
    b = Box(pad=1)
    b.line("▸⚠ gpt-4.1          openai · key expired 2 hours ago")
    b.line("   └ 401 Unauthorized: Incorrect API key provided.")
    b.line("     [ Replace key ]   [ Use another model ]")
    return b.render(indent=2)


def narrow() -> list[str]:
    b = Box(title="Model", right="● ready")
    b.line("Search")
    b.rule()
    b.line("▾ DATABRICKS · AI GATEWAY")
    b.line("✓ llama-4-maverick")
    b.line("    128k · 8k out · measured")
    b.line("○ gpt-oss-120b")
    b.line("    128k · 24k out · measured")
    b.rule()
    b.line("▾ YOUR PROVIDERS")
    b.line("○ gemini-3.8-flash")
    b.line("    vertex · 1M ctx · key …7f3a")
    b.line("⚠ gpt-4.1")
    b.line("    openai · key expired 2h ago")
    return b.render()


def section(title: str, body: list[str], note: list[str] | None = None) -> str:
    out = [f"### {title}", "", "```text", *body, "```", ""]
    if note:
        out += note + [""]
    return "\n".join(out)


def build() -> str:
    parts: list[str] = []

    parts.append(section(
        "Screen 1 · the topbar today",
        topbar("databricks-llama-4-maverick", "ready"),
        ["One `<select>` per session, its options formatted by `id.split(\"/\").pop()`: unsorted,",
         "ungrouped, no state, and two naming conventions in one list — see",
         "[01 E8](01-current-state.md#e8--the-picker-is-two-select-elements)."],
    ))

    tb = topbar("llama-4-maverick", "● ready")
    hang = [" " * TOP_X + V]
    parts.append(section(
        "Screen 2 · the picker, open",
        tb + hang + picker(),
        ["The popover hangs from the chip. The glyph column carries state so colour is never the",
         "only signal; the footer states the data source and how many providers are usable."],
    ))

    parts.append(section(
        "Screen 3 · filtered, focus entering the second group",
        tb + hang + filtered(),
        ["`▸` marks the focused row. A group with no match collapses to a count line inside its",
         "own group header, never disappearing — [U1](#screen-3--filtered-focus-entering-the-second-group)."],
    ))

    parts.append(section(
        "Screen 4 · the inspector (⌘I, and the only model facts surface below 1100 px)",
        inspector(),
        ["The per-turn breakdown is FR-10 made visible: a switch names the turn it took effect on,",
         "and earlier turns are explicitly not retargeted."],
    ))

    parts.append(section(
        "Screen 5 · providers and keys",
        providers(),
        ["The footer states the credential source. In degraded mode it reads",
         "`source: seed only — keys cannot be saved` and every key action is disabled with that reason."],
    ))

    parts.append(section(
        "Screen 6 · adding a service-account JSON key",
        add_key(),
        ["Validation runs per field on paste (K1), the private key is masked after validation (K2),",
         "and Test connection must pass before Save unless the user skips it with the error shown (K3/K4)."],
    ))

    parts.append(section(
        "Screen 7a · degraded: no database, the picker still opens",
        topbar("llama-4-maverick", "● ready") + [" " * TOP_X + V] + degraded(),
        ["C-5: a degraded app is not a broken app. Databricks models keep working and the reason",
         "external models are unavailable is stated, not implied."],
    ))

    parts.append(section(
        "Screen 7b · a degraded model row, focused",
        degraded_row(),
        ["The provider's own sentence, redacted, plus two actions — never \"internal error\". This is",
         "the failure mode [the ACP probe](../../docs/e2e/20_acp_config_probe.txt) §C recorded."],
    ))

    parts.append(section(
        "Screen 7c · narrow (≤ 820 px): the picker becomes a sheet",
        narrow(),
        ["Below 1100 px the chip is already hidden ([`styles.css:211-213`](../../apps/coding-agent/web/src/styles.css)),",
         "so the sheet is opened from the inspector's **Change model** and the palette command,",
         "both of which exist at every width."],
    ))

    return "\n".join(parts)


def check(text: str) -> int:
    """Sanity check on the rendered text: every box must close, and no line may be ragged.

    This is a cheap local guard. The authoritative check is
    `apps/coding-agent/web/scripts/verify-spec-ascii.mjs`, which parses the finished document — it is
    the one wired into CI, because it sees the files rather than this generator's own output.
    """
    bad = 0
    for i, line in enumerate(text.split("\n"), 1):
        stripped = line.rstrip()
        if stripped.strip().startswith(("│", "├")) and stripped and stripped[-1] not in "│┤":
            print(f"  line {i}: opens with a border but does not close: {stripped[-30:]!r}", file=sys.stderr)
            bad = 1
    return bad


BEGIN, END = "<!-- BEGIN GENERATED WIREFRAMES -->", "<!-- END GENERATED WIREFRAMES -->"


def write() -> int:
    """Regenerate the wireframes inside 07's marker pair."""
    doc = Path(__file__).resolve().parent.parent / "07-ux-ui-wireframes.md"
    text = build()
    bad = check(text)
    current = doc.read_text()
    if BEGIN not in current or END not in current:
        print(f"markers missing in {doc.name}", file=sys.stderr)
        return 2
    head, rest = current.split(BEGIN, 1)
    _, tail = rest.split(END, 1)
    doc.write_text(f"{head}{BEGIN}\n\n{text.strip()}\n\n{END}{tail}")
    print(f"wrote {len(text)} chars of wireframes into {doc.name}")
    return bad


if __name__ == "__main__":
    if "--write" in sys.argv:
        sys.exit(write())
    rendered = build()
    if "--check" in sys.argv:
        sys.exit(check(rendered))
    print(rendered)
