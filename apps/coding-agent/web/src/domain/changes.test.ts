import { describe, expect, it } from "vitest";
import { describeChanges, diffCells, sameCells } from "./changes";

const c = (source: string, kind: "code" | "markdown" = "code") => ({ id: source, kind, language: "python", source });

describe("diffCells", () => {
  it("sees an appended cell", () => {
    const d = diffCells([c("a")], [c("a"), c("# Conclusion", "markdown")]);
    expect(d).toEqual({ changed: [2], removed: 0 });
    expect(describeChanges(d, 1, 2)).toBe("1 cell added");
  });
  it("sees an edited cell", () => {
    const d = diffCells([c("a"), c("b")], [c("a"), c("b2")]);
    expect(d).toEqual({ changed: [2], removed: 0 });
    expect(describeChanges(d, 2, 2)).toBe("1 cell changed");
    expect(describeChanges(diffCells([c("a"), c("b")], [c("a")]), 2, 1)).toBe("1 cell removed");
  });
  it("does not call a moved cell changed", () => {
    expect(diffCells([c("a"), c("b")], [c("b"), c("a")]).changed).toEqual([]);
  });
  it("counts duplicates once each", () => {
    expect(diffCells([c("x")], [c("x"), c("x")]).changed).toEqual([2]);
  });
  it("reports nothing for identical notebooks", () => {
    expect(sameCells([c("a")], [c("a")])).toBe(true);
    expect(describeChanges(diffCells([c("a")], [c("a")]), 1, 1)).toBe("no visible change");
  });
});
