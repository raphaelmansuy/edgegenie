/** The dock's scroll and focus contract, in one hook (spec 012 §3).
 *
 *  - **Follow / read.** The region follows a streaming tail until the reader leaves it (domain/follow.ts).
 *  - **The whole panel scrolls it.** A wheel over the header, the status card or the composer's chrome
 *    used to scroll nothing — those are not scrollable and the page behind is not either — so a reader
 *    whose pointer was over the "Working on the server" card concluded the panel was frozen.
 *  - **A click on dead space gives the panel focus.** `aside` is focusable only so a skip link can land
 *    on it; focus on it means PageUp, Space and the arrows scroll nothing. Clicking the panel's dead
 *    space now moves focus to the log, the thing those keys are for.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  hasUnseenBelow, INITIAL_FOLLOW, isUpwardKey, onLeave, onScroll as followScroll, type FollowState,
} from "../domain/follow";

/** Things that already own a click: it must reach them untouched. */
const INTERACTIVE = [
  "a[href]", "button", "input", "textarea", "select", "summary", "label", "[contenteditable='true']",
  "[role='separator']", "[role='dialog']", "[role='menu']", "[role='listbox']", "[role='tab']",
].join(",");

function scrollsY(el: Element): boolean {
  if (!(el instanceof HTMLElement)) return false;
  if (el.scrollHeight <= el.clientHeight + 1) return false;
  return /(auto|scroll)/.test(getComputedStyle(el).overflowY);
}

export function useFollowScroll(resetKey: string, content: readonly unknown[]) {
  const scroller = useRef<HTMLDivElement>(null);
  const state = useRef<FollowState>(INITIAL_FOLLOW);
  /** Where our own last `scrollTo` landed: a scroll event AT this position is ours, not the reader's. */
  const ours = useRef<number | null>(null);
  const touchY = useRef<number | null>(null);
  const [behind, setBehind] = useState(false);

  const toEnd = useCallback(() => {
    const el = scroller.current;
    if (!el) return;
    // Instant, not smooth: a smooth scroll fires intermediate events that would read as the reader leaving.
    el.scrollTo({ top: el.scrollHeight, behavior: "instant" as ScrollBehavior });
    ours.current = el.scrollTop;
    state.current = { following: true, lastTop: el.scrollTop, lastHeight: el.scrollHeight };
    setBehind(false);
  }, []);

  const leave = useCallback(() => { state.current = onLeave(state.current); }, []);

  // A different conversation starts at its end.
  useEffect(() => { state.current = INITIAL_FOLLOW; }, [resetKey]);

  // The content grew: follow it, or tell the reader there is more below.
  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    if (state.current.following) toEnd();
    else setBehind(hasUnseenBelow({ top: el.scrollTop, height: el.scrollHeight, client: el.clientHeight }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resetKey, toEnd, ...content]);

  const onScroll = useCallback(() => {
    const el = scroller.current;
    if (!el) return;
    const sample = { top: el.scrollTop, height: el.scrollHeight, client: el.clientHeight };
    const programmatic = ours.current !== null && Math.abs(el.scrollTop - ours.current) <= 1;
    state.current = followScroll(state.current, { ...sample, programmatic });
    setBehind(!state.current.following && hasUnseenBelow(sample));
  }, []);

  /* Intent handlers go on the scroller itself. They only READ the event, so they stay passive. */
  const region = {
    onScroll,
    onWheel: (e: React.WheelEvent) => { if (e.deltaY < 0) leave(); },
    onKeyDown: (e: React.KeyboardEvent) => { if (isUpwardKey(e)) leave(); },
    onTouchStart: (e: React.TouchEvent) => { touchY.current = e.touches[0]?.clientY ?? null; },
    onTouchMove: (e: React.TouchEvent) => {
      const y = e.touches[0]?.clientY;
      // A finger moving DOWN drags the content down: the reader is going up.
      if (touchY.current !== null && y !== undefined && y > touchY.current + 2) leave();
      touchY.current = y ?? null;
    },
  };

  /* On the panel (the `aside`), not the region. */
  const forwardWheel = useCallback((e: React.WheelEvent<HTMLElement>) => {
    const el = scroller.current;
    const target = e.target as Element;
    if (!el || e.ctrlKey || el.contains(target)) return;
    for (let n: Element | null = target; n && n !== e.currentTarget; n = n.parentElement) {
      if (scrollsY(n)) return;                       // a list or a textarea that scrolls itself
    }
    if (e.deltaY < 0) leave();
    const unit = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? el.clientHeight : 1;
    el.scrollTop += e.deltaY * unit;
  }, [leave]);

  const claimFocus = useCallback((e: React.MouseEvent<HTMLElement>) => {
    if (e.button !== 0) return;
    const el = scroller.current;
    const target = e.target as Element;
    if (!el || el.contains(target) || target.closest(INTERACTIVE)) return;
    // Inside the log the browser already focuses it (it is focusable now), and must keep its default so
    // text can be selected to copy; that case returned above. Here is chrome with nothing to select.
    e.preventDefault();
    el.focus({ preventScroll: true });
  }, []);

  return { scroller, region, behind, toEnd, forwardWheel, claimFocus };
}
