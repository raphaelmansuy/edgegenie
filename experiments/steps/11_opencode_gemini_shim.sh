#!/bin/bash
# External-model path done right: OpenCode -> thought-signature shim -> Vertex AI
# (Gemini 3.8 Flash). The shim preserves extra_content.google.thought_signature
# across tool-call turns, which the plain OpenAI-compatible adapter drops.
set -u
export PATH="$HOME/.npm-global/bin:$PATH"
pkill -f gemini_sig_shim.py 2>/dev/null; sleep 1
export VX_TOKEN="$(cat /tmp/vx_token.txt)"
export DATABRICKS_TOKEN="$(cat /tmp/dbx_token.txt)"
nohup python3 /tmp/gemini_sig_shim.py > /tmp/shim.log 2>&1 &
sleep 2
curl -s -o /dev/null -w "shim_health:%{http_code}\n" http://127.0.0.1:8790/v1/models

mkdir -p "$HOME/gemtest" && cd "$HOME/gemtest" || exit 1
cat > opencode.json <<'JSON'
{
  "$schema": "https://opencode.ai/config.json",
  "model": "vertex/google/gemini-3.8-flash",
  "provider": {
    "vertex": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Vertex Gemini 3.8 Flash (via signature shim)",
      "options": {
        "baseURL": "http://127.0.0.1:8790/v1",
        "apiKey": "unused"
      },
      "models": {
        "google/gemini-3.8-flash": {
          "name": "gemini-3.8-flash",
          "limit": { "context": 1000000, "output": 30000 }
        }
      }
    }
  }
}
JSON
rm -f gen3.py g3.log
timeout 240 opencode run --model vertex/google/gemini-3.8-flash --auto \
  "Write gen3.py that computes the 20th Fibonacci number iteratively and prints it. Run python3 gen3.py, then tell me the printed value." \
  </dev/null >g3.log 2>&1
echo "EXIT=$?"
sed -e 's/\x1b\[[0-9;]*m//g' g3.log | tail -30
echo "--- gen3.py ---"; cat gen3.py 2>/dev/null | head -25
echo "--- run ---"; python3 gen3.py 2>&1
echo "--- shim log ---"; tail -5 /tmp/shim.log
