import { describe, expect, it } from "vitest";
import { reduce, type SessionView } from "./events";

describe("defensive reduce", () => {
  it("does not crash when a session arrives without turns", () => {
    // Regression: the server omits `turns` for a fresh session; a bare spread made it undefined
    // and the app died with "Cannot read properties of undefined (reading 'length')".
    const partial = { id: "s", status: "ready" } as unknown as SessionView;
    const after = reduce(partial, { seq: 1, sessionId: "s", type: "turn.started", turnId: "t1" } as never);
    expect(after.turns).toHaveLength(1);
  });
});
