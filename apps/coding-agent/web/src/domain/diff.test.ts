/** The diff contract, as properties (spec 003 DF-2, DF-3, DF-4).
 *
 * DF-2: accepting everything yields the proposal exactly.
 * DF-3: accepting nothing leaves the base byte-identical.
 * and: accepting a subset yields something well formed — never a half-written line.
 *
 * These are property tests over generated pairs, because a diff that is right for the example in
 * the docs and wrong for a real notebook is worse than no diff at all.
 */
import { describe, expect, it } from "vitest";
import { acceptAll, acceptNone, applyHunks, diffCells, diffLines } from "./diff";

/** Deterministic pseudo-random text, so a failure is reproducible. */
function rng(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
    return s / 0x100000000;
  };
}

function doc(rand: () => number): string {
  const atoms = ["a", "b", "c", "x = 1", "", "# note", "select 1", "  indented", "}"];
  const n = Math.floor(rand() * 12);
  return Array.from({ length: n }, () => atoms[Math.floor(rand() * atoms.length)]).join("\n");
}

describe("diffLines + applyHunks", () => {
  it("accepting every hunk yields the proposal exactly", () => {
    const rand = rng(7);
    for (let i = 0; i < 300; i += 1) {
      const base = doc(rand);
      const next = doc(rand);
      const d = diffLines(base, next);
      expect(applyHunks(d, acceptAll(d))).toBe(next);
    }
  });

  it("accepting nothing leaves the base untouched", () => {
    const rand = rng(11);
    for (let i = 0; i < 300; i += 1) {
      const base = doc(rand);
      const next = doc(rand);
      const d = diffLines(base, next);
      expect(applyHunks(d, acceptNone())).toBe(base);
    }
  });

  it("a subset produces a document that is a mix of both, line by line", () => {
    const rand = rng(13);
    for (let i = 0; i < 200; i += 1) {
      const base = doc(rand);
      const next = doc(rand);
      const d = diffLines(base, next);
      const take = new Set(d.hunks.filter(() => rand() > 0.5).map((h) => h.id));
      const out = applyHunks(d, take);
      // Every line of the result must come from one side or the other, never be invented.
      for (const line of out.split("\n")) {
        expect(base.split("\n").includes(line) || next.split("\n").includes(line)).toBe(true);
      }
    }
  });

  it("an identical pair produces no hunks and round-trips", () => {
    const text = "a\nb\nc";
    const d = diffLines(text, text);
    expect(d.hunks).toEqual([]);
    expect(applyHunks(d, acceptAll(d))).toBe(text);
  });

  it("an empty base reads as one empty line, and still round-trips", () => {
    // "".split("\n") is [""] — one empty line, not zero. The diff has to model that honestly,
    // otherwise applying it would produce an extra newline. The round trip is what matters.
    const d = diffLines("", "a\nb");
    expect(applyHunks(d, acceptAll(d))).toBe("a\nb");
    expect(applyHunks(d, acceptNone())).toBe("");
  });

  it("an empty proposal round-trips back to nothing", () => {
    const d = diffLines("a\nb", "");
    expect(applyHunks(d, acceptAll(d))).toBe("");
    expect(applyHunks(d, acceptNone())).toBe("a\nb");
  });

  it("groups consecutive changes into one hunk", () => {
    // One deletion of "b" and two additions X, Y: three operations, but *one* hunk, because they
    // are contiguous. That is what "accept this change" means to a reviewer.
    const d = diffLines("a\nb\nc", "a\nX\nY\nc");
    expect(d.hunks).toHaveLength(1);
    expect(d.hunks[0].lines).toHaveLength(3);
    expect(applyHunks(d, acceptAll(d))).toBe("a\nX\nY\nc");
  });

  it("splits hunks separated by unchanged lines", () => {
    const d = diffLines("a\nb\nc\nd\ne", "A\nb\nc\nd\nE");
    expect(d.hunks).toHaveLength(2);
  });

  it("numbers lines on both sides", () => {
    const d = diffLines("a\nb", "a\nb\nc");
    const added = d.lines.find((l) => l.op === "add");
    expect(added?.nextNo).toBe(3);
    expect(d.lines.find((l) => l.op === "same")?.baseNo).toBe(1);
  });

  it("falls back to whole-file replacement rather than hanging on a huge pair", () => {
    const big = Array.from({ length: 1500 }, (_, i) => `line ${i}`).join("\n");
    const other = Array.from({ length: 1500 }, (_, i) => `other ${i}`).join("\n");
    const d = diffLines(big, other);
    expect(applyHunks(d, acceptAll(d))).toBe(other);
    expect(applyHunks(d, acceptNone())).toBe(big);
  });
});

describe("diffCells", () => {
  const cell = (id: string, source: string) => ({ id, source });

  it("reports an add", () => {
    expect(diffCells([cell("a", "x")], [cell("a", "x"), cell("b", "y")]))
      .toEqual([{ id: "b", op: "added", summary: "added" }]);
  });

  it("reports a removal", () => {
    expect(diffCells([cell("a", "x"), cell("b", "y")], [cell("a", "x")]))
      .toEqual([{ id: "b", op: "removed", summary: "removed" }]);
  });

  it("reports an edit", () => {
    expect(diffCells([cell("a", "x")], [cell("a", "x2")]))
      .toEqual([{ id: "a", op: "changed", summary: "edited" }]);
  });

  it("reports a move as a move, not as delete + add", () => {
    // DF-4: a reorder presented as delete+add makes the reviewer re-read every cell.
    const out = diffCells([cell("a", "1"), cell("b", "2")], [cell("b", "2"), cell("a", "1")]);
    expect(out).toHaveLength(1);
    expect(out[0].op).toBe("moved");
  });

  it("reports nothing when nothing changed", () => {
    expect(diffCells([cell("a", "x")], [cell("a", "x")])).toEqual([]);
  });
});
