#!/bin/bash
# Run the app locally with a FRESH workspace token, for e2e and for the UX scorecard.
#
#   scripts/dev-token.sh [port]
#
# Why this exists: the scorecard and the e2e need a real workspace, and every one of them failed at
# least once on an expired token — Databricks issues it for an hour, and a debugging session is longer
# than that. The symptom is a 403 on /api/workspace/search, which looks like a product bug (an empty
# tree, a search stuck on its skeleton) and costs twenty minutes to diagnose.
#
# This script mints a token itself, so a run never starts with a stale one.
set -euo pipefail

PORT="${1:-8061}"
HOST="${DATABRICKS_HOST:-https://dbc-1e111e44-3334.cloud.databricks.com}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"

TOKEN="$(databricks auth token --host "$HOST" -o json | python3 -c 'import json,sys;print(json.load(sys.stdin)["access_token"])')"
if [ -z "$TOKEN" ]; then
  echo "could not mint a token for $HOST (try: databricks auth login --host $HOST)" >&2
  exit 1
fi

# The mode is FORCED, not defaulted: an `APP_AGENT_MODE=stdio` left in the shell by an earlier live
# test silently turned this into a real-agent run, whose turns then failed with "Invalid Token" and
# whose timeline dominated every measurement. A fixture script must not inherit the thing it is
# replacing. Pass `APP_AGENT_MODE=stdio` deliberately if that is what you want.
export APP_AGENT_MODE="${DEV_AGENT_MODE:-fake}"
export APP_DEMO_SCENARIO="${APP_DEMO_SCENARIO:-notebook}"
export APP_DEV_USER="${APP_DEV_USER:-raphael.mansuy@gmail.com}"
export DATABRICKS_HOST="$HOST"
export APP_DEV_TOKEN="$TOKEN"

cd "$HERE"
exec .venv/bin/python -m uvicorn api.main:app --host 127.0.0.1 --port "$PORT" --log-level warning
