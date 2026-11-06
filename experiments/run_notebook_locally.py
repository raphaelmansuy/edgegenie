#!/usr/bin/env python3
"""Run notebooks/launch_agent_from_notebook.py from a laptop, cell by cell, and save every cell's output.

This executes the REAL notebook code. Only three things are stood in for, because there is no Databricks notebook
around it: `spark` / `dbutils` (they only supply the workspace address and a token), the hidden token prompt
(answered from .env) and the GitHub copy in step 3 (replaced by the "copy from a folder" option, because the kit
may not be pushed yet). The outputs feed docs/tutorial.md and its screenshots.

    python experiments/run_notebook_locally.py [--out docs/tutorial/captures.json]
"""
from __future__ import annotations

import contextlib
import getpass
import io
import json
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "exams")); sys.path.insert(0, str(ROOT / "experiments"))
import lib  # noqa: E402
from render_captures import scrub  # noqa: E402

NB = ROOT / "notebooks" / "launch_agent_from_notebook.py"
OUT = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else ROOT / "docs" / "tutorial" / "captures.json"


def cells(text: str):
    for raw in text.split("# COMMAND ----------")[1:] if text.startswith("# Databricks") else text.split("# COMMAND ----------"):
        raw = raw.strip("\n")
        if not raw.strip():
            continue
        if all(l.startswith("# MAGIC") or not l.strip() for l in raw.splitlines()):
            md = "\n".join(l[len("# MAGIC"):].lstrip() for l in raw.splitlines() if l.startswith("# MAGIC") and l.strip() != "# MAGIC %md")
            yield "md", md
        else:
            yield "code", raw


def main() -> None:
    user = lib.USER
    scratch_schema, scratch_folder = "workspace.agent_scratch", f"/Workspace/Users/{user}/agent_scratch"
    lib.sql(f"CREATE SCHEMA IF NOT EXISTS {scratch_schema}")
    lib.mkdirs(scratch_folder)

    host_no_scheme = lib.HOST.replace("https://", "")
    spark = SimpleNamespace(conf=SimpleNamespace(get=lambda k, d=None: host_no_scheme))
    dbutils = MagicMock()
    dbutils.notebook.entry_point.getDbutils.return_value.notebook.return_value.getContext.return_value.apiToken.return_value.get.return_value = lib.TOKEN
    getpass.getpass = lambda prompt="": (print(prompt + "********"), lib.TOKEN)[1]
    ns: dict = {"spark": spark, "dbutils": dbutils, "__name__": "__notebook__"}

    src = NB.read_text().replace("YOU@example.com", user)
    # step 3: use the folder-copy option (the repo copy on GitHub may not contain this kit yet)
    src = re.sub(r"^print\(sh\(sandbox_id, f\"rm -rf ~/edgegenie && git clone.*$", "", src, flags=re.M)
    src = src.replace('# print(put_tree(sandbox_id, "/Workspace/Users/' + user + '/edgegenie", "~/edgegenie"))',
                      f'print(put_tree(sandbox_id, "/Workspace/Users/{user}/edgegenie", "~/edgegenie"))')
    src = src.replace(f"/Workspace/Users/{user}/edgegenie", str(ROOT)).replace("# Option B", "")

    def as_run(b: str) -> str:
        """Display form of a cell: placeholders intact, and the folder-copy option shown as active (it is what ran)."""
        if "git clone" not in b:
            return b
        b = re.sub(r"^(print\(sh\(sandbox_id, f\"rm -rf ~/edgegenie && git clone.*)$", r"# \1", b, flags=re.M)
        return b.replace("# print(put_tree(", "print(put_tree(").replace("# Option B", "").rstrip()

    shown_cells = [as_run(b) for k, b in cells(NB.read_text()) if k == "code"]   # what the reader sees (placeholders intact)
    caps, heading = [], ""
    try:
        for kind, body in cells(src):
            if kind == "md":
                heading = body.splitlines()[0].lstrip("# ").strip() if body.strip() else heading
                continue
            shown = shown_cells[len(caps)]
            buf, t0, err = io.StringIO(), time.time(), None
            with contextlib.redirect_stdout(buf):
                try:
                    exec(compile(body, "<cell>", "exec"), ns)
                except SystemExit:
                    raise
                except BaseException as e:  # noqa: BLE001
                    err = repr(e)
            out = buf.getvalue()
            if err:
                out += f"\nERROR: {err}"
            caps.append({"heading": heading, "code": scrub(shown), "output": scrub(out.rstrip("\n")), "seconds": round(time.time() - t0, 1), "error": err})
            print(f"[{len(caps)}] {heading} ({caps[-1]['seconds']}s){' ERROR' if err else ''}", flush=True)
            if err:
                break
    finally:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(caps, indent=1))
        print("saved", OUT)


if __name__ == "__main__":
    main()
