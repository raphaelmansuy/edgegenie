"""Minimal ACP v1 client: initialize -> session/new (with our MCP server) -> session/prompt -> read updates."""
import json, os, subprocess, sys, threading, time

HOST = os.environ["DATABRICKS_HOST"]; TOKEN = os.environ["DATABRICKS_TOKEN"]
MCP_PORT = os.environ.get("MCP_PORT", "8811")
PROMPT = os.environ.get("PROMPT", "How many rows are in samples.nyctaxi.trips?")

p = subprocess.Popen(["opencode", "acp"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
lock = threading.Lock(); pending = {}; updates = []; state = {"idle": False, "stop": None}

def send(obj):
    with lock:
        p.stdin.write(json.dumps(obj) + "\n"); p.stdin.flush()

def call(method, params, timeout=180):
    i = len(pending) + 100
    pending[i] = threading.Event(); pending[i].result = None
    send({"jsonrpc": "2.0", "id": i, "method": method, "params": params})
    pending[i].wait(timeout)
    return pending[i].result

def reader():
    for line in p.stdout:
        line = line.strip()
        if not line: continue
        try: msg = json.loads(line)
        except Exception: continue
        if "id" in msg and msg["id"] in pending:
            pending[msg["id"]].result = msg; pending[msg["id"]].set()
        elif msg.get("method") == "session/update":
            u = msg["params"]["update"]; updates.append(u)
            if u.get("sessionUpdate") == "state_update" and u.get("state") == "idle":
                state["idle"] = True; state["stop"] = u.get("stopReason")
        elif msg.get("method") == "session/request_permission":
            # auto-approve: this is a sandbox probe
            opts = msg["params"].get("options", [])
            pick = next((o for o in opts if o.get("kind") in ("allow_always", "allow_once")), opts[0] if opts else None)
            send({"jsonrpc": "2.0", "id": msg["id"], "result": {"outcome": {"outcome": "selected", "optionId": pick["optionId"]}}})

threading.Thread(target=reader, daemon=True).start()

r = call("initialize", {"protocolVersion": 1, "clientCapabilities": {"fs": {"readTextFile": True, "writeTextFile": True}, "terminal": False},
                        "clientInfo": {"name": "probe", "version": "0.1"}})
print("INIT:", json.dumps(r["result"].get("agentCapabilities"))[:200])

mcp = [{"type": "http", "name": "dbxnb", "url": f"http://127.0.0.1:{MCP_PORT}/mcp", "headers": []},
       {"type": "http", "name": "dbxnb2", "url": f"http://127.0.0.1:{MCP_PORT}/mcp",
        "headers": [{"name": "Authorization", "value": "Bearer x"}]}]
r = call("session/new", {"cwd": os.path.expanduser("~/proj"), "mcpServers": mcp})
print("SESSION:", json.dumps(r)[:400])
sid = (r.get("result") or {}).get("sessionId")
if not sid:
    print("NO SESSION ID -> stopping"); sys.exit(1)

print("UPDATES SO FAR:", json.dumps(updates)[:600])
t0 = time.time()
# ACP v1: the prompt IS a request; its response carries the stop reason (unlike v2).
resp = call("session/prompt", {"sessionId": sid, "prompt": [{"type": "text", "text": PROMPT}]}, timeout=200)
print("PROMPT RESPONSE:", json.dumps(resp)[:500])
print(f"ELAPSED {time.time()-t0:.0f}s  updates={len(updates)}")

print("RAW UPDATES:", json.dumps(updates)[:2500])
print("TOOL CALLS:", tools[:12])
print("ANSWER:", ("".join(text))[:900].replace("\n", " ")[:900])
p.terminate()
