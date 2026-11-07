/** Binds the layout module to React and to this browser's storage.
 *
 * Two rules: the module decides, this hook only carries. And storage is a nicety, never a dependency —
 * a private-mode browser, a full quota, or a corrupt value all leave a working shell. (SH-B1..B5.)
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  DEFAULTS, STORAGE_KEY, clampWidth, parse, reset, resetZone, resizeBy, serialize,
  type Layout, type RailTab, type Zone,
} from "../domain/layout";

const WRITE_DELAY = 150;   // below the threshold where "did it stick?" is asked, above drag frequency

export function useLayout(viewport: number) {
  const [layout, setLayout] = useState<Layout>(() => {
    try {
      return parse(window.localStorage.getItem(STORAGE_KEY), viewport);
    } catch {
      return reset();          // storage blocked entirely: work, just do not remember
    }
  });

  // Re-clamp when the window changes: a width valid at 1600 may be impossible at 1000.
  const firstViewport = useRef(viewport);
  useEffect(() => {
    if (firstViewport.current === viewport) return;
    firstViewport.current = viewport;
    setLayout((l) => ({
      ...l,
      railWidth: clampWidth("rail", l.railWidth, viewport, l),
      inspectorWidth: clampWidth("inspector", l.inspectorWidth, viewport, l),
    }));
  }, [viewport]);

  // Debounced write: a drag would otherwise hit storage once per frame.
  useEffect(() => {
    const id = window.setTimeout(() => {
      try { window.localStorage.setItem(STORAGE_KEY, serialize(layout)); } catch { /* quota/private */ }
    }, WRITE_DELAY);
    return () => window.clearTimeout(id);
  }, [layout]);

  const setWidth = useCallback((zone: Zone, px: number) => {
    setLayout((l) => (zone === "rail"
      ? { ...l, railWidth: clampWidth("rail", px, viewport, l) }
      : { ...l, inspectorWidth: clampWidth("inspector", px, viewport, l) }));
  }, [viewport]);

  const nudge = useCallback((zone: Zone, delta: number) => {
    setLayout((l) => resizeBy(zone, l, viewport, delta));
  }, [viewport]);

  const resetOne = useCallback((zone: Zone) => setLayout((l) => resetZone(zone, l)), []);

  const toggle = useCallback((zone: Zone, on?: boolean) => {
    setLayout((l) => (zone === "rail"
      ? { ...l, railVisible: on ?? !l.railVisible }
      : { ...l, inspectorVisible: on ?? !l.inspectorVisible }));
  }, []);

  const setRailTab = useCallback((railTab: RailTab) => setLayout((l) => ({ ...l, railTab })), []);

  const resetAll = useCallback(() => setLayout(reset()), []);

  return useMemo(() => ({
    layout, setWidth, nudge, resetOne, toggle, setRailTab, resetAll,
    defaults: DEFAULTS,
  }), [layout, setWidth, nudge, resetOne, toggle, setRailTab, resetAll]);
}
