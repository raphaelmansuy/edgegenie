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

/** Who answers a chord. Exactly one owner per combo — see `resolve`. */
export type Owner = "shell" | "notebook" | "composer";
/** When the owner answers. A dialog takes every chord except Escape (`when: "no-dialog"`). */
export type When = "always" | "no-dialog";

export interface Shortcut {
  id: string;
  combo: Combo;
  /** What it does, phrased as an instruction. Shown in the sheet and in tooltips. */
  label: string;
  group: "General" | "Navigate" | "Session" | "Compose" | "Panes" | "Appearance";
  /** The component that answers this chord. The sheet groups by it, so it states the scope truthfully. */
  owner: Owner;
  /** Defaults to "always". `no-dialog` means a modal owns the keyboard while it is open. */
  when?: When;
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
  // Editor tab cycling uses the physical Control key on every platform, including Windows/Linux
  // where other Control chords are represented as `mod` in the registry.
  if (key === "tab" && e.ctrlKey && !e.metaKey) parts.push("ctrl");
  else {
    if (mac ? e.metaKey : e.ctrlKey) parts.push("mod");
    if (mac ? e.ctrlKey : e.metaKey) parts.push("ctrl");
  }
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

/** Every shortcut the app offers. The sheet and the tooltips read this; nothing else hard-codes a key.
 *
 * `owner` is not decoration: it is what the sheet groups by (so "In a cell" is its own section,
 * `KB-6`) and what `resolve` arbitrates with (so two components can never both claim a chord,
 * `KB-2`). A test asserts that every combo appears once and that every binding the app installs is
 * declared here (`KB-5`).
 */
export const SHORTCUTS: Shortcut[] = [
  // General
  { id: "palette", combo: "mod+k", label: "Command palette — jump to anything", group: "General", owner: "shell", when: "no-dialog" },
  { id: "help", combo: "mod+slash", label: "Keyboard shortcuts", group: "General", owner: "shell", when: "no-dialog" },
  { id: "providers", combo: "mod+comma", label: "Providers and keys", group: "General", owner: "shell", when: "no-dialog" },
  // Navigate
  { id: "searchFiles", combo: "mod+p", label: "Search notebooks and files", group: "Navigate", owner: "shell", when: "no-dialog" },
  { id: "nextTab", combo: "ctrl+tab", label: "Next open tab", group: "Navigate", owner: "shell" },
  { id: "prevTab", combo: "ctrl+shift+tab", label: "Previous open tab", group: "Navigate", owner: "shell" },
  { id: "closeTab", combo: "mod+w", label: "Close the current tab", group: "Navigate", owner: "shell", when: "no-dialog" },
  { id: "reopenTab", combo: "mod+shift+t", label: "Reopen the last closed tab", group: "Navigate", owner: "shell", when: "no-dialog" },
  // Panes
  { id: "railSessions", combo: "mod+1", label: "Sessions panel", group: "Panes", owner: "shell" },
  { id: "railFiles", combo: "mod+2", label: "Files panel", group: "Panes", owner: "shell" },
  { id: "railCatalog", combo: "mod+3", label: "Catalog panel", group: "Panes", owner: "shell" },
  { id: "toggleRail", combo: "mod+b", label: "Show or hide the left panel", group: "Panes", owner: "shell" },
  { id: "toggleInspector", combo: "mod+i", label: "Show or hide the inspector", group: "Panes", owner: "shell" },
  { id: "toggleDock", combo: "mod+j", label: "Show or hide the assistant", group: "Panes", owner: "shell" },
  // In a cell — the notebook owns these, and they only apply when a cell has focus
  { id: "askCell", combo: "mod+shift+i", label: "Ask the agent about this cell", group: "Compose", owner: "notebook" },
  // Compose
  { id: "send", combo: "mod+enter", label: "Send the message", group: "Compose", owner: "composer" },
  { id: "focusComposer", combo: "mod+l", label: "Focus the message box", group: "Compose", owner: "shell" },
  { id: "stop", combo: "escape", label: "Stop the agent", group: "Compose", owner: "composer" },
  { id: "mention", combo: "mod+shift+a", label: "Add a notebook, file or table (@)", group: "Compose", owner: "shell" },
  // Appearance, Session
  { id: "cycleTheme", combo: "mod+shift+l", label: "Cycle the colour theme — system, light, dark", group: "Appearance", owner: "shell" },
  { id: "newSession", combo: "mod+shift+n", label: "New session", group: "Session", owner: "shell" },
  { id: "changeModel", combo: "mod+shift+m", label: "Change the model", group: "Session", owner: "shell" },
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

/** Where a chord applies, in words. The sheet says this so a row cannot claim more than it does. */
export const SCOPE: Record<Owner, string> = {
  shell: "Anywhere",
  notebook: "In a cell",
  composer: "In the message box",
};

/** The sheet, grouped by SCOPE rather than by theme (`KB-6`): "this only works in a cell" is the one
 *  thing a shortcut list must never hide. */
export function byScope(): { scope: string; items: Shortcut[] }[] {
  const order: Owner[] = ["shell", "notebook", "composer"];
  return order
    .map((owner) => ({ scope: SCOPE[owner], items: SHORTCUTS.filter((s) => s.owner === owner) }))
    .filter((g) => g.items.length > 0);
}

/** The state a chord is resolved against. Everything `resolve` needs, and nothing else: no DOM. */
export interface KeyContext {
  /** Focus is in a text field: bare keys are text. */
  typing: boolean;
  /** A modal (palette, sheet, settings, approval) owns the keyboard. */
  dialog: boolean;
  /** A cell has focus, so the notebook's chords apply. */
  cell: boolean;
  /** The agent is working, so Escape means "stop". */
  running: boolean;
}

export interface Resolved {
  shortcut: Shortcut;
  reason: string;
}

/**
 * Which shortcut answers this key press, or null. Pure, ordered, and the ONLY place the arbitration
 * lives (`KB-2`, `[D3]`).
 *
 * The order answers, in sequence:
 *  1. a bare key in a text field is text — `null`, whatever the registry says;
 *  2. a dialog takes everything except Escape and the chords that open dialogs (nothing else may
 *     act behind a modal);
 *  3. a chord whose owner is `notebook` applies only while a cell has focus;
 *  4. otherwise the first registry row whose combo matches and whose `when` allows it.
 */
export function resolve(
  e: Parameters<typeof comboOf>[0],
  ctx: KeyContext,
): Resolved | null {
  const combo = comboOf(e);
  const isCombo = combo.includes("+");
  if (!isCombo && ctx.typing) return null;             // a letter in a field is a letter

  const rows = SHORTCUTS.filter((s) => s.combo === combo);
  if (rows.length === 0) return null;

  if (ctx.dialog) {
    // Escape closes the dialog; everything else belongs to it.
    const esc = rows.find((s) => s.combo === "escape");
    return esc ? { shortcut: esc, reason: "the dialog owns the keyboard" } : null;
  }

  const cellScoped = rows.find((s) => s.owner === "notebook");
  if (cellScoped) {
    return ctx.cell
      ? { shortcut: cellScoped, reason: "a cell has focus" }
      : null;                                          // ⌘⇧I outside a cell does nothing
  }
  // Outside a dialog, a `no-dialog` row applies like any other: `when` says who may NOT answer, and
  // only the dialog branch above enforces it. Reading it as "only always-rows apply" made every
  // dialog-opening chord (⌘K, ⌘/, ⌘,) resolve to nothing — caught by its own test.
  const shellRow = rows.find((s) => s.owner !== "notebook");
  return shellRow ? { shortcut: shellRow, reason: "global" } : null;
}

/**
 * What Escape means right now (`KB-8`). Pure and ordered, so the precedence is reviewable and
 * testable rather than implied by the order of `if` statements in a listener.
 *
 * The last case is the important one: when nothing is open and the agent is not running, Escape is
 * nobody's — it must reach the browser, which is how a user leaves a full-screen or reader mode.
 */
export type EscapeTarget =
  | "dialog" | "popover" | "drawer" | "edit" | "stop-agent" | "nothing";

export function escapeTarget(ctx: {
  dialog: boolean;
  popover: boolean;
  drawer: boolean;
  editing: boolean;
  running: boolean;
  composerFocused: boolean;
}): EscapeTarget {
  if (ctx.dialog) return "dialog";
  if (ctx.popover) return "popover";
  if (ctx.drawer) return "drawer";
  if (ctx.editing) return "edit";
  if (ctx.running && ctx.composerFocused) return "stop-agent";
  return "nothing";
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
