#!/bin/bash
# Copilot CLI + Databricks SQL MCP (proper config dir).
set -u
export PATH="$HOME/.npm-global/bin:$PATH"
export DATABRICKS_TOKEN="$(cat /tmp/dbx_token.txt)"
mkdir -p "$HOME/cop" "$HOME/.copilot" && cd "$HOME/cop" || exit 1
cat > "$HOME/.copilot/mcp-config.json" <<JSON
{
  "mcpServers": {
    "dbsql": {
      "type": "http",
      "url": "https://dbc-cb61f1e1-bd8e.cloud.databricks.com/ai-gateway/mcp-services/system.ai.dbsql",
      "headers": { "Authorization": "Bearer $DATABRICKS_TOKEN" },
      "tools": ["*"]
    }
  }
}
JSON
export COPILOT_PROVIDER_BASE_URL="https://dbc-cb61f1e1-bd8e.cloud.databricks.com/ai-gateway/openai/v1"
export COPILOT_PROVIDER_API_KEY="$DATABRICKS_TOKEN"
export COPILOT_MODEL="system.ai.gpt-oss-120b"
export COPILOT_PROVIDER_WIRE_MODEL="system.ai.gpt-oss-120b"
export COPILOT_PROVIDER_MAX_OUTPUT_TOKENS="16000"
export COPILOT_OFFLINE="true"
rm -f c2.log
timeout 240 copilot -p "Use the dbsql MCP tool to run: SELECT current_catalog() AS catalog, count(*) AS n FROM samples.nyctaxi.trips. Report the row." --allow-all-tools </dev/null >c2.log 2>&1
echo "EXIT=$?"
sed -e 's/\x1b\[[0-9;]*m//g' c2.log | tail -30
