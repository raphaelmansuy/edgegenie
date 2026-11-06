#!/usr/bin/env python3
"""Refresh every <!-- BEGIN:name --> ... <!-- END:name --> block in README.md and docs/*.md
from the saved results, so documents never drift from the data.

    python3 exams/inject_tables.py
"""
import re
from pathlib import Path

from make_tables import blocks

ROOT = Path(__file__).resolve().parents[1]
B = blocks()
for f in [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]:
    t = f.read_text()
    def sub(m):
        name = m.group(1)
        body = B.get(name, "")
        return f"<!-- BEGIN:{name} -->\n{body.strip() or '_Not run yet._'}\n<!-- END:{name} -->"
    new = re.sub(r"<!-- BEGIN:(\w+) -->.*?<!-- END:\1 -->", sub, t, flags=re.S)
    if new != t:
        f.write_text(new); print("updated", f.relative_to(ROOT))
