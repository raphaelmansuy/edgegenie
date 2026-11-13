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
#
# Two kinds of check, because the platform decides which are possible:
#
#   platform  the Apps API: deployment state, app state, scopes, resources. Always available.
#   http      the live URL: routes, catalogue fields, the served bundle. Needs a USER token, because
#             the app sits behind the Databricks OAuth proxy and a personal access token is refused by
#             it (measured: 401 with an empty body and `server: databricks`). When only a PAT is
#             available these are SKIPPED and said to be skipped — a verification that quietly checks
#             nothing is worse than none.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$HERE/.." && pwd)"

# An environment name is optional here: the caller may set DATABRICKS_HOST and APP_NAME directly,
# which is how this ran before there was more than one workspace.
if [ -z "${DATABRICKS_HOST:-}" ] || [ -n "${APP_ENV_NAME:-}" ]; then
  # shellcheck source=env.sh
  . "$HERE/env.sh" "${APP_ENV_NAME:-prod}" || exit 2
fi
APP="${APP_NAME:-coding-agent}"
: "${DATABRICKS_HOST:?set DATABRICKS_HOST}"
export DATABRICKS_HOST

pass=0; fail=0; skip=0
ok()   { printf '  \033[32mPASS\033[0m %s\n' "$*"; pass=$((pass+1)); }
bad()  { printf '  \033[31mFAIL\033[0m %s\n' "$*"; fail=$((fail+1)); }
info() { printf '  \033[2m%s\033[0m\n' "$*"; }
skipped() { printf '  \033[33mSKIP\033[0m %s\n' "$*"; skip=$((skip+1)); }

URL="${1:-$(databricks apps get "$APP" -o json 2>/dev/null | python3 -c 'import json,sys;print(json.load(sys.stdin).get("url",""))')}"
[ -n "$URL" ] || { echo "no URL: is the app deployed?" >&2; exit 2; }
USER_EMAIL="${APP_DEV_USER:-raphael.mansuy@gmail.com}"

printf '\n\033[1mVerifying %s\033[0m\n' "$URL"

# -- 0. the platform's own view -------------------------------------------------------------------
# This part never needs a browser. A deployment can be SUCCEEDED while the process has crashed, so
# the two states are read separately and the stronger one wins.
APP_JSON="$(databricks apps get "$APP" -o json 2>/dev/null)"
if [ -z "$APP_JSON" ]; then
  bad "the app '$APP' does not exist in $DATABRICKS_HOST"
  printf '\n\033[31mNOT DEPLOYED\033[0m\n\n'; exit 1
fi
read -r DEP_STATE APP_STATE <<<"$(printf '%s' "$APP_JSON" | python3 -c '
import json,sys
d = json.load(sys.stdin)
dp = d.get("active_deployment") or {}
print((dp.get("status") or {}).get("state","none"), (d.get("app_status") or {}).get("state","none"))')"
info "deployment $DEP_STATE · app $APP_STATE"

[ "$DEP_STATE" = "SUCCEEDED" ] && ok "the last deployment SUCCEEDED" || bad "the last deployment is $DEP_STATE"
[ "$APP_STATE" = "RUNNING" ] && ok "the app process is RUNNING" || bad "the app process is $APP_STATE"

# Check the exact declared scopes and run-identity qualification before HTTP probes.
scopes_python="${PYTHON:-python3}"
[ ! -x "$APP_DIR/.venv/bin/python" ] || scopes_python="$APP_DIR/.venv/bin/python"
if printf '%s' "$APP_JSON" | "$scopes_python" "$HERE/check-app-scopes.py" coding-agent "${DEPLOY_REQUIRED_SCOPES_CSV:-}"; then
  ok "user API scopes match databricks.yml"
else
  bad "user API scopes differ from databricks.yml or could not be read"
fi
if "$scopes_python" "$HERE/check-run-identity.py"; then
  ok "agent run-identity declaration is safe"
else
  bad "agent run identity has not passed isolation qualification"
fi

# -- 0b. the volume a Python session exchanges its files through ---------------------------------
# The app can write those files but cannot create the volume, and cannot grant itself anything, so a
# missing grant is a session that cannot start. The app falls back to one-shot runs in words, which is
# why this is not a crash: it is a capability that is silently absent unless somebody checks for it.
SESSION_VOLUME="${DEPLOY_SESSION_VOLUME:-/Volumes/workspace/agent_scratch/kernel_sessions}"
# `/Volumes/a/b/c` is the path; the Unity Catalog permissions API wants `a.b.c`.
SESSION_VOLUME_NAME="$(printf '%s' "${SESSION_VOLUME#/Volumes/}" | tr '/' '.')"
SP_ID="$(printf '%s' "$APP_JSON" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("service_principal_client_id",""))')"
VOL_PERMS="$(databricks api get "/api/2.1/unity-catalog/permissions/volume/$SESSION_VOLUME_NAME" \
  -o json 2>/dev/null || true)"
if [ -z "$VOL_PERMS" ]; then
  info "could not read the grants on $SESSION_VOLUME (this identity may not administer it)"
else
  printf '%s' "$VOL_PERMS" | SP_ID="$SP_ID" python3 -c '
import json, os, sys
sp = os.environ["SP_ID"]
held = set()
for a in (json.load(sys.stdin).get("privilege_assignments") or []):
    if a.get("principal") == sp:
        held |= set(a.get("privileges") or [])
want = {"READ_VOLUME", "WRITE_VOLUME"}
missing = sorted(want - held)
if missing:
    print("  \033[31mFAIL\033[0m the app service principal lacks " + ", ".join(missing)
          + " on the session volume — a Python session cannot start")
    sys.exit(1)
print("  \033[32mPASS\033[0m the app service principal can read and write the session volume")' \
    && pass=$((pass+1)) || { fail=$((fail+1)); info "  fix: scripts/provision-session-volume.sh ${APP_ENV_NAME:-prod}"; }
fi

printf '%s' "$APP_JSON" | python3 -c '
import json,sys
have = {r.get("name") for r in (json.load(sys.stdin).get("resources") or [])}
missing = [r for r in ("vertex-sa","llm-kek") if r not in have]
if missing:
    print("  \033[31mFAIL\033[0m secret resources not attached: " + ", ".join(missing)); sys.exit(1)
print("  \033[32mPASS\033[0m secret resources attached (vertex-sa, llm-kek)")' \
  && pass=$((pass+1)) || fail=$((fail+1))

# -- 1. can the live URL be probed at all? --------------------------------------------------------
# A user token is required by the OAuth proxy. `databricks auth token` succeeds only for an OAuth
# login, not for a PAT, so its failure is the signal to skip the HTTP checks rather than fail them.
TOKEN=""
if TOKEN="$(databricks auth token --host "$DATABRICKS_HOST" -o json 2>/dev/null \
  | python3 -c 'import json,sys;print(json.load(sys.stdin).get("access_token",""))' 2>/dev/null)" \
  && [ -n "$TOKEN" ]; then
  H=(-H "Authorization: Bearer $TOKEN" -H "X-Forwarded-Email: $USER_EMAIL")
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 "$URL/api/health" "${H[@]}")
  if [ "$code" = "401" ]; then
    info "the OAuth proxy refused a token minted here; HTTP checks are skipped"
    TOKEN=""
  fi
fi

if [ -z "$TOKEN" ]; then
  skipped "HTTP probes: this credential cannot pass the app's OAuth proxy"
  info "  to run them: databricks auth login --host $DATABRICKS_HOST, then re-run"
  info "  or open $URL in a browser"
fi

# -- 2. it answers, and it is running YOUR code ---------------------------------------------------
# A route that exists only in recent work. 405/422 means the path is registered; 404 or the SPA's HTML
# means it is not. A catch-all front end answers 200 with index.html, which is why status alone lies.
if [ -n "$TOKEN" ]; then
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 "$URL/api/health" "${H[@]}")
  [ "$code" = "200" ] && ok "the app answers /api/health" || bad "/api/health returned $code"

  body=$(curl -s --max-time 30 -X POST "$URL/api/blobs" "${H[@]}" -H 'content-type: application/json' -d '{}')
  if printf '%s' "$body" | grep -q '<!doctype html'; then
    bad 'POST /api/blobs fell through to the front end — the backend is OLDER than this checkout'
  elif printf '%s' "$body" | grep -q 'sessionId'; then
    bad 'POST /api/blobs still requires a session — attaching before the first message is not deployed'
  elif printf '%s' "$body" | grep -qE '"(detail|type)"|blobId'; then
    ok 'POST /api/blobs is served, and a session is not required (home-screen attach)'
  else
    bad "POST /api/blobs gave an unexpected answer: ${body:0:160}"
  fi

  ev=$(curl -s --max-time 30 "$URL/api/sessions/__probe__/events" "${H[@]}")
  if printf '%s' "$ev" | grep -q '<!doctype html'; then
    bad '/api/sessions/{id}/events fell through to the front end — old backend'
  else
    ok '/api/sessions/{id}/events exists'
  fi

  # -- 2b. the object types spec 013 and spec 014 added (a fingerprint, not a health check) -------
  # These routes exist ONLY in this work, so a 404 or the SPA's HTML means the backend is older than the
  # checkout. A 200 with `items`, or a 403/502 carrying a sentence, both mean the route is registered:
  # a denial is a real answer and the pages render it (spec 013 [E-1], spec 014 [UI-3]).
  for route in /api/lakebase/projects /api/apps /api/jobs /api/pipelines; do
    body=$(curl -s --max-time 30 "$URL$route" "${H[@]}")
    if printf '%s' "$body" | grep -q '<!doctype html'; then
      bad "$route fell through to the front end — the backend is OLDER than this checkout"
    elif printf '%s' "$body" | grep -q '"items"'; then
      ok "$route is served and lists objects"
    elif printf '%s' "$body" | grep -qE '"detail"'; then
      ok "$route is served and answered with a reason: $(printf '%s' "$body" | head -c 90)"
    else
      bad "$route gave an unexpected answer: ${body:0:120}"
    fi
  done

  # -- 2c. the rules route proves spec 014's vocabulary is deployed, not only its routing ----------
  # `/api/infra/run-actions` is answered by `api.domain.jobs`, so the values below prove the state tables
  # shipped. A running run must offer Cancel and must NOT offer a Repair; a failed terminal run is the
  # reverse. Those two facts are the whole of [RUN-2] and [RUN-3], computed server-side.
  actions=$(curl -s --max-time 30 "$URL/api/infra/run-actions?life_cycle=RUNNING" "${H[@]}")
  if printf '%s' "$actions" | grep -q '<!doctype html'; then
    bad "/api/infra/run-actions fell through to the front end — spec 014 is not deployed"
  else
    printf '%s' "$actions" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    print("  \033[31mFAIL\033[0m run-actions did not parse"); sys.exit(1)
problems = []
if d.get("word") != "running":
    problems.append("a RUNNING run reads %r, expected running" % (d.get("word"),))
if d.get("cancel") is not True:
    problems.append("a RUNNING run does not offer Cancel")
if d.get("repair") is not False:
    problems.append("a RUNNING run offers a Repair, which the platform refuses")
if problems:
    print("  \033[31mFAIL\033[0m " + "; ".join(problems)); sys.exit(1)
print("  \033[32mPASS\033[0m the state vocabulary is live: a running run reads running, offers Cancel, no Repair")' \
      && pass=$((pass+1)) || fail=$((fail+1))
  fi

  # -- 2c-bis. the app states its own version, and it is THE version ------------------------------
  # `/api/health` is `{ok: true}` for every build ever deployed, so it cannot answer "is this the
  # release I just shipped". `VERSION` is the file inside this checkout; the live app must name the same
  # string. A mismatch is a stale deployment, and the message says so rather than "unexpected answer".
  want_version="$(cat "$APP_DIR/VERSION" 2>/dev/null | tr -d '[:space:]')"
  ver=$(curl -s --max-time 30 "$URL/api/version" "${H[@]}")
  if printf '%s' "$ver" | grep -q '<!doctype html'; then
    bad "/api/version fell through to the front end — the backend predates the version route"
  elif [ -z "$want_version" ]; then
    bad "apps/coding-agent/VERSION is missing or empty; nothing to compare the deployment with"
  else
    printf '%s' "$ver" | WANT="$want_version" python3 -c '
import json, os, sys
want = os.environ["WANT"]
try:
    d = json.load(sys.stdin)
except Exception:
    print("  \033[31mFAIL\033[0m /api/version did not parse"); sys.exit(1)
have = d.get("version")
if have != want:
    print(f"  \033[31mFAIL\033[0m the app reports v{have}, this checkout is v{want} — the deployment is stale")
    sys.exit(1)
# The commit is optional (a Workspace-folder deployment has no git), but it must be PRESENT as a key
# so a client can read it without a guard, and it must never be the literal string "unknown".
commit = d.get("commit")
if commit == "unknown":
    print("  \033[31mFAIL\033[0m the app reports its commit as unknown; empty is honest, \"unknown\" is not")
    sys.exit(1)
links = [d.get(k) for k in ("docs", "source", "releases")]
if not all(isinstance(x, str) and x.startswith("http") for x in links):
    print(f"  \033[31mFAIL\033[0m the version route does not carry the docs/source/releases links: {links}")
    sys.exit(1)
where = commit[:7] if commit else "no commit reported"
print(f"  \033[32mPASS\033[0m the app answers v{have} ({where}) and links its docs, source and releases")' \
      && pass=$((pass+1)) || fail=$((fail+1))
  fi

  # -- 2c-ter. the notebook session route exists, and the app says whether it is on ---------------
  # The Python session is the feature of 1.1.0: a route a stale deployment does not have. A 404 here
  # means the backend predates sessions. The answer is read too, because "switched off" and "not
  # deployed" are different facts and only one of them is a failure.
  ks=$(curl -s --max-time 30 "$URL/api/notebook/kernels?path=/probe/version-check" "${H[@]}")
  if printf '%s' "$ks" | grep -q '<!doctype html'; then
    bad '/api/notebook/kernels fell through to the front end — the backend predates Python sessions'
  elif printf '%s' "$ks" | grep -q '"state"'; then
    state=$(printf '%s' "$ks" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("state",""))' 2>/dev/null)
    case "$state" in
      off) info "the session route is live but sessions are switched off (APP_PYTHON_SESSION=off)" ;;
      *) ok "the notebook session route is live (state: $state)" ;;
    esac
  elif printf '%s' "$ks" | grep -q '"detail"'; then
    info "the session route answered $(printf '%s' "$ks" | head -c 120) — not an administrator for this build"
  else
    bad "GET /api/notebook/kernels gave an unexpected answer: $(printf '%s' "$ks" | head -c 160)"
  fi

  # -- 2d. there is NO write route for a job or a pipeline, by design -----------------------------
  # Every action goes through the agent so the write fence has one home (spec 014 [07 §5]). A POST here
  # answering anything but 404/405 means a second, un-fenced write path shipped.
  for route in /api/jobs/1 /api/pipelines/x; do
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 -X POST "$URL$route" "${H[@]}" \
             -H 'content-type: application/json' -d '{}')
    case "$code" in
      404|405) ok "POST $route is refused ($code) — the browser has no write path, as designed" ;;
      401|403) ok "POST $route is refused ($code) before reaching a handler" ;;
      *) bad "POST $route answered $code — a write route exists for an object that must only be written by the agent" ;;
    esac
  done

  # -- 3. the catalogue carries the vision fact ---------------------------------------------------
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
' && pass=$((pass+1)) || fail=$((fail+1))

  # -- 3b. the routes this assessment added, and the words that exist only in the new code ---------
  # A deploy that prints SUCCEEDED while serving the previous commit is the failure this whole script
  # exists for — and it HAPPENED on this deployment: the app reported commit 2063af3 while HEAD was
  # 19c471d. So these probe for the new surface by name, and a 404 means the backend is old.
  for route in /api/config /api/docs/search?q=fence; do
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "$URL$route" "${H[@]}")
    case "$code" in
      200) ok "GET $route answers 200 — the new backend is live" ;;
      401|403) ok "GET $route answers $code before reaching a handler (the proxy wall)" ;;
      404) bad "GET $route is 404 — this deployment is serving a backend WITHOUT the new routes" ;;
      *) bad "GET $route answered $code" ;;
    esac
  done
  # The write-mode vocabulary exists only in the new code. Its presence in the response proves the
  # module loaded, not merely that a route matched a prefix.
  cfg=$(curl -s --max-time 20 "$URL/api/config" "${H[@]}")
  printf '%s' "$cfg" | grep -q '"writeModes"' \
    && ok "the deployed backend publishes the three write modes" \
    || bad "the deployed backend does not publish writeModes — old code"

  # -- 4. the bundle in the browser is the current one -------------------------------------------
  # A string that exists only in the shipped front end. Written to FILES, not held in shell
  # variables: `printf '%s' "$js" | grep -q` on a 500 KB string gives a FALSE NEGATIVE (grep exits on
  # the match, the writer takes SIGPIPE, and `pipefail` reports failure). Measured — that bug made
  # this script claim a stale bundle when it was identical to the local build.
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
    # The version the browser will print. Compiled in from VERSION at build time, so a bundle that
    # lacks the current version string is a bundle from before this release, however new its filename.
    # The probe is the BARE number: the label is assembled at run time (`v${version}`), so minification
    # leaves `1.0.0` in the bundle and never the literal `v1.0.0`. Measured on this build.
    if [ -n "${want_version:-}" ] && grep -qF "$want_version" "$probe_dir/app.js"; then
      ok "the served bundle carries the compiled version $want_version"
    elif [ -n "${want_version:-}" ]; then
      bad "the served bundle does not contain $want_version — it was built before this release"
    fi
    # ...and the documentation link, so a reader of the deployed page can find the site from it.
    if grep -q 'raphaelmansuy.github.io/opengenie' "$probe_dir/app.js"; then
      ok "the served bundle links the documentation site"
    else
      bad "the served bundle has no link to raphaelmansuy.github.io/opengenie"
    fi
  fi

  # -- 5. the local build agrees with the deployed one -------------------------------------------
  local_js="$(ls -t "$APP_DIR"/web/dist/assets/index-*.js 2>/dev/null | head -1)"
  if [ -n "$local_js" ] && [ -n "${bundle:-}" ]; then
    if [ "$(basename "$local_js")" = "$(basename "$bundle")" ]; then
      ok "the deployed bundle is byte-identical to the local build"
    else
      info "local build is $(basename "$local_js"), deployed is $(basename "$bundle") — run: scripts/deploy.sh"
    fi
  fi

  # -- 6. a real session can start ---------------------------------------------------------------
  # The failure that produced an unusable screen: the default model had no key, so every new session
  # 409'd and the composer came up with no folder and no model.
  sid=$(curl -s --max-time 60 -X POST "$URL/api/sessions" "${H[@]}" -H 'content-type: application/json' \
          -d "{\"folder\":\"/Users/$USER_EMAIL/agent_scratch\"}")
  if printf '%s' "$sid" | grep -q '"id"'; then
    ok "a session starts with the default model"
    sidv=$(printf '%s' "$sid" | python3 -c 'import json,sys;print(json.load(sys.stdin)["id"])' 2>/dev/null)
    [ -n "$sidv" ] && curl -s --max-time 20 -X DELETE "$URL/api/sessions/$sidv" "${H[@]}" >/dev/null 2>&1
  else
    bad "a session does not start: $(printf '%s' "$sid" | head -c 140)"
  fi
fi

printf '\n'
if [ "$fail" -eq 0 ]; then
  if [ "$skip" -gt 0 ]; then
    printf '\033[33mPLATFORM CHECKS PASSED; LIVE APP NOT VERIFIED\033[0m — %d passed, %d skipped\n' "$pass" "$skip"
    exit 1
  fi
  printf '\033[32m\033[1mDEPLOYED AND CURRENT\033[0m — %d passed' "$pass"
  [ "$skip" -gt 0 ] && printf ', %d skipped (see above)' "$skip"
  printf '\n\n'
  exit 0
fi
printf '\033[31m\033[1mNOT CURRENT\033[0m — %d passed, %d failed. This deployment is serving something else.\n' "$pass" "$fail"
printf '  Next: scripts/deploy.sh %s\n\n' "${APP_ENV_NAME:-prod}"
exit 1
