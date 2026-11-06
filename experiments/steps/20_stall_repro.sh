#!/bin/bash
# Reproduce the post-tool stall deliberately and test mitigations.
# The earlier stall: 3-4 consecutive tool calls, then silence.
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
        "system.ai.gpt-oss-120b": { "limit": { "context": 128000, "output": 24000 } }
      }
    }
  },
  "mcp": { "dbxnb": { "type": "remote", "url": "http://127.0.0.1:8801/mcp", "oauth": false } }
}
JSON

run () {
  local label="$1"; shift
  rm -f "s_${label}.log"
  timeout 220 opencode run --model dbx/system.ai.gpt-oss-120b --auto "$@" </dev/null >"s_${label}.log" 2>&1
  local code=$?
  local last=$(sed -e 's/\x1b\[[0-9;]*m//g' "s_${label}.log" | grep -vE '^\s*$' | tail -1)
  local tools=$(grep -cE '^[[:space:]]*⚙' "s_${label}.log" || true)
  echo "--- $label: exit=$code tool_calls=$tools"
  echo "    last: $(echo "$last" | cut -c1-120)"
}

# 1. Multi-tool chain with a cheap, targeted question (the grep path).
run paged "Find every library imported by the notebook at /Users/raphael.mansuy@gmail.com/databricks-toolbox/01-schema-document-generator using dbxnb_dbx_grep_notebook with pattern '^[[:space:]]*import ' and pattern '^[[:space:]]*from '. Then answer with the list only."

# 2. Same question, one tool call, larger page.
run onepage "Call dbxnb_dbx_read_notebook once with path=/Users/raphael.mansuy@gmail.com/databricks-toolbox/01-schema-document-generator and max_chars=20000. Then list every import you see and the widget parameter name."

# 3. Pure-SQL chain via the Databricks SQL MCP (2 calls).
run sqlchain "Using dbsql, run SHOW CATALOGS, then run SELECT count(*) FROM samples.nyctaxi.trips. Report both results."
