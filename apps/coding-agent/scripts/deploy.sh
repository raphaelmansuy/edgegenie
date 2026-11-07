#!/usr/bin/env bash
# Create, configure and deploy the coding-agent app, then verify it end to end.
#
#   DATABRICKS_HOST=... DATABRICKS_TOKEN=... scripts/deploy.sh              # create + deploy + verify
#   scripts/deploy.sh verify                                                 # verify an existing deployment
#
# The script stops at the first blocking condition and says exactly what it is, because the
# platform's own errors are misleading (a missing git source reads as "a Git repository is
# required"; an exhausted daily quota reads as the same thing on some calls).
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$HERE/.." && pwd)"
APP="${APP_NAME:-coding-agent}"
: "${DATABRICKS_HOST:?set DATABRICKS_HOST}"
export DATABRICKS_HOST
unset DATABRICKS_CONFIG_FILE DATABRICKS_CONFIG_PROFILE

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
die() { printf '\033[31mSTOP: %s\033[0m\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- preflight
preflight() {
  say "1/6 Preflight"
  command -v databricks >/dev/null || die "the databricks CLI is not installed"
  databricks current-user me -o json >/dev/null 2>&1 || die "cannot authenticate: check DATABRICKS_TOKEN"
  echo "  authenticated as $(databricks current-user me -o json | python3 -c 'import json,sys;print(json.load(sys.stdin)["userName"])')"

  # The app build installs Python and Node dependencies, so the bundle must be complete.
  [ -f "$APP_DIR/api/main.py" ] || die "api/main.py missing"
  [ -f "$APP_DIR/app.yaml" ] || die "app.yaml missing"
  [ -d "$HERE/../web/dist" ] || echo "  note: web/dist is absent; the build produces it (npm run build)"
  echo "  app folder: $APP_DIR"
}

# ---------------------------------------------------------------- quota
check_quota() {
  say "2/6 App quota"
  # Try to start a stopped app: it is the only reliable probe, and the platform states the reason.
  local stopped
  stopped="$(databricks apps list -o json 2>/dev/null | python3 -c '
import json,sys
apps = json.load(sys.stdin) or []
print(next((a["name"] for a in apps if (a.get("compute_status") or {}).get("state") == "STOPPED"), ""))
')"
  if [ -z "$stopped" ]; then
    echo "  no stopped app to probe with; continuing"
    return
  fi
  local out
  if ! out="$(databricks apps start "$stopped" 2>&1)"; then
    case "$out" in
      *"free daily limit"*)
        die "this workspace has hit its free daily app-compute limit (probe: starting '$stopped').
     The app resource can be created, but nothing can run until the limit resets.
     Re-run tomorrow:  DATABRICKS_HOST=$DATABRICKS_HOST scripts/deploy.sh" ;;
      *) die "cannot start '$stopped': $out" ;;
    esac
  fi
  # A successful start request is not proof: confirm the state actually changed.
  sleep 5
  local state
  state="$(databricks apps get "$stopped" -o json | python3 -c 'import json,sys;print((json.load(sys.stdin).get("compute_status") or {}).get("state",""))')"
  if [ "$state" = "STOPPED" ]; then
    die "'$stopped' still reports STOPPED after a start request; compute is not available today"
  fi
  echo "  compute is available ('$stopped' is now $state)"
  databricks apps stop "$stopped" >/dev/null 2>&1 && echo "  stopped '$stopped' again to avoid spending the allowance"
}

# ---------------------------------------------------------------- create
create_app() {
  say "3/6 Create the app resource"
  if databricks apps get "$APP" >/dev/null 2>&1; then
    echo "  $APP already exists"
    return
  fi
  local out
  if ! out="$(databricks apps create --json "@$APP_DIR/app.create.json" --no-compute 2>&1)"; then
    case "$out" in
      *"free daily limit"*) die "quota exhausted while creating the app" ;;
      *) die "cannot create the app: $out" ;;
    esac
  fi
  echo "$out" | sed 's/^/  /' | head -4
  databricks apps get "$APP" >/dev/null 2>&1 || die "the app was not created"
  echo "  created $APP"
}

# ---------------------------------------------------------------- scopes
# The one list. `apps update` REPLACES the spec it is given: a call that sends only `resources` (or a
# shorter scope list) silently drops every scope it omits, and the Files and Catalog panes then fail
# with 403 for every user. That happened; this list and `check_scopes` exist so it cannot again.
# Names are the ones `apps update` ACCEPTS (docs: "Configure authorization in a Databricks app").
# `workspace`, `unity-catalog` and `jobs` appear in the platform's refusal text ("required scopes:
# workspace") but are rejected as grantable names ("not a valid scope"); the grantable SDK scopes are
# `workspace.workspace` and `catalog.*` (`:read` keeps them to GET). A user's token carries the scopes
# of the moment they signed in, so after changing this list a signed-in user must sign in again.
REQUIRED_SCOPES=(sql files model-serving ai-gateway genie workspace.workspace
                 catalog.catalogs:read catalog.schemas:read catalog.tables:read)

scopes_json() { printf '%s\n' "${REQUIRED_SCOPES[@]}" | python3 -c 'import json,sys;print(json.dumps([l.strip() for l in sys.stdin if l.strip()]))'; }

# Fails (and names the missing scopes) unless every required scope is EFFECTIVE, not merely requested.
check_scopes() {
  databricks apps get "$APP" -o json | REQUIRED="$(scopes_json)" python3 -c '
import json,os,sys
d = json.load(sys.stdin)
have = set(d.get("effective_user_api_scopes") or [])
missing = [s for s in json.loads(os.environ["REQUIRED"]) if s not in have]
print("  effective scopes:", ", ".join(sorted(have)) or "(none)")
if missing:
    print("  MISSING:", ", ".join(missing)); sys.exit(1)'
}

grant_scopes() {
  say "4/6 Grant user-authorization scopes"
  # Declaring scopes in app.yaml only *requests* them; they must be granted explicitly.
  databricks apps update "$APP" --json "{\"user_api_scopes\":$(scopes_json)}" 2>&1 | sed 's/^/  /' | head -3
  check_scopes || die "the app is missing scopes: the workspace panes would 403 for every user"
}

# ---------------------------------------------------------------- deploy
deploy() {
  say "5/6 Deploy"
  # The workspace takes the source from Git, so deploy from the repository branch.
  databricks apps deploy "$APP" 2>&1 | sed 's/^/  /' | tail -12
  for _ in $(seq 1 60); do
    state="$(databricks apps get "$APP" -o json | python3 -c 'import json,sys;print((json.load(sys.stdin).get("app_status") or {}).get("state",""))')"
    [ "$state" = "RUNNING" ] && { echo "  app is RUNNING"; return; }
    [ "$state" = "CRASHED" ] && die "the app crashed; inspect its logs with: databricks apps logs $APP"
    sleep 10
  done
  die "the app did not reach RUNNING within 10 minutes"
}

# ---------------------------------------------------------------- verify
verify() {
  say "6/6 Verify end to end"
  local url
  url="$(databricks apps get "$APP" -o json | python3 -c 'import json,sys;print(json.load(sys.stdin).get("url",""))')"
  [ -n "$url" ] || die "the app has no URL"
  echo "  url: $url"

  # These run against the deployed app, exactly as a browser would.
  local code
  code="$(curl -s -o /dev/null -w '%{http_code}' "$url/")"
  [ "$code" = "200" ] || die "the app returned $code for /"
  echo "  GET /           200"

  code="$(curl -s -o /dev/null -w '%{http_code}' "$url/api/health")"
  [ "$code" = "200" ] || die "/api/health returned $code"
  echo "  GET /api/health 200"

  curl -s "$url/api/models" | head -c 200 | sed 's/^/  models: /'; echo

  check_scopes || die "the deployed app is missing scopes (see above): Files and Catalog would fail"

  # Identity: with user authorization on, an unauthenticated call must not be treated as a user.
  code="$(curl -s -o /dev/null -w '%{http_code}' -X POST "$url/api/sessions" \
      -H 'Content-Type: application/json' -d '{"folder":"/tmp/x"}')"
  echo "  POST /api/sessions without a forwarded user -> $code (401 expected in production)"

  say "Next: run the UI end-to-end suite against the deployed URL"
  echo "  cd web && APP_URL=$url node scripts/shoot.mjs e2e/screenshots"
  echo "  (screenshots of the deployed app; compare against specs/001/e2e/screenshots)"
}

case "${1:-deploy}" in
  verify) verify ;;
  *) preflight; check_quota; create_app; grant_scopes; deploy; verify ;;
esac
