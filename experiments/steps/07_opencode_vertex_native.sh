#!/bin/bash
# Same Gemini 3.8 Flash test, but through OpenCode's NATIVE Google adapter
# (@ai-sdk/google-vertex), which round-trips thought signatures correctly.
set -u
export PATH="$HOME/.npm-global/bin:$PATH"
cd "$HOME/proj" || exit 1
export VX_TOKEN="$(cat /tmp/vx_token.txt)"
export DATABRICKS_TOKEN="$(cat /tmp/dbx_token.txt)"
mkdir -p "$HOME/proj/vertex-test" && cd "$HOME/proj/vertex-test"
cat > /tmp/gcp-creds.json <<'JSON'
{"type":"authorized_user","client_id":"","client_secret":"","refresh_token":""}
JSON
cat > opencode.json <<'JSON'
{
  "$schema": "https://opencode.ai/config.json",
  "model": "vertex/google/gemini-3.8-flash",
  "provider": {
    "vertex": {
      "npm": "@ai-sdk/google-vertex",
      "name": "Google Vertex AI",
      "options": {
        "project": "mobioos-506015",
        "location": "global",
        "apiKey": "{env:VX_TOKEN}"
      },
      "models": {
        "google/gemini-3.8-flash": {
          "name": "Gemini 3.8 Flash",
          "limit": { "context": 1000000, "output": 30000 }
        }
      }
    }
  }
}
JSON
rm -f gen2.py vx.log
timeout 150 opencode run --model vertex/google/gemini-3.8-flash --auto \
  "Write gen2.py computing the 20th Fibonacci number iteratively, then run it with python3 and tell me the result." \
  </dev/null >vx.log 2>&1
echo "EXIT=$?"
sed -e 's/\x1b\[[0-9;]*m//g' vx.log | tail -25
echo "--- file ---"; ls -la gen2.py 2>&1; python3 gen2.py 2>&1
