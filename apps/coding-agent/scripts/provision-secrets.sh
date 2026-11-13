#!/usr/bin/env bash
# Provision the secret scope a deployment reads its two secrets from.
#
#   scripts/provision-secrets.sh [dev|prod]
#
# Two secrets, and they are different in kind:
#
#   llm-kek    random 32 bytes, base64. Encrypts provider keys stored in Lakebase. It never existed
#              anywhere else, so it is generated here if absent. Replacing it makes every stored
#              provider key unreadable — that is the point of envelope encryption, and the reason
#              this script says "exists" rather than rotating.
#
#   vertex-sa  a Google service-account JSON for the Vertex/Gemini models. It is NOT generated:
#              it comes from Google Cloud, and this script refuses to invent one.
#
# Idempotent and non-destructive: an existing key is reported, never overwritten.
set -uo pipefail

ENV_NAME="${1:-${APP_ENV_NAME:-prod}}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=env.sh
. "$HERE/env.sh" "$ENV_NAME" || exit 1

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
die() { printf '\033[31mSTOP: %s\033[0m\n' "$*" >&2; exit 1; }

say "Provisioning secrets for '$ENV_NAME'"
require_workspace_identity || die "cannot confirm the workspace"

SCOPE="$DEPLOY_SECRET_SCOPE"
VERTEX_KEY_FILE="${VERTEX_SA_JSON:-}"

# ---------------------------------------------------------------- scope
if databricks secrets list-scopes -o json 2>/dev/null | python3 -c '
import json,sys
sys.exit(0 if any(s.get("name") == "'"$SCOPE"'" for s in json.load(sys.stdin)) else 1)'; then
  echo "  scope $SCOPE exists"
else
  databricks secrets create-scope "$SCOPE" >/dev/null 2>&1 || die "could not create scope $SCOPE"
  echo "  created scope $SCOPE"
fi

existing() {
  databricks secrets list-secrets "$SCOPE" -o json 2>/dev/null | python3 -c '
import json,sys
print("yes" if any(s.get("key") == sys.argv[1] for s in json.load(sys.stdin)) else "no")' "$1"
}

# ---------------------------------------------------------------- the KEK
say "1/2 llm-kek (encrypts provider keys stored in Lakebase)"
if [ "$(existing llm-kek)" = "yes" ]; then
  echo "  present — left alone (replacing it would make every stored provider key unreadable)"
else
  python3 -c "import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode(),end='')" \
    | databricks secrets put-secret "$SCOPE" llm-kek >/dev/null 2>&1 \
    || die "could not write llm-kek"
  echo "  generated (32 random bytes, base64)"
fi

# ---------------------------------------------------------------- the Vertex key
say "2/2 vertex-sa (Google service-account JSON, used by the Gemini models)"
if [ "$(existing vertex-sa)" = "yes" ]; then
  echo "  present — left alone"
elif [ -n "$VERTEX_KEY_FILE" ]; then
  [ -f "$VERTEX_KEY_FILE" ] || die "VERTEX_SA_JSON points at $VERTEX_KEY_FILE, which does not exist"
  python3 -c '
import json,sys
d = json.load(open(sys.argv[1]))
missing = [k for k in ("type","project_id","client_email","private_key") if not d.get(k)]
if missing: sys.exit("not a service-account JSON: missing " + ", ".join(missing))
if d.get("type") != "service_account": sys.exit("type is %r, expected service_account" % d.get("type"))
print(d["client_email"])' "$VERTEX_KEY_FILE" >/dev/null \
    || die "$VERTEX_KEY_FILE is not a usable service-account JSON"
  databricks secrets put-secret "$SCOPE" vertex-sa --string-value "$(cat "$VERTEX_KEY_FILE")" >/dev/null 2>&1 \
    || die "could not write vertex-sa"
  echo "  uploaded from $VERTEX_KEY_FILE"
else
  echo "  ABSENT — the Gemini/Vertex models will answer 'no key' until one is provided:"
  echo "    VERTEX_SA_JSON=/path/to/service-account.json scripts/provision-secrets.sh $ENV_NAME"
  echo "  the app deploys and runs without it; only the Vertex models are unavailable."
fi

say "Secrets for '$ENV_NAME'"
databricks secrets list-secrets "$SCOPE" -o json 2>/dev/null \
  | python3 -c 'import json,sys
for s in json.load(sys.stdin): print("  " + s["key"])'
