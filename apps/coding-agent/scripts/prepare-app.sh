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

python3 scripts/check-run-identity.py

echo "[prepare] installing the coding agent"
mkdir -p .bin
# Install from the exact dependency and lockfile. A missing agent is a failed build.
npm ci --ignore-scripts --no-audit --no-fund
agent_version=$(node_modules/.bin/opencode --version)
[ "$agent_version" = "1.18.19" ] || { echo "Unsupported agent: $agent_version" >&2; exit 1; }

echo "[prepare] installing the qualified app-log client"
python3 scripts/install-databricks-cli.py

echo "[prepare] building the front end"
# ALWAYS rebuild. This used to be `if [ ! -f web/dist/index.html ]`, which was correct only on the very
# first deployment: every later deploy found a bundle from the previous one and shipped it unchanged. The
# result was a deployment serving a front end from before the feature it was supposedly deploying —
# measured by fetching the deployed bundle and finding no "Attach a file" string in it, while the local
# build had one. A build step that skips itself is not a build step.
npm --prefix web ci --no-audit --no-fund 2>/dev/null || npm --prefix web install --no-audit --no-fund
npm --prefix web run build
[ -f web/dist/index.html ] && echo "[prepare] web bundle ready" || {
  echo "[prepare] ERROR: the web bundle was not built; the app would serve no UI" >&2; exit 1; }
