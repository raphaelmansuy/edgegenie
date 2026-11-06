#!/bin/bash
# GitHub Copilot CLI inside the Databricks sandbox, BYOK -> Databricks AI Gateway.
set -u
export PATH="$HOME/.npm-global/bin:$PATH"
export DATABRICKS_TOKEN="$(cat /tmp/dbx_token.txt)"
mkdir -p "$HOME/cop" && cd "$HOME/cop" || exit 1

# MCP server registration (Databricks SQL), no GitHub auth required.
cat > "$HOME/.copilot/mcp-config.json" <<JSON
{
  "mcpServers": {
    "dbsql": {
      "type": "http",
      "url": "https://dbc-cb61f1e1-bd8e.cloud.databricks.com/ai-gateway/mcp-services/system.ai.dbsql",
      "headers": { "Authorization": "Bearer $DATABRICKS_TOKEN" }
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

rm -f c1.log tri.py
timeout 240 copilot -p "Create tri.py containing a function that computes triangular numbers iteratively with a docstring, then run python3 tri.py so it prints the first 8 triangular numbers. Report the output." --allow-all-tools </dev/null >c1.log 2>&1
echo "EXIT=$?"
sed -e 's/\x1b\[[0-9;]*m//g' c1.log | tail -40
echo "--- tri.py ---"; cat tri.py 2>/dev/null
