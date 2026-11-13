import { describe, expect, it } from "vitest";
import {
  hasUnseenBelow, INITIAL_FOLLOW, isUpwardKey, onLeave, onScroll, REPIN_PX, type FollowState, type ScrollSample,
} from "./follow";

const sample = (top: number, extra: Partial<ScrollSample> = {}): ScrollSample => ({
  top, height: 2000, client: 400, programmatic: false, ...extra,
});
const BOTTOM = 1600;

describe("follow — the reader owns the position the moment they move up", () => {
  it("a small scroll up leaves the tail. The old 80 px dead zone is gone", () => {
    let s: FollowState = { following: true, lastTop: BOTTOM, lastHeight: 2000 };
    s = onScroll(s, sample(BOTTOM - 60));
    expect(s.following).toBe(false);
  });

  it("our own scroll to the end never counts as the reader leaving", () => {
    let s: FollowState = { following: true, lastTop: 1000, lastHeight: 2000 };
    s = onScroll(s, sample(BOTTOM, { programmatic: true }));
    expect(s.following).toBe(true);
  });

  it("content growing under a reader who is reading does not re-pin them", () => {
    let s: FollowState = { following: false, lastTop: 1000, lastHeight: 2000 };
    // The stream appended: height grew, top is unchanged, no scroll event fires — but if one does:
    s = onScroll(s, sample(1000, { height: 2600 }));
    expect(s.following).toBe(false);
  });

  it("re-pins when the reader returns to the bottom, within REPIN_PX", () => {
    let s: FollowState = { following: false, lastTop: 1000, lastHeight: 2000 };
    s = onScroll(s, sample(BOTTOM - REPIN_PX - 1));
    expect(s.following).toBe(false);
    s = onScroll(s, sample(BOTTOM - REPIN_PX));
    expect(s.following).toBe(true);
  });

  it("moving down while reading does not re-pin until the bottom", () => {
    let s: FollowState = { following: false, lastTop: 800, lastHeight: 2000 };
    s = onScroll(s, sample(900));
    expect(s.following).toBe(false);
  });

  it("a list that SHRINKS makes the browser clamp scrollTop: that is the content moving, not the reader", () => {
    // A retry replaced the tail: height fell 2000 -> 1700 and the browser pulled scrollTop down with it.
    const s = onScroll({ following: true, lastTop: 1600, lastHeight: 2000 }, sample(1300, { height: 1700 }));
    expect(s.following).toBe(true);
  });
});

describe("follow — intent is counted before any scroll event is measured", () => {
  it("a wheel, touch or key up leaves immediately", () => {
    expect(onLeave(INITIAL_FOLLOW).following).toBe(false);
  });
  it("leaving twice is the same as once, and returns the same object when nothing changes", () => {
    const left = onLeave(INITIAL_FOLLOW);
    expect(onLeave(left)).toBe(left);
  });
  it("names the keys that go up", () => {
    for (const key of ["PageUp", "ArrowUp", "Home"]) expect(isUpwardKey({ key })).toBe(true);
    expect(isUpwardKey({ key: " ", shiftKey: true })).toBe(true);
    for (const key of ["PageDown", "ArrowDown", "End", "a"]) expect(isUpwardKey({ key })).toBe(false);
    expect(isUpwardKey({ key: " " })).toBe(false);
  });
});

describe("hasUnseenBelow", () => {
  it("is true only when more than REPIN_PX of content is below the reader", () => {
    expect(hasUnseenBelow({ top: 0, height: 2000, client: 400 })).toBe(true);
    expect(hasUnseenBelow({ top: BOTTOM - REPIN_PX, height: 2000, client: 400 })).toBe(false);
    expect(hasUnseenBelow({ top: BOTTOM, height: 2000, client: 400 })).toBe(false);
  });
});
