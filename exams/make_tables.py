#!/usr/bin/env python3
"""Build the results tables used in docs/ from exams/results/*/*.json (no hand-copied numbers).

    python make_tables.py > /tmp/tables.md
"""
from __future__ import annotations

import glob
import json
import sys
from collections import defaultdict
from pathlib import Path

R = Path(__file__).parent / "results"
SKIP = {"_invalid_port_collision", "_old_v1_pre_port_fix", "accidental_dbsql_only", "smoke_v5"}
DEV = [f"M{i}" for i in range(1, 9)]
HELD = ["X1", "X2", "X3"]


import re


def trial_of(batch: str) -> str:
    m = re.search(r"_(t\d+)$", batch)
    return m.group(1) if m else "t1"


def load(trials: bool = False, via: str = "kit"):
    """trials=False: first trial only (what the main tables use). trials=True: every trial."""
    rows = []
    for f in glob.glob(str(R / "*" / "*.json")):
        b = Path(f).parent.name
        if b in SKIP or b.startswith("_") or f.endswith(".events.jsonl"):
            continue
        d = json.load(open(f))
        if d.get("via", "kit") != via or d.get("valid") is False:
            continue
        d["_batch"] = b
        d["_trial"] = trial_of(b)
        if trials or d["_trial"] == "t1":
            rows.append(d)
    return rows


def full_totals(rows):
    """Denominator per task = the total of a perfect run (what is really achievable). Graders return
    early or list extra checks when an artifact is missing, so a failed run's own 'total' varies.
    If no run was perfect, fall back to the largest total seen."""
    perfect, biggest = {}, {}
    for d in rows:
        m = d["mission"]
        biggest[m] = max(biggest.get(m, 0), d["total"])
        if d["score"] == d["total"]:
            perfect[m] = min(perfect.get(m, 10**9), d["total"])
    return {m: perfect.get(m, biggest[m]) for m in biggest}


def agg(rows, missions):
    """-> {(agent, variant, model): {mission: (score,total,tokens,calls,secs)}}"""
    out = defaultdict(dict)
    ft = full_totals(rows)
    for d in rows:
        if d["mission"] in missions:
            k = (d.get("agent", "opencode"), d["variant"], d["model"])
            out[k][d["mission"]] = (min(d["score"], ft[d["mission"]]), ft[d["mission"]], d["tokens"], d["tool_calls"], d["wall_seconds"], d["_batch"])
    return out


def table(rows, missions, title):
    a = agg(rows, missions)
    if not a:
        return ""
    s = [f"**{title}**\n", "| Agent | Variant | Model | " + " | ".join(missions) + " | Total | Tokens |",
         "|---|---|---|" + "---|" * (len(missions) + 2)]
    for k in sorted(a, key=lambda k: (k[2], k[1], k[0])):
        cells, ts, tt, tok = [], 0, 0, 0
        for m in missions:
            if m in a[k]:
                sc, tot, t, *_ = a[k][m]
                cells.append(f"{round(100 * sc / tot)}%")
                ts += sc; tt += tot; tok += t
            else:
                cells.append("-")
        full = all(m in a[k] for m in missions)
        s.append(f"| {k[0]} | {k[1]} | {k[2]} | " + " | ".join(cells) +
                 f" | **{round(100 * ts / tt)}%** ({ts}/{tt}){'' if full else ' *partial*'} | "
                 + (f"{tok // 1000}k |" if tok else "n/a |"))
    return "\n".join(s) + "\n"


def matrix(rows, missions, title):
    """variant x (agent/model) -> total %, one number per cell."""
    a = agg(rows, missions)
    cols = sorted({(k[0], k[2]) for k in a})
    vs = sorted({k[1] for k in a})
    s = [f"**{title}**\n", "| Variant | " + " | ".join(f"{c[0]} / {c[1]}" for c in cols) + " |",
         "|---|" + "---|" * len(cols)]
    for v in vs:
        cells = []
        for c in cols:
            k = (c[0], v, c[1])
            if k in a:
                ts = sum(x[0] for x in a[k].values()); tt = sum(x[1] for x in a[k].values())
                part = "" if all(m in a[k] for m in missions) else "*"
                cells.append(f"{round(100 * ts / tt)}%{part}")
            else:
                cells.append("-")
        s.append(f"| {v} | " + " | ".join(cells) + " |")
    return "\n".join(s) + "\n\n(`*` = not every task was run)\n"


def repeat_table(rows_all, key, missions, title):
    """Per-trial totals for one (agent, variant, model), with mean and range."""
    ft = full_totals(rows_all)
    per = defaultdict(lambda: [0, 0])
    seen = defaultdict(dict)
    for d in rows_all:
        if (d.get("agent", "opencode"), d["variant"], d["model"]) == key and d["mission"] in missions:
            seen[d["_trial"]][d["mission"]] = min(d["score"], ft[d["mission"]])
    trials = sorted(t for t in seen if all(m in seen[t] for m in missions))
    if len(trials) < 2:
        return ""
    tot = sum(ft[m] for m in missions)
    s = [f"**{title}**\n", "| Task | " + " | ".join(trials) + " | Mean | Range |", "|---|" + "---|" * (len(trials) + 2)]
    for m in missions:
        v = [round(100 * seen[t][m] / ft[m]) for t in trials]
        s.append(f"| {m} | " + " | ".join(f"{x}%" for x in v) + f" | {round(sum(v) / len(v))}% | {min(v)}-{max(v)}% |")
    tt = [round(100 * sum(seen[t].values()) / tot, 1) for t in trials]
    s.append("| **Total** | " + " | ".join(f"**{x}%**" for x in tt) + f" | **{round(sum(tt) / len(tt), 1)}%** | **{min(tt)}-{max(tt)}%** |")
    return "\n".join(s) + "\n"


def blocks() -> dict[str, str]:
    """Named markdown blocks. docs/ reference them with <!-- BEGIN:name --> ... <!-- END:name -->."""
    rows, allrows = load(), load(trials=True)
    app_rows = load(via="app")
    cop = [d for d in rows if d.get("agent") == "copilot"]
    oc = [d for d in rows if d.get("agent", "opencode") == "opencode"]
    return {
        "app_dev": table(app_rows, DEV, "App HTTP path: development set (M1-M8)"),
        "app_agent014": table(app_rows, [f"M{i}" for i in range(9, 15)], "App HTTP path: agent lifecycle qualification (M9-M14)"),
        "app_held": table(app_rows, HELD, "App HTTP path: held-out set (X1-X3)"),
        "dev": table(oc, DEV, "Kit path: development set (M1-M8): used while tuning V2-V4"),
        "held": table(oc, HELD, "Kit path: held-out set (X1-X3): never used for tuning"),
        "summary_dev": matrix(rows, DEV, "Development set (M1-M8), total score"),
        "summary_held": matrix(rows, HELD, "Held-out set (X1-X3), total score"),
        "repeat": repeat_table(allrows, ("opencode", "V4", "gpt-oss-120b"), DEV,
                               "Repeatability: V4 / gpt-oss-120b, the same setup run several times"),
        "copilot_dev": table(cop, DEV, "GitHub Copilot CLI, development set"),
        "copilot_held": table(cop, HELD, "GitHub Copilot CLI, held-out set"),
    }


if __name__ == "__main__":
    for k, v in blocks().items():
        print(f"<!-- {k} -->\n{v}")
