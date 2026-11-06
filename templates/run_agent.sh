#!/usr/bin/env bash
# Run OpenCode on one task with a "supervisor" that refuses to accept an empty or unproven answer.
#
#   bash run_agent.sh <task-file.txt> [model]            (model default: dbx/system.ai.gpt-oss-120b)
#
# Expects, in the current directory: opencode.json (see templates/), AGENTS.md (rules), and
# optionally .claude/skills/ (official Databricks skills). DATABRICKS_HOST and DATABRICKS_TOKEN must
# be set. Writes the full event log to events.jsonl; prints the final answer at the end.
set -u
TASK="${1:?usage: run_agent.sh <task-file> [model]}"
MODEL="${2:-dbx/system.ai.gpt-oss-120b}"
unset DATABRICKS_CONFIG_FILE DATABRICKS_CONFIG_PROFILE   # the sandbox sets a config file with no profile in it
export PATH="$HOME/.npm-global/bin:$PATH"

timeout 1500 opencode run --model "$MODEL" --auto --format json "$(cat "$TASK")" </dev/null > events.jsonl 2> stderr.log

# True when the last thing the agent did was write text (a final answer), not call a tool.
final_ok() { python3 - <<'PY'
import json, sys
last_tool, texts = -1, []
for i, line in enumerate(open("events.jsonl")):
    try: e = json.loads(line)
    except Exception: continue
    if e.get("type") == "tool_use": last_tool = i
    elif e.get("type") == "text": texts.append((i, e["part"].get("text", "")))
sys.exit(0 if any(i > last_tool and t.strip() for i, t in texts) else 1)
PY
}

AUDITS=0
for N in 1 2 3 4 5; do
  if ! final_ok; then
    echo "supervisor: empty final answer, continuing ($N)" >&2
    MSG="You stopped without a final answer. Continue the task: finish remaining work, verify it by running a check, then write your final report."
  elif [ "$AUDITS" -lt 2 ]; then
    AUDITS=$((AUDITS+1)); echo "supervisor: audit pass $AUDITS" >&2
    MSG="Audit pass. Re-read the original task. For EACH requirement, name the tool call whose real result proves it was done. Describing or planning is not evidence: if a requirement has no tool-call evidence, do the work NOW, then re-check. When every requirement is proven, write the final report."
  else
    break
  fi
  timeout 600 opencode run -c --model "$MODEL" --auto --format json "$MSG" </dev/null >> events.jsonl 2>> stderr.log
done

python3 - <<'PY'
import json
last_tool, texts = -1, []
for i, line in enumerate(open("events.jsonl")):
    try: e = json.loads(line)
    except Exception: continue
    if e.get("type") == "tool_use": last_tool = i
    elif e.get("type") == "text": texts.append((i, e["part"].get("text", "")))
print("\n=== FINAL ANSWER ===\n" + next((t for i, t in reversed(texts) if i > last_tool and t.strip()), "(none)"))
PY
