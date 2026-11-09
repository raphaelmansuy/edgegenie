#!/usr/bin/env bash
# Copy the TRACKED files of this app into the Workspace folder the Databricks App deploys from.
#
#   scripts/sync-app-source.sh [workspace-path]
#
# Why this exists: `databricks apps deploy` ships whatever is in
# /Workspace/Users/<me>/coding-agent — a Workspace folder, not a git checkout (the app has no git
# repository configured). Nothing in this repository ever wrote to it, so it was populated once by hand
# and every deploy afterwards served that snapshot. Measured: a deploy reported SUCCEEDED while the live
# backend had no `POST /api/blobs`, no `/sessions/{id}/events`, and no `seesImages` field — three
# commits of work absent from a "successful" deployment, and the UI showed none of the attach feature.
#
# The unit is `git ls-files`: 375 files. `import-dir .` walked node_modules (126 MB) and the venv (190 MB)
# and had to be killed. Tracked files are exactly what the build needs — it installs its own dependencies.
set -euo pipefail

HOST="${DATABRICKS_HOST:?set DATABRICKS_HOST}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$HERE/.." && pwd)"
REPO="$(cd "$APP_DIR/../.." && pwd)"
DEST="${1:-/Workspace/Users/raphael.mansuy@gmail.com/coding-agent}"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

export DATABRICKS_HOST="$HOST"

echo "staging tracked files from $APP_DIR"
cd "$REPO"
# Relative to the repo root, so this works from any checkout location.
git ls-files apps/coding-agent | while IFS= read -r f; do
  rel="${f#apps/coding-agent/}"
  mkdir -p "$STAGE/$(dirname "$rel")"
  cp "$REPO/$f" "$STAGE/$rel"
done
echo "  $(find "$STAGE" -type f | wc -l | tr -d ' ') files"

echo "uploading to $DEST"
# `--overwrite` replaces what changed and leaves the rest; `import-dir` creates directories as needed.
databricks workspace import-dir "$STAGE" "$DEST" --overwrite 2>&1 | tail -3

echo "verifying the source the app will build:"
for probe in api/domain/blob.py api/adapters/acp/blocks.py \
             api/adapters/llm/store/migrations/003_llm_model_vision.sql; do
  if databricks workspace list "$DEST/$(dirname "$probe")" 2>/dev/null | grep -q "$(basename "$probe")"; then
    echo "  ok   $probe"
  else
    echo "  MISSING $probe" >&2
  fi
done
