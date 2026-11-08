#!/usr/bin/env bash
# Build the site, serve it, and run the screenshot scenes — in one shell, so the server outlives the
# build and dies with it.
#
#   bash site/verify.sh              # build, check, every scene
#   bash site/verify.sh S2 S7        # a subset of scenes
#
# A separate process for the server is not a detail: `python3 -m http.server ... &` in a short-lived
# shell is killed when that shell exits, and the next command then fails with ERR_CONNECTION_REFUSED
# while the site itself is perfectly fine. That cost one debugging cycle; this file is the fix.
set -uo pipefail

cd "$(dirname "$0")/.."
PORT="${PORT:-8130}"

echo "==> build"
python3 site/build.py || exit 1

echo "==> claims tests"
python3 site/tests/test_claims.py || exit 1

echo "==> check"
python3 site/check.py || exit 1

echo "==> serve on :$PORT"
( cd site/dist && python3 -m http.server "$PORT" >/tmp/opengenie-site.log 2>&1 ) &
SERVER=$!
trap 'kill $SERVER 2>/dev/null' EXIT

for _ in $(seq 1 40); do
  if curl -sf -o /dev/null "http://127.0.0.1:$PORT/"; then break; fi
  sleep 0.25
done
if ! curl -sf -o /dev/null "http://127.0.0.1:$PORT/"; then
  echo "server did not start; see /tmp/opengenie-site.log" >&2
  exit 1
fi

echo "==> spec set: links, ASCII, Mermaid, freshness"
python3 specs/008-github-page/tools/draw_wireframes.py --check || exit 1
if [ -d apps/coding-agent/web/node_modules ]; then
  ( cd apps/coding-agent/web \
    && node scripts/verify-spec-links.mjs ../../../specs/008-github-page \
    && node scripts/verify-spec-ascii.mjs ../../../specs/008-github-page ) || exit 1
  if [ -n "${MERMAID_PATH:-}" ]; then
    ( cd apps/coding-agent/web && node scripts/verify-spec-mermaid.mjs ../../../specs/008-github-page ) || exit 1
  else
    echo "    (mermaid parse check skipped: set MERMAID_PATH and JSDOM_PATH to run it)"
  fi
else
  echo "    (spec link/ASCII checks skipped: apps/coding-agent/web/node_modules is absent)"
fi

echo "==> reproducibility: two builds, byte-identical"
rm -rf /tmp/opengenie-b1 /tmp/opengenie-b2
python3 site/build.py --no-stamp >/dev/null
cp -R site/dist /tmp/opengenie-b1
python3 site/build.py --no-stamp >/dev/null
cp -R site/dist /tmp/opengenie-b2
if diff -r /tmp/opengenie-b1 /tmp/opengenie-b2 >/dev/null; then
  echo "    identical"
else
  echo "    NOT identical — the build is not reproducible" >&2
  exit 1
fi

echo "==> scenes"
if [ $# -eq 0 ]; then
  APP_URL="http://127.0.0.1:$PORT" node site/shots.mjs --all
else
  args=()
  for s in "$@"; do args+=(--scene "$s"); done
  APP_URL="http://127.0.0.1:$PORT" node site/shots.mjs "${args[@]}"
fi
STATUS=$?

echo "==> shrink the screenshots that will be committed"
# A regenerated capture is a 24-bit PNG; the committed set is 8-bit with dithering, chosen by measuring
# its own error (site/optimize_shots.py). Running it here keeps the two in step: the pictures on disk are
# always the small ones, so a commit cannot add 15 MB of avoidable binary.
if python3 -c "import PIL" 2>/dev/null; then
  python3 site/optimize_shots.py | tail -3
else
  echo "    (skipped: Pillow is not installed; images stay uncompressed)"
fi

echo
echo "screenshots: specs/008-github-page/e2e/"

# The deployed audit answers a different question from the local one: does what Pages actually serves
# behave like what this repository builds? A local server serves from the root and Pages serves from a
# subpath, so only this run can see an absolute-path bug (it found d70f567).
if [ "${AUDIT_DEPLOYED:-0}" = "1" ]; then
  echo "==> the same audit against the published site"
  APP_URL="https://raphaelmansuy.github.io/opengenie" node site/shots.mjs --scene S1 --scene S2 \
    && cp specs/008-github-page/e2e/audit.json specs/008-github-page/e2e/audit-live.json \
    && git checkout -- specs/008-github-page/e2e/ \
    || echo "    (deployed audit reported a problem; see specs/008-github-page/e2e/audit.json)"
fi

exit $STATUS
