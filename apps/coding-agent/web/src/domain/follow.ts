/** When a streaming transcript follows its tail, and when it lets the reader go. Pure.
 *
 * Two states: FOLLOWING (new content scrolls into view) and READING (the reader's position is theirs).
 * The old rule was "pinned if within 80 px of the bottom, measured at the last scroll event". That
 * made the dead zone 80 px wide: one wheel notch or a short trackpad flick moved the reader up by
 * less than that, they were still "pinned", and the next streamed token took the scroll position
 * back. From the reader's chair the panel simply would not scroll while it was working.
 *
 * The rules, in the order they apply:
 *  1. **Intent wins.** A wheel up, a touch drag, or an upward key is the reader leaving, and it
 *     counts before any scroll event has been measured — the stream may append in between.
 *  2. A scroll that moved UP and was not ours is the reader leaving too (scrollbar drag, anything
 *     intent did not see).
 *  3. Following resumes only when the reader is back at the bottom, within `REPIN_PX` — small, and
 *     deliberately not the old 80.
 */
export const REPIN_PX = 24;

export interface FollowState {
  following: boolean;
  /** `scrollTop` at the previous scroll event, to tell up from down. */
  lastTop: number;
  /** `scrollHeight` at the previous scroll event: a shrinking list makes the browser clamp `scrollTop`
   *  downwards, and that is the content leaving, not the reader. */
  lastHeight: number;
}

export const INITIAL_FOLLOW: FollowState = { following: true, lastTop: 0, lastHeight: 0 };

export interface ScrollSample {
  top: number;
  height: number;
  client: number;
  /** The scroll was caused by our own `scrollTo`, not by the reader. */
  programmatic: boolean;
}

/** A scroll event. */
export function onScroll(state: FollowState, s: ScrollSample): FollowState {
  const distance = s.height - s.top - s.client;
  const clamped = s.height < state.lastHeight;
  const movedUp = s.top < state.lastTop - 1 && !clamped;
  let following = state.following;
  if (!s.programmatic && movedUp) following = false;
  else if (distance <= REPIN_PX) following = true;
  return { following, lastTop: s.top, lastHeight: s.height };
}

/** The reader said "up" with the wheel, a finger, or a key, before the browser reported a scroll. */
export function onLeave(state: FollowState): FollowState {
  return state.following ? { ...state, following: false } : state;
}

/** Keys that move the reader up. `Space` with Shift is a page up. */
export function isUpwardKey(e: { key: string; shiftKey?: boolean }): boolean {
  return e.key === "PageUp" || e.key === "ArrowUp" || e.key === "Home" || (e.key === " " && Boolean(e.shiftKey));
}

/** Should an update to the content move the scroll position? Only while following. */
export const shouldFollow = (state: FollowState): boolean => state.following;

/** Is there content below the reader that they are not seeing? Drives the "Latest" control. */
export function hasUnseenBelow(s: Pick<ScrollSample, "top" | "height" | "client">): boolean {
  return s.height - s.top - s.client > REPIN_PX;
}
