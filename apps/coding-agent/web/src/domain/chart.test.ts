import { describe, expect, it } from "vitest";
import {
  MAX_CATEGORIES, MAX_POINTS, MAX_SERIES, canChart, columnKinds, compact, defaultSpec, describe as say, model, niceTicks,
  scene, validSpec, type ChartSpec, type ChartTable,
} from "./chart";

const trips: ChartTable = {
  columns: ["period", "trips", "fare"], types: ["string", "int", "decimal"],
  rows: [["morning", "40", "80.00"], ["evening", "10", "12.50"], ["night", "5", "9.00"]],
};

describe("choosing what to chart", () => {
  it("reads column kinds from the engine's types, and from the values when there are none", () => {
    expect(columnKinds(trips)).toEqual(["text", "number", "number"]);
    expect(columnKinds({ columns: ["d", "n", "s"], types: ["date", "bigint", "string"], rows: [["2026-01-01", "1", "a"]] }))
      .toEqual(["time", "number", "text"]);
    expect(columnKinds({ columns: ["d", "n", "z"], rows: [["2026-01-01T10:00:00Z", "1", "02134"]] })).toEqual(["time", "number", "number"]);
  });
  it("does not call a zip code a number when the engine says it is a string", () => {
    expect(columnKinds({ columns: ["zip"], types: ["string"], rows: [["02134"]] })).toEqual(["text"]);
  });
  it("picks a category for x and a number for y, as a bar", () => {
    expect(defaultSpec(trips)).toEqual({ kind: "bar", x: 0, y: 1, group: null });
  });
  it("draws a line over time", () => {
    expect(defaultSpec({ columns: ["day", "n"], types: ["date", "int"], rows: [["2026-01-01", "1"], ["2026-01-02", "3"]] }))
      .toEqual({ kind: "line", x: 0, y: 1, group: null });
  });
  it("scatters two number columns", () => {
    expect(defaultSpec({ columns: ["a", "b"], types: ["int", "int"], rows: [["1", "2"]] })).toEqual({ kind: "scatter", x: 0, y: 1, group: null });
  });
  it.each([
    [{ columns: ["a", "b"], rows: [] }, "no rows"],
    [{ columns: ["a"], types: ["int"], rows: [["1"]] }, "needs a column for the x axis"],
    [{ columns: ["a", "b"], types: ["string", "string"], rows: [["x", "y"]] }, "column of numbers"],
  ] as [ChartTable, string][])("says why it cannot chart %#", (t, why) => {
    const c = canChart(t);
    expect(c.ok).toBe(false);
    expect(c.why).toContain(why);
    expect(defaultSpec(t)).toBeNull();
  });
  it("replaces a stored spec that does not fit this table", () => {
    const stale: ChartSpec = { kind: "bar", x: 0, y: 0, group: null };   // y is text now
    expect(validSpec(trips, stale)).toEqual(defaultSpec(trips));
    expect(validSpec(trips, { kind: "bar", x: 9, y: 1, group: null })).toEqual(defaultSpec(trips));
    expect(validSpec(trips, { kind: "line", x: 0, y: 2, group: null })).toEqual({ kind: "line", x: 0, y: 2, group: null });
    expect(validSpec(trips, { kind: "donut" as never, x: 0, y: 1, group: null })).toEqual(defaultSpec(trips));
  });
});

describe("the data behind a chart", () => {
  it("makes one series of categories", () => {
    const m = model(trips, { kind: "bar", x: 0, y: 1, group: null });
    expect(m.categories).toEqual(["morning", "evening", "night"]);
    expect(m.series).toHaveLength(1);
    expect(m.series[0].points.map((p) => [p.label, p.y])).toEqual([["morning", 40], ["evening", 10], ["night", 5]]);
    expect(m.notes).toEqual([]);
  });
  it("adds rows with the same category together, and says so", () => {
    const t = { ...trips, rows: [["a", "1", "0"], ["a", "2", "0"], ["b", "5", "0"]] };
    const m = model(t, { kind: "bar", x: 0, y: 1, group: null });
    expect(m.series[0].points.map((p) => p.y)).toEqual([3, 5]);
    expect(m.notes).toContain("Rows with the same x are added together.");
  });
  it("splits by a group column into series", () => {
    const t: ChartTable = { columns: ["month", "city", "n"], types: ["string", "string", "int"],
      rows: [["jan", "Oslo", "1"], ["jan", "Rome", "2"], ["feb", "Oslo", "3"]] };
    const m = model(t, { kind: "bar", x: 0, y: 2, group: 1 });
    expect(m.series.map((s) => s.name)).toEqual(["Oslo", "Rome"]);
    expect(m.series[1].points.map((p) => p.label)).toEqual(["jan"]);   // Rome has no feb: nothing is drawn, not a zero
  });
  it("drops what is not a number, counts it, and says so", () => {
    const t = { ...trips, rows: [["a", "1", "0"], ["b", "oops", "0"], ["c", null, "0"]] };
    const m = model(t, { kind: "bar", x: 0, y: 1, group: null });
    expect(m.series[0].points).toHaveLength(1);
    expect(m.notes[0]).toBe("2 rows were left out because its x or y was not a value the chart can draw.");
  });
  it("uses at most 1,000 rows, and says how many there were", () => {
    const rows = Array.from({ length: MAX_POINTS + 50 }, (_, i) => [String(i), String(i)] as (string | null)[]);
    const m = model({ columns: ["x", "y"], types: ["int", "int"], rows }, { kind: "scatter", x: 0, y: 1, group: null });
    expect(m.series[0].points).toHaveLength(MAX_POINTS);
    expect(m.notes[0]).toBe("Chart uses the first 1,000 of 1,050 rows.");
  });
  it("cuts categories and groups past the limits, and says so", () => {
    const many = Array.from({ length: MAX_CATEGORIES + 5 }, (_, i) => [`c${i}`, "1"] as (string | null)[]);
    const bars = model({ columns: ["k", "v"], types: ["string", "int"], rows: many }, { kind: "bar", x: 0, y: 1, group: null });
    expect(bars.categories).toHaveLength(MAX_CATEGORIES);
    expect(bars.notes.join(" ")).toContain(`first ${MAX_CATEGORIES} of ${MAX_CATEGORIES + 5} categories`);
    const groups = Array.from({ length: MAX_SERIES + 2 }, (_, i) => ["x", `g${i}`, "1"] as (string | null)[]);
    const g = model({ columns: ["x", "g", "v"], types: ["string", "string", "int"], rows: groups }, { kind: "bar", x: 0, y: 2, group: 1 });
    expect(g.series).toHaveLength(MAX_SERIES);
    expect(g.notes.join(" ")).toContain("2 more groups are not drawn");
  });
  it("sorts a line by x and reads time as time", () => {
    const t: ChartTable = { columns: ["d", "n"], types: ["date", "int"], rows: [["2026-01-03", "3"], ["2026-01-01", "1"], ["2026-01-02", "2"]] };
    const m = model(t, { kind: "line", x: 0, y: 1, group: null });
    expect(m.xKind).toBe("time");
    expect(m.series[0].points.map((p) => p.y)).toEqual([1, 2, 3]);
  });
  it("keeps the order of a scatter", () => {
    const t: ChartTable = { columns: ["a", "b"], types: ["int", "int"], rows: [["3", "1"], ["1", "2"]] };
    expect(model(t, { kind: "scatter", x: 0, y: 1, group: null }).series[0].points.map((p) => p.x)).toEqual([3, 1]);
  });
  it("folds a pie into slices, the biggest first, small ones into Other, and drops zero or negative", () => {
    const rows = Array.from({ length: 15 }, (_, i) => [`s${i}`, String(100 - i)] as (string | null)[]);
    rows.push(["neg", "-5"], ["zero", "0"]);
    const m = model({ columns: ["k", "v"], types: ["string", "int"], rows }, { kind: "pie", x: 0, y: 1, group: null });
    expect(m.series[0].points).toHaveLength(13);
    expect(m.series[0].points.at(-1)?.label).toBe("Other");
    expect(m.series[0].points[0].y).toBe(100);
    expect(m.notes.join(" ")).toContain("2 slices are left out");
    expect(m.notes.join(" ")).toContain("drawn together as Other");
  });
  it("says in one sentence what is charted", () => {
    expect(say(model(trips, { kind: "bar", x: 0, y: 1, group: null }))).toBe("Bar chart of trips by period: 3 points.");
  });
});

describe("the geometry", () => {
  it("puts nice numbers on the axis", () => {
    expect(niceTicks(0, 100)).toEqual([0, 20, 40, 60, 80, 100]);
    expect(niceTicks(0, 7)).toEqual([0, 2, 4, 6, 8]);
    expect(niceTicks(-3, 3)).toEqual([-4, -2, 0, 2, 4]);
    expect(niceTicks(5, 5).length).toBeGreaterThan(1);
    expect(niceTicks(NaN, 1)).toEqual([0]);
  });
  it("always covers the data, so no mark falls outside the axis", () => {
    for (const [lo, hi] of [[0, 7], [0.3, 0.71], [-13, 94], [1000, 1003], [0, 1e9], [-1e-6, 3e-6], [2, 2], [99.9, 100]]) {
      const t = niceTicks(lo, hi);
      expect(t[0], `${lo}..${hi}`).toBeLessThanOrEqual(lo);
      expect(t[t.length - 1], `${lo}..${hi}`).toBeGreaterThanOrEqual(hi);
      expect(t.length).toBeGreaterThan(1);
    }
  });
  it("writes large numbers compactly and small ones whole", () => {
    expect([compact(12), compact(15_000), compact(2_500_000), compact(3e9), compact(0.125)]).toEqual(["12", "15k", "2.5M", "3B", "0.13"]);
  });
  it("draws a bar as tall as its value, from zero", () => {
    const s = scene(model(trips, { kind: "bar", x: 0, y: 1, group: null }));
    const rects = s.marks.filter((m) => m.t === "rect");
    expect(rects).toHaveLength(3);
    const [a, b, c] = rects as { h: number; y: number }[];
    expect(a.h).toBeGreaterThan(b.h);
    expect(b.h).toBeGreaterThan(c.h);
    expect(a.h / b.h).toBeCloseTo(4, 0);
    expect(a.y + a.h).toBeCloseTo(b.y + b.h, 5);                 // they stand on one line
    expect(s.xTicks.map((t) => t.label)).toEqual(["morning", "evening", "night"]);
    expect(s.legend).toEqual([]);
  });
  it("draws negative bars below the zero line", () => {
    const t = { ...trips, rows: [["a", "5", "0"], ["b", "-5", "0"]] };
    const [up, down] = scene(model(t, { kind: "bar", x: 0, y: 1, group: null })).marks as { y: number; h: number }[];
    expect(down.y).toBeCloseTo(up.y + up.h, 5);
  });
  it("keeps every mark inside the plot", () => {
    const rows = Array.from({ length: 50 }, (_, i) => [String(i), String(Math.sin(i) * 100)] as (string | null)[]);
    const s = scene(model({ columns: ["x", "y"], types: ["int", "double"], rows }, { kind: "scatter", x: 0, y: 1, group: null }));
    for (const m of s.marks) {
      if (m.t !== "dot") continue;
      expect(m.x).toBeGreaterThanOrEqual(s.plot.x - 0.01);
      expect(m.x).toBeLessThanOrEqual(s.plot.x + s.plot.w + 0.01);
      expect(m.y).toBeGreaterThanOrEqual(s.plot.y - 0.01);
      expect(m.y).toBeLessThanOrEqual(s.plot.y + s.plot.h + 0.01);
    }
  });
  it("draws a line as one path, an area as a closed one under it", () => {
    const t: ChartTable = { columns: ["d", "n"], types: ["date", "int"], rows: [["2026-01-01", "1"], ["2026-01-02", "3"], ["2026-01-03", "2"]] };
    const line = scene(model(t, { kind: "line", x: 0, y: 1, group: null })).marks;
    expect(line.filter((m) => m.t === "path")).toHaveLength(1);
    const area = scene(model(t, { kind: "area", x: 0, y: 1, group: null })).marks.filter((m) => m.t === "path") as { d: string; area: boolean }[];
    expect(area.map((p) => p.area)).toEqual([true, false]);
    expect(area[0].d.endsWith("Z")).toBe(true);
  });
  it("labels a time axis with dates", () => {
    const t: ChartTable = { columns: ["d", "n"], types: ["date", "int"], rows: [["2026-01-01", "1"], ["2026-01-09", "3"]] };
    expect(scene(model(t, { kind: "line", x: 0, y: 1, group: null })).xTicks[0].label).toBe("2026-01-01");
  });
  it("gives each series a legend entry only when there is more than one", () => {
    const t: ChartTable = { columns: ["m", "c", "n"], types: ["string", "string", "int"], rows: [["j", "A", "1"], ["j", "B", "2"]] };
    expect(scene(model(t, { kind: "bar", x: 0, y: 2, group: 1 })).legend.map((l) => l.name)).toEqual(["A", "B"]);
  });
  it("splits a pie by value and lists the share of each slice", () => {
    const s = scene(model(trips, { kind: "pie", x: 0, y: 1, group: null }));
    expect(s.marks.filter((m) => m.t === "slice")).toHaveLength(3);
    expect(s.legend[0]).toEqual({ name: "morning", series: 0, detail: "40 · 72.7%" });
  });
  it("draws a pie of one slice as a whole circle", () => {
    const s = scene(model({ ...trips, rows: [["only", "1", "0"]] }, { kind: "pie", x: 0, y: 1, group: null }));
    expect((s.marks[0] as { d: string }).d).toContain("a");
    expect(s.marks).toHaveLength(1);
  });
  it("says it is empty when nothing could be drawn", () => {
    const t = { ...trips, rows: [["a", "x", "y"]] };
    expect(scene(model(t, { kind: "bar", x: 0, y: 1, group: null })).empty).toBe(true);
  });
});
