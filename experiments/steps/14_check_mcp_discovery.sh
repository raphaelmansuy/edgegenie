#!/bin/bash
# Is the custom MCP actually connected, and are its tools visible to OpenCode?
set -u
export PATH="$HOME/.npm-global/bin:$PATH"
export DATABRICKS_TOKEN="$(cat /tmp/dbx_token.txt)"
cd "$HOME/proj" || exit 1
echo "--- mcp server listening? ---"
curl -s -o /dev/null -w "http:%{http_code}\n" -H "Accept: application/json, text/event-stream" \
  -X POST -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"probe","version":"1"}}}' \
  http://127.0.0.1:8801/mcp
echo "--- opencode debug mcp ---"
timeout 60 opencode mcp list 2>&1 | sed -e 's/\x1b\[[0-9;]*m//g' | head -20
echo "--- opencode debug tools ---"
timeout 60 opencode debug --help 2>&1 | head -20
