import { describe, expect, it } from "vitest";
import {
  CENTRE_MIN, DEFAULTS, INSPECTOR_DEFAULT, INSPECTOR_MAX, INSPECTOR_MIN, KEY_STEP, KEY_STEP_COARSE,
  RAIL_DEFAULT, RAIL_MIN, clampWidth, columns, defaultWidth, minWidth, modeFor, parse, reset,
  resetZone, resizeBy, serialize, type Layout,
} from "./layout";

const at = (_w: number, extra: Partial<Layout> = {}): Layout => ({ ...DEFAULTS, ...extra });

describe("mode", () => {
  it("switches at 1180 and 820", () => {
    expect(modeFor(1600)).toBe("wide");
    expect(modeFor(1180)).toBe("mid");
    expect(modeFor(1181)).toBe("wide");
    expect(modeFor(820)).toBe("narrow");
    expect(modeFor(821)).toBe("mid");
  });
  it("survives a nonsense viewport", () => {
    expect(modeFor(NaN)).toBe("wide");
    expect(modeFor(0)).toBe("wide");
    expect(modeFor(-100)).toBe("wide");
  });
});

describe("bounds — the arithmetic that must be right", () => {
  it("never lets a panel starve the centre column", () => {
    const viewport = 1280;
    const wide = clampWidth("rail", 9999, viewport, at(viewport));
    expect(wide).toBeLessThanOrEqual(viewport - INSPECTOR_DEFAULT - CENTRE_MIN);
    expect(wide).toBeGreaterThanOrEqual(RAIL_MIN);
  });
  it("respects the 40% share", () => {
    expect(clampWidth("inspector", 9999, 1600, at(1600))).toBeLessThanOrEqual(Math.floor(1600 * 0.4));
  });
  it("caps the inspector at its own maximum", () => {
    expect(clampWidth("inspector", 9999, 4000, at(4000))).toBe(INSPECTOR_MAX);
  });
  it("clamps up to the minimum too", () => {
    expect(clampWidth("rail", 10, 1440)).toBe(RAIL_MIN);
    expect(clampWidth("inspector", 10, 1440)).toBe(INSPECTOR_MIN);
  });
  it("rounds, because a half-pixel divider renders blurry", () => {
    expect(clampWidth("rail", 300.6, 1440)).toBe(301);
    expect(clampWidth("rail", NaN, 1440)).toBe(RAIL_DEFAULT);
  });
  it("lets the centre win when both panels are wide in a small window", () => {
    const viewport = 900;
    const both = at(viewport, { railWidth: 400, inspectorWidth: 400 });
    const cols = columns(both, viewport).split(" ");
    const rail = parseInt(cols[0], 10);
    const insp = parseInt(cols[2], 10);
    expect(rail + insp).toBeLessThanOrEqual(viewport - CENTRE_MIN);
  });
  it("a hidden zone frees its space for the other", () => {
    const viewport = 1440;
    const withBoth = clampWidth("rail", 9999, viewport, at(viewport));
    const withoutInspector = clampWidth("rail", 9999, viewport, at(viewport, { inspectorVisible: false }));
    expect(withoutInspector).toBeGreaterThanOrEqual(withBoth);
  });
});

describe("columns — the only producer of the grid string", () => {
  it("three columns when wide and both visible", () => {
    expect(columns(at(1440), 1440)).toBe(`${RAIL_DEFAULT}px minmax(0, 1fr) ${INSPECTOR_DEFAULT}px`);
  });
  it("two columns when a zone is hidden", () => {
    expect(columns(at(1440, { railVisible: false }), 1440)).toBe(`minmax(0, 1fr) ${INSPECTOR_DEFAULT}px`);
    expect(columns(at(1440, { inspectorVisible: false }), 1440)).toBe(`${RAIL_DEFAULT}px minmax(0, 1fr)`);
  });
  it("one column when both are hidden", () => {
    expect(columns(at(1440, { railVisible: false, inspectorVisible: false }), 1440)).toBe("minmax(0, 1fr)");
  });
  it("an overlay takes no column, even when it is visible", () => {
    // mid: the inspector is drawn over the work area, so it must not reserve width
    expect(columns(at(1100), 1100)).toBe(`${RAIL_DEFAULT}px minmax(0, 1fr)`);
    // narrow: neither does
    expect(columns(at(760), 760)).toBe("minmax(0, 1fr)");
  });
  it("always contains a flexible centre column", () => {
    for (const v of [760, 900, 1180, 1440, 1920]) {
      expect(columns(at(v), v)).toContain("minmax(0, 1fr)");
    }
  });
});

describe("resize and reset", () => {
  it("moves by the delta and clamps at both ends", () => {
    const wide = resizeBy("rail", at(1440), 1440, 40);
    expect(wide.railWidth).toBe(RAIL_DEFAULT + 40);
    expect(resizeBy("rail", at(1440), 1440, -9999).railWidth).toBe(RAIL_MIN);
  });
  it("resizes one zone without touching the other", () => {
    const next = resizeBy("inspector", at(1440), 1440, 20);
    expect(next.inspectorWidth).toBe(INSPECTOR_DEFAULT + 20);
    expect(next.railWidth).toBe(RAIL_DEFAULT);
  });
  it("resets one zone, not both", () => {
    const moved = resizeBy("rail", at(1440), 1440, 60);
    expect(resetZone("rail", moved).railWidth).toBe(RAIL_DEFAULT);
    expect(resetZone("rail", moved).inspectorWidth).toBe(moved.inspectorWidth);
  });
  it("exposes the steps the keyboard uses", () => {
    expect(KEY_STEP).toBe(8);
    expect(KEY_STEP_COARSE).toBe(64);
    expect(defaultWidth("rail")).toBe(RAIL_DEFAULT);
    expect(minWidth("inspector")).toBe(INSPECTOR_MIN);
  });
});

describe("parse is total — a stored preference must never break the shell", () => {
  const vp = 1440;
  it("null and empty give the defaults", () => {
    expect(parse(null, vp)).toEqual(DEFAULTS);
    expect(parse("", vp)).toEqual(DEFAULTS);
    expect(parse(undefined, vp)).toEqual(DEFAULTS);
  });
  it("garbage gives the defaults and does not throw", () => {
    for (const bad of ["{nope", "[]", "null", "42", '"hello"', "{}"]) {
      expect(() => parse(bad, vp)).not.toThrow();
    }
    expect(parse("{nope", vp)).toEqual(DEFAULTS);
    expect(parse("[]", vp)).toEqual(DEFAULTS);
  });
  it("a future version falls back whole, rather than half-applying", () => {
    const future = JSON.stringify({ version: 9, railWidth: 400, inspectorVisible: false });
    expect(parse(future, vp)).toEqual(DEFAULTS);
  });
  it("a bad field falls back for that field only", () => {
    const mixed = JSON.stringify({ version: 1, railWidth: "abc", inspectorWidth: 380, railTab: "nope" });
    const got = parse(mixed, vp);
    expect(got.railWidth).toBe(RAIL_DEFAULT);
    expect(got.inspectorWidth).toBe(380);
    expect(got.railTab).toBe("sessions");
  });
  it("re-clamps a width that the current window cannot hold", () => {
    // At mid width the inspector is an overlay, so the rail may use the room; at wide it may not.
    const wide = JSON.stringify({ version: 1, railWidth: 900, inspectorVisible: true });
    expect(parse(wide, 1440).railWidth).toBeLessThanOrEqual(1440 - INSPECTOR_DEFAULT - CENTRE_MIN);
    expect(parse(wide, 1440).railWidth).toBeLessThan(900);
  });
  it("a tiny window yields the minimum, not a negative width", () => {
    const tiny = JSON.stringify({ version: 1, railWidth: 900 });
    expect(parse(tiny, 400).railWidth).toBe(RAIL_MIN);
  });
  it("an overlay panel does not constrain the column beside it", () => {
    // 900 px is mid: the inspector takes no column, so the rail may exceed what it would at wide.
    const midRail = clampWidth("rail", 9999, 900, at(900, { inspectorVisible: true }));
    expect(midRail).toBeGreaterThan(RAIL_MIN);
    expect(midRail).toBeLessThanOrEqual(Math.floor(900 * 0.4));
  });
  it("round-trips", () => {
    const l = at(1440, { railWidth: 320, inspectorWidth: 400, railVisible: false, railTab: "files" });
    expect(parse(serialize(l), 1440)).toEqual(l);
  });
});

describe("serialize carries geometry and a tab name — nothing from the workspace", () => {
  it("has exactly the six known keys", () => {
    expect(Object.keys(JSON.parse(serialize(DEFAULTS))).sort()).toEqual(
      ["inspectorVisible", "inspectorWidth", "railTab", "railVisible", "railWidth", "version"]);
  });
  it("contains no path, no user, no token", () => {
    const blob = serialize(at(1440, { railWidth: 333 }));
    expect(blob).not.toMatch(/Users|agent_scratch|token|dapi|@/);
  });
  it("reset equals the defaults", () => {
    expect(reset()).toEqual(DEFAULTS);
  });
});
