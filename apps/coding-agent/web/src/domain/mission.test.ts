import { describe, expect, it } from "vitest";
import { emptySession, newTurn, reduce } from "./events";
import { missionLabel, missionStatus } from "./mission";

describe("server mission visibility", () => {
  it("separates observation loss from execution and never claims fresh offline progress", () => {
    const s = { ...emptySession("s"), status: "streaming" };
    expect(missionStatus(s, { kind: "live" }).title).toBe("Working on the server");
    /* `StreamNotice` owns the announcement now (specs/012 [ST-4]), so `missionStatus` reports the
       tone and lets that component say "offline" or "reconnecting". What this test still guards is
       the thing it was written for: a disconnection never makes the mission claim fresh progress. */
    expect(missionStatus(s, { kind: "reconnecting", attempt: 1, nextInMs: 1000 }).tone).toBe("connection");
    expect(missionStatus(s, { kind: "reconnecting", attempt: 2, nextInMs: 2000 }).detail).toContain("catch up");
  });
  it("offers explicit recovery ahead of a stale running indicator", () => {
    const s = { ...emptySession("s"), status: "streaming", requiresResume: true };
    expect(missionStatus(s, { kind: "live" }).tone).toBe("attention");
    expect(missionLabel(s)).toBe("Needs attention");
  });
  it("marks a completed mission ready for review", () => {
    const s = { ...emptySession("s"), turns: [{ ...newTurn("t", 1), status: "completed" as const }] };
    expect(missionStatus(s, { kind: "live" }).title).toBe("Ready for your review");
  });
  it("expires old permissions on recovery and clears recovery after load", () => {
    const s = { ...emptySession("s"), approvals: [{ approvalId: "a", action: "write", target: "/x", reason: "", options: [] }] };
    const restored = reduce(s, { seq: 1, sessionId: "s", type: "session.recovery_required" });
    expect(restored.requiresResume).toBe(true);
    expect(restored.approvals[0].outcome).toBe("expired");
    expect(reduce(restored, { seq: 2, sessionId: "s", type: "session.ready" }).requiresResume).toBe(false);
  });
});

import { currentMission, isAchieved, lastAchieved, missionProof, missionView } from "./mission";
import type { SessionView, Turn, TurnStatus } from "./events";

const finished = (id = "done", index = 1): Turn => ({ ...newTurn(id, index, "Build a verified notebook", "recorded/model"), status: "completed",
  tools: [{ callId: "c1", name: "write_notebook", status: "completed", args: '{"path":"/Shared/demo/report"}' }],
  evidence: [{ requirement: "Write notebook", toolCallId: "c1", tool: "write_notebook", summary: "Written", verified: true }],
});
const sessionOf = (...turns: Turn[]): SessionView => ({ ...emptySession("s"), status: "ready", turns });

describe("mission projection — spec 011", () => {
  it("selects running and auditing ahead of queued follow-ups", () => {
    for (const status of ["running", "auditing"] as const) {
      const active = { ...newTurn("active", 2), status };
      expect(currentMission(sessionOf(finished(), active, { ...newTurn("q", 3), status: "queued" }))).toBe(active);
    }
  });
  it("uses the first queued mission or latest terminal and handles an empty session", () => {
    const q = { ...newTurn("q", 2), status: "queued" as const };
    expect(currentMission(sessionOf(finished(), q, { ...q, id: "q2" }))).toBe(q);
    expect(currentMission(sessionOf(finished("a"), finished("b", 2)))?.id).toBe("b");
    expect(currentMission(sessionOf())).toBeUndefined();
    expect(missionView(sessionOf(), undefined, { kind: "live" }).state).toBe("ready");
    expect(missionView(emptySession(), undefined, { kind: "live" }).state).toBe("starting");
  });
  it("requires nonempty proof, a successful matching call and completion for achievement", () => {
    const t = finished();
    expect(isAchieved(t)).toBe(true);
    expect(isAchieved({ ...t, evidence: [] })).toBe(false);
    expect(isAchieved({ ...t, status: "auditing" })).toBe(false);
    for (const patch of [{ verified: false }, { toolCallId: "absent" }, { tool: "different_tool" }]) {
      expect(isAchieved({ ...t, evidence: [{ ...t.evidence[0], ...patch }] })).toBe(false);
    }
    for (const status of ["error", "running", "failed", "cancelled"]) {
      expect(isAchieved({ ...t, tools: [{ ...t.tools[0], status }] })).toBe(false);
    }
  });
  it("does not let another mission provide a missing source", () => {
    const previous = finished();
    const current = { ...finished("second", 2), tools: [] };
    expect(missionView(sessionOf(previous, current), current, { kind: "live" }).proven).toBe(0);
    expect(lastAchieved(sessionOf(previous, current))).toBe(previous);
  });
  it("finds last achieved independently of last completed and current failures", () => {
    const a = finished();
    expect(lastAchieved(sessionOf(a, { ...finished("b", 2), evidence: [] }, { ...newTurn("c", 3), status: "failed" }))).toBe(a);
    expect(lastAchieved(sessionOf({ ...a, evidence: [] }))).toBeUndefined();
  });
  it.each(["running", "auditing", "queued", "blocked", "failed", "cancelled", "interrupted"] as TurnStatus[])("keeps %s explicit", (status) => {
    const t = { ...newTurn("t", 1), status };
    expect(missionView(sessionOf(t), t, { kind: "live" }).state).toBe(status);
  });
  it("overlays recovery and permission only on the foreground; archive is read only", () => {
    const old = finished(), t = newTurn("t", 2);
    const s = { ...sessionOf(old, t), requiresResume: true, approvals: [{ approvalId: "a", action: "write", target: "/x", reason: "", options: [] }] };
    expect(missionView(s, t, { kind: "live" }).state).toBe("recovery");
    expect(missionView(s, old, { kind: "live" }).state).toBe("achieved");
    expect(missionView({ ...s, requiresResume: false }, t, { kind: "live" }).state).toBe("waiting");
    expect(missionView({ ...s, status: "archived" }, t, { kind: "live" }).state).toBe("archived");
  });
  it("separates transport freshness from saved execution", () => {
    const t = newTurn("t", 1), s = sessionOf(finished(), t);
    for (const conn of [{ kind: "reconnecting", attempt: 1, nextInMs: 1000 }, { kind: "connecting" }, { kind: "reconnecting", attempt: 2, nextInMs: 2000 }] as const) {
      expect(missionView(s, t, conn)).toMatchObject({ state: "running", paused: true });
      expect(missionView(s, s.turns[0], conn).paused).toBe(false);
    }
  });
  it("never auto-completes an unknown or unfinished plan", () => {
    const t = { ...finished(), plan: [{ content: "A", status: "completed" }, { content: "B", status: "unknown" }] };
    const v = missionView(sessionOf(t), t, { kind: "live" });
    expect(v.planDone).toBe(1); expect(v.plan[1].status).toBe("unknown");
    expect(missionView(sessionOf(finished()), finished(), { kind: "live" }).plan).toEqual([]);
  });
  it("counts failed calls without discarding recovered proof; keeps per-turn artifacts", () => {
    const t = { ...finished(), tools: [...finished().tools, { callId: "bad", name: "run_sql", status: "error" }] };
    expect(missionView(sessionOf(t), t, { kind: "live" })).toMatchObject({ state: "achieved", failedCalls: 1, proven: 1 });
    const next = newTurn("next", 2);
    expect(missionView(sessionOf(t, next), next, { kind: "live" }).artifacts).toEqual([]);
    expect(missionProof(t)[0].source?.callId).toBe("c1");
  });
  it("preserves complete request, model provenance and only valid recorded durations", () => {
    const t = { ...finished(), prompt: `${"Long objective ".repeat(20)}\nKeep the full second line [[scenario:notebook]]`, seconds: NaN };
    const v = missionView({ ...sessionOf(t), model: "future/model" }, t, { kind: "live" });
    expect(v.title.length).toBe(110); expect(v.request).toContain("second line"); expect(v.request).not.toContain("[[scenario:");
    expect(v.model).toBe("recorded/model"); expect(v.seconds).toBeUndefined();
    expect(missionView(sessionOf({ ...t, seconds: 4.2 }), { ...t, seconds: 4.2 }, { kind: "live" }).seconds).toBe(4.2);
  });
});
