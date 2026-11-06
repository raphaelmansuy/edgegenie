#!/bin/bash
# Which available model actually completes a multi-step agent loop through the
# Databricks AI Gateway? Same task, three models.
set -u
export PATH="$HOME/.npm-global/bin:$PATH"
export DATABRICKS_TOKEN="$(cat /tmp/dbx_token.txt)"
cd "$HOME/proj" || exit 1

cat > opencode.json <<'JSON'
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "dbx": {
      "npm": "@ai-sdk/openai-compatible",
      "options": {
        "baseURL": "https://dbc-cb61f1e1-bd8e.cloud.databricks.com/ai-gateway/openai/v1",
        "apiKey": "{env:DATABRICKS_TOKEN}"
      },
      "models": {
        "system.ai.gpt-oss-120b": { "limit": { "context": 128000, "output": 24000 } },
        "system.ai.gpt-oss-20b": { "limit": { "context": 128000, "output": 24000 } },
        "system.ai.qwen3-next-80b-a3b-instruct": { "limit": { "context": 128000, "output": 24000 } },
        "system.ai.llama-4-maverick": { "limit": { "context": 128000, "output": 24000 } }
      }
    }
  },
  "mcp": {
    "dbxnb": { "type": "remote", "url": "http://127.0.0.1:8801/mcp", "oauth": false }
  }
}
JSON

for M in system.ai.gpt-oss-120b system.ai.qwen3-next-80b-a3b-instruct system.ai.llama-4-maverick; do
  tag=$(echo "$M" | tr '/.' '__')
  rm -f "m_${tag}.log"
  start=$(date +%s)
  timeout 200 opencode run --model "dbx/$M" --auto \
    "Call dbxnb_dbx_describe_table with full_name=samples.nyctaxi.trips, then list the column names and their types in a table." \
    </dev/null >"m_${tag}.log" 2>&1
  code=$?; dur=$(( $(date +%s) - start ))
  # A completed run ends with prose; an aborted one ends on a tool line.
  tail_line=$(sed -e 's/\x1b\[[0-9;]*m//g' "m_${tag}.log" | grep -vE '^\s*$' | tail -1)
  echoes=$(grep -cE '^[[:space:]]*[⚙✗←→$]' "m_${tag}.log" 2>/dev/null || echo 0)
  if echo "$tail_line" | grep -qE '^[[:space:]]*[⚙✗←→$]'; then verdict="STALLED"; else verdict="ANSWERED"; fi
  printf "%-38s exit=%s %ss tools=%s %s\n" "$M" "$code" "$dur" "$echoes" "$verdict"
  echo "   last: $(echo "$tail_line" | cut -c1-110)"
done
