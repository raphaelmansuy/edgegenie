/** Keyboard shortcuts: one registry, one matcher, one formatter. Pure, no React.
 *
 * The bar set by the best desktop-class web apps in 2026 (Linear, Raycast, Cursor, Superhuman) is not
 * "some keys work" — it is a complete, discoverable, documented set: a command palette, a shortcut
 * sheet, and every control reachable without a mouse. That needs the shortcuts to be data, not
 * scattered `if (e.key === ...)` branches, so they can be listed, matched and displayed from one place.
 */

export type Platform = "mac" | "other";

/** A key combination in one canonical text form: modifiers first, always lower case. */
export type Combo = string;

export interface Shortcut {
  id: string;
  combo: Combo;
  /** What it does, phrased as an instruction. Shown in the sheet and in tooltips. */
  label: string;
  group: "General" | "Navigate" | "Session" | "Compose" | "Panes" | "Appearance";
}

const IS_MAC = typeof navigator !== "undefined" && /mac|iphone|ipad/i.test(navigator.platform || navigator.userAgent);
export const platform = (): Platform => (IS_MAC ? "mac" : "other");

/** "mod+k", "shift+enter", "escape", "alt+arrowright". `mod` is ⌘ on macOS, Ctrl elsewhere. */
export function comboOf(e: {
  key: string; metaKey?: boolean; ctrlKey?: boolean; shiftKey?: boolean; altKey?: boolean;
}): Combo {
  const key = normaliseKey(e.key);
  const parts: string[] = [];
  // A shortcut that means ⌘ on a Mac must mean Ctrl elsewhere, and never both.
  const mac = platform() === "mac";
  if (mac ? e.metaKey : e.ctrlKey) parts.push("mod");
  if (mac ? e.ctrlKey : e.metaKey) parts.push("ctrl");
  if (e.altKey) parts.push("alt");
  if (e.shiftKey) parts.push("shift");
  parts.push(key);
  return parts.join("+");
}

//: Punctuation has a spoken name in the registry and a character on the key. One table, so a
//: shortcut written as "mod+slash" and the key press "/" cannot drift apart.
const ALIASES: Record<string, string> = {
  " ": "space",
  esc: "escape",
  return: "enter",
  del: "delete",
  "/": "slash",
  "\\": "backslash",
  ",": "comma",
  ".": "period",
  "-": "dash",
  "=": "equals",
  "[": "bracketleft",
  "]": "bracketright",
  "`": "backtick",
  "'": "quote",
};

function normaliseKey(key: string): string {
  const k = key.toLowerCase();
  return ALIASES[k] ?? k;
}

/** True when the key event is exactly this shortcut (no extra modifiers). */
export function matches(combo: Combo, e: Parameters<typeof comboOf>[0]): boolean {
  return comboOf(e) === combo;
}

/** How a combo reads to a person on this platform: ⌘K, ⇧⌘P, ↑, Esc. */
export function display(combo: Combo): string {
  const mac = platform() === "mac";
  const names: Record<string, string> = mac
    ? { mod: "⌘", ctrl: "⌃", alt: "⌥", shift: "⇧", enter: "⏎", escape: "Esc", space: "Space",
      arrowup: "↑", arrowdown: "↓", arrowleft: "←", arrowright: "→", delete: "⌫", tab: "Tab",
      backspace: "⌫", slash: "/", comma: ",", period: ".", dash: "-", equals: "=",
      bracketleft: "[", bracketright: "]", backtick: "`", quote: "'", backslash: "\\" }
    : { mod: "Ctrl", ctrl: "Ctrl", alt: "Alt", shift: "Shift", enter: "Enter", escape: "Esc",
      space: "Space", arrowup: "↑", arrowdown: "↓", arrowleft: "←", arrowright: "→",
      delete: "Del", tab: "Tab", backspace: "Backspace", slash: "/", comma: ",", period: ".",
      dash: "-", equals: "=", bracketleft: "[", bracketright: "]", backtick: "`", quote: "'",
      backslash: "\\" };
  const parts = combo.split("+");
  const key = parts.pop() ?? "";
  const mods = parts.map((p) => names[p] ?? p);
  const label = names[key] ?? (key.length === 1 ? key.toUpperCase() : key);
  // macOS convention puts modifiers tight: ⌘⇧P. Everywhere else: Ctrl+Shift+P.
  return mac ? `${mods.join("")}${label}` : [...mods, label].join("+");
}

/** Every shortcut the app offers. The sheet and the tooltips read this; nothing else hard-codes a key. */
export const SHORTCUTS: Shortcut[] = [
  { id: "palette", combo: "mod+k", label: "Command palette — jump to anything", group: "General" },
  { id: "help", combo: "mod+slash", label: "Keyboard shortcuts", group: "General" },
  { id: "newSession", combo: "mod+shift+n", label: "New session", group: "Session" },
  { id: "changeModel", combo: "mod+shift+m", label: "Change the model", group: "Session" },
  { id: "providers", combo: "mod+comma", label: "Providers and keys", group: "General" },
  { id: "send", combo: "mod+enter", label: "Send the message", group: "Compose" },
  { id: "focusComposer", combo: "mod+l", label: "Focus the message box", group: "Compose" },
  { id: "stop", combo: "escape", label: "Stop the agent", group: "Compose" },
  { id: "mention", combo: "mod+shift+a", label: "Add a notebook, file or table (@)", group: "Compose" },
  { id: "railSessions", combo: "mod+1", label: "Sessions panel", group: "Panes" },
  { id: "railFiles", combo: "mod+2", label: "Files panel", group: "Panes" },
  { id: "railCatalog", combo: "mod+3", label: "Catalog panel", group: "Panes" },
  { id: "toggleRail", combo: "mod+b", label: "Show or hide the left panel", group: "Panes" },
  { id: "toggleInspector", combo: "mod+i", label: "Show or hide the inspector", group: "Panes" },
  { id: "cycleTheme", combo: "mod+shift+l", label: "Cycle the colour theme — system, light, dark", group: "Appearance" },
  { id: "searchFiles", combo: "mod+p", label: "Search notebooks and files", group: "Navigate" },
  { id: "nextTab", combo: "ctrl+tab", label: "Next open tab", group: "Navigate" },
  { id: "prevTab", combo: "ctrl+shift+tab", label: "Previous open tab", group: "Navigate" },
  { id: "closeTab", combo: "mod+w", label: "Close the current tab", group: "Navigate" },
];

/** Each part of a combo as its own keycap: ["⌘","⇧","P"] on a Mac, ["Ctrl","Shift","P"] elsewhere. */
export function caps(combo: Combo): string[] {
  const mac = platform() === "mac";
  const names: Record<string, string> = mac
    ? { mod: "⌘", ctrl: "⌃", alt: "⌥", shift: "⇧" }
    : { mod: "Ctrl", ctrl: "Ctrl", alt: "Alt", shift: "Shift" };
  const parts = combo.split("+");
  const key = parts.pop() ?? "";
  const special: Record<string, string> = {
    enter: mac ? "⏎" : "Enter", escape: "Esc", space: "Space", tab: "Tab",
    arrowup: "↑", arrowdown: "↓", arrowleft: "←", arrowright: "→",
    delete: mac ? "⌫" : "Del", backspace: mac ? "⌫" : "Backspace",
    slash: "/", comma: ",", period: ".", dash: "-", equals: "=", backtick: "`", quote: "'",
    bracketleft: "[", bracketright: "]", backslash: "\\",
  };
  return [
    ...parts.map((p) => names[p] ?? p),
    special[key] ?? (key.length === 1 ? key.toUpperCase() : key),
  ];
}

export const byId = (id: string): Shortcut | undefined => SHORTCUTS.find((s) => s.id === id);

/** Grouped for the sheet, in the order people learn them. */
export function grouped(): { group: Shortcut["group"]; items: Shortcut[] }[] {
  const order: Shortcut["group"][] = ["General", "Navigate", "Compose", "Panes", "Appearance", "Session"];
  return order
    .map((group) => ({ group, items: SHORTCUTS.filter((s) => s.group === group) }))
    .filter((g) => g.items.length > 0);
}

/**
 * Whether a key event should reach an app shortcut at all.
 *
 * A bare letter typed into the composer is text, not a command. Modified combos still work there,
 * which is what people expect: ⌘K opens the palette from inside any field.
 */
export function isTyping(target: EventTarget | null, isCombo: boolean): boolean {
  if (isCombo) return false;
  const el = target as HTMLElement | null;
  if (!el) return false;
  const tag = el.tagName?.toLowerCase();
  return tag === "input" || tag === "textarea" || tag === "select" || el.isContentEditable === true;
}
