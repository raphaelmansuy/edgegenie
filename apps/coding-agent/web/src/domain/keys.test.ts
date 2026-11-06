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
