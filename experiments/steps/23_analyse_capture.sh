#!/bin/bash
# Analyse the captured turns: did the model return prose, a tool call, or empty?
set -u
echo "=== capture inventory ==="
ls -1 /tmp/capture/
for f in /tmp/capture/*.json; do
  python3 - "$f" <<'PY'
import json,sys
p=sys.argv[1]
b=json.load(open(p))
msgs=b.get("messages",[])
last=msgs[-1] if msgs else {}
print(f"\n--- {p.split('/')[-1]}  model={b.get('model')} stream={b.get('stream')} msgs={len(msgs)}")
print(f"    last_role={last.get('role')} last_len={len(json.dumps(last))}")
print(f"    tools_advertised={len(b.get('tools',[]))}")
PY
done
echo
echo "=== error responses ==="
for f in /tmp/capture/*.err; do
  [ -e "$f" ] && echo "--- $f" && head -c 300 "$f" && echo
done
echo
echo "=== agent output ==="
sed -e 's/\x1b\[[0-9;]*m//g' "$HOME/proj/px.log" | grep -vE '^\s*$' | tail -15
