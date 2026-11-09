#!/usr/bin/env bash
# Is the DEPLOYED app serving THIS checkout? Exits non-zero when it is not.
#
#   scripts/verify-deployed.sh [url]
#
# Why this exists. On 2026-11-09 `databricks apps deploy` printed "App started successfully" three times
# while the live app was missing three commits of work: no `POST /api/blobs`, no `/sessions/{id}/events`,
# no `seesImages` on any model, and no attach control in the bundle. Every check I ran before this file
# existed passed, because they asked "is it up?" and the answer was always yes.
#
# So this asks the question that matters: does the RUNNING app have what the SOURCE has? It probes for
# FINGERPRINTS of the current work — routes, fields, and a string that exists only in the current bundle —
# rather than health, which says nothing about version.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$HERE/.." && pwd)"
APP="${APP_NAME:-coding-agent}"
: "${DATABRICKS_HOST:?set DATABRICKS_HOST}"
export DATABRICKS_HOST

pass=0; fail=0
ok()   { printf '  \033[32mPASS\033[0m %s\n' "$*"; pass=$((pass+1)); }
bad()  { printf '  \033[31mFAIL\033[0m %s\n' "$*"; fail=$((fail+1)); }
info() { printf '  \033[2m%s\033[0m\n' "$*"; }

URL="${1:-$(databricks apps get "$APP" -o json 2>/dev/null | python3 -c 'import json,sys;print(json.load(sys.stdin).get("url",""))')}"
[ -n "$URL" ] || { echo "no URL: is the app deployed?" >&2; exit 2; }
TOKEN="$(databricks auth token --host "$DATABRICKS_HOST" -o json | python3 -c 'import json,sys;print(json.load(sys.stdin)["access_token"])')"
USER_EMAIL="${APP_DEV_USER:-raphael.mansuy@gmail.com}"

# The app sits behind the platform's OAuth proxy; a bearer token plus the forwarded-user header is how a
# logged-in browser reaches it, so that is what a probe must send.
H=(-H "Authorization: Bearer $TOKEN" -H "X-Forwarded-Email: $USER_EMAIL")

printf '\n\033[1mVerifying %s\033[0m\n' "$URL"
info "$(databricks apps get "$APP" -o json 2>/dev/null | python3 -c 'import json,sys;d=json.load(sys.stdin);dp=d.get("active_deployment") or {};print("deployment", dp.get("deployment_id"), "created", dp.get("create_time"))' 2>/dev/null)"

# -- 1. it answers at all -----------------------------------------------------------------------
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 "$URL/api/health" "${H[@]}")
[ "$code" = "200" ] && ok "the app answers /api/health" || bad "/api/health returned $code"

if [ "$code" != "200" ]; then
  printf '\n\033[31mThe app is not answering; nothing else can be checked.\033[0m See: make logs\n'
  exit 1
fi

# -- 2. it is running YOUR code, not a snapshot --------------------------------------------------
# A route that exists only in recent work. 405/422 means the path is registered; 404 or the SPA's HTML
# means it is not. A catch-all front end answers 200 with index.html, which is why status alone lies.
body=$(curl -s --max-time 30 -X POST "$URL/api/blobs" "${H[@]}" -H 'content-type: application/json' -d '{}')
if printf '%s' "$body" | grep -q '<!doctype html'; then
  bad 'POST /api/blobs fell through to the front end — the backend is OLDER than this checkout'
elif printf '%s' "$body" | grep -qE '"(detail|type)"|blobId'; then
  ok 'POST /api/blobs is served by the backend (the attach feature is deployed)'
else
  bad "POST /api/blobs gave an unexpected answer: ${body:0:100}"
fi

# The finite event read, added with the vision work.
ev=$(curl -s --max-time 30 "$URL/api/sessions/__probe__/events" "${H[@]}")
if printf '%s' "$ev" | grep -q '<!doctype html'; then
  bad '/api/sessions/{id}/events fell through to the front end — old backend'
else
  ok '/api/sessions/{id}/events exists'
fi

# -- 3. the catalogue carries the vision fact ----------------------------------------------------
models=$(curl -s --max-time 30 "$URL/api/llm/models" "${H[@]}")
printf '%s' "$models" | python3 -c '
import json,sys
try: d=json.load(sys.stdin)
except Exception: print("  \033[31mFAIL\033[0m the model catalogue did not parse"); sys.exit(1)
av=d.get("available") or []
if not av: print("  \033[31mFAIL\033[0m the catalogue is empty"); sys.exit(1)
missing=[m["id"] for m in av if "seesImages" not in m]
if missing:
    print(f"  \033[31mFAIL\033[0m {len(missing)} of {len(av)} models do not declare seesImages — old backend")
    sys.exit(1)
vis=[m["id"] for m in av if m.get("seesImages")]
print(f"  \033[32mPASS\033[0m {len(av)} models all declare seesImages; {len(vis)} declare vision")
for v in vis[:6]: print(f"        {v}")
' || fail=$((fail+1))

# -- 4. the bundle in the browser is the current one ---------------------------------------------
# A string that exists only in the shipped front end. If the deployed JS lacks it, the UI cannot show the
# attach menu no matter what the backend does — which is exactly what happened.
#
# Written to a FILE, not held in a shell variable: `printf '%s' "$js" | grep -q` on a 500 KB string gives a
# FALSE NEGATIVE (grep exits on the match, the writer takes SIGPIPE, and `set -o pipefail` reports failure).
# Measured — that bug made this very script claim the bundle was stale when it was identical to the local
# build, which the next check then contradicted.
probe_dir="$(mktemp -d)"; trap 'rm -rf "$probe_dir"' EXIT
index="$probe_dir/index.html"
curl -s --max-time 30 "$URL/" "${H[@]}" -o "$index"
bundle=$(grep -oE '/assets/index-[A-Za-z0-9_-]+\.js' "$index" | head -1)
if [ -z "$bundle" ]; then
  bad 'no JS bundle in the served HTML'
else
  curl -s --max-time 60 "$URL$bundle" "${H[@]}" -o "$probe_dir/app.js"
  if grep -q 'Attach a file' "$probe_dir/app.js"; then
    ok "the served bundle has the attach control ($bundle)"
  else
    bad "the served bundle has NO attach control ($bundle) — the front end was not rebuilt"
  fi
fi

# -- 5. the local build agrees with the deployed one ---------------------------------------------
# If the local dist differs from what is served, someone is testing a different app than they think.
local_js="$(ls -t "$APP_DIR"/web/dist/assets/index-*.js 2>/dev/null | head -1)"
if [ -n "$local_js" ]; then
  if [ "$(basename "$local_js")" = "$(basename "$bundle")" ]; then
    ok "the deployed bundle is byte-identical to the local build"
  else
    info "local build is $(basename "$local_js"), deployed is $(basename "$bundle") — run: make deploy"
  fi
fi

# -- 6. a real session can start ------------------------------------------------------------------
# The failure that produced an unusable screen: the default model had no key, so every new session 409'd
# and the composer came up with no folder and no model.
sid=$(curl -s --max-time 60 -X POST "$URL/api/sessions" "${H[@]}" -H 'content-type: application/json' \
        -d "{\"folder\":\"/Users/$USER_EMAIL/agent_scratch\"}")
if printf '%s' "$sid" | grep -q '"id"'; then
  ok "a session starts with the default model"
  sidv=$(printf '%s' "$sid" | python3 -c 'import json,sys;print(json.load(sys.stdin)["id"])' 2>/dev/null)
  [ -n "$sidv" ] && curl -s --max-time 20 -X DELETE "$URL/api/sessions/$sidv" "${H[@]}" >/dev/null 2>&1
else
  bad "a session does not start: $(printf '%s' "$sid" | head -c 140)"
fi

printf '\n'
if [ "$fail" -eq 0 ]; then
  printf '\033[32m\033[1mDEPLOYED AND CURRENT\033[0m — %d checks passed\n\n' "$pass"
  exit 0
fi
printf '\033[31m\033[1mNOT CURRENT\033[0m — %d passed, %d failed. This deployment is serving something else.\n' "$pass" "$fail"
printf '  Next: make sync && make deploy-only && make verify\n\n'
exit 1
