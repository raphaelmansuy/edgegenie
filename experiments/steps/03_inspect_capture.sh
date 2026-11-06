#!/bin/bash
# Inspect what the proxy captured.
set -u
echo "--- capture files ---"
ls -1 /tmp/capture 2>/dev/null | head -20
echo "--- opencode log ---"
sed -e 's/\x1b\[[0-9;]*m//g' "$HOME/proj/run.log" 2>/dev/null | tail -25
echo "--- last captured body (keys) ---"
LAST=$(ls -1 /tmp/capture/*.json 2>/dev/null | tail -1)
echo "file=$LAST"
if [ -n "$LAST" ]; then
  python3 - "$LAST" <<'PY'
import json,sys
b=json.load(open(sys.argv[1]))
print("KEYS:", sorted(b.keys()))
print("MODEL:", b.get("model"))
print("STREAM:", b.get("stream"))
print("N_MESSAGES:", len(b.get("messages",[])))
if b.get("messages"):
    print("ROLES:", [m.get("role") for m in b["messages"]])
    print("SIZES:", [len(json.dumps(m)) for m in b["messages"]])
print("TOOLS:", [t.get("function",{}).get("name") for t in b.get("tools",[])][:20])
print("N_TOOLS:", len(b.get("tools",[])))
for k in b:
    if k not in ("messages","tools"):
        print(f"{k} = {json.dumps(b[k])[:200]}")
PY
fi
echo "--- error files ---"
for f in /tmp/capture/*.err; do [ -e "$f" ] && echo "$f:" && head -c 400 "$f" && echo; done
