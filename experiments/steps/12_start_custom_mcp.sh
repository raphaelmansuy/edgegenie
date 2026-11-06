#!/bin/bash
# Push the custom notebook MCP server into the sandbox and start it over HTTP
# so OpenCode can reach it exactly like any other remote MCP server.
set -u
export PATH="$HOME/.npm-global/bin:$PATH"
pkill -f databricks_notebook_mcp.py 2>/dev/null; sleep 1
/usr/bin/python3 -c "import mcp" 2>/dev/null || pip3 install --quiet --user mcp httpx 2>&1 | tail -2
export DATABRICKS_HOST="https://dbc-cb61f1e1-bd8e.cloud.databricks.com"
export DATABRICKS_TOKEN="$(cat /tmp/dbx_token.txt)"
export NBMCP_TRANSPORT=http
export NBMCP_PORT=8801
export NBMCP_HOST=127.0.0.1
export NBMCP_ALLOW_WRITES=1
nohup python3 /tmp/databricks_notebook_mcp.py > /tmp/nbmcp.log 2>&1 &
sleep 6
echo "--- health ---"
curl -s -o /dev/null -w "mcp_http:%{http_code}\n" http://127.0.0.1:8801/mcp
echo "--- log ---"
tail -8 /tmp/nbmcp.log
which python3; python3 -c "import mcp,httpx;print('deps ok')" 2>&1 | tail -3
