#!/bin/bash
# Capture the exact request/response of the failing turn.
# Proxy on :8787 logs every body; agent talks to the proxy instead of the gateway.
set -u
export PATH="$HOME/.npm-global/bin:$PATH"
export DATABRICKS_TOKEN="$(cat /tmp/dbx_token.txt)"
pkill -f /tmp/proxy.py 2>/dev/null; sleep 1
rm -rf /tmp/capture && mkdir -p /tmp/capture
export DBX_TOKEN="$DATABRICKS_TOKEN"
nohup python3 /tmp/proxy.py > /tmp/proxy.log 2>&1 &
sleep 3
curl -s -o /dev/null -w "proxy:%{http_code}\n" http://127.0.0.1:8787/v1/models

cd "$HOME/proj" || exit 1
cat > opencode.json <<'JSON'
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "px": {
      "npm": "@ai-sdk/openai-compatible",
      "options": { "baseURL": "http://127.0.0.1:8787/v1", "apiKey": "unused" },
      "models": {
        "system.ai.gpt-oss-120b": { "limit": { "context": 128000, "output": 24000 } }
      }
    }
  },
  "mcp": { "dbxnb": { "type": "remote", "url": "http://127.0.0.1:8801/mcp", "oauth": false } }
}
JSON
rm -f px.log
timeout 200 opencode run --model px/system.ai.gpt-oss-120b --auto \
  "Use dbxnb_dbx_grep_notebook twice: first with pattern '^[[:space:]]*import ' and then pattern '^[[:space:]]*from ', both on path /Users/raphael.mansuy@gmail.com/databricks-toolbox/01-schema-document-generator. Then list every imported library." \
  </dev/null >px.log 2>&1
echo "EXIT=$?"
sed -e 's/\x1b\[[0-9;]*m//g' px.log | grep -vE '^\s*$' | tail -12
echo "=== captured turns: $(ls -1 /tmp/capture/*.json 2>/dev/null | wc -l) ==="
ls -1 /tmp/capture/
