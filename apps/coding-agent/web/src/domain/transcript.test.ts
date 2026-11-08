import { describe, expect, it } from "vitest";
import type { Turn } from "./events";
import { conversationMarkdown, exportName } from "./transcript";

const turn = (over: Partial<Turn> = {}): Turn => ({
  id: "t", index: 1, prompt: "Build a notebook", model: "m", status: "completed", thought: "secret thoughts",
  answer: "I wrote it.", tools: [{ callId: "1", name: "write_notebook", status: "completed", args: '{"path":"/a/b"}' }],
  evidence: [], auditPasses: 0, ...over,
});

describe("conversation export", () => {
  it("has the question, one line per tool, and the answer", () => {
    const md = conversationMarkdown("Revenue", [turn()]);
    expect(md).toMatch(/^# Revenue\n/);
    expect(md).toContain("## You\n\nBuild a notebook");
    expect(md).toContain("- wrote");
    expect(md).toContain("## Agent\n\nI wrote it.");
  });

  it("leaves the plumbing out", () => {
    const md = conversationMarkdown("x", [turn({ usage: { input: 9, output: 9, cached: 9 } })]);
    expect(md).not.toContain("secret thoughts");
    expect(md).not.toMatch(/tokens|cached/);
  });

  it("drops the evidence section, which the app shows as a table", () => {
    const md = conversationMarkdown("x", [turn({ answer: "Result.\n\n## Evidence\n| a |\n| 1 |" })]);
    expect(md).toContain("Result.");
    expect(md).not.toContain("Evidence");
  });

  it("says when a turn did not finish, and marks a failed tool", () => {
    const md = conversationMarkdown("x", [turn({ status: "blocked", tools: [{ callId: "1", name: "run_sql", status: "error" }] })]);
    expect(md).toContain("(failed)");
    expect(md).toContain("_This turn ended blocked._");
  });

  it("an empty title still produces a heading and a safe file name", () => {
    expect(conversationMarkdown("  ", [])).toMatch(/^# Conversation/);
    expect(exportName("Revenue by month / Q3!")).toBe("revenue-by-month-q3.md");
    expect(exportName("")).toBe("conversation.md");
    expect(exportName("../../etc/passwd")).toBe("etc-passwd.md");
  });
});
