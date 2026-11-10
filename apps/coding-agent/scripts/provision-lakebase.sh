#!/usr/bin/env bash
# Provision the Lakebase side of a deployment: the project, and the app role's privileges.
#
#   scripts/provision-lakebase.sh [dev|prod]
#
# Idempotent: every step checks first and says what it found. It exists because "the app crashed on
# deploy" is a terrible way to learn that the database was never created, and because the two
# prerequisites that actually break a deploy are not obvious:
#
#   1. the Lakebase project must exist (the app cannot create one);
#   2. the app's SERVICE PRINCIPAL must hold CONNECT + CREATE on the database, because the app
#      creates its own `llm` and `agent` schemas at boot and will crash without them.
#
# Step 2 cannot always be done from here. On a workspace whose Lakebase endpoint is a private-link
# ingress, port 5432 is unroutable from a laptop (measured: reachable-looking, then 30 s timeouts).
# In that case the grants are applied by a notebook on in-workspace compute, which does reach it.
# The script decides by trying, not by assuming.
set -uo pipefail

ENV_NAME="${1:-${APP_ENV_NAME:-prod}}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=env.sh
. "$HERE/env.sh" "$ENV_NAME" || exit 1

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
die() { printf '\033[31mSTOP: %s\033[0m\n' "$*" >&2; exit 1; }

say "Provisioning Lakebase for '$ENV_NAME'"
require_workspace_identity || die "cannot confirm the workspace"

PROJECT="projects/${DEPLOY_LAKEBASE_PROJECT}"

# ---------------------------------------------------------------- project
say "1/3 Project"
if databricks postgres get-project "$PROJECT" -o json >/dev/null 2>&1; then
  echo "  $PROJECT exists"
else
  echo "  creating $PROJECT"
  databricks postgres create-project "$DEPLOY_LAKEBASE_PROJECT" \
    --json "{\"spec\":{\"display_name\":\"${DEPLOY_LAKEBASE_PROJECT} (${ENV_NAME})\"}}" >/dev/null 2>&1 \
    || die "could not create $PROJECT"
  echo "  created $PROJECT"
fi

ENDPOINT_HOST="$(databricks postgres get-endpoint "$DEPLOY_LAKEBASE_ENDPOINT" -o json 2>/dev/null \
  | python3 -c 'import json,sys;print((json.load(sys.stdin).get("status",{}).get("hosts") or {}).get("host",""))' 2>/dev/null)"
[ -n "$ENDPOINT_HOST" ] || die "endpoint $DEPLOY_LAKEBASE_ENDPOINT has no host yet; wait for the project to finish"
echo "  endpoint   $DEPLOY_LAKEBASE_ENDPOINT"
echo "  host       $ENDPOINT_HOST"

# ---------------------------------------------------------------- app and its identity
say "2/3 The app's service principal"
APP_JSON="$(databricks apps get "$APP_NAME" -o json 2>/dev/null)" \
  || die "app '$APP_NAME' does not exist yet; create it first (scripts/deploy.sh does)"
APP_SP="$(printf '%s' "$APP_JSON" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("service_principal_client_id",""))')"
[ -n "$APP_SP" ] || die "app '$APP_NAME' has no service principal client id"
echo "  service principal $APP_SP"

# A Postgres role backed by the service principal. `--replace-existing` makes a re-run a no-op
# rather than an error, so this script can be run on every deploy.
databricks postgres create-role "projects/${DEPLOY_LAKEBASE_PROJECT}/branches/${DEPLOY_LAKEBASE_BRANCH}" \
  --role-id "${APP_NAME}-sp" --replace-existing \
  --json "{\"spec\":{\"identity_type\":\"SERVICE_PRINCIPAL\",\"postgres_role\":\"${APP_SP}\",\"auth_method\":\"LAKEBASE_OAUTH_V1\"}}" \
  >/dev/null 2>&1 || die "could not create the Postgres role for $APP_SP"
echo "  role ${APP_NAME}-sp -> $APP_SP"

# ---------------------------------------------------------------- privileges
say "3/3 Privileges (CONNECT + CREATE, so the app can create its llm/agent schemas)"

grant_direct() {
  # Works only where the endpoint is routable. Tried first because it needs no job.
  local token
  token="$(databricks postgres generate-database-credential "$DEPLOY_LAKEBASE_ENDPOINT" -o json 2>/dev/null \
    | python3 -c 'import json,sys;print(json.load(sys.stdin).get("token",""))' 2>/dev/null)"
  [ -n "$token" ] || return 2
  local me
  me="$(databricks current-user me -o json | python3 -c 'import json,sys;print(json.load(sys.stdin)["userName"])')"
  PGPASSWORD="$token" psql -w \
    "host=$ENDPOINT_HOST port=5432 dbname=databricks_postgres user=$me sslmode=require connect_timeout=20" \
    -v ON_ERROR_STOP=1 -q -c "
      GRANT CONNECT, CREATE ON DATABASE databricks_postgres TO \"$APP_SP\";
      GRANT USAGE, CREATE ON SCHEMA public TO \"$APP_SP\";" >/dev/null 2>&1
}

if [ "$DEPLOY_LAKEBASE_DIRECT" = "yes" ] && command -v psql >/dev/null && grant_direct; then
  echo "  granted directly over psql"
else
  # The path that works when port 5432 is not routable from here: run the grants on in-workspace
  # compute, which is inside the network the endpoint lives in.
  echo "  applying grants with an in-workspace job"
  GRANT_NOTEBOOK="/Workspace/Users/$(databricks current-user me -o json \
    | python3 -c 'import json,sys;print(json.load(sys.stdin)["userName"])')/lakebase_grants"

  databricks workspace import "$GRANT_NOTEBOOK" --file "$HERE/lakebase_grants.notebook" \
    --format SOURCE --language PYTHON --overwrite >/dev/null 2>&1 \
    || die "could not upload the grants notebook"

  RUN_ID="$(databricks jobs submit -o json --json "$(python3 - "$GRANT_NOTEBOOK" "$DEPLOY_LAKEBASE_ENDPOINT" "$APP_SP" <<'PY'
import json, sys
notebook, endpoint, app_sp = sys.argv[1], sys.argv[2], sys.argv[3]
print(json.dumps({
    "run_name": "lakebase-grants",
    "tasks": [{
        "task_key": "grants",
        "notebook_task": {
            "notebook_path": notebook,
            "source": "WORKSPACE",
            "base_parameters": {"endpoint": endpoint, "database": "databricks_postgres", "app_sp": app_sp},
        },
        "environment_key": "default",
    }],
    "environments": [{"environment_key": "default",
                      "spec": {"client": "2", "dependencies": ["psycopg2-binary"]}}],
}))
PY
)" 2>&1 | python3 -c 'import json,sys;print(json.load(sys.stdin).get("run_id",""))' 2>/dev/null)"

  [ -n "$RUN_ID" ] || die "could not submit the grants job"
  echo "  job run $RUN_ID"

  TASK_RUN="$(databricks jobs get-run "$RUN_ID" -o json | python3 -c 'import json,sys;d=json.load(sys.stdin);print((d.get("tasks") or [{}])[0].get("run_id",""))')"
  STATE="$(databricks jobs get-run "$TASK_RUN" -o json | python3 -c 'import json,sys;print((json.load(sys.stdin).get("state") or {}).get("result_state",""))')"
  [ "$STATE" = "SUCCESS" ] || die "the grants job ended as ${STATE:-unknown}; see run $RUN_ID"

  databricks workspace delete "$GRANT_NOTEBOOK" >/dev/null 2>&1 || true
  echo "  grants applied"
fi

say "Lakebase for '$ENV_NAME' is ready"
printf '  %s\n  %s\n' "$DEPLOY_LAKEBASE_ENDPOINT" "role ${APP_NAME}-sp ($APP_SP): CONNECT, CREATE"
