#!/usr/bin/env python3
"""Summarise exam results.

    python report.py baseline                 # one batch
    python report.py baseline v2 --md         # compare batches (markdown table)
    python report.py baseline --fails         # list failed checks per run
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RES = Path(__file__).resolve().parent / "results"


def load(batch: str) -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted((RES / batch).glob("*.json"))]


def last_event(batch: str, r: dict) -> str:
    p = RES / batch / f"{r['mission']}__{r['variant']}__{r.get('tag', r['model'])}.events.jsonl"
    reason = "?"
    if p.exists():
        for line in p.read_text().splitlines():
            try:
                e = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if e.get("type") == "step_finish":
                reason = e["part"].get("reason", "?")
            elif e.get("type") == "result":
                reason = "exit%s" % e.get("exitCode")
    return reason


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    md = "--md" in sys.argv
    fails = "--fails" in sys.argv
    batches = args or [d.name for d in RES.iterdir() if d.is_dir()]
    for b in batches:
        rs = load(b)
        if not rs:
            continue
        tot = sum(r["score"] for r in rs)
        den = sum(r["total"] for r in rs)
        print(f"\n## {b}: {tot}/{den} = {round(100 * tot / max(den, 1), 1)}%")
        if md:
            print("| Mission | Variant/model | Score | Tool calls | Tokens | Time | Last stop |")
            print("|---|---|---|---|---|---|---|")
        for r in rs:
            line = (f"{r['mission']} {r['variant']}/{r.get('tag', r['model'])}", f"{r['score']}/{r['total']} ({r['pct']}%)",
                    r.get("tool_calls"), r.get("tokens"), f"{r['wall_seconds']}s", last_event(b, r), r.get("rate_limited"))
            print("| " + " | ".join(map(str, line)) + " |" if md else
                  f"{line[0]:<34} {line[1]:<14} calls={line[2]} tok={line[3]} {line[4]} stop={line[5]} 429s={line[6]}"
                  f"  tools={r.get('tools_used')}")
            if fails:
                for c in r.get("checks", []):
                    if not c["passed"]:
                        print(f"      x [{c['weight']}] {c['name']}  {c['detail'][:90]}")


if __name__ == "__main__":
    main()
