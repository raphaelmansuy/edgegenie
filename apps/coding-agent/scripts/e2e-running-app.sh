#!/bin/bash
# End-to-end against a RUNNING app (local or deployed): real opencode over ACP.
#
#   scripts/e2e-running-app.sh https://coding-agent-xxxx.aws.databricksapps.com
#
# Exits non-zero if any check fails. Works whether or not the model is available: a turn that ends
# in a explained failure is a pass, because "the app told the truth" is what this checks.
set -u
URL="${1:-http://127.0.0.1:8020}"
pass=0; fail=0
check() { if [ "$2" = "$3" ]; then echo "  PASS $1 ($2)"; pass=$((pass+1)); else echo "  FAIL $1 (got $2, want $3)"; fail=$((fail+1)); fi; }

echo "== health"
check "GET /" "$(curl -s -o /dev/null -w '%{http_code}' "$URL/")" 200
check "GET /api/health" "$(curl -s -o /dev/null -w '%{http_code}' "$URL/api/health")" 200
check "GET /api/ready" "$(curl -s -o /dev/null -w '%{http_code}' "$URL/api/ready")" 200
check "GET /api/models" "$(curl -s -o /dev/null -w '%{http_code}' "$URL/api/models")" 200

echo "== session lifecycle (real agent)"
SID=$(curl -s -X POST "$URL/api/sessions" -H 'Content-Type: application/json' \
  -d '{"folder":"/tmp/acp-cwd","model":"dbx/system.ai.gpt-oss-120b"}' | python3 -c 'import json,sys;print(json.load(sys.stdin).get("id",""))' 2>/dev/null)
[ -n "$SID" ] && echo "  PASS session created ($SID)" && pass=$((pass+1)) || { echo "  FAIL session not created"; fail=$((fail+1)); }

AGENT=$(curl -s "$URL/api/sessions/$SID" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("agent",""))' 2>/dev/null)
check "agent is real opencode" "$AGENT" "OpenCode"

check "unknown session is 404" "$(curl -s -o /dev/null -w '%{http_code}' "$URL/api/sessions/nope")" 404
check "empty message is 422" "$(curl -s -o /dev/null -w '%{http_code}' -X POST "$URL/api/sessions/$SID/messages" -H 'Content-Type: application/json' -d '{"text":""}')" 422
check "bad model is 422" "$(curl -s -o /dev/null -w '%{http_code}' -X POST "$URL/api/sessions/$SID/model" -H 'Content-Type: application/json' -d '{"model":"nope/nope"}')" 422

echo "== a turn reaches a terminal state (model may be rate limited today)"
curl -s -X POST "$URL/api/sessions/$SID/messages" -H 'Content-Type: application/json' \
  -H "Idempotency-Key: e2e-$(date +%s)" -d '{"text":"Reply with exactly READY."}' >/dev/null
for _ in $(seq 1 40); do
  ST=$(curl -s "$URL/api/sessions/$SID" | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d["turns"][0]["status"] if d.get("turns") else "")' 2>/dev/null)
  case "$ST" in completed|blocked|failed|cancelled) break ;; esac
  sleep 5
done
case "$ST" in
  completed) echo "  PASS turn completed"; pass=$((pass+1)) ;;
  failed|blocked) echo "  PASS turn reached a terminal state and explained itself ($ST)"; pass=$((pass+1)) ;;
  *) echo "  FAIL turn never reached a terminal state (status=$ST)"; fail=$((fail+1)) ;;
esac

echo "== stream replay"
EV=$(curl -s "$URL/api/sessions/$SID/stream?after=0" --max-time 3 | grep -c '^data: ')
[ "$EV" -ge 3 ] && { echo "  PASS stream replays $EV events"; pass=$((pass+1)); } || { echo "  FAIL stream replayed $EV events"; fail=$((fail+1)); }

echo
echo "RESULT: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
