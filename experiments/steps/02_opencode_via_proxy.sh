#!/bin/bash
# Point OpenCode at the local capture proxy and run a minimal prompt.
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
      "name": "Databricks via proxy",
      "options": {
        "baseURL": "http://127.0.0.1:8787/v1",
        "apiKey": "unused"
      },
      "models": {
        "system.ai.gpt-oss-120b": { "name": "gpt-oss-120b" }
      }
    }
  }
}
JSON
rm -f run.log
timeout 90 opencode run --model dbx/system.ai.gpt-oss-120b --auto "Say only: PONG" </dev/null >run.log 2>&1
echo "EXIT=$?"
sed -e 's/\x1b\[[0-9;]*m//g' run.log | tail -20
echo "--- captured request ---"
ls -1 /tmp/capture 2>/dev/null
