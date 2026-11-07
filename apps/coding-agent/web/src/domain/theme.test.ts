import { describe, expect, it } from "vitest";
import { attrFor, describe as describeTheme, LABELS, next, parsePref, PREFS, resolve } from "./theme";

describe("theme preference", () => {
  it("falls back to system for anything unrecognised", () => {
    // A stale key, a hand-edited value, or a value from a future version must not break the app.
    expect(parsePref(null)).toBe("system");
    expect(parsePref(undefined)).toBe("system");
    expect(parsePref("")).toBe("system");
    expect(parsePref("solarized")).toBe("system");
    expect(parsePref("DARK")).toBe("system");
  });

  it("keeps the three real preferences", () => {
    expect(parsePref("system")).toBe("system");
    expect(parsePref("light")).toBe("light");
    expect(parsePref("dark")).toBe("dark");
  });

  it("resolves system against the OS answer", () => {
    expect(resolve("system", true)).toBe("dark");
    expect(resolve("system", false)).toBe("light");
  });

  it("lets an explicit preference beat the OS in both directions", () => {
    // This is the whole point of three states: a user who picks light on a dark machine gets light.
    expect(resolve("light", true)).toBe("light");
    expect(resolve("dark", false)).toBe("dark");
  });

  it("removes the attribute for system so the media query drives the paint", () => {
    // If we wrote data-theme="system", every CSS rule matching [data-theme="dark"] would miss and
    // the sheet's media query would never take over — the app would silently ignore the OS.
    expect(attrFor("system")).toBeNull();
    expect(attrFor("light")).toBe("light");
    expect(attrFor("dark")).toBe("dark");
  });

  it("cycles through every preference and returns to the start", () => {
    let p = PREFS[0];
    const seen = [p];
    for (let i = 0; i < PREFS.length - 1; i += 1) {
      p = next(p);
      seen.push(p);
    }
    expect(seen).toEqual([...PREFS]);
    expect(next(PREFS[PREFS.length - 1])).toBe(PREFS[0]);
  });

  it("cycles backwards too, so a Shift+shortcut lands where a user expects", () => {
    expect(next("system", -1)).toBe("dark");
    expect(next("light", -1)).toBe("system");
  });

  it("describes the state in a sentence a tooltip can show", () => {
    expect(describeTheme("system", "dark")).toContain("follows your system");
    expect(describeTheme("system", "dark")).toContain("dark");
    expect(describeTheme("light", "light")).toBe("Theme: always light");
  });

  it("has a label for every preference, so the control never renders blank", () => {
    for (const p of PREFS) expect(LABELS[p]).toBeTruthy();
  });
});
