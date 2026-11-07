#!/usr/bin/env python3
"""Validate one model end to end against a RUNNING app (local or deployed). Real agent, real provider.

    scripts/validate_model.py URL [--model google_vertex/google/gemini-3.8-flash]
                                  [--token-cmd "databricks auth token ..."] [--tools]
                                  [--leak PATTERN ...] [--out specs/005-llm-models/e2e/live]

What it proves, in order (each line is a PASS/FAIL; the exit code is the number of FAILs):

1. the catalogue lists the model, selectable, and a credential is present **without any secret**;
2. a session starts on that model (the app writes the config, spawns the agent, hands it the key);
3. a plain turn completes and the model answered what was asked;
4. with --tools: a multi-step turn calls workspace tools and comes back with the real result. That
   is the case that breaks Gemini over an OpenAI-compatible client (thought_signature), so it is the
   one that matters;
5. the model facts block names the model the turn actually used, and the limit evidence;
6. nothing the app returned (responses, stream, facts) contains a secret. `--leak` adds patterns
   (a private-key fragment, a token prefix); the built-in secret detector always runs.

The token never reaches stdout: it is minted by `--token-cmd` and held in memory.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import httpx

BUILTIN_LEAKS = [r"-----BEGIN [A-Z ]*PRIVATE KEY-----", r"ya29\.[A-Za-z0-9_\-]{20,}",
                 r"\"private_key\"\s*:", r"dapi[0-9a-f]{20,}", r"sk-[A-Za-z0-9]{20,}"]
TERMINAL = {"completed", "blocked", "failed", "cancelled", "interrupted"}


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, bool, str]] = []
        self.seen: list[str] = []          # everything the app returned, for the leak scan

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.rows.append((name, ok, detail))
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""), flush=True)
        return ok

    def record(self, *blobs: object) -> None:
        for b in blobs:
            self.seen.append(b if isinstance(b, str) else json.dumps(b))

    @property
    def failures(self) -> int:
        return sum(1 for _, ok, _ in self.rows if not ok)


def token_from(cmd: str | None) -> str:
    if not cmd:
        return ""
    out = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
    text = out.stdout.strip()
    try:
        return json.loads(text).get("access_token", "")
    except json.JSONDecodeError:
        return text


def events_of(client: httpx.Client, url: str, sid: str, turn_id: str, wait: float) -> list[dict]:
    """Read the SSE stream for up to `wait` seconds; keep one turn, stop when it is terminal."""
    out: list[dict] = []
    deadline = time.time() + wait
    try:
        with client.stream("GET", f"{url}/api/sessions/{sid}/stream", params={"after": 0},
                           timeout=httpx.Timeout(wait + 5, read=wait)) as r:
            for line in r.iter_lines():
                if line.startswith("data: "):
                    ev = json.loads(line[6:])
                    if ev.get("turnId") != turn_id:
                        continue
                    out.append(ev)
                    if ev["type"] in ("turn.completed", "turn.failed", "turn.blocked", "turn.cancelled"):
                        break
                if time.time() > deadline:
                    break
    except (httpx.ReadTimeout, httpx.RemoteProtocolError):
        pass
    return out


def run_turn(client: httpx.Client, url: str, sid: str, text: str, wait: float, rep: Report) -> tuple[str, str, list[dict]]:
    r = client.post(f"{url}/api/sessions/{sid}/messages", json={"text": text},
                    headers={"Idempotency-Key": f"v-{time.time_ns()}"})
    rep.record(r.text)
    if r.status_code >= 300:
        return "http_" + str(r.status_code), r.text[:300], []
    evs = events_of(client, url, sid, r.json()["turnId"], wait)
    rep.record(*[json.dumps(e) for e in evs])
    reply = "".join(e.get("text", "") for e in evs if e["type"] == "message.delta")
    last = [e["type"] for e in evs if e["type"].startswith("turn.")]
    return (last[-1].split(".", 1)[1] if last else "none"), reply, evs


def experience(client: httpx.Client, url: str, sid: str, args: argparse.Namespace, rep: Report) -> None:
    # A. closed tab: submit, never open the stream, come back later, and the whole turn is there.
    r = client.post(f"{url}/api/sessions/{sid}/messages", headers={"Idempotency-Key": f"x-{time.time_ns()}"},
                    json={"text": "In one sentence, what is the capital of France? Answer without using tools."})
    turn = r.json().get("turnId", "")
    rep.check("a turn is accepted with no stream attached", r.status_code == 202, f"HTTP {r.status_code}")
    time.sleep(12)                                    # the user closed the tab and went for coffee
    back = events_of(client, url, sid, turn, 20)      # ... and reopens it: replay from the start
    rep.record(*[json.dumps(e) for e in back])
    kinds = [e["type"] for e in back]
    answer = "".join(e.get("text", "") for e in back if e["type"] == "message.delta")
    rep.check("reopening replays the finished turn from the server", "turn.completed" in kinds,
              f"{len(back)} events, answer: {answer.strip()[:60]!r}")
    rep.check("\"answer without using tools\" is honoured: no tool calls, no audit pass",
              "tool_call.started" not in kinds and "turn.auditing" not in kinds,
              f"{kinds.count('tool_call.started')} tool calls, {kinds.count('turn.auditing')} audit passes")
    rep.check("and the answer is right", "paris" in answer.lower())

    # B. cross-provider switch, then a turn on the new model, then back; each turn keeps its own model
    sw = client.post(f"{url}/api/sessions/{sid}/model", json={"model": args.other_model})
    rep.record(sw.text)
    rep.check("switching to another provider is accepted", sw.status_code == 200,
              f"HTTP {sw.status_code} restartRequired={sw.json().get('restartRequired') if sw.status_code == 200 else ''}")
    if sw.status_code == 200:
        status, reply, _ = run_turn(client, url, sid, "Reply with exactly the word SECOND.", args.wait, rep)
        rep.check("a turn on the other provider completes", status == "completed" and "SECOND" in reply.upper(),
                  f"{status}: {reply.strip()[:40]!r}")
        back_sw = client.post(f"{url}/api/sessions/{sid}/model", json={"model": args.model})
        rep.record(back_sw.text)
        status, reply, _ = run_turn(client, url, sid, "Reply with exactly the word THIRD.", args.wait, rep)
        rep.check("and back again, on the first model", status == "completed" and "THIRD" in reply.upper(),
                  f"{status}: {reply.strip()[:40]!r}")
        turns = client.get(f"{url}/api/sessions/{sid}").json().get("turns", [])
        rep.record(turns)
        models = [t.get("model") for t in turns]
        expect_other = args.other_model
        rep.check("every turn kept the model it was sent on (immutable pin)",
                  expect_other in models and models.count(args.model) >= 3
                  and models[-1] == args.model,
                  " > ".join(m.split("/")[-1] for m in models))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--model", default="google_vertex/google/gemini-3.8-flash")
    ap.add_argument("--token-cmd", default=None, help="a command that prints a bearer token (never echoed)")
    ap.add_argument("--folder", default="/tmp/acp-cwd")
    ap.add_argument("--tools", action="store_true", help="also run a multi-step tool turn")
    ap.add_argument("--experience", action="store_true",
                    help="also prove: a turn survives a closed tab, and a cross-provider switch pins each turn")
    ap.add_argument("--other-model", default="databricks/databricks-llama-4-maverick",
                    help="the model to switch to for --experience (a different provider)")
    ap.add_argument("--wait", type=float, default=150)
    ap.add_argument("--leak", action="append", default=[])
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    url = args.url.rstrip("/")
    token = token_from(args.token_cmd)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    rep = Report()
    client = httpx.Client(headers=headers, timeout=60, follow_redirects=False)
    print(f"== {url}\n== model {args.model}", flush=True)

    # 1. catalogue + credential, with no secret in either
    r = client.get(f"{url}/api/llm/models")
    rep.record(r.text)
    ok = r.status_code == 200
    rep.check("catalogue answers", ok, f"HTTP {r.status_code}")
    if not ok:
        return report_out(rep, args, 1)
    spec = next((m for m in r.json().get("available", []) if m["id"] == args.model), None)
    rep.check("model is in the catalogue", spec is not None)
    if spec is None:
        return report_out(rep, args, 1)
    rep.check("model is selectable", bool(spec.get("selectable")),
              f"state={spec.get('state')} source={spec.get("limitEvidence") or spec.get("limits", {}).get("evidence")}")
    creds = client.get(f"{url}/api/llm/credentials")
    rep.record(creds.text)
    provider = args.model.split("/", 1)[0]
    have = [c for c in creds.json().get("credentials", []) if c.get("provider") == provider]
    rep.check("a credential is configured for the provider", bool(have),
              f"{have[0]['scope']} …{have[0]['last4']}" if have else "none")

    # 2. a session on that model
    s = client.post(f"{url}/api/sessions", json={"folder": args.folder, "model": args.model})
    rep.record(s.text)
    if not rep.check("session starts on the model", s.status_code == 201, f"HTTP {s.status_code} {s.text[:200]}"):
        return report_out(rep, args, 1)
    sid = s.json()["id"]
    info = client.get(f"{url}/api/sessions/{sid}").json()
    rep.record(info)
    rep.check("the real agent is running", info.get("agent") not in ("", None), str(info.get("agent")))

    # 3. a plain turn
    t0 = time.time()
    status, reply, _ = run_turn(client, url, sid, "Reply with exactly the word READY and nothing else.",
                                args.wait, rep)
    rep.check("plain turn completes", status == "completed", f"{status} in {time.time() - t0:.1f}s")
    rep.check("the model answered what was asked", "READY" in reply.upper(), reply.strip()[:80])

    # 4. a multi-step tool turn
    if args.tools:
        t0 = time.time()
        status, reply, evs = run_turn(
            client, url, sid,
            "Use your tools to run this SQL and tell me the result: SELECT 6 * 7 AS answer. "
            "State the number you got.", args.wait, rep)
        calls = [e for e in evs if e["type"] == "tool_call.updated"]
        rep.check("tool turn completes", status == "completed", f"{status} in {time.time() - t0:.1f}s")
        rep.check("the model called a workspace tool", len(calls) > 0, f"{len(calls)} tool events")
        rep.check("the reply carries the tool's real result", "42" in reply, reply.strip()[:120])

    # 4b. the experience claims (what a hosted agent can do that a browser-tab agent cannot)
    if args.experience:
        experience(client, url, sid, args, rep)

    # 5. model facts
    facts = client.get(f"{url}/api/sessions/{sid}/model-facts")
    rep.record(facts.text)
    ok = facts.status_code == 200
    rep.check("model facts answer", ok, f"HTTP {facts.status_code}")
    if ok:
        f = facts.json()
        used = {t.get("model") for t in f.get("turns", [])}
        rep.check("facts name the model the turns used", args.model in used, ", ".join(sorted(map(str, used))))
        res = f.get("resolved", {})
        rep.check("facts carry the wire and limit evidence", bool(res.get("evidence")) and bool(res.get("wire")),
                  f"wire={res.get('wire')} context={res.get('context')} output={res.get('output')} "
                  f"evidence={res.get('evidence')}")

    # 6. nothing secret anywhere we looked
    pats = BUILTIN_LEAKS + args.leak
    blob = "\n".join(rep.seen)
    hits = [p for p in pats if re.search(p, blob)]
    rep.check("no secret in any response or event", not hits, f"{len(blob)} chars scanned; hits={len(hits)}")

    client.delete(f"{url}/api/sessions/{sid}")
    return report_out(rep, args, rep.failures)


def report_out(rep: Report, args: argparse.Namespace, code: int) -> int:
    print(f"\nRESULT: {len(rep.rows) - rep.failures} passed, {rep.failures} failed", flush=True)
    if args.out:
        folder = Path(args.out)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "result.json").write_text(json.dumps(
            {"url": args.url, "model": args.model,
             "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in rep.rows]}, indent=2))
    return min(code, 99)


if __name__ == "__main__":
    sys.exit(main())
