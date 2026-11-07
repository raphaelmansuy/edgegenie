/** The theme control: System / Light / Dark, as a segmented control.
 *
 * A two-state toggle would be smaller, but it cannot express "follow the machine", and that is
 * the state most people want — it is the default here for that reason. Three segments make the
 * current state readable at a glance and make the third option discoverable, which a hidden
 * "cycle" button never is.
 *
 * Each segment shows its own glyph so the control is legible before it is read: a monitor for
 * system, a sun for light, a moon for dark. Colour is not the only carrier of meaning, so it
 * survives greyscale and forced-colours.
 */
import { createElement, memo, type ReactNode } from "react";
import { Monitor, Moon, Sun } from "./Icons";
import { LABELS, PREFS, type ThemePref } from "../domain/theme";

/* Drawn, not typed: "☀" and "☾" differ in size and weight per platform, and the monitor glyph
   "▭" is not a monitor at all. These share the grid with every other icon in the chrome. */
const GLYPH: Record<ThemePref, (p: { size?: number }) => ReactNode> = {
  system: Monitor, light: Sun, dark: Moon,
};

interface Props {
  pref: ThemePref;
  onChoose: (p: ThemePref) => void;
  title: string;
}

export const ThemeSwitch = memo(function ThemeSwitch({ pref, onChoose, title }: Props) {
  return (
    <div className="theme-switch" role="radiogroup" aria-label="Colour theme" title={title}>
      {PREFS.map((p) => (
        <button
          key={p}
          role="radio"
          aria-checked={pref === p}
          className="theme-opt"
          onClick={() => onChoose(p)}
          title={p === "system" ? "Follow the system setting" : `Always ${LABELS[p].toLowerCase()}`}
        >
          <span aria-hidden className="theme-glyph">{createElement(GLYPH[p], { size: 14 })}</span>
          <span className="theme-label">{LABELS[p]}</span>
        </button>
      ))}
    </div>
  );
});
