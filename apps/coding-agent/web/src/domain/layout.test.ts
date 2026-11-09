import { describe, expect, it } from "vitest";
import {
  ASSISTANT_COLUMN_MIN, ASSISTANT_DEFAULT, ASSISTANT_MAX, ASSISTANT_MIN, CENTRE_MIN, DEFAULTS, INSPECTOR_DEFAULT, drawerWidth,
  INSPECTOR_MAX, INSPECTOR_MIN, KEY_STEP, KEY_STEP_COARSE, RAIL_DEFAULT, RAIL_MIN, clampWidth,
  columns, defaultWidth, describe as describeZone, minWidth, modeFor, parse, reset, resetZone, resizeBy,
  serialize, takesColumn, type Layout, bounds, maxWidth, reclamp, withWidth,
} from "./layout";

const at = (_w: number, extra: Partial<Layout> = {}): Layout => ({ ...DEFAULTS, inspectorVisible: true, ...extra });

describe("mode", () => {
  it("opens Context on demand so the first editor has room", () => { expect(DEFAULTS.inspectorVisible).toBe(false); });
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
  it("all four columns when the window can hold them", () => {
    // 1600 is above ASSISTANT_COLUMN_MIN (1476), so the inspector keeps its column beside the dock.
    expect(columns(at(1600), 1600)).toBe(
      `${RAIL_DEFAULT}px minmax(0, 1fr) ${INSPECTOR_DEFAULT}px ${ASSISTANT_DEFAULT}px`);
  });
  it("below ASSISTANT_COLUMN_MIN the inspector yields to the conversation", () => {
    // 1440 is wid but too narrow for all three: the dock keeps its column, the inspector overlays.
    expect(columns(at(1440), 1440)).toBe(
      `${RAIL_DEFAULT}px minmax(0, 1fr) ${ASSISTANT_DEFAULT}px`);
    expect(takesColumn("inspector", at(1440), 1440)).toBe(false);
    expect(takesColumn("assistant", at(1440), 1440)).toBe(true);
  });
  it("two columns when a zone is hidden", () => {
    expect(columns(at(1440, { railVisible: false, assistantVisible: false }), 1440))
      .toBe(`minmax(0, 1fr) ${INSPECTOR_DEFAULT}px`);
    expect(columns(at(1440, { inspectorVisible: false, assistantVisible: false }), 1440))
      .toBe(`${RAIL_DEFAULT}px minmax(0, 1fr)`);
  });
  it("one column when all are hidden", () => {
    expect(columns(at(1440, { railVisible: false, inspectorVisible: false, assistantVisible: false }), 1440))
      .toBe("minmax(0, 1fr)");
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

describe("the assistant zone (006)", () => {
  it("takes a column as soon as a column fits — an overlay covers the work", () => {
    // 1138 = rail 276 + centre 480 + dock 380 + the two 1px gaps. Above it, a column; below, an overlay.
    expect(takesColumn("assistant", at(1600), 1600)).toBe(true);
    expect(takesColumn("assistant", at(1180), 1180)).toBe(true);
    expect(takesColumn("assistant", at(ASSISTANT_COLUMN_MIN), ASSISTANT_COLUMN_MIN)).toBe(true);
    expect(takesColumn("assistant", at(ASSISTANT_COLUMN_MIN - 1), ASSISTANT_COLUMN_MIN - 1)).toBe(false);
    expect(takesColumn("assistant", at(900), 900)).toBe(false);
  });
  it("the inspector yields to the dock, so a run control is never covered", () => {
    // The defect this encodes: at 1180 the dock was an overlay and covered a cell's run button at
    // x=1042. A column shrinks the editor instead of covering it.
    expect(takesColumn("inspector", at(1180), 1180)).toBe(false);
    expect(takesColumn("inspector", at(1440), 1440)).toBe(false);
    expect(takesColumn("inspector", at(1600), 1600)).toBe(true);
    expect(columns(at(1180), 1180)).toBe(`${RAIL_DEFAULT}px minmax(0, 1fr) ${ASSISTANT_DEFAULT}px`);
  });
  it("is clamped to its own bounds, which are wider than the inspector's", () => {
    expect(clampWidth("assistant", 9999, 4000, at(4000))).toBe(ASSISTANT_MAX);
    expect(clampWidth("assistant", 10, 1440)).toBe(ASSISTANT_MIN);
    expect(ASSISTANT_MIN).toBeGreaterThan(INSPECTOR_MIN);
  });
  it("never pushes the centre below CENTRE_MIN, whatever the widths or the window", () => {
    // The case that matters: every zone dragged to its maximum, at every width from small to huge.
    for (const v of [821, 900, 1180, 1181, 1280, 1440, 1600, 1920, 2560, 3200]) {
      for (const widths of [{}, { railWidth: 9999, inspectorWidth: 9999, assistantWidth: 9999 }]) {
        const wide = at(v, widths);
        const parts = columns(wide, v).split(" ").filter((p) => p.endsWith("px"));
        const used = parts.reduce((sum, p) => sum + parseInt(p, 10), 0);
        expect(used, `viewport ${v} with ${JSON.stringify(widths)}`).toBeLessThanOrEqual(v - CENTRE_MIN);
      }
    }
  });
  /* The gap is 1px and there are (tracks − 1) of them, so an arithmetic that only sums the explicit
     tracks is off by up to 3px — which is how a 1180 px window produced `276 261 380 260`: the drawer's
     own minimum was treated as a floor and the centre paid for it. Counted here, per combination,
     because "close enough" is how a 261 px centre passed a test that only summed the px tracks.
     Note `minmax(0, 1fr)` contains a space, so tracks are counted, not split on whitespace. */
  const tracksOf = (s: string): string[] => s.match(/minmax\(0, 1fr\)|[^\s]+px/g) ?? [];
  it("reserves CENTRE_MIN with the grid gaps counted, in every combination", () => {
    for (const v of [821, 900, 1024, 1136, 1180, 1181, 1400, 1476, 1600, 1920, 2560]) {
      for (const flag of [true, false]) {
        for (const drawer of [true, false]) {
          const layout = at(v, { railVisible: flag, assistantVisible: flag, inspectorVisible: flag });
          const tracks = tracksOf(columns(layout, v, false, drawer));
          const fixed = tracks.filter((t) => t.endsWith("px")).reduce((s, t) => s + parseInt(t, 10), 0);
          expect(fixed + (tracks.length - 1), `v=${v} rail/dock=${flag} drawer=${drawer} → ${tracks.join(" ")}`)
            .toBeLessThanOrEqual(v - CENTRE_MIN);
        }
      }
    }
  });
  /* A track and a child are the same decision. `columns()` emitting N tracks while the markup renders
     N+1 children is not a cosmetic bug: the extra child flows onto an implicit second row, so at 1480
     and 1600 the assistant rendered *under the navigator*, 276 px wide instead of 380. Every zone that
     takes a column gets exactly one track, and no zone that does not gets one either. */
  it("emits exactly one track per zone that takes a column", () => {
    for (const v of [800, 900, 1024, 1136, 1180, 1400, 1476, 1600, 1920]) {
      for (const drawer of [true, false]) {
        const layout = at(v);
        const zones = (["rail", "inspector", "assistant"] as const)
          .filter((z) => takesColumn(z, layout, v)).length;
        /* The drawer is only a track when it is asked for, it fits, AND the inspector is not already a
           column — one panel, one track. The centre takes its track unconditionally, including in
           `narrow`, where the rail is hidden but the work area is still a column of its own. */
        const drawerTrack = drawer && !takesColumn("inspector", layout, v) && drawerWidth(layout, v) !== null;
        const drawn = 1 + zones + (drawerTrack ? 1 : 0);
        expect(tracksOf(columns(layout, v, false, drawer)).length, `v=${v} drawer=${drawer}`).toBe(drawn);
      }
    }
  });
  it("a drawer that would starve the centre is not a track at all", () => {
    // 1180: rail 276 + dock 380 + gaps leave 519, and CENTRE_MIN is 480 — 39 px is not an inspector.
    const roomy = at(1180);
    expect(drawerWidth(roomy, 1180)).toBeNull();
    // Wide enough for all four: it is a real track, and still not so wide that the centre suffers.
    const wide = drawerWidth(at(1600), 1600);
    expect(wide).toBeGreaterThanOrEqual(INSPECTOR_MIN);
    expect(wide).toBeLessThanOrEqual(INSPECTOR_DEFAULT);
  });
  it("a hidden zone frees its space for the others", () => {
    const v = 1600;
    const withAll = clampWidth("assistant", 9999, v, at(v));
    const withoutInspector = clampWidth("assistant", 9999, v, at(v, { inspectorVisible: false }));
    expect(withoutInspector).toBeGreaterThanOrEqual(withAll);
    // And the other way: the inspector stops constraining the dock once it has yielded its column.
    const narrow = 1440;
    expect(clampWidth("assistant", 9999, narrow, at(narrow)))
      .toBe(clampWidth("assistant", 9999, narrow, at(narrow, { inspectorVisible: false })));
  });
  it("resizes and resets like every other zone", () => {
    const grown = resizeBy("assistant", at(1600), 1600, 40);
    expect(grown.assistantWidth).toBe(ASSISTANT_DEFAULT + 40);
    expect(grown.railWidth).toBe(RAIL_DEFAULT);
    expect(resetZone("assistant", grown).assistantWidth).toBe(ASSISTANT_DEFAULT);
    expect(describeZone("assistant", grown).label).toBe("Resize the assistant");
  });
});


describe("resize and reset", () => {
  it("moves by the delta and clamps at both ends", () => {
    const wide = resizeBy("rail", at(1440), 1440, 40);
    expect(wide.railWidth).toBe(RAIL_DEFAULT + 40);
    expect(resizeBy("rail", at(1440), 1440, -9999).railWidth).toBe(RAIL_MIN);
  });
  it("resizes one zone without touching the others", () => {
    const next = resizeBy("inspector", at(1600), 1600, 20);
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
    const mixed = JSON.stringify({ version: 1, railWidth: "abc", assistantWidth: 420, railTab: "nope" });
    const got = parse(mixed, 1600);
    expect(got.railWidth).toBe(RAIL_DEFAULT);
    expect(got.assistantWidth).toBe(420);
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
    // 1920, because 1600 cannot hold a 320 rail beside a 400 inspector and a 420 dock: the parser
    // would clamp it, correctly, and a round-trip test would be measuring the clamp, not the format.
    const l = at(1920, { railWidth: 320, inspectorWidth: 400, assistantWidth: 420, railVisible: false, railTab: "files" });
    expect(parse(serialize(l), 1920)).toEqual(l);
  });
});

describe("serialize carries geometry and a tab name — nothing from the workspace", () => {
  it("has exactly the eight known keys", () => {
    expect(Object.keys(JSON.parse(serialize(DEFAULTS))).sort()).toEqual(
      ["assistantVisible", "assistantWidth", "inspectorVisible", "inspectorWidth", "railTab",
        "railVisible", "railWidth", "version"]);
  });
  it("upgrades a v1 blob rather than discarding it", () => {
    // At 1600 all three columns fit, so the stored widths are the ones that survive.
    const v1 = JSON.stringify({ version: 1, railWidth: 320, inspectorWidth: 300, railTab: "files" });
    const got = parse(v1, 1600);
    expect(got.railWidth).toBe(320);
    expect(got.inspectorWidth).toBe(300);
    expect(got.railTab).toBe("files");
    // A v1 blob has no opinion about the dock, and the dock's default is open.
    expect(got.assistantVisible).toBe(true);
    expect(got.assistantWidth).toBe(ASSISTANT_DEFAULT);
  });
  it("contains no path, no user, no token", () => {
    const blob = serialize(at(1440, { railWidth: 333 }));
    expect(blob).not.toMatch(/Users|agent_scratch|token|dapi|@/);
  });
  it("reset equals the defaults", () => {
    expect(reset()).toEqual(DEFAULTS);
  });
});

describe("withWidth — every zone writes its own field", () => {
  const wide = 1600;
  it.each([
    ["rail", "railWidth", 330], ["inspector", "inspectorWidth", 400], ["assistant", "assistantWidth", 500],
  ] as const)("%s", (zone, field, px) => {
    const next = withWidth(zone, reset(), px, wide);
    expect(next[field]).toBe(px);
    // and no other width moved
    for (const other of ["railWidth", "inspectorWidth", "assistantWidth"] as const) {
      if (other !== field) expect(next[other]).toBe(reset()[other]);
    }
  });

  // The bug: dragging the dock's separator changed the inspector, which is hidden at 1136–1476 px,
  // so "it is impossible to resize the right panel".
  it("dragging the assistant never touches the inspector", () => {
    const l = withWidth("assistant", reset(), 520, 1300);
    expect(l.assistantWidth).toBe(520);
    expect(l.inspectorWidth).toBe(reset().inspectorWidth);
  });

  it("the assistant can widen to its cap and narrow to its minimum, and no further", () => {
    const two = { ...reset(), inspectorVisible: false };
    expect(withWidth("assistant", two, 9999, wide).assistantWidth).toBe(560);
    expect(withWidth("assistant", two, 10, wide).assistantWidth).toBe(320);
    // with the inspector also a column the arithmetic is tighter: 1600 - 276 - 340 - 480
    expect(withWidth("assistant", { ...reset(), inspectorVisible: true }, 9999, wide).assistantWidth).toBe(504);
  });

  it("the centre keeps its minimum when the dock is dragged wide in a small window", () => {
    const l = withWidth("assistant", reset(), 560, 1200);
    expect(1200 - l.railWidth - l.assistantWidth).toBeGreaterThanOrEqual(480);
  });

  it("reclamp brings all three zones back inside a smaller window", () => {
    const big = { ...reset(), railWidth: 500, inspectorWidth: 500, assistantWidth: 560 };
    const small = reclamp(big, 1200);
    expect(small.assistantWidth).toBeLessThanOrEqual(maxWidth("assistant", small, 1200));
    expect(small.assistantWidth).toBeGreaterThanOrEqual(320);
  });

  it("bounds reports the limit that applies in this window", () => {
    expect(bounds("assistant", { ...reset(), inspectorVisible: false }, wide)).toEqual({ min: 320, max: 560 });
    expect(bounds("assistant", { ...reset(), inspectorVisible: true }, wide)).toEqual({ min: 320, max: 504 });
  });
});
