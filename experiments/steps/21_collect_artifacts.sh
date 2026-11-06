#!/bin/bash
# Produce terminal-capture artifacts (ANSI-stripped transcripts) for the docs.
# These are the E2E evidence: real agent sessions inside Databricks.
set -u
cd "$HOME/proj" || exit 1
OUT=/tmp/e2e_artifacts
mkdir -p "$OUT"
strip() { sed -e 's/\x1b\[[0-9;]*m//g' -e 's/\r$//' "$1"; }

{
  echo "# E2E: OpenCode inside Databricks sandbox -> AI Gateway (gpt-oss-120b)"
  echo "# task: create fib.py, run it, report output"
  echo '```'
  strip run2.log 2>/dev/null | head -60
  echo '```'
} > "$OUT/01_opencode_gateway.md"

{
  echo "# E2E: OpenCode -> Databricks SQL MCP (system.ai.dbsql)"
  echo '```'
  strip mcp1.log 2>/dev/null | head -40
  echo '```'
} > "$OUT/02_opencode_sql_mcp.md"

{
  echo "# E2E: OpenCode -> custom notebook MCP (dbxnb)"
  echo '```'
  strip c1b.log 2>/dev/null | head -40
  echo '```'
} > "$OUT/03_opencode_custom_mcp.md"

{
  echo "# E2E: OpenCode -> Vertex Gemini 3.8 Flash via signature shim"
  echo '```'
  strip g3.log 2>/dev/null | head -40
  echo '```'
} > "$OUT/04_gemini38_shim.md"

{
  echo "# E2E: GitHub Copilot CLI BYOK -> Databricks AI Gateway"
  echo '```'
  strip c1.log 2>/dev/null | head -40
  echo '```'
} > "$OUT/05_copilot_byok.md"

{
  echo "# E2E: GitHub Copilot CLI -> Databricks SQL MCP"
  echo '```'
  strip c2.log 2>/dev/null | head -40
  echo '```'
} > "$OUT/06_copilot_mcp.md"

{
  echo "# E2E: failure - Gemini 3.x via plain OpenAI-compat adapter (thought_signature)"
  echo '```'
  strip gem.log 2>/dev/null | head -40
  echo '```'
} > "$OUT/07_gemini_thought_signature_failure.md"

{
  echo "# E2E: failure - agent defaults to local filesystem tools (Case A)"
  echo '```'
  strip ab_A.log 2>/dev/null | head -30
  echo '```'
} > "$OUT/08_custom_mcp_not_chosen.md"

{
  echo "# E2E: stall after consecutive tool calls (Case E)"
  echo '```'
  strip e_case.log 2>/dev/null | head -30
  echo '```'
} > "$OUT/09_post_tool_stall.md"

ls -la "$OUT"
tar czf /tmp/e2e_artifacts.tgz -C /tmp e2e_artifacts
echo "PACKED $(wc -c < /tmp/e2e_artifacts.tgz) bytes"
