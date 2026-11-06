#!/usr/bin/env python3
"""Capture a real shell session in a Databricks sandbox, for the tutorial's screenshots.

Creates a fresh sandbox, installs the kit, starts the tool server, asks the agent one question,
and records each command with its real output. The output feeds docs/tutorial.md via
experiments/render_captures.py (terminal style).

    python experiments/capture_shell.py [--out docs/tutorial/shell_captures.json]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "exams"))
sys.path.insert(0, str(ROOT / "experiments"))
import lib  # noqa: E402
from dbx_mcp import rpc  # noqa: E402
from render_captures import scrub  # noqa: E402
from sandbox_put import upload  # noqa: E402
from sandbox_run import run  # noqa: E402

EP = "/ai-gateway/mcp-services/system.ai.sandbox"
OUT = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else ROOT / "docs" / "tutorial" / "shell_captures.json"
USER = lib.USER
SCHEMA, FOLDER = "workspace.agent_scratch", f"/Workspace/Users/{USER}/agent_scratch"

TOOLS_LIST = r'''
~/pyenv/bin/python - <<'PY'
import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def main():
    async with streamablehttp_client("http://127.0.0.1:8765/mcp") as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = (await s.list_tools()).tools
            print(f"{len(tools)} tools the agent can use:\n")
            for t in tools:
                first = (t.description or "").strip().splitlines()[0][:88]
                print(f"  {t.name:<26} {first}")  # noqa: E501

asyncio.run(main())
PY
'''

caps: list[dict] = []


def step(title: str, command: str, script: str, seconds_note: str = "", timeout: int = 175) -> None:
    t0 = time.time()
    out = run(script, SID, timeout)
    caps.append({"title": title, "command": scrub(command), "output": scrub(out.strip()),
                 "seconds": seconds_note or f"{time.time() - t0:.0f} s"})
    print(f"[{len(caps)}] {title} ({time.time() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    lib.sql(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    lib.mkdirs(FOLDER)
    SID = json.loads(rpc(EP, "tools/call", {"name": "create_sandbox", "arguments": {}})["result"]["content"][0]["text"])["sandbox_id"]
    globals()["SID"] = SID
    print("sandbox:", SID, flush=True)
    (ROOT / "exams" / ".tok").write_text(lib.TOKEN)
    upload(str(ROOT / "exams" / ".tok"), "/tmp/dbx_token.txt", SID)
    (ROOT / "exams" / ".tok").unlink()

    run("mkdir -p ~/edgegenie/templates ~/edgegenie/mcp/skills ~/edgegenie/mcp", SID, 60)
    for f, remote in [
        ("templates/setup_agent.sh", "~/edgegenie/templates/setup_agent.sh"),
        ("templates/start_mcp.sh", "~/edgegenie/templates/start_mcp.sh"),
        ("templates/ask.sh", "~/edgegenie/templates/ask.sh"),
        ("templates/run_agent.sh", "~/edgegenie/templates/run_agent.sh"),
        ("templates/AGENTS.rules.md", "~/edgegenie/templates/AGENTS.rules.md"),
        ("mcp/databricks_notebook_mcp.py", "~/edgegenie/mcp/databricks_notebook_mcp.py"),
    ] + [(f"mcp/skills/{n}", f"~/edgegenie/mcp/skills/{n}") for n in
         ("databricks-apps.md", "etl-pipelines.md", "lakebase-postgres.md", "notebook-authoring.md")]:
        upload(str(ROOT / f), remote, SID)

    HOST = lib.HOST
    step("What is on the machine before we start", "uname -sm; databricks --version; node --version; opencode --version 2>&1 | tail -1",
         "uname -sm; databricks --version; node --version; command -v opencode || echo 'opencode: not installed yet'")
    step("Install the agent", "bash templates/setup_agent.sh",
         f"export DATABRICKS_HOST={HOST}; cd ~/edgegenie && bash templates/setup_agent.sh 2>&1 | tail -12")
    step("Start the tool server (the fence)", "bash start_mcp.sh workspace.agent_scratch /Workspace/Users/you/agent_scratch",
         f"export DATABRICKS_HOST={HOST}; cd ~/agent-work && bash start_mcp.sh {SCHEMA} {FOLDER}")
    step("The tools the agent can use", "python -c '... list tools from http://127.0.0.1:8765/mcp ...'", TOOLS_LIST, timeout=120)
    step("Ask a question from the shell", 'bash ask.sh "How many trips are in samples.nyctaxi.trips, and over what date range?"',
         f"""export DATABRICKS_HOST={HOST}
cd ~/agent-work && bash ask.sh "How many trips are in samples.nyctaxi.trips, and over what date range?" 2>&1 | tail -32""")
    step("The log shows every tool call", "python3 -c '... read events.jsonl ...'",
         r"""cd ~/agent-work && python3 - <<'PY'
import json
for line in open("events.jsonl"):
    e = json.loads(line)
    if e.get("type") == "tool_use":
        p = e["part"]; st = p.get("state", {})
        arg = json.dumps(st.get("input", {}))[:70]
        print(f"{p['tool']:<24} {st.get('status',''):<10} {arg}")
PY""")
    step("Use the Databricks CLI directly (same token, no agent)", "databricks current-user me; databricks workspace list /Users/you",
         f"""export DATABRICKS_HOST={HOST} DATABRICKS_TOKEN="$(cat /tmp/dbx_token.txt)"
unset DATABRICKS_CONFIG_FILE DATABRICKS_CONFIG_PROFILE
databricks current-user me | python3 -c "import json,sys;d=json.load(sys.stdin);print('userName :',d['userName']);print('active   :',d['active'])"
echo
echo 'first folders in your workspace:'
databricks workspace list /Users/{USER} 2>&1 | head -6""", timeout=120)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(caps, indent=1))
    print("saved", OUT)
    print(run("cd ~/agent-work && bash start_mcp.sh stop", SID, 60))
    print(rpc(EP, "tools/call", {"name": "delete_sandbox", "arguments": {"sandbox_id": SID}})["result"]["content"][0]["text"])
