import { describe, expect, it } from "vitest";
import { peekOf } from "./peek";

const turn = (over = {}) => ({ id: "t", index: 1, prompt: "p", model: "m", status: "running", thought: "", answer: "", tools: [],
  evidence: [], auditPasses: 0, ...over }) as never;
const sess = (status: string, turns: unknown[], approvals: unknown[] = []) => ({ status, turns, approvals }) as never;

describe("peekOf", () => {
  it("is idle before the first turn", () => expect(peekOf(sess("ready", [])).state).toBe("idle"));
  it("names the tool that is running right now", () => {
    const p = peekOf(sess("streaming", [turn({ tools: [{ callId: "1", name: "dbxnb_dbx_write_notebook", status: "in_progress" }] })]));
    expect(p).toMatchObject({ state: "working", headline: "Writing a notebook…" });
  });
  it("says it is thinking between tools", () => {
    const p = peekOf(sess("streaming", [turn({ tools: [{ callId: "1", name: "run_sql", status: "completed" }] })]));
    expect(p.headline).toBe("Thinking about the result…");
  });
  it("waits for the user ahead of everything else", () => {
    expect(peekOf(sess("streaming", [turn()], [{ approvalId: "a" }])).state).toBe("waiting");
  });
  it("reports a finished turn with the first line of its answer, and counts failures honestly", () => {
    const ok = peekOf(sess("ready", [turn({ status: "completed", answer: "## Done\nCreated the chart." })]));
    expect(ok).toMatchObject({ state: "done", headline: "Done" });
    expect(ok.detail).toContain("Done");
    const bad = peekOf(sess("ready", [turn({ status: "completed", tools: [{ callId: "1", name: "run_sql", status: "failed" }] })]));
    expect(bad.headline).toBe("Done, with 1 failed tool call");
  });
  it("is failed for a blocked or interrupted turn", () => {
    expect(peekOf(sess("ready", [turn({ status: "blocked" })])).state).toBe("failed");
  });
});
