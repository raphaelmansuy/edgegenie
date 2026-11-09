/** Compact theme selection: system, light and dark remain explicit menu choices.
 * Shares focus/keyboard behavior with document and shell actions. */
import { createElement, memo, type ReactNode } from "react";
import { Monitor, Moon, Sun } from "./Icons";
import { ActionMenu } from "./ActionMenu";
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
  return <ActionMenu label={`Colour theme: ${LABELS[pref]}`} title={title} className="btn ghost theme-trigger"
    actions={PREFS.map((p) => ({ label: LABELS[p], checked: pref === p, onSelect: () => onChoose(p) }))}>
    {createElement(GLYPH[pref], { size: 16 })}
  </ActionMenu>;
});
