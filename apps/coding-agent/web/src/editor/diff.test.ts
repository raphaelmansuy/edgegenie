import { describe, expect, it } from "vitest";
import { minimalChange } from "./diff";

const apply = (s: string, c: { from: number; to: number; insert: string } | null) => (c ? s.slice(0, c.from) + c.insert + s.slice(c.to) : s);

describe("minimalChange", () => {
  it("is null for equal text", () => expect(minimalChange("abc", "abc")).toBeNull());
  it("replaces only the middle", () => {
    expect(minimalChange("select 1 from t", "select 2 from t")).toEqual({ from: 7, to: 8, insert: "2" });
  });
  it("handles insertions, deletions and totals", () => {
    for (const [a, b] of [["", "x"], ["x", ""], ["abc", "abXc"], ["abXc", "abc"], ["aaa", "aa"], ["aa", "aaa"], ["hello", "world"]]) {
      expect(apply(a, minimalChange(a, b))).toBe(b);
    }
  });
});
