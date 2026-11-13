/** Scroll hand-off arithmetic. Every edge measured without a browser.
 *
 * The bug this prevents is a composition one: three nested scrollers, each with
 * `overscroll-behavior: contain`, trap the wheel at the inner edge.
 */
import { describe, expect, it } from "vitest";
import {
  absorb, direction, DOM_DELTA_LINE, DOM_DELTA_PAGE, DOM_DELTA_PIXEL, LINE_PX, scrollable, toPixels,
  type Box,
} from "./scroll";

const box = (scrollTop: number, scrollHeight: number, clientHeight: number): Box =>
  ({ scrollTop, scrollHeight, clientHeight });

describe("absorb: the four positions of a box", () => {
  it("in the middle, takes the whole delta", () => {
    expect(absorb(box(100, 500, 200), 50)).toBe(50);
    expect(absorb(box(100, 500, 200), -50)).toBe(50);
  });

  it("at the top, a negative delta passes through entirely", () => {
    expect(absorb(box(0, 500, 200), -50)).toBe(0);
  });

  it("at the bottom, a positive delta passes through entirely", () => {
    expect(absorb(box(300, 500, 200), 50)).toBe(0);
  });

  it("takes only the remainder when the delta is larger than the room left", () => {
    // 10 px of travel left, a 50 px wheel: the ancestor gets the other 40.
    expect(absorb(box(290, 500, 200), 50)).toBe(10);
  });

  it("treats a sub-pixel offset as the edge, because trackpads produce them", () => {
    expect(absorb(box(299.5, 500, 200), 50)).toBe(0);
  });

  it("takes nothing when the box cannot scroll at all", () => {
    // The common case: a cell output shorter than its max-height.
    expect(absorb(box(0, 200, 200), 50)).toBe(0);
    expect(absorb(box(0, 150, 200), -50)).toBe(0);
  });

  it("takes nothing for a zero delta", () => {
    expect(absorb(box(100, 500, 200), 0)).toBe(0);
  });

  it("never returns a negative magnitude", () => {
    for (const top of [0, 50, 100, 299, 300, 400]) {
      for (const d of [-100, -1, 0, 1, 100]) {
        expect(absorb(box(top, 500, 200), d)).toBeGreaterThanOrEqual(0);
      }
    }
  });

  it("never asks for more than the remaining travel", () => {
    for (const top of [0, 120, 300]) {
      const a = absorb(box(top, 500, 200), 400);
      expect(a).toBeLessThanOrEqual(Math.max(0, 300 - top) + 1);
    }
  });
});

describe("toPixels: the three units a wheel reports", () => {
  it("passes pixels through", () => {
    expect(toPixels(120, DOM_DELTA_PIXEL, 800)).toBe(120);
  });

  it("converts lines", () => {
    expect(toPixels(3, DOM_DELTA_LINE, 800)).toBe(3 * LINE_PX);
  });

  it("converts pages", () => {
    expect(toPixels(2, DOM_DELTA_PAGE, 800)).toBe(1600);
  });

  it("never divides by a zero viewport, which a hidden tab can report", () => {
    expect(toPixels(1, DOM_DELTA_PAGE, 0)).toBe(1);
  });
});

describe("direction: a vertical gesture only", () => {
  it("reports down and up", () => {
    expect(direction(0, 40)).toBe(1);
    expect(direction(0, -40)).toBe(-1);
  });

  it("ignores a horizontal swipe, so it cannot become a vertical scroll (E-26)", () => {
    expect(direction(80, 0)).toBe(0);
    expect(direction(-120, 10)).toBe(0);   // a diagonal with a dominant X: still horizontal
  });

  it("ignores a negligible delta, which a trackpad emits constantly", () => {
    expect(direction(0, 0.4)).toBe(0);
  });
});

describe("scrollable", () => {
  it("is false when the content fits", () => {
    expect(scrollable(box(0, 200, 200))).toBe(false);
    expect(scrollable(box(0, 100, 200))).toBe(false);
  });

  it("is true when there is travel", () => {
    expect(scrollable(box(0, 500, 200))).toBe(true);
  });
});
