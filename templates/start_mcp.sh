#!/usr/bin/env bash
# Start the Databricks tool server for the agent, with writes limited to ONE schema and ONE folder.
#
#   bash start_mcp.sh <catalog.schema> </Workspace/Users/you/folder>   start (or restart)
#   bash start_mcp.sh stop                                              stop
#
# The limits are enforced by the server itself, not by the agent's good manners.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
if [ "${1:-}" = "stop" ]; then [ -f mcp.pid ] && kill "$(cat mcp.pid)" 2>/dev/null; rm -f mcp.pid; echo stopped; exit 0; fi
SCHEMA="${1:?usage: start_mcp.sh <catalog.schema> <workspace-folder>}"
FOLDER="${2:?usage: start_mcp.sh <catalog.schema> <workspace-folder>}"
: "${DATABRICKS_HOST:?set DATABRICKS_HOST}"
[ -f mcp.pid ] && kill "$(cat mcp.pid)" 2>/dev/null || true
unset DATABRICKS_CONFIG_FILE DATABRICKS_CONFIG_PROFILE
export DATABRICKS_TOKEN="$(cat /tmp/dbx_token.txt)"
NBMCP_TRANSPORT=http NBMCP_PORT=8765 NBMCP_HOST=127.0.0.1 NBMCP_ALLOW_WRITES=1 \
NBMCP_WRITE_SCHEMAS="$SCHEMA" NBMCP_WRITE_PATHS="${FOLDER%/}/" NBMCP_PROFILE=core \
NBMCP_SKILLS_DIR="$PWD/skills" NBMCP_WRITE_JOB_PREFIX="agent_" NBMCP_WRITE_INSTANCE_PREFIX="agent-" \
  nohup "$HOME/pyenv/bin/python" databricks_notebook_mcp.py > mcp.log 2>&1 &
echo $! > mcp.pid
for i in $(seq 1 15); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8765/mcp)" != "000" ] && { echo "tool server is up"; echo "  can write tables in : $SCHEMA"; echo "  can write files in  : ${FOLDER%/}/"; echo "  can create jobs named: agent_*"; exit 0; }
  sleep 1
done
echo "tool server did not start:"; tail -5 mcp.log; exit 1
