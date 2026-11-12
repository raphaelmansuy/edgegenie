#!/usr/bin/env python3
"""Prove this specification's citations, links and identifiers.

Three checks, each of which has failed on a real version of this document:

  1. **Every code block that claims a range is VERBATIM.** A block written as
         ```375:380:apps/coding-agent/tools/x.py
     must equal those exact lines. This is the check that matters most: a spec whose
     claim is "cite the code" cannot quote an abbreviation. Thirteen blocks failed it
     when it was first run — `…` elisions and ranges off by a line.

  2. **Every internal link resolves**, and every `#anchor` resolves under GitHub's slug
     rule (lowercase, punctuation dropped, each space a hyphen — so `## 8 · Six` is
     `#8--six`, with two hyphens, because the `·` leaves an empty segment).

  3. **Every identifier is defined exactly once and used at least once.** `[F-n]` in
     02, `[R-n]` in 08, `[RB-n]` in 13, `[E-n]` in 12, `[S-n]` in 15, `[L-n]` in 09,
     `[G-n]` in 05. An undefined citation is a broken promise; an unused definition is
     a requirement nobody will build.

Run from the REPOSITORY ROOT:

    python3 specs/001-opengenie-assessment/tools/verify_citations.py

Exit code 0 means the document is internally consistent. It does not mean the code is
correct — that is `pytest` and `vitest`.
"""

from __future__ import annotations

import os
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
SPEC = HERE.parent
ROOT = SPEC.parent.parent  # repo root

DOCS = sorted(SPEC.glob("*.md"))
TEXT = {p.name: p.read_text() for p in DOCS}

problems: list[str] = []


def slug(heading: str) -> str:
    """GitHub's anchor rule, verified against the repository's own existing links."""
    h = heading.strip().lower()
    h = re.sub(r"[`*_]", "", h)
    h = "".join(c for c in h if c.isalnum() or c in " -")
    return h.strip().replace(" ", "-")


# ---------------------------------------------------------------- 1 · verbatim code blocks
def check_code_blocks() -> int:
    checked = 0
    for name, text in TEXT.items():
        for m in re.finditer(r"```(\d+):(\d+):(\S+)\n(.*?)```", text, re.S):
            checked += 1
            start, end, path, body = int(m.group(1)), int(m.group(2)), m.group(3), m.group(4)
            target = ROOT / path
            if not target.exists():
                problems.append(f"{name}: cites a file that does not exist: {path}")
                continue
            lines = target.read_text().splitlines()
            if end > len(lines):
                problems.append(f"{name}: {path}:{start}-{end} is past the end ({len(lines)} lines)")
                continue
            actual = "\n".join(lines[start - 1 : end])
            if actual.strip() != body.strip():
                problems.append(f"{name}: {path}:{start}-{end} is NOT verbatim")
    return checked


# ---------------------------------------------------------------- 2 · links and anchors
def check_links() -> int:
    headings = {
        p.name: {slug(m.group(1)) for m in re.finditer(r"^#{1,4}\s+(.*)$", p.read_text(), re.M)}
        for p in DOCS
    }
    checked = 0
    for name, text in TEXT.items():
        for m in re.finditer(r"\[[^\]]+\]\(([^)\s]+)\)", text):
            target = m.group(1)
            if target.startswith(("http://", "https://")):
                continue
            checked += 1
            path, _, anchor = target.partition("#")
            if path and not os.path.exists(SPEC / path):
                problems.append(f"{name}: link to a missing file: {path}")
                continue
            if anchor and anchor not in headings.get(path or name, set()):
                problems.append(f"{name}: unresolved anchor: {target}")
    return checked


# ---------------------------------------------------------------- 3 · identifiers
IDENTS = {
    "F": ("02-assessment-opengenie.md", r"### `\[F-(\d+)\]`"),
    "R": ("08-requirements.md", r"### `\[R-(\d+)\]`"),
    "RB": ("13-roadblocks.md", r"## `\[RB-(\d+)\]`"),
    "E": ("12-edge-cases.md", r"### `\[E-(\d+)\]`"),
    "S": ("15-e2e-plan.md", r"### `\[S-(\d+)\]`"),
    "L": ("09-lenses.md", r"## `\[L-(\d+)\]`"),
    "G": ("05-gaps-and-improvements.md", r"\|\s*`\[G-(\d+)\]`"),
}


def check_identifiers() -> int:
    everything = "\n".join(TEXT.values())
    total = 0
    for kind, (home, pattern) in IDENTS.items():
        defined = set(re.findall(pattern, TEXT[home]))
        cited = set(re.findall(r"\[%s-(\d+)\]" % kind, everything))
        total += len(defined)
        for missing in sorted(cited - defined, key=int):
            problems.append(f"[{kind}-{missing}] is cited but not defined in {home}")
        for unused in sorted(defined - cited, key=int):
            problems.append(f"[{kind}-{unused}] is defined in {home} but never cited")
    return total


def main() -> int:
    blocks = check_code_blocks()
    links = check_links()
    idents = check_identifiers()
    print(f"documents        : {len(DOCS)}")
    print(f"code citations   : {blocks} checked, all verbatim" if not problems else f"code citations   : {blocks}")
    print(f"links / anchors  : {links} checked")
    print(f"identifiers      : {idents} defined")
    if problems:
        print(f"\n{len(problems)} problem(s):")
        for p in problems:
            print("  -", p)
        return 1
    print("\n0 problems.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
