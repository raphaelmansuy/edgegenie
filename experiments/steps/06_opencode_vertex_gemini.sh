#!/bin/bash
# External-model path: OpenCode inside Databricks, model served by Vertex AI
# (Gemini 3.8 Flash) through its OpenAI-compatible endpoint.
set -u
export PATH="$HOME/.npm-global/bin:$PATH"
cd "$HOME/proj" || exit 1
export VX_TOKEN="$(cat /tmp/vx_token.txt)"
export DATABRICKS_TOKEN="$(cat /tmp/dbx_token.txt)"
cat > opencode.json <<'JSON'
{
  "$schema": "https://opencode.ai/config.json",
  "model": "vertex/google/gemini-3.8-flash",
  "provider": {
    "vertex": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Vertex AI (Gemini 3.8 Flash)",
      "options": {
        "baseURL": "https://aiplatform.googleapis.com/v1/projects/mobioos-506015/locations/global/endpoints/openapi",
        "apiKey": "{env:VX_TOKEN}"
      },
      "models": {
        "google/gemini-3.8-flash": {
          "name": "gemini-3.8-flash",
          "limit": { "context": 1000000, "output": 30000 }
        }
      }
    },
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
rm -f gen.py gem.log
timeout 240 opencode run --model vertex/google/gemini-3.8-flash --auto \
  "Write gen.py that computes the 20th Fibonacci number iteratively and prints it. Run it with python3. Then use the dbsql MCP tool to run: SELECT 2+2 AS x. Report both results." \
  </dev/null >gem.log 2>&1
echo "EXIT=$?"
sed -e 's/\x1b\[[0-9;]*m//g' gem.log | tail -40
echo "--- gen.py ---"; cat gen.py 2>/dev/null | head -20
echo "--- run ---"; python3 gen.py 2>&1
