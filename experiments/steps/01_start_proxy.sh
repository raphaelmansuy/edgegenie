#!/bin/bash
# Start the capture proxy (files already uploaded).
set -u
TOKEN="$(cat /tmp/dbx_token.txt)"
printf '%s' "$TOKEN" > "$HOME/.dbx_token"
chmod 600 "$HOME/.dbx_token"
pkill -f /tmp/proxy.py 2>/dev/null
sleep 1
rm -rf /tmp/capture && mkdir -p /tmp/capture
export DBX_TOKEN="$TOKEN"
nohup python3 /tmp/proxy.py > /tmp/proxy.log 2>&1 &
sleep 3
echo "--- health ---"
curl -s -o /dev/null -w "proxy_models:%{http_code}\n" http://127.0.0.1:8787/v1/models
echo "--- proxy log ---"
cat /tmp/proxy.log
