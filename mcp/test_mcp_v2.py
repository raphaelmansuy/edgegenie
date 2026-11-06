#!/usr/bin/env python3
"""Conformance + scope-enforcement test for the V2 tools of nbmcp.

Boots the server over stdio with a SCOPED config (as the exam harness does) and
checks both that the new tools work and that every escape attempt is refused.
Writes docs/e2e/mcp_conformance_v2.json.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "exams"))
from lib import TOKEN, USER, sql  # noqa: E402

RID = "t" + str(int(time.time()))[-5:]
SCHEMA = f"workspace.exam_{RID}"
HOME = f"/Users/{USER}/exams/{RID}"


def body(res) -> str:
    return "\n".join(getattr(c, "text", "") for c in res.content)


async def main() -> None:
    sql(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    env = dict(os.environ, DATABRICKS_HOST="https://dbc-cb61f1e1-bd8e.cloud.databricks.com",
               DATABRICKS_TOKEN=TOKEN, NBMCP_ALLOW_WRITES="1", NBMCP_PROFILE="core",
               NBMCP_WRITE_SCHEMAS=SCHEMA, NBMCP_WRITE_PATHS=HOME + "/",
               NBMCP_WRITE_JOB_PREFIX=f"{RID}_", NBMCP_WRITE_INSTANCE_PREFIX=f"{RID}-")
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "mcp" / "databricks_notebook_mcp.py")], env=env)
    results: list[dict] = []

    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = sorted(t.name for t in (await s.list_tools()).tools)

            async def call(name: str, args: dict, expect: str, ok_if) -> str:
                try:
                    res = await s.call_tool(name, args)
                    text = body(res)
                    err = bool(res.isError)
                except Exception as e:  # noqa: BLE001
                    text, err = repr(e), True
                passed = bool(ok_if(text, err))
                results.append({"tool": name, "expect": expect, "passed": passed, "excerpt": text[:260]})
                print(("PASS" if passed else "FAIL"), name, "-", expect)
                return text

            await call("dbx_run_sql", {"sql": f"CREATE TABLE {SCHEMA}.t AS SELECT 1 AS x"}, "write inside scope allowed",
                       lambda t, e: "error" not in t.lower() or "SUCCEEDED" in t)
            await call("dbx_run_sql", {"sql": "DROP TABLE workspace.edgequake.nothing"}, "write outside scope REFUSED",
                       lambda t, e: "blocked" in t)
            await call("dbx_run_sql", {"sql": "CREATE TABLE t_unqualified AS SELECT 1"}, "unqualified write REFUSED",
                       lambda t, e: "blocked" in t)
            cj = json.dumps([{"type": "markdown", "source": "# T\nq"}, {"type": "code", "source": "x = 1"},
                             {"type": "markdown", "source": "## more"}, {"type": "code", "source": "print(x)"}])
            await call("dbx_write_notebook", {"path": f"{HOME}/cells_nb", "cells_json": cj},
                       "cells_json -> 4 cells, 2 markdown (correct SOURCE structure)",
                       lambda t, e: '"cells": 4' in t and '"markdown_cells": 2' in t)
            ip = json.dumps([{"cell_type": "markdown", "source": ["# A\n", "b"]}, {"cell_type": "code", "source": ["print(1)"]}])
            await call("dbx_write_notebook", {"path": f"{HOME}/ipynb_nb", "source": ip},
                       "Jupyter-style JSON in `source` is converted, not stored verbatim",
                       lambda t, e: '"cells": 2' in t and "converted" in t)
            await call("dbx_run_notebook", {"path": f"{HOME}/cells_nb", "wait_seconds": 200},
                       "success without exit() is flagged (no exit_value note)",
                       lambda t, e: "never called dbutils.notebook.exit" in t)
            await call("dbx_write_notebook", {"path": f"/Users/{USER}/not_mine_nb", "source": "print(1)"},
                       "notebook write outside path scope REFUSED", lambda t, e: "blocked" in t or e)
            await call("dbx_write_file", {"path": f"{HOME}/app/app.yaml", "content": "command: [python, app.py]\n"},
                       "write_file inside scope creates a FILE", lambda t, e: '"object_type": "FILE"' in t)
            await call("dbx_write_file", {"path": f"/Users/{USER}/escape.txt", "content": "x"},
                       "write_file outside scope REFUSED", lambda t, e: "blocked" in t or e)
            await call("dbx_write_notebook",
                       {"path": f"{HOME}/nb", "source": "import json\ndbutils.notebook.exit(json.dumps({'ok': 1}))\n"},
                       "write notebook inside scope", lambda t, e: not e)
            run = await call("dbx_run_notebook", {"path": f"{HOME}/nb", "wait_seconds": 200},
                             "run notebook on serverless, return exit value",
                             lambda t, e: '"result": "SUCCESS"' in t and "ok" in t)
            await call("dbx_write_notebook",
                       {"path": f"{HOME}/bad", "source": "x = 1 / 0\n"}, "write failing notebook", lambda t, e: not e)
            await call("dbx_run_notebook", {"path": f"{HOME}/bad", "wait_seconds": 200},
                       "failing run returns the error text", lambda t, e: "ZeroDivision" in t or "division" in t.lower())
            job = await call("dbx_create_job", {"name": f"{RID}_job", "tasks_json": json.dumps([
                {"task_key": "a", "notebook_path": f"{HOME}/nb"},
                {"task_key": "b", "notebook_path": f"{HOME}/nb", "depends_on": ["a"]}])},
                "create 2-task job with dependency", lambda t, e: '"job_id"' in t)
            await call("dbx_create_job", {"name": "other_job", "tasks_json": "[]"},
                       "job without the prefix REFUSED", lambda t, e: "blocked" in t or e)
            jid = json.loads(job)["job_id"] if '"job_id"' in job else None
            if jid:
                await call("dbx_run_job", {"job_id": jid, "wait_seconds": 240}, "run job and wait for per-task results",
                           lambda t, e: t.count('"result": "SUCCESS"') >= 3)
                import urllib.request
                req = urllib.request.Request(f"https://dbc-cb61f1e1-bd8e.cloud.databricks.com/api/2.1/jobs/delete",
                                             data=json.dumps({"job_id": jid}).encode(),
                                             headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
                urllib.request.urlopen(req)
            await call("dbx_lakebase_create", {"name": "someoneelse-lb"}, "instance without the prefix REFUSED",
                       lambda t, e: "blocked" in t or e)
            await call("dbx_create_app", {"name": f"{RID}-app", "source_code_path": f"{HOME}/app"},
                       "app create surfaces the platform refusal verbatim",
                       lambda t, e: "platform_error" in t and "Git" in t)

    sql(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
    from lib import delete_path
    delete_path(HOME)
    passed = sum(r["passed"] for r in results)
    out = {"profile": "core", "tools": tools, "n_tools": len(tools), "passed": passed, "total": len(results), "cases": results}
    p = ROOT / "docs" / "e2e" / "mcp_conformance_v2.json"
    p.write_text(json.dumps(out, indent=2))
    print(f"{passed}/{len(results)} passed; {len(tools)} tools in core profile; wrote {p}")
    sys.exit(0 if passed == len(results) else 1)


asyncio.run(main())
