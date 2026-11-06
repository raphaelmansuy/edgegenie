#!/usr/bin/env bash
# One-command setup of the coding agent inside the Databricks sandbox.
#
#   bash templates/setup_agent.sh            (run from the repository root, inside the sandbox)
#
# Needs: DATABRICKS_HOST in the environment and your token in /tmp/dbx_token.txt.
# Creates ~/agent-work with: opencode.json, AGENTS.md (rules), skills/, and a python env for the tool server.
set -euo pipefail
: "${DATABRICKS_HOST:?set DATABRICKS_HOST, for example https://my-workspace.cloud.databricks.com}"
[ -s /tmp/dbx_token.txt ] || { echo "Missing /tmp/dbx_token.txt (your token). See tutorial step 3."; exit 1; }
KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="${AGENT_WORK:-$HOME/agent-work}"
HOST="${DATABRICKS_HOST%/}"
mkdir -p "$WORK" ~/.npm-global
export PATH="$HOME/pyenv/bin:$HOME/.npm-global/bin:$PATH"

echo "[1/5] Installing the OpenCode agent (no root needed)"
npm config set prefix ~/.npm-global >/dev/null 2>&1
command -v opencode >/dev/null || npm install -g opencode-ai 2>&1 | { grep -v "npm warn" || true; } | tail -1
echo "      opencode $(opencode --version 2>&1 | tail -1)"

echo "[2/5] Creating the Python environment for the tool server"
[ -x ~/pyenv/bin/python ] || uv venv --system-site-packages ~/pyenv -q
uv pip install -q --python ~/pyenv/bin/python "mcp<2" httpx requests psycopg2-binary 2>&1 | tail -1 || true
~/pyenv/bin/python -c "import mcp, httpx; print('      python packages ok')"

echo "[3/5] Writing the agent config (model + tool server + safety switches)"
HOST="$HOST" WORK="$WORK" python3 - <<'PY'
import json, os
host, work = os.environ["HOST"], os.environ["WORK"]
cfg = {
  "$schema": "https://opencode.ai/config.json",
  "model": "dbx/system.ai.gpt-oss-120b",
  "provider": {"dbx": {
      "npm": "@ai-sdk/openai-compatible", "name": "Databricks AI Gateway",
      "options": {"baseURL": f"{host}/ai-gateway/openai/v1", "apiKey": "{env:DATABRICKS_TOKEN}"},
      # 24000 is the line people miss: the model allows 25,000 output tokens, agents ask for more by default.
      "models": {"system.ai.gpt-oss-120b": {"name": "gpt-oss-120b", "limit": {"context": 128000, "output": 24000}}}}},
  "mcp": {"dbxnb": {"type": "remote", "url": "http://127.0.0.1:8765/mcp", "oauth": False}},
  # Hide the agent's built-in file tools: they act on the sandbox disk, not on the workspace.
  "permission": {"edit": "deny", "webfetch": "deny", "task": "deny", "todowrite": "deny", "skill": "deny"},
  "tools": {"read": False, "write": False, "glob": False, "grep": False},
}
json.dump(cfg, open(os.path.join(work, "opencode.json"), "w"), indent=2)
PY

echo "[4/5] Copying the rules file and skills"
cp "$KIT/templates/AGENTS.rules.md" "$WORK/AGENTS.md"
mkdir -p "$WORK/skills" && cp "$KIT"/mcp/skills/*.md "$WORK/skills/"
cp "$KIT/templates/run_agent.sh" "$KIT/templates/ask.sh" "$KIT/templates/start_mcp.sh" "$WORK/"
cp "$KIT/mcp/databricks_notebook_mcp.py" "$WORK/"

echo "[5/5] Checking the token against the workspace"
unset DATABRICKS_CONFIG_FILE DATABRICKS_CONFIG_PROFILE
DATABRICKS_TOKEN="$(cat /tmp/dbx_token.txt)" databricks current-user me -o json 2>/dev/null \
  | python3 -c "import json,sys; print('      signed in as', json.load(sys.stdin)['userName'])" \
  || { echo "      could not sign in: check the token and DATABRICKS_HOST"; exit 1; }
echo
echo "READY. Next:  cd $WORK && bash start_mcp.sh <catalog.schema> <workspace-folder>"
