#!/usr/bin/env bash
# Provision the Unity Catalog volume a Python session exchanges its commands and results through.
#
#   scripts/provision-session-volume.sh [dev|prod]
#
# Idempotent: every step checks first and says what it found. It exists because the app can create a
# session's FILES (it writes them with the Files API) but it cannot create the volume they live in, and
# it cannot grant itself anything. Without this, the first Python cell of a session fails with
# PERMISSION_DENIED on a path the app never had a say in.
#
# The three grants are all required, and the least obvious is USE_CATALOG: a volume path is resolved
# through its catalog and schema, so an app that holds WRITE_VOLUME alone still gets a permission error
# that names the volume and not the missing parent grant.
set -uo pipefail

ENV_NAME="${1:-${APP_ENV_NAME:-prod}}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=env.sh
. "$HERE/env.sh" "$ENV_NAME" || exit 1

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
die() { printf '\033[31mSTOP: %s\033[0m\n' "$*" >&2; exit 1; }

#: `<catalog>/<schema>/<volume>`, from the app's own setting so the two cannot disagree.
FULL="${DEPLOY_SESSION_VOLUME#/Volumes/}"
CATALOG="${FULL%%/*}"
REST="${FULL#*/}"
SCHEMA="${REST%%/*}"
VOLUME="${REST#*/}"
[ -n "$CATALOG" ] && [ -n "$SCHEMA" ] && [ -n "$VOLUME" ] && [ "$VOLUME" != "$REST" ] \
  || die "APP_SESSION_VOLUME is '$DEPLOY_SESSION_VOLUME'; expected /Volumes/<catalog>/<schema>/<volume>"

say "Provisioning the session volume for '$ENV_NAME'"
require_workspace_identity || die "cannot confirm the workspace"

APP_SP="$(databricks apps get "$APP_NAME" -o json | python3 -c '
import json,sys
print(json.load(sys.stdin).get("service_principal_client_id",""))')"
[ -n "$APP_SP" ] || die "cannot read the service principal of '$APP_NAME'"
echo "  volume     $DEPLOY_SESSION_VOLUME"
echo "  principal  $APP_SP"

# ---------------------------------------------------------------- the volume
if databricks volumes read "$CATALOG.$SCHEMA.$VOLUME" -o json >/dev/null 2>&1; then
  echo "  exists"
else
  echo "  creating it"
  databricks volumes create "$CATALOG" "$SCHEMA" "$VOLUME" MANAGED >/dev/null 2>&1 \
    || die "cannot create $CATALOG.$SCHEMA.$VOLUME (the schema must exist, and this identity must own it)"
  databricks volumes read "$CATALOG.$SCHEMA.$VOLUME" -o json >/dev/null 2>&1 \
    || die "the volume was not created"
fi

# ---------------------------------------------------------------- the grants
# Each grant is applied unconditionally: PATCH adds a privilege already held without error, so this
# step is idempotent without reading the current list back and comparing it.
grant() {
  local kind="$1" name="$2" privileges="$3"
  local json
  json="$(python3 - "$APP_SP" "$privileges" <<'PY'
import json, sys
principal, wanted = sys.argv[1], sys.argv[2].split(",")
print(json.dumps({"changes": [{"principal": principal, "add": wanted}]}))
PY
)"
  databricks api patch "/api/2.1/unity-catalog/permissions/$kind/$name" --json "$json" >/dev/null 2>&1 \
    || die "cannot grant $privileges on $kind $name to $APP_SP"
  echo "  granted $privileges on $kind $name"
}

grant catalog "$CATALOG" "USE_CATALOG"
grant schema "$CATALOG.$SCHEMA" "USE_SCHEMA"
grant volume "$CATALOG.$SCHEMA.$VOLUME" "READ_VOLUME,WRITE_VOLUME"

echo "  the app can now read and write $DEPLOY_SESSION_VOLUME"
