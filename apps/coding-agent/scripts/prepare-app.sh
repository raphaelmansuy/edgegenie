#!/usr/bin/env bash
# Build-time preparation for a Databricks App deployment.
#
# The platform installs Python and npm dependencies at build time, but the coding agent itself is
# an npm package and was NOT installed by the app build: that is why the first deployment served
# no UI and could not have started an agent. This script is run by the root package.json "build".
#
#   npm run build  ->  web bundle  +  the agent binary in .bin/
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "[prepare] installing the coding agent"
mkdir -p .bin
if [ ! -x .bin/.installed ]; then
  npm install --no-save --no-audit --no-fund opencode-ai >/dev/null 2>&1 || {
    echo "[prepare] WARNING: could not install opencode-ai; the app will start without an agent" >&2
  }
  touch .bin/.installed
fi
echo "[prepare] agent: $(command -v opencode || echo 'not installed')"

echo "[prepare] building the front end"
if [ ! -f web/dist/index.html ]; then
  npm --prefix web ci --no-audit --no-fund 2>/dev/null || npm --prefix web install --no-audit --no-fund
  npm --prefix web run build
fi
[ -f web/dist/index.html ] && echo "[prepare] web bundle ready" || {
  echo "[prepare] ERROR: the web bundle was not built; the app would serve no UI" >&2; exit 1; }
