import { describe, expect, it } from "vitest";
import { emptySession, newTurn, reduce } from "./events";
import { missionLabel, missionStatus } from "./mission";

describe("server mission visibility", () => {
  it("separates observation loss from execution and never claims fresh offline progress", () => {
    const s = { ...emptySession("s"), status: "streaming" };
    expect(missionStatus(s, "live").title).toBe("Working on the server");
    expect(missionStatus(s, "lost").title).toBe("You’re offline");
    expect(missionStatus(s, "reconnecting").detail).toContain("catch up");
  });
  it("offers explicit recovery ahead of a stale running indicator", () => {
    const s = { ...emptySession("s"), status: "streaming", requiresResume: true };
    expect(missionStatus(s, "live").tone).toBe("attention");
    expect(missionLabel(s)).toBe("Needs attention");
  });
  it("marks a completed mission ready for review", () => {
    const s = { ...emptySession("s"), turns: [{ ...newTurn("t", 1), status: "completed" as const }] };
    expect(missionStatus(s, "live").title).toBe("Ready for your review");
  });
  it("expires old permissions on recovery and clears recovery after load", () => {
    const s = { ...emptySession("s"), approvals: [{ approvalId: "a", action: "write", target: "/x", reason: "", options: [] }] };
    const restored = reduce(s, { seq: 1, sessionId: "s", type: "session.recovery_required" });
    expect(restored.requiresResume).toBe(true);
    expect(restored.approvals[0].outcome).toBe("expired");
    expect(reduce(restored, { seq: 2, sessionId: "s", type: "session.ready" }).requiresResume).toBe(false);
  });
});
