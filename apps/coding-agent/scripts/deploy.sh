#!/usr/bin/env bash
# Create, configure and deploy the coding-agent app, then verify it end to end.
#
#   DATABRICKS_TOKEN=... scripts/deploy.sh dev       # development workspace (git source)
#   DATABRICKS_TOKEN=... scripts/deploy.sh prod      # live workspace (Workspace-folder source)
#   scripts/deploy.sh verify dev                     # verify an existing deployment
#
# Where each environment points, and how its source reaches the workspace, is declared in env.sh —
# not here. The two workspaces differ in a way no flag can bridge: one accepts a Workspace folder and
# the other accepts ONLY git. See the header of env.sh for the measurement.
#
# The script stops at the first blocking condition and says exactly what it is, because the
# platform's own errors are misleading (a missing git source reads as "a Git repository is
# required"; an exhausted daily quota reads as the same thing on some calls).
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$HERE/.." && pwd)"

ACTION="deploy"
ENV_NAME="${APP_ENV_NAME:-}"
case "${1:-}" in
  verify) ACTION="verify"; ENV_NAME="${2:-${APP_ENV_NAME:-prod}}" ;;
  dev|prod) ENV_NAME="$1" ;;
  "") ENV_NAME="${ENV_NAME:-prod}" ;;
  *) printf 'usage: %s [deploy|verify] [dev|prod]\n' "$0" >&2; exit 2 ;;
esac

# shellcheck source=env.sh
. "$HERE/env.sh" "$ENV_NAME" || exit 1

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
die() { printf '\033[31mSTOP: %s\033[0m\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- preflight
preflight() {
  say "1/8 Preflight"
  command -v databricks >/dev/null || die "the databricks CLI is not installed"
  require_workspace_identity || die "cannot authenticate to $DATABRICKS_HOST"

  # The app build installs Python and Node dependencies, so the bundle must be complete.
  [ -f "$APP_DIR/api/main.py" ] || die "api/main.py missing"
  [ -f "$APP_DIR/app.yaml" ] || die "app.yaml missing"
  [ -d "$APP_DIR/web/dist" ] || echo "  note: web/dist is absent; the build produces it (npm run build)"

  if [ "$DEPLOY_SOURCE" = "git" ]; then
    # This workspace builds from a COMMITTED tree. An uncommitted change is not deployed, and the
    # most expensive failure mode is believing it was. Say so before deploying, every time.
    local dirty
    dirty="$(git -C "$APP_DIR" status --porcelain --untracked-files=no -- . | head -5)"
    if [ -n "$dirty" ]; then
      echo "  WARNING: uncommitted changes in apps/coding-agent; this deploy ships the last commit:"
      printf '%s\n' "$dirty" | sed 's/^/    /'
      echo "  commit and push to deploy them."
    fi
    local head_remote head_local
    head_local="$(git -C "$APP_DIR" rev-parse HEAD)"
    head_remote="$(git -C "$APP_DIR" ls-remote "$DEPLOY_GIT_URL" "refs/heads/$DEPLOY_GIT_BRANCH" | cut -f1)"
    if [ "$head_local" != "$head_remote" ]; then
      echo "  WARNING: HEAD ($head_local) is not $DEPLOY_GIT_BRANCH on the remote ($head_remote)."
      echo "  the app builds from the remote branch, so the remote is what will run."
    fi
  fi
  echo "  app folder: $APP_DIR"
}

# ---------------------------------------------------------------- quota
check_quota() {
  say "2/8 App compute"
  # Probe only the app selected by this environment; another app is outside this deployment.
  local stopped state
  state="$(databricks apps get "$APP_NAME" -o json | python3 -c '
import json,sys
print((json.load(sys.stdin).get("compute_status") or {}).get("state", ""))')" \
    || die "cannot read compute status for '$APP_NAME'"
  if [ "$state" != "STOPPED" ]; then
    echo "  $APP_NAME compute is $state; continuing"
    return
  fi
  stopped="$APP_NAME"
  local out
  if ! out="$(databricks apps start "$stopped" --no-wait -o json 2>&1)"; then
    case "$out" in
      *"free daily limit"*)
        die "this workspace has hit its free daily app-compute limit (probe: starting '$stopped').
     The app resource can be created, but nothing can run until the limit resets." ;;
      *) die "cannot start '$stopped': $out" ;;
    esac
  fi
  # A successful start request is not proof: confirm the state actually changed.
  sleep 5
  local state
  state="$(databricks apps get "$stopped" -o json | python3 -c 'import json,sys;print((json.load(sys.stdin).get("compute_status") or {}).get("state",""))')"
  [ "$state" = "STOPPED" ] && die "'$stopped' still reports STOPPED after a start request; compute is not available"
  echo "  compute is available ('$stopped' is now $state)"
  # DO NOT stop it again. The deploy in step 6 requires the app to be RUNNING — measured: this probe
  # used to stop the app "to avoid spending the allowance", and the very next step failed with
  # `Cannot deploy app as it is not in RUNNING state`. The allowance is spent by the deploy that
  # follows a second later, so stopping here saved nothing and broke the deploy.
  echo "  leaving it running: the deploy in step 6 needs it RUNNING"
}

# ---------------------------------------------------------------- the one app body
# `apps update` is a FULL REPLACEMENT: a request that omits `user_api_scopes` or `resources` clears
# them, and the Files and Catalog panes then 403 for every user. That happened. So the body is built
# in exactly one place, from the one scope list in env.sh, and every field is always sent.
REQUIRED_SCOPES=("${DEPLOY_REQUIRED_SCOPES[@]}")

app_body() {
  # $1 = mode: create | update
  python3 - "$1" "$APP_NAME" "$DEPLOY_SOURCE" "$DEPLOY_GIT_URL" "$DEPLOY_GIT_PATH" "$DEPLOY_SECRET_SCOPE" \
    "$DEPLOY_REQUIRED_SCOPES_CSV" <<'PY'
import json, sys

mode, name, source, git_url, git_path, scope, scopes_csv = sys.argv[1:8]
body = {
    "name": name,
    "description": "Chat with a coding agent (ACP) that works in your workspace",
    "user_api_scopes": scopes_csv.split(),
    "resources": [
        {"name": "vertex-sa",
         "secret": {"scope": scope, "key": "vertex-sa", "permission": "READ"}},
        {"name": "llm-kek",
         "secret": {"scope": scope, "key": "llm-kek", "permission": "READ"}},
    ],
}
if source == "git":
    # The git repository is a property of the app and must be present on update too: this workspace
    # refuses any app that lacks one ("Git repository is required for Databricks Apps").
    body["git_repository"] = {"url": git_url, "provider": "gitHub"}
print(json.dumps(body))
PY
}

# Fails (and names the missing scopes) unless every required scope is EFFECTIVE, not merely requested.
check_scopes() {
  databricks apps get "$APP_NAME" -o json | REQUIRED="${REQUIRED_SCOPES[*]}" python3 -c '
import json,os,sys
d = json.load(sys.stdin)
have = set(d.get("effective_user_api_scopes") or [])
missing = [s for s in os.environ["REQUIRED"].split() if s not in have]
print("  effective scopes:", ", ".join(sorted(have)) or "(none)")
if missing:
    print("  MISSING:", ", ".join(missing)); sys.exit(1)'
}

# ---------------------------------------------------------------- create + configure
create_app() {
  say "3/8 Create the app resource"
  if databricks apps get "$APP_NAME" >/dev/null 2>&1; then
    echo "  $APP_NAME already exists"
  else
    local out
    if ! out="$(databricks apps create --json "$(app_body create)" --no-compute 2>&1)"; then
      case "$out" in
        *"free daily limit"*) die "quota exhausted while creating the app" ;;
        *"Git repository is required"*)
          die "this workspace refuses a non-git app source; check DEPLOY_SOURCE in scripts/env.sh" ;;
        *) die "cannot create the app: $out" ;;
      esac
    fi
    echo "$out" | sed 's/^/  /' | head -4
    databricks apps get "$APP_NAME" >/dev/null 2>&1 || die "the app was not created"
    echo "  created $APP_NAME"
  fi
}

grant_scopes() {
  say "4/8 Grant user-authorization scopes and attach secrets"
  # Declaring scopes in app.yaml only REQUESTS them; they must be granted explicitly. This is also
  # where the secret resources are attached, in the same full-replacement call, never separately.
  local out
  if ! out="$(databricks apps update "$APP_NAME" --json "$(app_body update)" 2>&1)"; then
    die "cannot update the app: $out"
  fi
  echo "  scopes and resources sent"
  check_scopes || die "the app is missing scopes: the workspace panes would 403 for every user"

  local r
  for r in vertex-sa llm-kek; do
    databricks apps get "$APP_NAME" -o json | python3 -c '
import json,sys
name = sys.argv[1]
d = json.load(sys.stdin)
have = [x.get("name") for x in (d.get("resources") or [])]
print("  resource %-10s %s" % (name, "attached" if name in have else "MISSING"))
sys.exit(0 if name in have else 1)' "$r" || die "secret resource '$r' is not attached to the app"
  done
}

# ---------------------------------------------------------------- lakebase
provision_lakebase() {
  say "5/8 Lakebase (project, service-principal role, privileges)"
  # The app refuses to start in production without a durable journal, and it creates its own
  # `llm`/`agent` schemas at boot. Both facts make these privileges a deployment prerequisite.
  "$HERE/provision-lakebase.sh" "$ENV_NAME" || die "Lakebase provisioning failed; the app would crash at boot"
}

# ---------------------------------------------------------------- session volume
provision_session_volume() {
  say "6/8 Session volume (the app's read and write on it)"
  # A Python session keeps its variables in a process, and that process is driven through files in this
  # volume. The app can WRITE those files but cannot create the volume, and cannot grant itself
  # anything: an unprovisioned volume is a session that cannot start, which the app reports in words and
  # falls back from. Provisioning it here is what makes the fallback the exception.
  "$HERE/provision-session-volume.sh" "$ENV_NAME" || die "the session volume is not provisioned"
}

# ---------------------------------------------------------------- deploy
deploy() {
  say "7/8 Deploy"
  # Starting an app may resume its old deployment. Both compute and that deployment must settle
  # before a new submission; accepting the start request does not make deployment ready.
  local ready=0 compute previous i
  for i in $(seq 1 60); do
    read -r compute previous <<<"$(databricks apps get "$APP_NAME" -o json | python3 -c '
import json, sys
d = json.load(sys.stdin)
print((d.get("compute_status") or {}).get("state", "unknown"),
      ((d.get("active_deployment") or {}).get("status") or {}).get("state", "none"))')"
    if [ "$compute" = "ACTIVE" ] && [ "$previous" != "IN_PROGRESS" ]; then
      ready=1; break
    fi
    [ "$compute" != "STOPPED" ] || die "app compute stopped before deployment"
    echo "  waiting for deployment readiness: compute=$compute previous=$previous"
    sleep 10
  done
  [ "$ready" = "1" ] || die "app did not become ready for deployment within 10 minutes"
  local out
  if [ "$DEPLOY_SOURCE" = "git" ]; then
    # Resolve once and pin the remote commit; a branch moving during deployment cannot change it.
    local remote_commit body
    remote_commit="$(git -C "$APP_DIR" ls-remote "$DEPLOY_GIT_URL" "refs/heads/$DEPLOY_GIT_BRANCH" | cut -f1)" \
      || die "cannot resolve the deployment branch"
    [[ "$remote_commit" =~ ^[0-9a-f]{40}$ ]] || die "deployment branch has no valid commit"
    body="$(python3 - "$remote_commit" "$DEPLOY_GIT_PATH" <<'PYDEPLOY'
import json, sys
print(json.dumps({"git_source": {"commit": sys.argv[1], "source_code_path": sys.argv[2]}}))
PYDEPLOY
)"
    out="$(databricks apps deploy "$APP_NAME" --json "$body" --no-wait -o json 2>&1)" \
      || die "deploy failed: $(printf '%s' "$out" | head -5)"
    printf '%s' "$out" | python3 -c 'import json,sys
d = json.load(sys.stdin)
print("  deployment", d.get("deployment_id"))
g = d.get("git_source") or {}
print("  commit    ", g.get("resolved_commit"), "on", g.get("branch"))' 2>/dev/null
  else
    # The workspace builds from a Workspace folder. That folder must be updated FIRST, or the deploy
    # ships a snapshot: measured three times, a "SUCCEEDED" deploy serving code from days earlier.
    "$HERE/sync-app-source.sh" "$DEPLOY_WS_SRC" || die "could not sync the source into $DEPLOY_WS_SRC"
    out="$(databricks apps deploy "$APP_NAME" --source-code-path "$DEPLOY_WS_SRC" \
      --no-wait -o json 2>&1)" \
      || die "deploy failed: $(printf '%s' "$out" | head -5)"
    printf '%s' "$out" | python3 -c 'import json,sys
print("  deployment", json.load(sys.stdin).get("deployment_id"))' 2>/dev/null
  fi

  local i state app_state
  for i in $(seq 1 60); do
    read -r state app_state <<<"$(databricks apps get "$APP_NAME" -o json | python3 -c '
import json,sys
d = json.load(sys.stdin)
dp = d.get("active_deployment") or {}
print((dp.get("status") or {}).get("state",""), (d.get("app_status") or {}).get("state",""))')"
    case "$state" in
      SUCCEEDED) echo "  deployment SUCCEEDED"; break ;;
      FAILED) die "the deployment FAILED; inspect with: databricks apps get $APP_NAME -o json" ;;
    esac
    [ "$i" = "60" ] && die "the deployment did not finish within 10 minutes"
    sleep 10
  done

  # SUCCEEDED means "the process started", not "it is healthy": a crashed process still reports a
  # successful deployment. So the app's own state is checked separately, and a crash is a failure.
  for i in $(seq 1 30); do
    app_state="$(databricks apps get "$APP_NAME" -o json | python3 -c 'import json,sys;print((json.load(sys.stdin).get("app_status") or {}).get("state",""))')"
    case "$app_state" in
      RUNNING) echo "  app is RUNNING"; return ;;
      CRASHED) die "the app CRASHED after a successful deploy — read the logs:
     databricks apps logs $APP_NAME   (needs an OAuth login; a PAT is refused)" ;;
    esac
    sleep 8
  done
  die "the app never reached RUNNING (last state: ${app_state:-unknown})"
}

# ---------------------------------------------------------------- verify
verify() {
  say "8/8 Verify the deployment"
  local rc=0
  check_database_health || rc=1
  "$HERE/verify-deployed.sh" || rc=1
  [ "$rc" = "0" ] || die "verification failed (see above)"
}

# Runs the health probe on in-workspace compute, because the app sits behind an OAuth proxy that
# refuses a PAT — which is the only credential a CI deploy has. Reading the app's own database proves
# more than /api/health would: that it booted, authenticated to Lakebase as its service principal, and
# ran its migrations.
check_database_health() {
  local notebook="/Workspace/Users/$(databricks current-user me -o json \
    | python3 -c 'import json,sys;print(json.load(sys.stdin)["userName"])')/app_health_probe"

  databricks workspace import "$notebook" --file "$HERE/app_health_probe.notebook" \
    --format SOURCE --language PYTHON --overwrite >/dev/null 2>&1 || {
      echo "  SKIP database probe: could not upload the notebook"; return 0; }

  local run_id
  run_id="$(databricks jobs submit -o json --json "$(python3 - "$notebook" "$DEPLOY_LAKEBASE_ENDPOINT" <<'PY'
import json, sys
notebook, endpoint = sys.argv[1], sys.argv[2]
print(json.dumps({
    "run_name": "app-health-probe",
    "tasks": [{"task_key": "probe",
               "notebook_task": {"notebook_path": notebook, "source": "WORKSPACE",
                                "base_parameters": {"endpoint": endpoint}},
               "environment_key": "default"}],
    "environments": [{"environment_key": "default",
                      "spec": {"client": "2", "dependencies": ["psycopg2-binary"]}}],
}))
PY
)" 2>&1 | python3 -c 'import json,sys;print(json.load(sys.stdin).get("run_id",""))' 2>/dev/null)"

  if [ -z "$run_id" ]; then
    echo "  SKIP database probe: could not submit the job"; return 0
  fi

  local task_run result
  task_run="$(databricks jobs get-run "$run_id" -o json \
    | python3 -c 'import json,sys;d=json.load(sys.stdin);print((d.get("tasks") or [{}])[0].get("run_id",""))')"
  result="$(databricks jobs get-run-output "$task_run" -o json 2>/dev/null \
    | python3 -c 'import json,sys;d=json.load(sys.stdin);print((d.get("notebook_output") or {}).get("result",""))' 2>/dev/null)"

  databricks workspace delete "$notebook" >/dev/null 2>&1 || true

  if [ -z "$result" ]; then
    echo "  SKIP database probe: the job produced no result (see run $run_id)"; return 0
  fi

  # The notebook exits a JSON OBJECT: {"checks": [...], "skipped": [...]}. It used to exit a bare list,
  # and this reader iterated the object's keys — `check["pass"]` on the string "checks" raised a
  # TypeError that printed a traceback and then reported "verification failed", which hid the real
  # verdict. Both shapes are accepted so an older deployed notebook still verifies.
  printf '%s' "$result" | python3 -c '
import json, sys

data = json.load(sys.stdin)
if isinstance(data, dict):
    checks, skipped = data.get("checks") or [], data.get("skipped") or []
else:
    checks, skipped = data, []

failed = 0
for check in checks:
    ok = bool(check.get("pass"))
    failed += 0 if ok else 1
    mark = "\033[32mPASS\033[0m" if ok else "\033[31mFAIL\033[0m"
    print("  %s %s — %s" % (mark, check.get("check"), check.get("detail")))
# A skip is NOT a pass. Saying so is the point: the first version of the probe counted an HTTP 401 from
# the app proxy as "served", so four routes passed without a handler ever running.
for skip in skipped:
    print("  \033[33mSKIP\033[0m %s — %s" % (skip.get("check"), skip.get("detail")))

if failed or not checks:
    print("  \033[31mFAIL\033[0m the database probe verified %d check(s)" % len(checks))
    sys.exit(1)
sys.exit(0)'
}

case "$ACTION" in
  verify) verify ;;
  *) preflight; check_quota; create_app; grant_scopes; provision_lakebase; provision_session_volume; deploy; verify ;;
esac
