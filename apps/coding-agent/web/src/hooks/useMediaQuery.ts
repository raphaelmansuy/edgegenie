/** Tracks a CSS media query in React state. Pure plumbing, one listener per query.
 *
 * The shell needs this to make a real decision rather than a CSS one: on a narrow window the side
 * panels become drawers over the content, and a drawer that starts open hides the thing you opened
 * the app for. So the initial state depends on the width, which means JavaScript has to know it.
 */
import { useEffect, useState } from "react";

export function useMediaQuery(query: string): boolean {
  const read = () => typeof window !== "undefined" && window.matchMedia(query).matches;
  const [matches, setMatches] = useState(read);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const onChange = () => setMatches(mq.matches);
    onChange();
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [query]);
  return matches;
}

/** Below this the whole layout is one column: both side panels are overlays over the content. */
export const NARROW = "(max-width: 820px)";

/** Between these widths the inspector is an overlay, because the three columns no longer fit. */
export const INSPECTOR_DRAWER = "(max-width: 1180px)";

/** True when the inspector is an overlay rather than a column. */
export function inspectorIsOverlay(): boolean {
  return typeof window !== "undefined" && window.matchMedia(INSPECTOR_DRAWER).matches;
}

/** True when the left panel is an overlay rather than a column. */
export function railIsOverlay(): boolean {
  return typeof window !== "undefined" && window.matchMedia(NARROW).matches;
}
