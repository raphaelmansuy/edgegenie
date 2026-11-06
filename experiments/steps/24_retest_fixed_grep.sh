#!/bin/bash
# Re-run the previously-failing task with the fixed grep tool.
set -u
export PATH="$HOME/.npm-global/bin:$PATH"
export DATABRICKS_TOKEN="$(cat /tmp/dbx_token.txt)"
pkill -f databricks_notebook_mcp.py 2>/dev/null; sleep 1
export DATABRICKS_HOST="https://dbc-cb61f1e1-bd8e.cloud.databricks.com"
export NBMCP_TRANSPORT=http NBMCP_PORT=8801 NBMCP_HOST=127.0.0.1 NBMCP_ALLOW_WRITES=0
nohup python3 /tmp/databricks_notebook_mcp.py > /tmp/nbmcp.log 2>&1 &
sleep 6
cd "$HOME/proj" || exit 1
cat > opencode.json <<'JSON'
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "px": {
      "npm": "@ai-sdk/openai-compatible",
      "options": { "baseURL": "http://127.0.0.1:8787/v1", "apiKey": "unused" },
      "models": { "system.ai.gpt-oss-120b": { "limit": { "context": 128000, "output": 24000 } } }
    }
  },
  "mcp": { "dbxnb": { "type": "remote", "url": "http://127.0.0.1:8801/mcp", "oauth": false } }
}
JSON
rm -f fx.log
timeout 240 opencode run --model px/system.ai.gpt-oss-120b --auto \
  "Use dbxnb_dbx_grep_notebook with pattern '^\\s*(import|from)\\s' on /Users/raphael.mansuy@gmail.com/databricks-toolbox/01-schema-document-generator. Then list every library the notebook imports, with line numbers." \
  </dev/null >fx.log 2>&1
echo "EXIT=$?"
sed -e 's/\x1b\[[0-9;]*m//g' fx.log | grep -vE '^\s*$' | tail -30
