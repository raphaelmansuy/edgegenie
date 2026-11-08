/** The first element of a list that is actually painted. Pure over a DOM list; no React.
 *
 * `display: none` (and any ancestor with it) leaves an element with no client rects, which is the
 * one test that is true for every way of hiding: a media query, a collapsed panel, a closed drawer.
 */
export function firstVisible<T extends Element>(list: Iterable<T>): T | null {
  for (const el of list) if (el.getClientRects().length > 0) return el;
  return null;
}
