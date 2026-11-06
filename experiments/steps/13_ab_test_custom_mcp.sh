#!/bin/bash
# Decisive test: the SAME agent task, run twice.
#   A) only Databricks-provided MCP servers (dbsql)
#   B) dbsql + our custom notebook MCP
# The task needs workspace-artefact access, which dbsql cannot provide.
set -u
export PATH="$HOME/.npm-global/bin:$PATH"
export DATABRICKS_TOKEN="$(cat /tmp/dbx_token.txt)"
cd "$HOME/proj" || exit 1
PROMPT="There is a notebook at /Users/raphael.mansuy@gmail.com/databricks-toolbox/01-schema-document-generator. Tell me: (1) what Python libraries it imports, (2) the exact name of the parameter it takes, and (3) whether it handles glob patterns. Do not guess — if you cannot read the notebook, say so explicitly."

run_case () {
  local label="$1"; local with_custom="$2"
  if [ "$with_custom" = "yes" ]; then
    cat > opencode.json <<'JSON'
{
  "$schema": "https://opencode.ai/config.json",
  "model": "dbx/system.ai.gpt-oss-120b",
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
  "mcp": {
    "dbsql": {
      "type": "remote",
      "url": "https://dbc-cb61f1e1-bd8e.cloud.databricks.com/ai-gateway/mcp-services/system.ai.dbsql",
      "oauth": false,
      "headers": { "Authorization": "Bearer {env:DATABRICKS_TOKEN}" }
    },
    "dbxnb": {
      "type": "remote",
      "url": "http://127.0.0.1:8801/mcp",
      "oauth": false
    }
  }
}
JSON
  else
    cat > opencode.json <<'JSON'
{
  "$schema": "https://opencode.ai/config.json",
  "model": "dbx/system.ai.gpt-oss-120b",
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
  "mcp": {
    "dbsql": {
      "type": "remote",
      "url": "https://dbc-cb61f1e1-bd8e.cloud.databricks.com/ai-gateway/mcp-services/system.ai.dbsql",
      "oauth": false,
      "headers": { "Authorization": "Bearer {env:DATABRICKS_TOKEN}" }
    }
  }
}
JSON
  fi
  rm -f "ab_${label}.log"
  timeout 240 opencode run --model dbx/system.ai.gpt-oss-120b --auto "$PROMPT" \
    </dev/null >"ab_${label}.log" 2>&1
  echo "===== CASE ${label} (custom_mcp=${with_custom}) EXIT=$? ====="
  sed -e 's/\x1b\[[0-9;]*m//g' "ab_${label}.log" | grep -vE '^\s*$' | tail -28
}

run_case A no
run_case B yes
