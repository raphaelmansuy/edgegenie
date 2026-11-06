#!/bin/bash
# Restart the custom MCP with paging + grep, then re-test the exact task that
# previously produced a confidently wrong answer.
set -u
export PATH="$HOME/.npm-global/bin:$PATH"
export DATABRICKS_TOKEN="$(cat /tmp/dbx_token.txt)"
pkill -f databricks_notebook_mcp.py 2>/dev/null; sleep 1
export DATABRICKS_HOST="https://dbc-cb61f1e1-bd8e.cloud.databricks.com"
export NBMCP_TRANSPORT=http NBMCP_PORT=8801 NBMCP_HOST=127.0.0.1 NBMCP_ALLOW_WRITES=1
nohup python3 /tmp/databricks_notebook_mcp.py > /tmp/nbmcp.log 2>&1 &
sleep 6
curl -s -o /dev/null -w "mcp_up:%{http_code}\n" -H "Accept: application/json, text/event-stream" \
  -X POST -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"p","version":"1"}}}' \
  http://127.0.0.1:8801/mcp

cd "$HOME/proj" || exit 1
echo "===== CASE E: paged/grep tools, natural prompt (was wrong before) ====="
rm -f e_case.log
timeout 240 opencode run --model dbx/system.ai.gpt-oss-120b --auto \
  "The notebook /Users/raphael.mansuy@gmail.com/databricks-toolbox/01-schema-document-generator is available through the dbxnb tools. Determine (1) every Python library it imports, (2) the exact widget parameter name, (3) whether glob patterns are supported. Use dbxnb_dbx_grep_notebook to find imports rather than dumping the whole file. Cite the line numbers you used." \
  </dev/null >e_case.log 2>&1
echo "EXIT=$?"
sed -e 's/\x1b\[[0-9;]*m//g' e_case.log | grep -vE '^\s*$' | tail -30
