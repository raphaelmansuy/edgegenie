/** Scroll hand-off: one delegated wheel listener, so a contained scroller hands its remainder up.
 *
 * The problem is a composition failure, not a bug in any one rule. `.cell-output`, `.transcript` and
 * `.dock-body` each carry `overscroll-behavior: contain`, which is individually right — it stops a
 * trackpad flick from chaining out to the page. Composed, they trap the wheel: at the end of a cell's
 * 220 px output the delta goes nowhere and the user must move the pointer into the notebook to keep
 * reading (specs/012 [F8], [SC-1]).
 *
 * The fix is NOT to remove `contain` (that restores the bug it was written for). It is to hand the
 * remainder to the nearest scrollable ancestor explicitly, which is what this does.
 *
 * Deliberately additive and quiet:
 *   - it only acts when the innermost scroller could NOT take the whole delta;
 *   - it never prevents a default at the document, so a platform gesture still works ([SC-3]);
 *   - it ignores horizontal gestures entirely ([E-26], [E-27]).
 */
import { useEffect } from "react";
import { absorb, direction, toPixels, type Box } from "../domain/scroll";

/** The box a DOM element presents to the arithmetic. */
const boxOf = (el: HTMLElement): Box => ({
  scrollTop: el.scrollTop,
  scrollHeight: el.scrollHeight,
  clientHeight: el.clientHeight,
});

/** Is this element a scroller that overflows vertically? `overflow: visible` elements are not
 *  candidates, and `clientHeight === 0` is a hidden one. */
function scrollsVertically(el: HTMLElement): boolean {
  if (el.clientHeight === 0) return false;
  const oy = getComputedStyle(el).overflowY;
  return (oy === "auto" || oy === "scroll" || oy === "overlay") && el.scrollHeight > el.clientHeight;
}

/** The scrollers from `start` up to the document, innermost first. */
function chain(start: HTMLElement | null): HTMLElement[] {
  const out: HTMLElement[] = [];
  for (let el: HTMLElement | null = start; el && el !== document.body && el !== document.documentElement; el = el.parentElement) {
    if (scrollsVertically(el)) out.push(el);
  }
  return out;
}

export function useScrollHandoff(): void {
  useEffect(() => {
    const onWheel = (e: WheelEvent) => {
      // A horizontal trackpad swipe is not ours. Neither is a gesture with no vertical intent.
      const dir = direction(e.deltaX, e.deltaY);
      if (dir === 0) return;

      const start = e.target instanceof HTMLElement ? e.target : null;
      const scrollers = chain(start);
      if (scrollers.length === 0) return;      // not inside a scroller: native behaviour is correct

      // Normalise once: three units exist, and only pixels are meaningful to `absorb`.
      const px = toPixels(e.deltaY, e.deltaMode, window.innerHeight);
      const room = absorb(boxOf(scrollers[0]), px);

      // The innermost scroller can take all of it: the browser has already scrolled it. Do nothing,
      // and do NOT prevent — this is the common case and it must feel native.
      if (room === px) return;

      // Hand the remainder up. `remaining` keeps the sign; `room` is a magnitude.
      let remaining = px - Math.sign(px) * room;
      let moved = false;
      for (const el of scrollers.slice(1)) {
        const take = absorb(boxOf(el), remaining);
        if (take === 0) continue;
        el.scrollTop += Math.sign(remaining) * take;
        remaining -= Math.sign(remaining) * take;
        moved = true;
        if (remaining === 0) break;
      }
      // Nothing above could move either: let the browser have the event so a platform gesture (a
      // back-navigation swipe, a page bounce) still works. [SC-3]
      if (!moved) return;
      /* Suppress the default only for the part we consumed. The native scroll already happened on
         the innermost element before this listener runs, so preventing here stops the OUTER elements
         from also scrolling by the full delta — which would double the movement. */
      e.preventDefault();
    };

    /* Passive: false, because the hand-off has to be able to prevent the default for the remainder.
       Registered once on the window and delegated, so a cell added mid-render needs no listener. */
    window.addEventListener("wheel", onWheel, { passive: false });
    return () => window.removeEventListener("wheel", onWheel);
  }, []);
}
