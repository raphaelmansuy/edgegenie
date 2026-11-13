/** The paging mirror: what a card says about a partial reply. `[R-3]`.
 *
 *  The server contract is `api/domain/payload.py`, and the two must agree about WORDS. A card that says
 *  "200 tables" for a 38-of-200 page is the visual form of the defect the payload window fixed.
 */
import { describe, expect, it } from "vitest";
import { isPartial, pageLabel, pageOf, progress } from "./paging";

describe("pageOf: reads a window, tolerates the absence of one", () => {
  it("reads the four fields the server writes", () => {
    expect(pageOf({ returned: 38, total: 200, next_offset: 38 })).toEqual({
      returned: 38, total: 200, nextOffset: 38, oversize: false,
    });
  });

  it("treats a null offset as the last page", () => {
    const info = pageOf({ returned: 200, total: 200, next_offset: null });
    expect(info?.nextOffset).toBeNull();
    expect(isPartial(info)).toBe(false);
  });

  it("returns null for a reply with no window at all", () => {
    expect(pageOf({ tables: [] })).toBeNull();
    expect(pageOf(null)).toBeNull();
    expect(pageOf("text")).toBeNull();
  });

  it("marks an oversize single item, which has an offset of null AND truncated", () => {
    const info = pageOf({ returned: 1, total: 1, next_offset: null, truncated: true });
    expect(info?.oversize).toBe(true);
  });
});

describe("pageLabel: the one sentence", () => {
  it("says how much of the world this page is", () => {
    expect(pageLabel(pageOf({ returned: 38, total: 200, next_offset: 38 }))).toBe("38 of 200 items");
  });

  it("says nothing when the reply is whole, because 200 of 200 is noise", () => {
    expect(pageLabel(pageOf({ returned: 200, total: 200, next_offset: null }))).toBe("");
    expect(pageLabel(null)).toBe("");
  });

  it("uses the singular for one item", () => {
    expect(pageLabel(pageOf({ returned: 1, total: 1, next_offset: null, truncated: true })))
      .toBe("1 item, larger than the page limit");
  });

  it("never claims a partial page is complete", () => {
    const label = pageLabel(pageOf({ returned: 3, total: 4000, next_offset: 3 }));
    expect(label).toContain("of 4000");
    expect(label).not.toMatch(/^3 items$/);
  });
});

describe("progress: for a bar, not for a claim", () => {
  it("is a fraction while paging", () => {
    expect(progress(pageOf({ returned: 50, total: 200, next_offset: 50 }))).toBe(0.25);
  });

  it("is null when the reply is whole, so no bar is drawn for a complete answer", () => {
    expect(progress(pageOf({ returned: 200, total: 200, next_offset: null }))).toBeNull();
  });

  it("is clamped, because a server may report more than it returned", () => {
    expect(progress(pageOf({ returned: 999, total: 10, next_offset: 999 }))).toBe(1);
  });
});
