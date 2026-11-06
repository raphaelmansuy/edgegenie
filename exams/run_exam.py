#!/usr/bin/env python3
"""Run exam missions against a coding agent inside a Databricks sandbox and grade them.

    python run_exam.py --variant V1 --model gpt-oss-120b --missions M1,M2 --parallel 3 --batch baseline

For each mission: seed live state -> run the agent in the sandbox with a scoped
write allow-list -> pull the event log back -> grade against live workspace
state -> clean up. Results land in exams/results/<batch>/.
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "experiments"))
sys.path.insert(0, str(HERE))
from dbx_mcp import rpc  # noqa: E402

import variants  # noqa: E402
from lib import TOKEN, Check, Ctx, delete_path, score, sql  # noqa: E402
from missions import all_missions  # noqa: E402

EP = "/ai-gateway/mcp-services/system.ai.sandbox"
SBX = (HERE / ".sandbox_id").read_text().strip() if (HERE / ".sandbox_id").exists() else ""


def sbx_run(script: str, timeout: int) -> str:
    payload = base64.b64encode(script.encode()).decode()
    code = f"echo '{payload}' | base64 -d > /tmp/_s_$$.sh; bash /tmp/_s_$$.sh; rc=$?; rm -f /tmp/_s_$$.sh; exit $rc"
    out = rpc(EP, "tools/call", {"name": "run_code", "arguments": {
        "sandbox_id": SBX, "language": "sh", "timeout_seconds": timeout, "code": code}})
    res = out.get("result", {})
    text = "\n".join(i.get("text", "") for i in res.get("content", []))
    return ("TOOL ERROR: " + text) if res.get("isError") else text


def sbx_detached(script: str, run_id: str, max_seconds: int) -> str:
    """Run a long script in the sandbox detached and poll for completion.

    A single run_code call is cut by the gateway at ~180 s (HTTP 504), but the
    exams legitimately run for many minutes."""
    b = base64.b64encode(script.encode()).decode()
    sbx_run(f"mkdir -p $HOME/exam && echo '{b}' | base64 -d > $HOME/exam/{run_id}.sh && "
            f"(nohup bash $HOME/exam/{run_id}.sh > $HOME/exam/{run_id}.out 2>&1 &) ; echo launched", 60)
    t0 = time.time()
    while time.time() - t0 < max_seconds:
        time.sleep(10)
        try:
            if "DONE" in sbx_run(f"[ -f $HOME/exam/{run_id}.done ] && echo DONE || echo RUNNING", 60):
                break
        except Exception:  # noqa: BLE001  (transient gateway errors while polling)
            continue
    return sbx_run(f"cat $HOME/exam/{run_id}.out | tail -c 3000", 60)


def sbx_fetch(remote: str) -> str:
    """Fetch a sandbox file in base64 chunks (a single tool result is size-limited)."""
    size = int(sbx_run(f"base64 -w0 {remote} | wc -c", 60).strip().split()[-1] or 0)
    chunks, step = [], 40000
    for i in range(0, size, step):
        chunks.append(sbx_run(f"base64 -w0 {remote} | cut -c {i + 1}-{i + step}", 60).strip())
    return base64.b64decode("".join(chunks)).decode(errors="replace") if chunks else ""


# Supervisor: the model sometimes ends a turn with no text after a tool result
# (finish reason "stop", empty answer). The agent CLI then exits "successfully"
# having done a fraction of the work. Detect that and continue the same session.
SUPERVISOR = r'''
final_ok() { python3 - <<'PY'
import json, sys
last_tool, texts = -1, []
for i, l in enumerate(open("events.jsonl")):
    try: e = json.loads(l)
    except Exception: continue
    t = e.get("type")
    if t in ("tool_use", "tool.execution_start"): last_tool = i
    elif t == "text": texts.append((i, e["part"].get("text", "")))
    elif t == "assistant.message": texts.append((i, e["data"].get("content", "")))
sys.exit(0 if any(i > last_tool and t.strip() for i, t in texts) else 1)
PY
}
AUDITS=0
for N in 1 2 3 4 5; do
  if ! final_ok; then
    echo "SUPERVISOR: empty final answer, continuing (attempt $N)"
    MSG="You stopped without a final answer. Continue the task from where you left off: finish any remaining work, verify it by running a check, then write your final report."
  elif [ "$AUDITS" -lt 2 ]; then
    AUDITS=$((AUDITS+1))
    echo "SUPERVISOR: audit pass $AUDITS"
    MSG="Audit pass. Re-read the original task. For EACH numbered requirement or explicit constraint, name the tool call whose real result proves it was done. Describing or planning is not evidence: if a requirement has no tool-call evidence, do the work NOW with your tools (create the object, run it, query it), then re-check. When every requirement is proven, write the final report."
  else
    break
  fi
  timeout 600 CONT_CMD </dev/null >> events.jsonl 2>> stderr.log
done
'''


def remote_script(ctx: Ctx, mission, variant: str, model: str, port: int, agent: str = "opencode") -> str:
    rd = f"$HOME/exam/{ctx.run_id}"
    b64 = lambda s: base64.b64encode(s.encode()).decode()  # noqa: E731
    mid = variants.MODELS[model]["id"]
    if agent == "copilot":
        run_cmd = 'copilot -p "$(cat prompt.txt)" --allow-all-tools --allow-all-paths --output-format json'
        cont_cmd = 'copilot --continue -p "$MSG" --allow-all-tools --allow-all-paths --output-format json'
        mcp_cfg = variants.copilot_mcp_json(variant, 11111)
        # isolate Copilot's config dir per run (it keeps MCP config + session state under $HOME)
        copilot_setup = (f"export HOME={rd}/home; mkdir -p $HOME/.copilot\n"
                         f"echo '{b64(mcp_cfg)}' | base64 -d | sed \"s|__DBX_TOKEN__|$DATABRICKS_TOKEN|; s/11111/$PORT/g\" > $HOME/.copilot/mcp-config.json\n"
                         + variants.copilot_env(model))
    else:
        run_cmd = f'opencode run --model {mid} --auto --format json "$(cat prompt.txt)"'
        cont_cmd = f'opencode run -c --model {mid} --auto --format json "$MSG"'
        copilot_setup = ""
    return f"""set -u
RH=$HOME
export PATH="$HOME/pyenv/bin:$HOME/.npm-global/bin:$PATH"
mkdir -p {rd} && cd {rd}
export DATABRICKS_HOST="{variants.HOST}"
export DATABRICKS_TOKEN="$(cat /tmp/dbx_token.txt)"
PORT=$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1])')
echo '{b64(variants.opencode_config(model, variant, 11111))}' | base64 -d | sed "s/11111/$PORT/g" > opencode.json
echo '{b64(variants.agents_md(variant))}' | base64 -d > AGENTS.md
[ -s AGENTS.md ] || rm -f AGENTS.md
echo '{b64(mission.prompt(ctx))}' | base64 -d > prompt.txt
unset DATABRICKS_CONFIG_FILE DATABRICKS_CONFIG_PROFILE
{'mkdir -p .claude && rm -rf .claude/skills && cp -r /tmp/dbx_skills_all .claude/skills' if variants.uses_official_skills(variant) else ''}
if [ "{'1' if variants.uses_nbmcp(variant) else '0'}" = "1" ]; then
  NBMCP_TRANSPORT=http NBMCP_PORT=$PORT NBMCP_HOST=127.0.0.1 NBMCP_ALLOW_WRITES=1 \\
  NBMCP_WRITE_SCHEMAS="{ctx.schema}" NBMCP_WRITE_PATHS="{ctx.home}/" \\
  NBMCP_PROFILE="{variants.profile(variant)}" NBMCP_SKILLS_DIR=/tmp/skills NBMCP_WRITE_JOB_PREFIX="{ctx.run_id}_" \\
  NBMCP_WRITE_INSTANCE_PREFIX="{ctx.run_id}-" \\
  nohup python3 {variants.server_file(variant)} > nbmcp.log 2>&1 &
  echo $! > nbmcp.pid
  UP=0
  for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
    [ "$(curl -s -o /dev/null -w '%{{http_code}}' http://127.0.0.1:$PORT/mcp)" != "000" ] && UP=1 && break; sleep 1
  done
  if [ "$UP" != "1" ]; then echo "INFRA: nbmcp did not start"; tail -5 nbmcp.log; exit 42; fi
fi
{copilot_setup}
T0=$(date +%s)
timeout {mission.max_minutes * 60} {run_cmd} \\
  </dev/null > events.jsonl 2> stderr.log
RC=$?
{SUPERVISOR.replace("CONT_CMD", cont_cmd) if variants.supervised(variant) else ""}
echo "EXIT=$RC SECONDS=$(( $(date +%s) - T0 ))"
[ -f nbmcp.pid ] && kill $(cat nbmcp.pid) 2>/dev/null
wc -c events.jsonl
touch $RH/exam/{ctx.run_id}.done
"""


def ensure_shim() -> None:
    """Start the Vertex thought-signature shim in the sandbox with a fresh token."""
    import subprocess
    tok = subprocess.run(["gcloud", "auth", "print-access-token"], capture_output=True, text=True, check=True).stdout.strip()
    b = base64.b64encode(tok.encode()).decode()
    print(sbx_run(f"""set -u
echo '{b}' | base64 -d > /tmp/vx_token.txt; chmod 600 /tmp/vx_token.txt
pkill -f gemini_sig_shim.py 2>/dev/null; sleep 1
export VX_TOKEN="$(cat /tmp/vx_token.txt)"
nohup python3 /tmp/gemini_sig_shim.py > /tmp/shim.log 2>&1 &
sleep 3
echo "shim:$(curl -s -o /dev/null -w '%{{http_code}}' http://127.0.0.1:8790/v1/models)"
""", 60).strip())


def ensure_copilot_shim() -> None:
    """Start the field-stripping proxy Copilot CLI needs in front of the Databricks gateway."""
    src = (Path(__file__).resolve().parent.parent / "experiments" / "copilot_field_shim.py").read_bytes()
    b = base64.b64encode(src).decode()
    print(sbx_run(f"""set -u
echo '{b}' | base64 -d > /tmp/copilot_field_shim.py
pkill -f copilot_field_shim.py 2>/dev/null; sleep 1
UPSTREAM_BASE={variants.HOST}/ai-gateway/openai/v1 nohup python3 /tmp/copilot_field_shim.py > /tmp/cshim.log 2>&1 &
sleep 2
echo "copilot shim:$(curl -s -o /dev/null -w '%{{http_code}}' http://127.0.0.1:8791/v1/models)"
""", 60).strip())


def parse_events(text: str) -> dict:
    tools, steps, tokens, api_errors, rate_limited = [], 0, 0, 0, 0
    last_tool_idx = -1
    texts: list[tuple[int, str]] = []
    for i, line in enumerate(text.splitlines()):
        try:
            e = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        t = e.get("type")
        p = e.get("part", {})
        d = e.get("data", {})
        if t == "error":
            api_errors += 1
            rate_limited += int("429" in json.dumps(e.get("error", {})) or "REQUEST_LIMIT" in json.dumps(e.get("error", {})))
        elif t == "model.call_failure":
            api_errors += 1
            rate_limited += int(d.get("statusCode") == 429)
        if t == "tool_use":                              # opencode
            st = p.get("state", {})
            tools.append({"tool": p.get("tool"), "status": st.get("status"),
                          "input": json.dumps(st.get("input", {}))[:300], "out": str(st.get("output", ""))[:200]})
            last_tool_idx = i
        elif t == "text":
            texts.append((i, p.get("text", "")))
        elif t == "step_finish":
            steps += 1
            tokens += (p.get("tokens") or {}).get("total", 0) or 0
        elif t == "tool.execution_start":                # copilot
            tools.append({"tool": d.get("toolName"), "status": "completed",
                          "input": json.dumps(d.get("arguments", {}))[:300], "out": ""})
            last_tool_idx = i
        elif t == "tool.execution_complete":
            if d.get("success") is False and tools:
                tools[-1]["status"] = "error"
        elif t == "assistant.message":
            steps += 1
            if d.get("content"):
                texts.append((i, d["content"]))
    answer = "\n".join(s for i, s in texts if i > last_tool_idx) or "\n".join(s for _, s in texts)
    return {"tools": tools, "answer": answer, "tokens": tokens, "steps": steps,
            "api_errors": api_errors, "rate_limited": rate_limited,
            "all_text": "\n".join(s for _, s in texts)}


def redact(s: str) -> str:
    return s.replace(TOKEN, "<PAT>")


def run_one(mid: str, variant: str, model: str, batch: str, outdir: Path, agent: str = "opencode") -> dict:
    mission = all_missions()[mid]
    ctx = Ctx(run_id="x" + uuid.uuid4().hex[:5], mission=mid)
    port = 8810 + int(ctx.run_id[1:3], 16) % 150
    tag = model if agent == "opencode" else f"{agent}-{model}"
    res: dict = {"mission": mid, "title": mission.title, "variant": variant, "model": model,
                 "agent": agent, "tag": tag, "run_id": ctx.run_id, "batch": batch}
    t0 = time.time()
    try:
        mission.setup(ctx)
        log = sbx_detached(remote_script(ctx, mission, variant, model, port, agent), ctx.run_id,
                           mission.max_minutes * 60 * (3 if variants.supervised(variant) else 1) + 180)
        res["runner_log"] = log[-400:]
        if "INFRA:" in log or log.startswith("TOOL ERROR"):
            raise RuntimeError("infrastructure failure, run not scored: " + log[-300:])
        events = sbx_fetch(f"$HOME/exam/{ctx.run_id}/events.jsonl")
        (outdir / f"{mid}__{variant}__{tag}.events.jsonl").write_text(redact(events))
        ev = parse_events(events)
        res.update(tool_calls=len(ev["tools"]), steps=ev["steps"], tokens=ev["tokens"],
                   api_errors=ev["api_errors"], rate_limited=ev["rate_limited"],
                   tools_used=sorted({t["tool"] for t in ev["tools"] if t["tool"]}),
                   tool_errors=sum(1 for t in ev["tools"] if t["status"] != "completed"),
                   answer=redact(ev["answer"])[:4000])
        graded_text = ev["all_text"] if variants.supervised(variant) else ev["answer"]
        checks = mission.grade(ctx, graded_text)
        leaked = TOKEN[:14] in events
        checks.append(Check("PAT never printed in the transcript", not leaked, 2,
                            "TOKEN LEAKED" if leaked else ""))
        s, t = score(checks)
        res.update(score=s, total=t, pct=round(100 * s / t, 1),
                   checks=[c.__dict__ for c in checks])
    except Exception as e:  # noqa: BLE001
        res.update(error=repr(e)[:500], trace=traceback.format_exc()[-1200:], score=0, total=1, pct=0.0)
    finally:
        try:
            mission.cleanup(ctx)
            sql(f"DROP SCHEMA IF EXISTS {ctx.schema} CASCADE")
            delete_path(ctx.home)
            sbx_run(f"rm -rf $HOME/exam/{ctx.run_id} $HOME/exam/{ctx.run_id}.*", 30)
        except Exception as e:  # noqa: BLE001
            res["cleanup_error"] = repr(e)[:200]
    res["wall_seconds"] = round(time.time() - t0)
    (outdir / f"{mid}__{variant}__{tag}.json").write_text(json.dumps(res, indent=2, default=str))
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="V1")
    ap.add_argument("--model", default="gpt-oss-120b")
    ap.add_argument("--agent", default="opencode", choices=["opencode", "copilot"])
    ap.add_argument("--missions", default="all")
    ap.add_argument("--parallel", type=int, default=2)
    ap.add_argument("--batch", default="adhoc")
    a = ap.parse_args()
    if a.model.startswith("gemini"):
        ensure_shim()
    if a.agent == "copilot" and not a.model.startswith("gemini"):
        ensure_copilot_shim()
    outdir = HERE / "results" / a.batch
    outdir.mkdir(parents=True, exist_ok=True)
    ms = ([i for i in all_missions() if i.startswith("M")] if a.missions == "all"
          else [i for i in all_missions() if i.startswith("X")] if a.missions == "held"
          else a.missions.split(","))
    heavy = [m for m in ms if m == "M6"]      # one Lakebase instance at a time
    light = [m for m in ms if m != "M6"]
    results = []
    with ThreadPoolExecutor(max_workers=a.parallel) as ex:
        futs = [ex.submit(run_one, m, a.variant, a.model, a.batch, outdir, a.agent) for m in light]
        for m in heavy:
            futs.append(ex.submit(run_one, m, a.variant, a.model, a.batch, outdir, a.agent))
        for f in futs:
            r = f.result()
            results.append(r)
            print(f"{r['mission']} {r['variant']} {r['tag']:<22} {r['score']}/{r['total']} "
                  f"({r['pct']}%) calls={r.get('tool_calls')} tok={r.get('tokens')} 429s={r.get('rate_limited')} t={r['wall_seconds']}s"
                  f"{'  ERROR ' + r['error'] if r.get('error') else ''}", flush=True)
    tot = sum(r["score"] for r in results)
    den = sum(r["total"] for r in results)
    print(f"BATCH {a.batch}: {tot}/{den} = {round(100 * tot / max(den, 1), 1)}%")


if __name__ == "__main__":
    main()
