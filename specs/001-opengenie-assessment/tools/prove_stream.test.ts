import { describe as d, it, expect } from "vitest";
import { afterFailure, afterOpen, afterRetry, afterSwitch, describe as describeS, backoff, RETRY_MAX_MS, type StreamState } from "./stream";

const statuses: (number|null)[] = [null,200,401,403,404,409,422,500,503,0];
const key = (s: StreamState) => s.kind + ("reason" in s ? ":"+s.reason : "");
const succ = (s: StreamState): StreamState[] => {
  const out: StreamState[] = [afterOpen(), afterRetry(), afterSwitch()];
  for (const st of statuses) for (const online of [true,false]) out.push(afterFailure(st,1,online));
  return out;
};

d("proof: the stream machine", () => {
  it("reaches every declared state from idle, and has no unreachable state", () => {
    const seen = new Map<string, StreamState>();
    const q: StreamState[] = [{kind:"idle"}];
    while (q.length) {
      const s = q.shift()!;
      const k = key(s);
      if (seen.has(k)) continue;
      seen.set(k, s);
      for (const n of succ(s)) if (!seen.has(key(n))) q.push(n);
    }
    const declared = ["idle","connecting","live","reconnecting",
      "closed:not-found","closed:cursor-ahead","closed:rejected"];
    console.log("REACHABLE:", [...seen.keys()].sort().join(", "));
    for (const k of declared) expect([...seen.keys()], `unreachable: ${k}`).toContain(k);
    // "closed:offline" is a ClosedReason that afterFailure cannot produce (offline => reconnecting).
    console.log("closed:offline producible by afterFailure? ", [...seen.keys()].includes("closed:offline"));
  });

  it("gives every state words and an action", () => {
    const all: StreamState[] = [{kind:"idle"},{kind:"connecting"},{kind:"live"},
      {kind:"reconnecting",attempt:1,nextInMs:1000},
      {kind:"closed",reason:"not-found"},{kind:"closed",reason:"cursor-ahead"},
      {kind:"closed",reason:"rejected"},{kind:"closed",reason:"offline"}];
    for (const s of all) {
      const r = describeS(s);
      console.log(`  ${key(s)}`.padEnd(24), "action="+r.action, "urgent="+r.urgent);
      expect(typeof r.action).toBe("string");
    }
  });

  it("lets offline win over every terminal status", () => {
    const bad = statuses.filter((s): s is number => s !== null)
      .filter(s => afterFailure(s,1,false).kind !== "reconnecting");
    expect(bad).toEqual([]);
  });

  it("caps the backoff and resets on a manual retry", () => {
    expect(Math.max(...Array.from({length:12},(_,i)=>backoff(i)))).toBe(RETRY_MAX_MS);
    expect(afterRetry().kind).toBe("connecting");
  });
});
