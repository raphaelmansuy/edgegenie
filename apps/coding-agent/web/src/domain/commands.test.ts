import { describe, expect, it } from "vitest";
import { applyCommand, commandAt, matchCommands, pushHistory, stepHistory } from "./commands";

describe("slash commands", () => {
  it("opens only when a command is being typed at the caret", () => {
    expect(commandAt("/ex", 3)).toEqual({ query: "ex", open: true });
    expect(commandAt("please /fi", 10)).toEqual({ query: "fi", open: true });
    expect(commandAt("a/b", 3).open).toBe(false);
    expect(commandAt("/fix it", 7).open).toBe(false);
  });
  it("a bare slash lists every command, so the menu is discoverable", () => {
    expect(commandAt("/", 1)).toEqual({ query: "", open: true });
    expect(matchCommands("").length).toBeGreaterThanOrEqual(10);
    expect(matchCommands("").map((c) => c.name)).toContain("/optimize");
  });
  it("filters by prefix and inserts the prompt in place", () => {
    expect(matchCommands("fi").map((c) => c.name)).toEqual(["/fix", "/findtables"]);
    expect(matchCommands("fix").map((c) => c.name)).toEqual(["/fix"]);
    const r = applyCommand("please /fi now", 10, matchCommands("fix")[0]);
    expect(r.text.startsWith("please Review the attached notebook")).toBe(true);
    expect(r.text.endsWith(" now")).toBe(true);
    expect(r.caret).toBe(r.text.indexOf(" now"));
  });
});

describe("prompt history", () => {
  it("keeps the newest first, once, capped", () => {
    let h: string[] = [];
    for (let i = 0; i < 5; i += 1) h = pushHistory(h, `p${i}`, 3);
    expect(h).toEqual(["p4", "p3", "p2"]);
    expect(pushHistory(h, "p3", 3)).toEqual(["p3", "p4", "p2"]);
    expect(pushHistory(h, "   ", 3)).toBe(h);
  });
  it("walks up, then down, and past the newest is an empty box", () => {
    const h = ["new", "old"];
    expect(stepHistory(h, -1, "ArrowUp")).toEqual({ at: 0, text: "new" });
    expect(stepHistory(h, 0, "ArrowUp")).toEqual({ at: 1, text: "old" });
    expect(stepHistory(h, 1, "ArrowDown")).toEqual({ at: 0, text: "new" });
    expect(stepHistory(h, 0, "ArrowDown")).toEqual({ at: -1, text: "" });
    expect(stepHistory([], -1, "ArrowUp")).toEqual({ at: -1 });
  });
});
