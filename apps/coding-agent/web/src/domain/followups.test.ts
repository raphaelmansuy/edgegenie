import { describe, expect, it } from "vitest";
import type { Turn } from "./events";
import { followUps } from "./followups";

const turn = (over: Partial<Turn> = {}): Turn => ({
  id: "t", index: 1, prompt: "p", model: "m", status: "completed", thought: "", answer: "Done.",
  tools: [], evidence: [], auditPasses: 0, ...over,
});
const tool = (name: string, status = "completed", table?: boolean) => ({
  callId: name, name, status, ...(table ? { table: { columns: ["a"], rows: [["1"]], truncated: false } } : {}),
});

describe("follow-ups", () => {
  it("offers nothing until the turn has finished with an answer", () => {
    expect(followUps(null)).toEqual([]);
    expect(followUps(turn({ status: "running" }))).toEqual([]);
    expect(followUps(turn({ status: "blocked" }))).toEqual([]);
    expect(followUps(turn({ answer: "  " }))).toEqual([]);
  });

  it("a written notebook that was not run offers to run it first", () => {
    const f = followUps(turn({ tools: [tool("write_notebook")] }));
    expect(f[0].label).toBe("Run it and show the result");
  });

  it("a notebook that was written and run does not offer to run it again", () => {
    const f = followUps(turn({ tools: [tool("write_notebook"), tool("run_notebook")] }));
    expect(f.map((x) => x.label)).not.toContain("Run it and show the result");
    expect(f.length).toBeLessThanOrEqual(3);
  });

  it("rows on screen offer to chart and explain them", () => {
    const f = followUps(turn({ tools: [tool("run_sql", "completed", true)] }));
    expect(f.map((x) => x.label)).toEqual(["Chart these results", "Turn this into a notebook", "Explain these numbers"]);
  });

  it("a failure puts the fix first", () => {
    const f = followUps(turn({ tools: [tool("run_sql", "error")] }));
    expect(f[0].label).toBe("Find the cause and fix it");
  });

  it("falls back to two generic, honest prompts, never more than the cap", () => {
    const f = followUps(turn());
    expect(f.map((x) => x.label)).toEqual(["Summarise what you did", "What should I check next?"]);
    expect(followUps(turn({ tools: [tool("write_notebook"), tool("run_sql", "completed", true)] }), 2)).toHaveLength(2);
  });

  it("labels are unique and every prompt is a full sentence", () => {
    const f = followUps(turn({ tools: [tool("write_notebook"), tool("run_sql", "completed", true)] }), 9);
    expect(new Set(f.map((x) => x.label)).size).toBe(f.length);
    for (const x of f) expect(x.prompt.endsWith(".")).toBe(true);
  });
});
