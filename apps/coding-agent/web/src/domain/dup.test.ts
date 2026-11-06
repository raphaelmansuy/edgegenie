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
