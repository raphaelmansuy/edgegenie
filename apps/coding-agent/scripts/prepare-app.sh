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
# ALWAYS rebuild. This used to be `if [ ! -f web/dist/index.html ]`, which was correct only on the very
# first deployment: every later deploy found a bundle from the previous one and shipped it unchanged. The
# result was a deployment serving a front end from before the feature it was supposedly deploying —
# measured by fetching the deployed bundle and finding no "Attach a file" string in it, while the local
# build had one. A build step that skips itself is not a build step.

# The rolldown native binding that vite 8 uses declares `node ^20.19 || >=22.12`, and npm SILENTLY
# SKIPS an optional dependency whose `engines` is unmet. On an older Node the install succeeds and the
# BUILD then dies with "Cannot find module '@rolldown/binding-<platform>'", which names the wrong
# package. Check the version here so the message names the cause. Not fatal: a Node new enough to have
# installed the binding works regardless, so the build below is still what decides.
NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
NODE_MINOR="$(node -p 'process.versions.node.split(".")[1]' 2>/dev/null || echo 0)"
if [ "$NODE_MAJOR" -lt 20 ] || { [ "$NODE_MAJOR" -eq 20 ] && [ "$NODE_MINOR" -lt 19 ]; }; then
  echo "[prepare] WARNING: node $(node --version) is older than the ^20.19 that the front-end toolchain" >&2
  echo "[prepare]          needs. If the build fails looking for '@rolldown/binding-*', that is why:" >&2
  echo "[prepare]          npm skips optional native binaries whose engines are unmet." >&2
fi

npm --prefix web ci --no-audit --no-fund 2>/dev/null || npm --prefix web install --no-audit --no-fund
npm --prefix web run build
[ -f web/dist/index.html ] && echo "[prepare] web bundle ready" || {
  echo "[prepare] ERROR: the web bundle was not built; the app would serve no UI" >&2; exit 1; }
