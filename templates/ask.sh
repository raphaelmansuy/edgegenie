#!/usr/bin/env bash
# Ask the agent to do something. It keeps going until it has proof, then prints a short report.
#
#   bash ask.sh "your request in plain words"
#
# Run from ~/agent-work after start_mcp.sh. A long task can outlive one sandbox call (about 180 s);
# start it in the background:  nohup bash ask.sh "..." > run.log 2>&1 &   then:  tail -f run.log
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
[ -n "${1:-}" ] || { echo 'usage: bash ask.sh "your request"'; exit 1; }
export DATABRICKS_HOST="${DATABRICKS_HOST:?set DATABRICKS_HOST}"
export DATABRICKS_TOKEN="$(cat /tmp/dbx_token.txt)"
printf '%s\n' "$1" > task.txt
bash run_agent.sh task.txt
python3 - <<'PY'
import json
calls = []
for line in open("events.jsonl"):
    try: e = json.loads(line)
    except Exception: continue
    if e.get("type") == "tool_use": calls.append(e["part"].get("tool", "?"))
print(f"\n--- the agent made {len(calls)} tool calls: " + ", ".join(sorted(set(c.replace('dbxnb_', '') for c in calls))))
PY
