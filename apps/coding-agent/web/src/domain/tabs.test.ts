import { describe, expect, it } from "vitest";
import { afterClose, docTabId, moveTab } from "./tabs";

const docs = [{ id: "a", rev: 4 }, { id: "b", rev: 2 }, { id: "c", rev: 9 }];
describe("tab metadata invariants (TM-04/07/08)", () => {
  it("moves left/right to a final index without cloning a document", () => {
    const next = moveTab(docs, "a", 2);
    expect(next.map((d) => d.id)).toEqual(["b", "c", "a"]);
    expect(next[2]).toBe(docs[0]);
    expect(moveTab(next, "a", 0)).toEqual(docs);
    expect(docs.map((d) => d.id)).toEqual(["a", "b", "c"]);
  });
  it("clamps boundaries and ignores stale IDs, empty arrays and invalid indexes", () => {
    expect(moveTab(docs, "b", 900).map((d) => d.id)).toEqual(["a", "c", "b"]);
    expect(moveTab(docs, "b", -1).map((d) => d.id)).toEqual(["b", "a", "c"]);
    expect(moveTab(docs, "b", 1)).toBe(docs);
    expect(moveTab(docs, "missing", 0)).toBe(docs);
    expect(moveTab(docs, "b", NaN)).toBe(docs);
    expect(moveTab([], "a", 0)).toEqual([]);
  });
  it("is a permutation for every source and target, retaining revisions and references", () => {
    for (const d of docs) for (let to = -2; to < 5; to++) {
      const next = moveTab(docs, d.id, to);
      expect(new Set(next.map((d) => d.id)).size).toBe(docs.length);
      for (const item of docs) expect(next).toContain(item);
    }
  });
  it("selects right neighbor, then left, then Home, skipping bulk-closed documents", () => {
    expect(afterClose(docs, "b", new Set(["b"]))).toBe("c");
    expect(afterClose(docs, "c", new Set(["c"]))).toBe("b");
    expect(afterClose(docs, "a", new Set(["a", "b"]))).toBe("c");
    expect(afterClose(docs, "a", new Set(["a", "b", "c"]))).toBe("chat");
    expect(afterClose(docs, "b", new Set(["a"]))).toBe("b");
    expect(afterClose(docs, "chat", new Set(["a"]))).toBe("chat");
  });
  it("keeps punctuation and Unicode identities distinct in DOM references", () => {
    const ids = ["file:/a.b", "file:/a_b", "file:/a/b", "file:/a%b", "file:/报表", "file:/a b"];
    expect(new Set(ids.map(docTabId)).size).toBe(ids.length);
  });
});
