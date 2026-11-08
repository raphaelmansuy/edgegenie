import { describe, expect, it } from "vitest";
import { CELL_INTENTS, clipError, editPrompt, fixPrompt, insertLabel, insertPrompt } from "./cellprompt";

describe("cell prompts", () => {
  it("an edit names its cell and says what must not change", () => {
    const p = editPrompt(3, "  use a left join ");
    expect(p.startsWith("Cell 3: use a left join")).toBe(true);
    expect(p).toMatch(/Change only cell 3/);
  });

  it("an insert says where, and forbids touching the rest", () => {
    expect(insertPrompt(0, "load the data")).toContain("as the first cell");
    expect(insertPrompt(2, "chart it")).toContain("right after cell 2");
    expect(insertPrompt(2, "chart it")).toMatch(/Do not change any existing cell/);
  });

  it("a fix quotes the engine and names the cell", () => {
    const p = fixPrompt(4, "[TABLE_OR_VIEW_NOT_FOUND] no such table\nSearch path: a, b");
    expect(p.startsWith("Cell 4 failed.")).toBe(true);
    expect(p).toContain("> [TABLE_OR_VIEW_NOT_FOUND] no such table");
    expect(p).toContain("> Search path: a, b");
    expect(p).toMatch(/fix this cell only/);
  });

  it("a fix with no error text still asks for a diagnosis", () => {
    const p = fixPrompt(1, "");
    expect(p).not.toContain("The engine said");
    expect(p).toContain("Find the cause");
  });

  it("clips a long error at its head, where the cause is", () => {
    const long = `CAUSE ${"x".repeat(5000)}`;
    const out = clipError(long, 100);
    expect(out.startsWith("CAUSE")).toBe(true);
    expect(out.length).toBeLessThan(110);
    expect(clipError("short")).toBe("short");
  });

  it("every intent is an instruction that stands on its own", () => {
    expect(CELL_INTENTS.map((i) => i.id)).toEqual(["explain", "fix", "optimize", "comment"]);
    for (const i of CELL_INTENTS) expect(i.instruction.length).toBeGreaterThan(20);
  });

  it("insert labels say where, in words", () => {
    expect(insertLabel(0, 4)).toBe("Add a cell at the top");
    expect(insertLabel(2, 4)).toBe("Add a cell after cell 2");
    expect(insertLabel(4, 4)).toBe("Add a cell at the end");
  });
});
