"""Probe: does session/set_config_option actually switch the model mid-session?"""
import json, os, subprocess, threading, time, sys

p = subprocess.Popen(["opencode","acp"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                     stderr=subprocess.PIPE, text=True, bufsize=1)
lock=threading.Lock(); pending={}; updates=[]
def send(o):
    with lock: p.stdin.write(json.dumps(o)+"\n"); p.stdin.flush()
def call(m,params,timeout=120):
    i=len(pending)+500; pending[i]=threading.Event(); pending[i].r=None
    send({"jsonrpc":"2.0","id":i,"method":m,"params":params}); pending[i].wait(timeout)
    return pending[i].r
def reader():
    for line in p.stdout:
        line=line.strip()
        if not line: continue
        try: msg=json.loads(line)
        except Exception: continue
        if "id" in msg and msg["id"] in pending:
            pending[msg["id"]].r=msg; pending[msg["id"]].set()
        elif msg.get("method")=="session/update": updates.append(msg["params"]["update"])
threading.Thread(target=reader,daemon=True).start()

print("INIT", call("initialize",{"protocolVersion":1,"clientCapabilities":{"fs":{"readTextFile":True,"writeTextFile":True},"terminal":False},"clientInfo":{"name":"probe","version":"0.1"}})["result"]["protocolVersion"])
r=call("session/new",{"cwd":os.path.expanduser("~/proj"),"mcpServers":[]})
sid=r["result"]["sessionId"]
opts=r["result"]["configOptions"]
print("MODEL OPTIONS:", [o["value"] for o in opts[0]["options"]][:6])
print("CURRENT:", opts[0]["currentValue"])
target=[o["value"] for o in opts[0]["options"] if "haiku" in o["value"].lower() or "gpt-4" in o["value"].lower()]
if not target:
    target=[o["value"] for o in opts[0]["options"] if o["value"]!=opts[0]["currentValue"]][:1]
target=target[0]
print("SWITCHING TO:", target)
sw=call("session/set_config_option",{"sessionId":sid,"configId":"model","value":target})
print("SET_PLAIN_STRING:", json.dumps(sw)[:400])
sw2=call("session/set_config_option",{"sessionId":sid,"configId":"model","value":{"type":"string","value":target}})
print("SET_TYPED_STRING:", json.dumps(sw2)[:400])
r=call("session/list",{})
print("SESSION_LIST:", json.dumps(r)[:300])
r2=call("session/prompt",{"sessionId":sid,"prompt":[{"type":"text","text":"Reply with exactly: OK"}]},timeout=150)
print("PROMPT:", json.dumps(r2)[:300])
time.sleep(1)
print("UPDATES:", [u.get("sessionUpdate") for u in updates])
p.terminate()
