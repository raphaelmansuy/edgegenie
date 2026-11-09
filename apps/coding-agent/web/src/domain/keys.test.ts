import { describe, expect, it } from "vitest";
import { comboOf, display, grouped, isTyping, matches, SHORTCUTS } from "./keys";
import { highlight, rank, score, type Candidate } from "./fuzzy";

const mac_ = () => (globalThis as { navigator: { platform: string } }).navigator.platform;
const mac = mac_;

describe("keyboard combos", () => {
  it("reads a macOS command as mod and never as both mod and ctrl", () => {
    const platform = String(mac());
    const combo = comboOf({ key: "k", metaKey: true });
    expect(combo).toBe(/mac/i.test(platform) ? "mod+k" : "ctrl+k");
    expect(comboOf({ key: "K", metaKey: true })).not.toContain("shift");
  });
  it("normalises names people actually press", () => {
    expect(comboOf({ key: "Escape" })).toBe("escape");
    expect(comboOf({ key: " ", ctrlKey: true })).toContain("space");
    expect(comboOf({ key: "ArrowDown", altKey: true })).toContain("arrowdown");
  });
  it("keeps physical Control+Tab cycling portable on every platform", () => {
    expect(comboOf({ key: "Tab", ctrlKey: true })).toBe("ctrl+tab");
    expect(comboOf({ key: "Tab", ctrlKey: true, shiftKey: true })).toBe("ctrl+shift+tab");
  });
  it("names punctuation the same way the registry does", () => {
    // The registry writes "mod+slash"; a real key press is "/". If these drift, ⌘/ silently dies.
    const mac = /mac/i.test(String(mac_()));
    expect(comboOf({ key: "/", metaKey: true })).toBe(`${mac ? "mod" : "ctrl"}+slash`);
    expect(display("mod+slash")).toMatch(/\/$/);
    expect(comboOf({ key: ",", ctrlKey: true })).toContain("comma");
  });
  it("matches only the exact combination", () => {
    const combo = comboOf({ key: "k", metaKey: true });
    expect(matches(combo, { key: "k", metaKey: true })).toBe(true);
    expect(matches(combo, { key: "k", metaKey: true, shiftKey: true })).toBe(false);
    expect(matches(combo, { key: "j", metaKey: true })).toBe(false);
  });
  it("prints keys the way the platform does", () => {
    const isMac = /mac/i.test(String(mac()));
    expect(display("mod+k")).toBe(isMac ? "⌘K" : "Ctrl+K");
    expect(display("escape")).toBe("Esc");
    expect(display("ctrl+tab")).toMatch(/tab/i);
  });
  it("every shortcut is unique, described, and grouped", () => {
    const combos = SHORTCUTS.map((s) => s.combo);
    expect(new Set(combos).size).toBe(combos.length);
    for (const s of SHORTCUTS) {
      expect(s.label.length).toBeGreaterThan(8);
      expect(display(s.combo).length).toBeGreaterThan(0);
    }
    expect(grouped().flatMap((g) => g.items).length).toBe(SHORTCUTS.length);
  });
  it("lets modified keys through a text field, and stops bare letters", () => {
    const input = { tagName: "TEXTAREA" } as unknown as HTMLElement;
    expect(isTyping(input, false)).toBe(true);
    expect(isTyping(input, true)).toBe(false);
    expect(isTyping({ tagName: "DIV" } as unknown as HTMLElement, false)).toBe(false);
  });
});

describe("fuzzy search", () => {
  it("prefers the exact substring, at a word boundary, at the start", () => {
    expect(score("Open notebook", "open")).toBeGreaterThan(score("Reopen notebook", "open"));
    expect(score("New notebook", "nb")).toBeGreaterThan(0);
    expect(score("Open notebook", "zzz")).toBe(-1);
  });
  it("matches an abbreviation across word boundaries and ranks it first", () => {
    const candidates: Candidate[] = [
      { id: "a", title: "Toggle inspector", group: "Panes", run: () => {} },
      { id: "b", title: "New notebook", group: "Files", run: () => {} },
      { id: "c", title: "Open notebook in Databricks", group: "Files", run: () => {} },
    ];
    expect(rank(candidates, "nb")[0].candidate.id).toBe("b");
    expect(rank(candidates, "nb").map((r) => r.candidate.id)).not.toContain("a");
    expect(rank(candidates, "insp")[0].candidate.id).toBe("a");
  });
  it("returns everything for an empty query, and nothing for nonsense", () => {
    const candidates: Candidate[] = [
      { id: "x", title: "Alpha", group: "G", run: () => {} },
      { id: "y", title: "Beta", group: "G", run: () => {} },
    ];
    expect(rank(candidates, "  ").map((r) => r.candidate.id)).toEqual(["x", "y"]);
    expect(rank(candidates, "qqqq")).toEqual([]);
    // a keyword that does not match must not sneak a row in with a discounted non-score
    expect(rank([{ id: "z", title: "Alpha", keywords: "zzz", group: "G", run: () => {} }], "nb")).toEqual([]);
  });
  it("searches keywords the user cannot see, at a discount", () => {
    const candidates: Candidate[] = [
      { id: "s", title: "Sessions", group: "Panes", keywords: "rail panel left", run: () => {} },
    ];
    expect(rank(candidates, "left")[0].candidate.id).toBe("s");
  });
  it("highlights the contiguous hit, else the scattered characters", () => {
    expect(highlight("Open notebook", "note")).toEqual([
      { text: "Open ", hit: false }, { text: "note", hit: true }, { text: "book", hit: false },
    ]);
    const scattered = highlight("New notebook", "nb").filter((r) => r.hit).map((r) => r.text).join("");
    expect(scattered.toLowerCase()).toBe("nb");
    expect(highlight("Alpha", "")).toEqual([{ text: "Alpha", hit: false }]);
  });
});

// ---------------------------------------------------------------------------------------------
// 007: the registry is a contract. These tests are the reason a chord cannot have two owners.
import { byScope, escapeTarget, platform, resolve, SCOPE } from "./keys";

describe("the registry is a contract (KB-5, E-14)", () => {
  it("declares every combo exactly once", () => {
    const combos = SHORTCUTS.map((s) => s.combo);
    expect(new Set(combos).size).toBe(combos.length);
  });
  it("gives every shortcut an owner and an id that is unique", () => {
    expect(SHORTCUTS.every((s) => ["shell", "notebook", "composer"].includes(s.owner))).toBe(true);
    expect(new Set(SHORTCUTS.map((s) => s.id)).size).toBe(SHORTCUTS.length);
  });
  it("names the inspector ⌘I and the cell prompt ⌘⇧I, so the sheet cannot lie (KB-2)", () => {
    expect(SHORTCUTS.find((s) => s.id === "toggleInspector")?.combo).toBe("mod+i");
    expect(SHORTCUTS.find((s) => s.id === "askCell")?.combo).toBe("mod+shift+i");
  });
  it("lists ⌘J, which used to be bound but undiscoverable", () => {
    expect(SHORTCUTS.find((s) => s.id === "toggleDock")?.combo).toBe("mod+j");
  });
  it("groups by scope, so 'in a cell' is its own section", () => {
    const scopes = byScope();
    expect(scopes[0].scope).toBe(SCOPE.shell);
    expect(scopes.find((g) => g.scope === SCOPE.notebook)?.items.map((s) => s.id)).toEqual(["askCell"]);
  });
});

describe("resolve: one owner per press (KB-2, D3)", () => {
  const ctx = (o: Partial<Parameters<typeof resolve>[1]> = {}) =>
    ({ typing: false, dialog: false, cell: false, running: false, ...o });
  /** `mod` is ⌘ on macOS and Ctrl elsewhere; the test must press the one this platform uses, or it is
   *  testing a different chord than the registry declares. */
  const MOD = platform() === "mac" ? "metaKey" : "ctrlKey";
  const key = (k: string, m: Partial<{ metaKey: boolean; ctrlKey: boolean; shiftKey: boolean; altKey: boolean }> = {}) =>
    ({ key: k, metaKey: false, ctrlKey: false, shiftKey: false, altKey: false, ...m, [MOD]: true });
  /** A key with no modifier at all: a bare letter, or Escape. */
  const bare = (k: string) => ({ key: k, metaKey: false, ctrlKey: false, shiftKey: false, altKey: false });

  it("⌘I is the inspector, from a cell (the whole bug)", () => {
    expect(resolve(key("i"), ctx({ cell: true }))?.shortcut.id).toBe("toggleInspector");
  });
  it("⌘⇧I is the cell prompt, but only while a cell has focus", () => {
    expect(resolve(key("I", { shiftKey: true }), ctx({ cell: true }))?.shortcut.id).toBe("askCell");
    expect(resolve(key("I", { shiftKey: true }), ctx({ cell: false }))).toBeNull();
  });
  it("a bare letter in a field is text, not a command", () => {
    expect(resolve(bare("j"), ctx({ typing: true }))).toBeNull();
    expect(resolve(bare("j"), ctx())).toBeNull();       // and not a shortcut either: ⌘J is
  });
  it("a modified chord still resolves while typing (E-12)", () => {
    expect(resolve(key("k"), ctx({ typing: true }))?.shortcut.id).toBe("palette");
    expect(resolve(key("i"), ctx({ typing: true }))?.shortcut.id).toBe("toggleInspector");
  });
  it("a dialog owns everything but Escape (E-13)", () => {
    expect(resolve(key("k"), ctx({ dialog: true }))).toBeNull();
    expect(resolve(key("i"), ctx({ dialog: true, cell: true }))).toBeNull();
    expect(resolve(bare("Escape"), ctx({ dialog: true }))?.shortcut.id).toBe("stop");
  });
  it("⌘J toggles the dock", () => {
    expect(resolve(key("j"), ctx())?.shortcut.id).toBe("toggleDock");
  });
  it("an unbound chord is nobody's", () => {
    expect(resolve(key("r"), ctx())).toBeNull();
  });
});

describe("escapeTarget: one ordered meaning (KB-8)", () => {
  const base = { dialog: false, popover: false, drawer: false, editing: false, running: false, composerFocused: false };
  it("unwinds from the topmost transient", () => {
    expect(escapeTarget({ ...base, dialog: true, drawer: true, running: true })).toBe("dialog");
    expect(escapeTarget({ ...base, popover: true, drawer: true })).toBe("popover");
    expect(escapeTarget({ ...base, drawer: true, editing: true })).toBe("drawer");
    expect(escapeTarget({ ...base, editing: true, running: true })).toBe("edit");
  });
  it("stops the agent only from the composer, and only when it is running", () => {
    expect(escapeTarget({ ...base, running: true, composerFocused: true })).toBe("stop-agent");
    expect(escapeTarget({ ...base, running: true })).toBe("nothing");
    expect(escapeTarget(base)).toBe("nothing");
  });
});
