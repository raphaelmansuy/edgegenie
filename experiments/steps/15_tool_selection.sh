#!/bin/bash
# Isolate the tool-selection failure.
#   C) explicit tool name in the prompt, custom MCP present
#   D) implicit (natural) prompt but with the notebook mounted as a local file
# This separates "agent cannot reach the data" from "agent did not choose the tool".
set -u
export PATH="$HOME/.npm-global/bin:$PATH"
export DATABRICKS_TOKEN="$(cat /tmp/dbx_token.txt)"
cd "$HOME/proj" || exit 1

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

echo "===== CASE C: explicit tool instruction ====="
rm -f c_case.log
timeout 240 opencode run --model dbx/system.ai.gpt-oss-120b --auto \
  "Call the dbxnb_dbx_read_notebook tool with path=/Users/raphael.mansuy@gmail.com/databricks-toolbox/01-schema-document-generator . From the returned source, report: (1) the Python libraries it imports, (2) the exact parameter name it takes, (3) whether it supports glob patterns." \
  </dev/null >c_case.log 2>&1
echo "EXIT=$?"
sed -e 's/\x1b\[[0-9;]*m//g' c_case.log | grep -vE '^\s*$' | tail -30

echo "===== CASE D: notebook exported to local file, natural prompt ====="
mkdir -p "$HOME/proj/repo" && cd "$HOME/proj/repo"
python3 - <<'PY'
import base64, json, urllib.request, os
tok = open('/tmp/dbx_token.txt').read().strip()
url = "https://dbc-cb61f1e1-bd8e.cloud.databricks.com/api/2.0/workspace/export?path=/Users/raphael.mansuy@gmail.com/databricks-toolbox/01-schema-document-generator&format=SOURCE"
req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"})
src = base64.b64decode(json.load(urllib.request.urlopen(req))["content"]).decode()
open("01-schema-document-generator.py", "w").write(src)
print("exported", len(src), "chars")
PY
rm -f d_case.log
timeout 240 opencode run --model dbx/system.ai.gpt-oss-120b --auto \
  "Read 01-schema-document-generator.py in this directory. Report: (1) the Python libraries it imports, (2) the exact parameter name it takes, (3) whether it supports glob patterns." \
  </dev/null >d_case.log 2>&1
echo "EXIT=$?"
sed -e 's/\x1b\[[0-9;]*m//g' d_case.log | grep -vE '^\s*$' | tail -30
