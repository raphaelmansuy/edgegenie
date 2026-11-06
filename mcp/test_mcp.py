#!/usr/bin/env python3
"""Conformance test for mcp/databricks_notebook_mcp.py.

Boots the server over stdio exactly as an agent would, lists tools, then calls
each of them against the live workspace and records PASS/FAIL.

    python mcp/test_mcp.py            # read-only tools
    NBMCP_ALLOW_WRITES=1 python mcp/test_mcp.py   # include write tools
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
SERVER = ROOT / "mcp" / "databricks_notebook_mcp.py"


def token() -> str:
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("TOKEN="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("no token")


CASES = [
    ("dbx_whoami", {}),
    ("dbx_list_catalogs", {}),
    ("dbx_list_schemas", {"catalog": "samples"}),
    ("dbx_list_tables", {"catalog": "samples", "schema": "nyctaxi", "limit": 10}),
    ("dbx_describe_table", {"full_name": "samples.nyctaxi.trips"}),
    ("dbx_sample_rows", {"full_name": "samples.nyctaxi.trips", "n": 3}),
    ("dbx_search_tables", {"needle": "trip", "catalog": "samples", "limit": 5}),
    ("dbx_table_lineage", {"full_name": "samples.nyctaxi.trips"}),
    ("dbx_grants", {"securable_type": "table", "full_name": "samples.nyctaxi.trips"}),
    ("dbx_run_sql", {"sql": "SELECT current_user() AS who, 1+1 AS two"}),
    ("dbx_list_notebooks", {"path": "/Users/raphael.mansuy@gmail.com"}),
    ("dbx_list_jobs", {"limit": 5}),
    ("dbx_list_pipelines", {"limit": 5}),
    ("dbx_list_warehouses", {}),
]

WRITE_CASES = [
    ("dbx_write_notebook", {
        "path": "/Users/raphael.mansuy@gmail.com/_mcp_conformance",
        "source": "print('written by databricks-notebook-mcp')\n",
    }),
    ("dbx_read_notebook", {"path": "/Users/raphael.mansuy@gmail.com/_mcp_conformance"}),
]


async def main() -> None:
    env = {
        **os.environ,
        "DATABRICKS_HOST": "https://dbc-cb61f1e1-bd8e.cloud.databricks.com",
        "DATABRICKS_TOKEN": token(),
        "NBMCP_ALLOW_WRITES": os.environ.get("NBMCP_ALLOW_WRITES", "0"),
        "PATH": os.environ["PATH"],
    }
    params = StdioServerParameters(
        command=sys.executable, args=[str(SERVER)], env=env
    )
    results = []
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print(f"tools exposed: {len(tools.tools)}")
            for t in tools.tools:
                print(f"  - {t.name}")
            cases = CASES + (WRITE_CASES if env["NBMCP_ALLOW_WRITES"] == "1" else [])
            for name, args in cases:
                started = time.time()
                try:
                    res = await session.call_tool(name, args)
                    text = "\n".join(
                        c.text for c in res.content if getattr(c, "type", "") == "text"
                    )
                    ok = not res.isError
                except Exception as exc:  # noqa: BLE001
                    text, ok = f"{type(exc).__name__}: {exc}", False
                elapsed = round(time.time() - started, 2)
                results.append({"tool": name, "ok": ok, "seconds": elapsed,
                                "preview": text[:300]})
                print(f"[{'PASS' if ok else 'FAIL'}] {name} ({elapsed}s) "
                      f"{text[:120].replace(chr(10), ' ')}")
    passed = sum(1 for r in results if r["ok"])
    out = ROOT / "docs" / "e2e" / "mcp_conformance.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"passed": passed, "total": len(results),
                               "results": results}, indent=2))
    print(f"\n{passed}/{len(results)} tools passed -> {out}")


if __name__ == "__main__":
    asyncio.run(main())
