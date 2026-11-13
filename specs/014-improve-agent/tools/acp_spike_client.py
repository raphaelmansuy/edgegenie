"""Spike ACP client for spec 014: record what the pinned agent really sends.

It starts `opencode acp` in a throwaway folder OUTSIDE the home directory, with an allow-listed
environment and an isolated HOME, attaches the do-nothing MCP server in `acp_spike_mcp.py`, sends one
prompt, and prints a summary of every frame. It never prints a credential.

    PROBE_PORT=8899 python acp_spike_mcp.py &
    export SPIKE_ADC=/path/to/service-account.json     # a Vertex service-account key file
    export SPIKE_VERTEX_PROJECT=<gcp project>
    python acp_spike_client.py opencode.ask.json reject "Call probe_write with path '/a' and content 'b'."

Arguments: <config file> <permission policy: allow|reject|none> <prompt>
Optional: PERM_DELAY (seconds a "person" takes to answer), PROBE_TIMEOUT (seconds to wait for the turn).
The results recorded for the spec are in ../14-live-investigation.md.
"""
import collections
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

config, policy, prompt = sys.argv[1], sys.argv[2], sys.argv[3]
port = os.environ.get("PROBE_PORT", "8899")
timeout = float(os.environ.get("PROBE_TIMEOUT", "240"))

# Outside the home directory on purpose: the agent walks up from its working folder and loads every
# skill and instruction file it finds on the way (finding F-40).
root = tempfile.mkdtemp(prefix="spec014-spike-", dir="/tmp")
cwd = os.path.join(root, "work")
os.makedirs(cwd)
shutil.copyfile(config, os.path.join(cwd, "opencode.json"))
for d in ("home", "config", "data", "cache", "state"):
    os.makedirs(os.path.join(root, d))

ALLOW = ("PATH", "LANG", "LC_ALL", "TMPDIR")
env = {k: os.environ[k] for k in ALLOW if k in os.environ}
env.update({
    "HOME": os.path.join(root, "home"),
    "XDG_CONFIG_HOME": os.path.join(root, "config"), "XDG_DATA_HOME": os.path.join(root, "data"),
    "XDG_CACHE_HOME": os.path.join(root, "cache"), "XDG_STATE_HOME": os.path.join(root, "state"),
    "OPENCODE_DISABLE_AUTOUPDATE": "1", "NODE_NO_WARNINGS": "1",
    "GOOGLE_APPLICATION_CREDENTIALS": os.environ["SPIKE_ADC"],
    "GOOGLE_VERTEX_PROJECT": os.environ["SPIKE_VERTEX_PROJECT"],
    "GOOGLE_VERTEX_LOCATION": os.environ.get("SPIKE_VERTEX_LOCATION", "global"),
})

p = subprocess.Popen(["opencode", "acp"], cwd=cwd, env=env, stdin=subprocess.PIPE,
                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
t0 = time.monotonic()
lock = threading.Lock()
pending: dict[int, threading.Event] = {}
results: dict[int, dict] = {}
frames: list[tuple[float, dict]] = []
permissions: list[dict] = []
other_requests: list[str] = []
stderr_tail: collections.deque = collections.deque(maxlen=12)


def send(obj):
    with lock:
        p.stdin.write(json.dumps(obj) + "\n")
        p.stdin.flush()


def call(method, params, wait):
    i = len(pending) + 1
    pending[i] = threading.Event()
    send({"jsonrpc": "2.0", "id": i, "method": method, "params": params})
    pending[i].wait(wait)
    return results.get(i)


def reader():
    for line in p.stdout:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if "id" in msg and ("result" in msg or "error" in msg) and msg["id"] in pending:
            results[msg["id"]] = msg
            pending[msg["id"]].set()
        elif "id" in msg and "method" in msg:
            if msg["method"] == "session/request_permission":
                rec = {"t": round(time.monotonic() - t0, 2), "params": msg["params"], "replied": 0.0}
                permissions.append(rec)

                def answer(msg=msg, rec=rec):
                    # Off the reader thread, so frames that arrive while a person "thinks" keep their time.
                    time.sleep(float(os.environ.get("PERM_DELAY", "0")))
                    rec["replied"] = round(time.monotonic() - t0, 2)
                    opts = msg["params"].get("options", [])
                    want = {"allow": "allow_once", "reject": "reject_once"}.get(policy)
                    pick = next((o for o in opts if o.get("kind") == want), None)
                    if pick:
                        send({"jsonrpc": "2.0", "id": msg["id"],
                              "result": {"outcome": {"outcome": "selected", "optionId": pick["optionId"]}}})
                    else:
                        send({"jsonrpc": "2.0", "id": msg["id"], "result": {"outcome": {"outcome": "cancelled"}}})

                threading.Thread(target=answer, daemon=True).start()
            else:
                other_requests.append(msg["method"])
                send({"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32601, "message": "no handler"}})
        elif "method" in msg:
            frames.append((time.monotonic() - t0, msg))


def drain_err():
    for line in p.stderr:
        stderr_tail.append(line.rstrip()[:200])


threading.Thread(target=reader, daemon=True).start()
threading.Thread(target=drain_err, daemon=True).start()


def short(v, n=160):
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    return s if len(s) <= n else s[:n] + "…"


def finish(code=0):
    p.terminate()
    shutil.rmtree(root, ignore_errors=True)
    sys.exit(code)


init = call("initialize", {"protocolVersion": 1, "clientInfo": {"name": "spec014-spike", "version": "0"},
                           "clientCapabilities": {"fs": {"readTextFile": False, "writeTextFile": False},
                                                  "terminal": False}}, 60)
if not init or "result" not in init:
    print("INIT FAILED", short(init), "| stderr:", list(stderr_tail)[-4:])
    finish(1)
r = init["result"]
print("INIT agentInfo:", r.get("agentInfo"), "| protocolVersion:", r.get("protocolVersion"))
print("INIT agentCapabilities:", json.dumps(r.get("agentCapabilities")))
print("INIT authMethods:", [m.get("id") for m in r.get("authMethods") or []])

new = call("session/new", {"cwd": cwd, "mcpServers": [
    {"type": "http", "name": "probe", "url": f"http://127.0.0.1:{port}/mcp", "headers": []}]}, 90)
if not new or "result" not in new:
    print("SESSION FAILED", short(new, 500), "| stderr:", list(stderr_tail)[-4:])
    finish(1)
nr = new["result"]
sid = nr["sessionId"]
print("NEW keys:", sorted(nr.keys()))
for o in nr.get("configOptions") or []:
    values = [x.get("value") for x in o.get("options") or []]
    print("NEW configOption:", {k: o.get(k) for k in ("id", "category", "type", "currentValue")},
          "values:", values if len(values) <= 6 else f"{len(values)} values")
time.sleep(2.5)
for u in [m["params"]["update"] for _, m in frames if m.get("method") == "session/update"]:
    if u.get("sessionUpdate") == "available_commands_update":
        print("PRE available commands:", [c.get("name") for c in u.get("availableCommands", [])])
    else:
        print("PRE update:", u.get("sessionUpdate"), sorted(k for k in u if k != "sessionUpdate"))

n_before = len(frames)
t_prompt = time.monotonic() - t0
resp = call("session/prompt", {"sessionId": sid, "prompt": [{"type": "text", "text": prompt}]}, timeout)
t_end = time.monotonic() - t0
time.sleep(1.0)

turn = frames[n_before:]
kinds = collections.Counter(m["params"]["update"].get("sessionUpdate") for _, m in turn
                            if m.get("method") == "session/update")
print("TURN update kinds:", dict(kinds))
print("TURN agent->client requests other than permission:", other_requests)

last = t_prompt
gap = (0.0, "")
text = []
for t, m in turn:
    if m.get("method") != "session/update":
        continue
    u = m["params"]["update"]
    k = u.get("sessionUpdate")
    if t - last > gap[0]:
        gap = (t - last, f"before {k} at +{t - t_prompt:.1f}s")
    last = t
    if k in ("tool_call", "tool_call_update"):
        raw_in = u.get("rawInput")
        print(f"  +{t - t_prompt:6.1f}s {k}", json.dumps({
            "id": str(u.get("toolCallId"))[-6:], "title": u.get("title"), "name": u.get("name", "<absent>"),
            "kind": u.get("kind"), "status": u.get("status", "<absent>"),
            "rawInput": short(raw_in, 90) if raw_in is not None else "<absent>",
            "content": [(c.get("type"), short((c.get("content") or {}).get("text", ""), 110))
                        if c.get("type") == "content" else c.get("type") for c in u.get("content") or []] or "<absent>",
            "rawOutput": short(u.get("rawOutput"), 110) if "rawOutput" in u else "<absent>"}, ensure_ascii=False))
    elif k == "usage_update":
        print(f"  +{t - t_prompt:6.1f}s usage_update", {x: u.get(x) for x in u if x != "sessionUpdate"})
    elif k == "agent_message_chunk":
        text.append((u.get("content") or {}).get("text", ""))
    elif k != "agent_thought_chunk":
        print(f"  +{t - t_prompt:6.1f}s {k}", short({x: u[x] for x in u if x != "sessionUpdate"}, 200))
if t_end - last > gap[0]:
    gap = (t_end - last, "before the prompt response")
print(f"TURN longest silence: {gap[0]:.1f}s ({gap[1]}) | turn seconds: {t_end - t_prompt:.1f}")

for pr in permissions:
    q = pr["params"]
    tc = q.get("toolCall") or {}
    print("PERMISSION top-level keys:", sorted(q.keys()))
    print("PERMISSION toolCall:", json.dumps({
        "keys": sorted(tc.keys()), "title": tc.get("title"), "name": tc.get("name", "<absent>"),
        "kind": tc.get("kind"), "status": tc.get("status"), "rawInput": short(tc.get("rawInput"), 160),
        "content_types": [c.get("type") for c in tc.get("content") or []]}, ensure_ascii=False))
    print("PERMISSION options:", [(o.get("optionId"), o.get("kind"), o.get("name")) for o in q.get("options", [])])
    with_args = [t for t, m in turn if m.get("method") == "session/update"
                 and m["params"]["update"].get("toolCallId") == tc.get("toolCallId")
                 and m["params"]["update"].get("rawInput")]
    print("PERMISSION timing: requested at %.2fs, replied at %.2fs, first update carrying arguments at %s"
          % (pr["t"] - t_prompt, pr["replied"] - t_prompt,
             ("%.2fs" % (with_args[0] - t_prompt)) if with_args else "never"))
if not permissions:
    print("PERMISSION: none requested")

if resp is None:
    print("PROMPT: no response within", timeout, "s | stderr:", list(stderr_tail)[-4:])
elif "error" in resp:
    print("PROMPT error:", short(resp["error"], 400))
else:
    print("PROMPT result:", json.dumps(resp["result"])[:500])
print("ANSWER:", short("".join(text).strip().replace("\n", " "), 500))
finish(0)
