/** Theme preference: what the user asked for, not what is currently painted.
 *
 * Three states, because two is a trap. A light/dark switch silently overrides the operating
 * system, and then the app stops following the machine at dusk — the user has to remember to
 * switch it back. Following the reference design system (gr8r-studio), the stored value is the
 * *preference* (`system` | `light` | `dark`), and the *effective* theme is derived from it.
 *
 * This module is pure: it takes a stored string and a media-query answer and returns a decision.
 * That keeps "what colour is the app" testable without a DOM, and keeps the CSS free of logic.
 */

export type ThemePref = "system" | "light" | "dark";
export type Theme = "light" | "dark";

export const STORAGE_KEY = "coding-agent:theme:v1";

/** The order shown in the segmented control: least surprising first. */
export const PREFS: readonly ThemePref[] = ["system", "light", "dark"] as const;

export const LABELS: Record<ThemePref, string> = {
  system: "System",
  light: "Light",
  dark: "Dark",
};

/** Read a stored preference. Anything unrecognised — a stale key, a hand-edited value, a value
 *  written by a future version — falls back to `system` rather than throwing or guessing. */
export function parsePref(raw: string | null | undefined): ThemePref {
  return raw === "light" || raw === "dark" || raw === "system" ? raw : "system";
}

/** The theme actually painted. `system` defers to the media query; the other two are absolute. */
export function resolve(pref: ThemePref, systemPrefersDark: boolean): Theme {
  if (pref === "light") return "light";
  if (pref === "dark") return "dark";
  return systemPrefersDark ? "dark" : "light";
}

/** The attribute value for `<html data-theme>`. `system` removes the attribute so the CSS media
 *  query takes over — that is what makes the app follow the OS live, without JS re-rendering. */
export function attrFor(pref: ThemePref): string | null {
  return pref === "system" ? null : pref;
}

/** Next preference when the user cycles with a keyboard shortcut or clicks the control twice.
 *  Cycles in the order the segmented control shows, so the visible state and the key agree. */
export function next(pref: ThemePref, step = 1): ThemePref {
  const at = PREFS.indexOf(pref);
  return PREFS[(at + step + PREFS.length) % PREFS.length];
}

/** A human sentence for the button title, which must explain what the current state means. */
export function describe(pref: ThemePref, effective: Theme): string {
  if (pref === "system") return `Theme: follows your system (currently ${effective})`;
  return `Theme: always ${pref}`;
}
