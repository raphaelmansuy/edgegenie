#!/bin/bash
# OpenCode inside the sandbox, wired to Databricks managed MCP servers.
# Proves: agent -> MCP -> Unity Catalog SQL, all from inside the workspace.
set -u
export PATH="$HOME/.npm-global/bin:$PATH"
cd "$HOME/proj" || exit 1
export DATABRICKS_TOKEN="$(cat /tmp/dbx_token.txt)"
cat > opencode.json <<'JSON'
{
  "$schema": "https://opencode.ai/config.json",
  "model": "dbx/system.ai.gpt-oss-120b",
  "provider": {
    "dbx": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Databricks AI Gateway",
      "options": {
        "baseURL": "https://dbc-cb61f1e1-bd8e.cloud.databricks.com/ai-gateway/openai/v1",
        "apiKey": "{env:DATABRICKS_TOKEN}"
      },
      "models": {
        "system.ai.gpt-oss-120b": {
          "name": "gpt-oss-120b",
          "limit": { "context": 128000, "output": 24000 }
        }
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
rm -f mcp1.log
timeout 240 opencode run --model dbx/system.ai.gpt-oss-120b --auto \
  "Use the dbsql MCP tool to run this exact query and report the first 3 rows: SELECT current_catalog() AS catalog, current_user() AS who, count(*) AS n FROM samples.nyctaxi.trips. If the table does not exist, run SHOW CATALOGS and report what you found instead." \
  </dev/null >mcp1.log 2>&1
echo "EXIT=$?"
sed -e 's/\x1b\[[0-9;]*m//g' mcp1.log | tail -35
