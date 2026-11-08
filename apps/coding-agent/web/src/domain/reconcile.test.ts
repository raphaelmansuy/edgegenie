import { describe, expect, it } from "vitest";
import { reconcileIds } from "./reconcile";

const c = (id: string, source: string, kind: "code" | "markdown" = "code") => ({ id, kind, language: "python", source });
const ids = (cells: { id: string }[]) => cells.map((x) => x.id);

describe("reconcileIds", () => {
  it("keeps every id when nothing changed", () => {
    const before = [c("a", "1"), c("b", "2")];
    expect(ids(reconcileIds(before, [c("x", "1"), c("y", "2")]))).toEqual(["a", "b"]);
  });
  it("keeps the ids around an appended cell and mints one for the new cell", () => {
    const out = reconcileIds([c("a", "1"), c("b", "2")], [c("x", "1"), c("y", "2"), c("z", "3")]);
    expect(ids(out).slice(0, 2)).toEqual(["a", "b"]);
    expect(out[2].id).not.toMatch(/^(a|b)$/);
  });
  it("lets an edited cell keep its identity (only its text changes)", () => {
    const out = reconcileIds([c("a", "1"), c("b", "2"), c("c", "3")], [c("x", "1"), c("y", "2 edited"), c("z", "3")]);
    expect(ids(out)).toEqual(["a", "b", "c"]);
    expect(out[1].source).toBe("2 edited");
  });
  it("does not shift later ids when a cell is inserted in the middle", () => {
    const out = reconcileIds([c("a", "1"), c("b", "2"), c("c", "3")], [c("x", "1"), c("n", "new"), c("y", "2"), c("z", "3")]);
    expect(out[0].id).toBe("a");
    expect(out[2].id).toBe("b");
    expect(out[3].id).toBe("c");
  });
  it("drops the id of a removed cell and keeps the rest", () => {
    expect(ids(reconcileIds([c("a", "1"), c("b", "2"), c("c", "3")], [c("x", "1"), c("z", "3")]))).toEqual(["a", "c"]);
  });
  it("never returns a duplicate id", () => {
    const out = reconcileIds([c("a", "same")], [c("x", "same"), c("y", "same")]);
    expect(new Set(ids(out)).size).toBe(2);
  });
  it("handles an empty side", () => {
    expect(reconcileIds([], [c("x", "1")])).toHaveLength(1);
    expect(reconcileIds([c("a", "1")], [])).toEqual([]);
  });
});
