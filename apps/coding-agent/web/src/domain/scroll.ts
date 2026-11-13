/** Scroll hand-off: how much of a wheel delta a box can absorb.
 *
 * The problem this solves is a composition failure, not a bug in any one rule. Three nested
 * scrollers (`.dock-body`, `.cell-output`, `.transcript`) each carry
 * `overscroll-behavior: contain`, which is individually correct — it stops a trackpad flick from
 * chaining out to the page. Composed, they trap the wheel: at the end of a cell's 220 px output the
 * delta goes nowhere, and the user must move the pointer into the notebook to keep reading.
 *
 * The fix is not to remove `contain` (that would restore the bug it was written for) but to hand the
 * remainder down explicitly. This module is the arithmetic; the hook does the DOM walking.
 *
 * Pure, and total: any box and any delta produce a number, with no special cases for callers to
 * remember. See specs/012-ux-improve 07 §3.
 */

export interface Box {
  scrollTop: number;
  scrollHeight: number;
  clientHeight: number;
}

/** Wheel deltas arrive in one of three units. A mouse reports pixels; Firefox's line mode reports
 *  lines; a page-based wheel exists. Normalising here means the arithmetic below only ever sees
 *  pixels and the three conversions are testable without a browser. */
export const DOM_DELTA_PIXEL = 0;
export const DOM_DELTA_LINE = 1;
export const DOM_DELTA_PAGE = 2;

/** A line is ~16 px at the app's type scale (13 px body, 1.55 line-height ≈ 20 px, and browsers use
 *  a slightly tighter figure for wheel lines). The exact number does not matter; the unit does. */
export const LINE_PX = 16;

export function toPixels(
  delta: number,
  deltaMode: number,
  pageHeight: number,
  linePx: number = LINE_PX,
): number {
  if (deltaMode === DOM_DELTA_LINE) return delta * linePx;
  if (deltaMode === DOM_DELTA_PAGE) return delta * Math.max(1, pageHeight);
  return delta;
}

/** How much of `deltaPx` this box can absorb before it reaches an edge.
 *
 * Returns a non-negative magnitude; the caller keeps the sign. Zero means "this box cannot move this
 * way, pass the whole delta to the ancestor".
 *
 * The four cases, all measured by `scroll.test.ts`:
 *   - a box with nothing to scroll (`scrollHeight === clientHeight`) absorbs nothing;
 *   - at the top, a negative delta absorbs nothing;
 *   - at the bottom, a positive delta absorbs nothing;
 *   - in the middle, absorbs the whole delta, or the remainder when it is larger.
 */
export function absorb(box: Box, deltaPx: number): number {
  const extent = Math.max(0, box.scrollHeight - box.clientHeight);
  if (extent <= 0 || deltaPx === 0) return 0;
  const atTop = box.scrollTop <= 0;
  const atBottom = box.scrollTop >= extent - 1;   // -1: sub-pixel offsets are common on trackpads
  if (deltaPx < 0) return atTop ? 0 : Math.min(-deltaPx, box.scrollTop);
  return atBottom ? 0 : Math.min(deltaPx, extent - box.scrollTop);
}

/** Which direction the delta wants to move content. `0` for a horizontal or empty gesture, which the
 *  hand-off ignores on purpose: a horizontal trackpad swipe over a vertical scroller must not become
 *  a vertical scroll (edge cases E-26, E-27). */
export const direction = (deltaX: number, deltaY: number): -1 | 0 | 1 => {
  if (Math.abs(deltaY) < 1 || Math.abs(deltaY) <= Math.abs(deltaX)) return 0;
  return deltaY < 0 ? -1 : 1;
};

/** Does this box scroll at all? Used by the hook to decide whether a candidate is worth walking to. */
export const scrollable = (box: Box): boolean => box.scrollHeight - box.clientHeight > 0;
