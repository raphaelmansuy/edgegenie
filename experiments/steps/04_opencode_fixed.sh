#!/bin/bash
# OpenCode -> Databricks AI Gateway, with the model output limit matched to the
# model's real max_output_tokens (the default 32000 is rejected).
set -u
export PATH="$HOME/.npm-global/bin:$PATH"
cd "$HOME/proj" || exit 1
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
  }
}
JSON
export DATABRICKS_TOKEN="$(cat /tmp/dbx_token.txt)"
rm -f fib.py run2.log
timeout 180 opencode run --model dbx/system.ai.gpt-oss-120b --auto \
  "Create fib.py with an iterative fibonacci function that has a docstring, plus a main guard that prints the first 10 numbers. Then run python3 fib.py and report the exact output." \
  </dev/null >run2.log 2>&1
echo "EXIT=$?"
sed -e 's/\x1b\[[0-9;]*m//g' run2.log | tail -30
echo "--- fib.py ---"
cat fib.py 2>/dev/null
echo "--- python3 fib.py ---"
python3 fib.py 2>&1
