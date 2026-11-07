/** Binds the theme preference to the document and to React.
 *
 * Two details matter more than the state itself:
 *
 * 1. No flash. The theme must be on `<html>` before the first paint, so `main.tsx` calls
 *    `applyStoredTheme()` synchronously at module load. Without that a dark-mode user sees a
 *    white frame on every navigation, which reads as a bug.
 *
 * 2. `system` is live. When the preference is `system`, the `data-theme` attribute is *removed*
 *    and the CSS media query takes over, so switching the OS theme repaints without any JS. The
 *    media-query listener exists only to keep the reported `effective` value truthful (the label
 *    in the menu), not to repaint.
 */
import { useCallback, useEffect, useState } from "react";
import { attrFor, describe, next, parsePref, resolve, STORAGE_KEY, type Theme, type ThemePref } from "../domain/theme";

const QUERY = "(prefers-color-scheme: dark)";

function systemPrefersDark(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia(QUERY).matches
    : false;
}

function writeAttr(pref: ThemePref): void {
  const doc = document.documentElement;
  const attr = attrFor(pref);
  if (attr === null) doc.removeAttribute("data-theme");
  else doc.setAttribute("data-theme", attr);
}

/** Called once, before React mounts, so the first paint is already correct. */
export function applyStoredTheme(): ThemePref {
  let raw: string | null = null;
  try {
    raw = window.localStorage.getItem(STORAGE_KEY);
  } catch {
    // Private mode or storage disabled: follow the system rather than failing to render.
  }
  const pref = parsePref(raw);
  writeAttr(pref);
  return pref;
}

export function useTheme() {
  const [pref, setPref] = useState<ThemePref>(() => parsePref(
    (() => { try { return window.localStorage.getItem(STORAGE_KEY); } catch { return null; } })(),
  ));
  const [systemDark, setSystemDark] = useState(systemPrefersDark);

  // Keep the reported system answer current so the "follows your system" label stays honest.
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const mq = window.matchMedia(QUERY);
    const onChange = (e: MediaQueryListEvent) => setSystemDark(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  const choose = useCallback((p: ThemePref) => {
    setPref(p);
    writeAttr(p);
    try { window.localStorage.setItem(STORAGE_KEY, p); } catch { /* private mode */ }
  }, []);

  const cycle = useCallback(() => {
    // Cycling must use the latest preference, not a value captured when the handler was built.
    setPref((cur) => {
      const n = next(cur);
      writeAttr(n);
      try { window.localStorage.setItem(STORAGE_KEY, n); } catch { /* private mode */ }
      return n;
    });
  }, []);

  const effective: Theme = resolve(pref, systemDark);
  return { pref, effective, choose, cycle, title: describe(pref, effective) };
}
