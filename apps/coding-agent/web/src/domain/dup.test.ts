import { describe, expect, it } from "vitest";
import { emptySession, reduce } from "./events";

describe("tool card duplication", () => {
  it("starting the same call id twice keeps one card", () => {
    let s = emptySession("s");
    s = reduce(s, { seq: 1, sessionId: "s", type: "turn.started", turnId: "t1" } as any);
    for (let i = 0; i < 2; i++) {
      s = reduce(s, { seq: 2 + i, sessionId: "s", type: "tool_call.started", turnId: "t1", callId: "c1", name: "x" } as any);
    }
    expect(s.turns[0].tools).toHaveLength(1);
  });
  it("a different call id adds a card", () => {
    let s = emptySession("s");
    s = reduce(s, { seq: 1, sessionId: "s", type: "turn.started", turnId: "t1" } as any);
    s = reduce(s, { seq: 2, sessionId: "s", type: "tool_call.started", turnId: "t1", callId: "c1", name: "x" } as any);
    s = reduce(s, { seq: 3, sessionId: "s", type: "tool_call.started", turnId: "t1", callId: "c2", name: "y" } as any);
    expect(s.turns[0].tools).toHaveLength(2);
  });
});

import { describe as d2, expect as e2, it as i2 } from "vitest";
d2("failed turns explain themselves", () => {
  i2("carries the agent's reason into the blocked panel", () => {
    let s = emptySession("s");
    s = reduce(s, { seq: 1, sessionId: "s", type: "turn.started", turnId: "t1" } as never);
    s = reduce(s, {
      seq: 2, sessionId: "s", type: "turn.failed", turnId: "t1",
      reason: "no event from the agent for 180s\nError: free daily limit",
    } as never);
    e2(s.turns[0].status).toBe("failed");
    e2(s.turns[0].blocked?.reason).toContain("free daily limit");
  });
});
