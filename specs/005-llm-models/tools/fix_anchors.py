#!/usr/bin/env python3
"""Rewrite broken in-document anchors to the slug GitHub actually generates.

The verifier (`verify-spec-links.mjs`) drops punctuation before collapsing whitespace, so a heading
"E8 · The picker is two `<select>` elements" slugs to `e8-the-picker-is-two-select-elements` — one
hyphen, not two. Authoring those by hand is a losing game, so this repairs them by matching on the
letters and digits only, which is stable under every punctuation choice.

    python3 tools/fix_anchors.py            # rewrite
    python3 tools/fix_anchors.py --check    # report only
"""
from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOCS = HERE.parent
FENCE = re.compile(r"^```", re.M)
LINK = re.compile(r"\[([^\]]*)\]\(([^)\s]+)\)")


def slug(heading: str) -> str:
    """Mirror of the JS verifier's slug(): strip emphasis, drop punctuation, collapse spaces."""
    s = heading.strip().lower()
    s = re.sub(r"[`*_]", "", s)
    s = "".join(ch for ch in s if ch.isalnum() or ch.isspace() or ch == "-")
    s = s.strip()
    return re.sub(r"\s+", "-", s)


def loose(s: str) -> str:
    """Letters and digits only: the invariant part of a slug, whatever punctuation was used."""
    s = unicodedata.normalize("NFKC", s).lower()
    return "".join(ch for ch in s if ch.isalnum())


def headings(path: Path) -> list[tuple[str, str]]:
    """(slug, loose) for every heading outside a fenced block."""
    out, fenced = [], False
    for line in path.read_text().split("\n"):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            out.append((slug(m.group(2)), loose(m.group(2))))
    return out


def main() -> int:
    check = "--check" in sys.argv
    index = {p.name: headings(p) for p in DOCS.glob("*.md")}
    by_loose: dict[str, dict[str, str]] = {
        name: {lo: sl for sl, lo in rows} for name, rows in index.items()
    }
    fixed = broken = 0

    for path in sorted(DOCS.glob("*.md")):
        text = path.read_text()
        # keep fenced code untouched: a link inside an example is not a link
        parts = re.split(r"(```[\s\S]*?```)", text)

        def repair(m: re.Match) -> str:
            nonlocal fixed, broken
            label, target = m.group(1), m.group(2)
            if re.match(r"^(https?:|mailto:)", target):
                return m.group(0)
            rel, _, anchor = target.partition("#")
            if not anchor:
                return m.group(0)
            target_file = rel or path.name
            target_file = target_file.split("/")[-1]
            rows = index.get(target_file)
            if not rows:
                return m.group(0)
            if any(sl == anchor for sl, _ in rows):
                return m.group(0)  # already correct
            want = loose(anchor)
            for slug_, lo in rows:
                if lo == want:
                    fixed += 1
                    if not check:
                        print(f"  {path.name}: #{anchor} -> #{slug_}")
                    return f"[{label}]({rel + '#' if rel else '#'}{slug_})"
            broken += 1
            print(f"  {path.name}: NO MATCH for #{anchor} in {target_file}", file=sys.stderr)
            return m.group(0)

        for i in range(0, len(parts)):
            if i % 2 == 0:
                parts[i] = LINK.sub(repair, parts[i])
        new = "".join(parts)
        if new != text and not check:
            path.write_text(new)

    print(f"{'checked' if check else 'fixed'}: {fixed} repaired, {broken} unmatched")
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
