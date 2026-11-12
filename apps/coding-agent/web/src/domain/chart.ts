/**
 * A chart of a result table, drawn as SVG with no library.
 *
 * Everything here is pure: the data model (`model`), the geometry (`scene`) and the choices
 * (`defaultSpec`, `canChart`) are functions of the table, so they are tested without a DOM. The component
 * only turns a `Scene` into elements.
 *
 * What it will and will not do, in words, because a chart that silently drops rows is a wrong chart:
 *  - at most 1,000 rows are used, and the note says so when there were more;
 *  - values that are not numbers are dropped and counted;
 *  - rows with the same category are ADDED together (a bar of a sum), and the note says so;
 *  - more than 8 groups or 60 categories are cut, and the note says how many.
 */
import { numericColumns } from "./cellrun";

export type ChartKind = "bar" | "line" | "area" | "scatter" | "pie";
export const CHART_KINDS: { kind: ChartKind; label: string }[] = [
  { kind: "bar", label: "Bar" }, { kind: "line", label: "Line" }, { kind: "area", label: "Area" },
  { kind: "scatter", label: "Scatter" }, { kind: "pie", label: "Pie" },
];

export interface ChartSpec {
  kind: ChartKind;
  /** Column index for the x axis (or the slices of a pie). */
  x: number;
  /** Column index for the y axis (or the size of a slice). A number column. */
  y: number;
  /** Column index that splits the data into series, or null. */
  group: number | null;
}

/** What a result table shows: the table, or a chart of it. Stored with the result. */
export interface TableView { mode: "table" | "chart"; spec?: ChartSpec }

export interface ChartTable {
  columns: readonly string[];
  rows: readonly (string | null)[][];
  types?: readonly string[];
}

export const MAX_POINTS = 1000;
export const MAX_SERIES = 8;
export const MAX_CATEGORIES = 60;
export const MAX_SLICES = 12;

export type ColKind = "number" | "time" | "text";

const TIME_TYPES = ["date", "timestamp", "timestamp_ntz", "timestamp_ltz"];

export function toNumber(v: string | null | undefined): number | null {
  if (v === null || v === undefined) return null;
  const t = v.trim();
  if (!t) return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}

export function toTime(v: string | null | undefined): number | null {
  if (v === null || v === undefined || !/^\d{4}-\d{2}-\d{2}/.test(v.trim())) return null;
  const ms = Date.parse(v.trim());
  return Number.isNaN(ms) ? null : ms;
}

/** Number, time or text, from the engine's type when it gave one and from the values when it did not. */
export function columnKinds(t: ChartTable): ColKind[] {
  const numeric = numericColumns(t.columns, t.rows, t.types);
  return t.columns.map((_, c) => {
    const type = t.types?.[c]?.toLowerCase();
    if (type) {
      if (numeric[c]) return "number";
      return TIME_TYPES.includes(type) ? "time" : "text";
    }
    if (numeric[c]) return "number";
    const seen = t.rows.map((r) => r[c]).filter((v): v is string => v !== null && v !== undefined && v !== "");
    return seen.length > 0 && seen.every((v) => toTime(v) !== null) ? "time" : "text";
  });
}

/** Whether a chart makes sense for this table, and if not, why (shown as the button's reason). */
export function canChart(t: ChartTable): { ok: boolean; why: string } {
  if (t.rows.length === 0) return { ok: false, why: "There are no rows to chart" };
  if (t.columns.length < 2) return { ok: false, why: "A chart needs a column for the x axis and a number column" };
  if (!columnKinds(t).includes("number")) return { ok: false, why: "A chart needs a column of numbers" };
  return { ok: true, why: "" };
}

export function defaultSpec(t: ChartTable): ChartSpec | null {
  if (!canChart(t).ok) return null;
  const kinds = columnKinds(t);
  let x = kinds.indexOf("time");
  if (x < 0) x = kinds.indexOf("text");
  if (x < 0) x = 0;
  const y = kinds.findIndex((k, i) => k === "number" && i !== x);
  if (y < 0) return null;
  const kind: ChartKind = kinds[x] === "time" ? "line" : kinds[x] === "number" ? "scatter" : "bar";
  return { kind, x, y, group: null };
}

/** A spec that no longer fits the table (a stored one, a different run) is replaced by the default. */
export function validSpec(t: ChartTable, spec: ChartSpec | undefined): ChartSpec | null {
  if (!spec) return defaultSpec(t);
  const n = t.columns.length;
  const kinds = columnKinds(t);
  const inRange = (c: number | null) => c === null || (Number.isInteger(c) && c >= 0 && c < n);
  const fine = inRange(spec.x) && inRange(spec.y) && inRange(spec.group) && kinds[spec.y] === "number"
    && CHART_KINDS.some((k) => k.kind === spec.kind);
  return fine ? spec : defaultSpec(t);
}

/* ---- the data ----------------------------------------------------------------------------------- */

export interface Point { x: number; label: string; y: number }
export interface Series { name: string; points: Point[] }
export interface Model {
  kind: ChartKind;
  /** band: the x values are categories, drawn evenly; linear and time: they are numbers on a scale. */
  xKind: "band" | "linear" | "time";
  categories: string[];
  series: Series[];
  /** Sentences that say what was left out or added together. */
  notes: string[];
  xName: string;
  yName: string;
}

const plural = (n: number, one: string, many: string) => `${n.toLocaleString("en-US")} ${n === 1 ? one : many}`;

export function model(t: ChartTable, spec: ChartSpec): Model {
  const kinds = columnKinds(t);
  const notes: string[] = [];
  let rows = t.rows;
  if (rows.length > MAX_POINTS) {
    notes.push(`Chart uses the first ${MAX_POINTS.toLocaleString("en-US")} of ${rows.length.toLocaleString("en-US")} rows.`);
    rows = rows.slice(0, MAX_POINTS);
  }
  const xKind: Model["xKind"] = spec.kind === "bar" || spec.kind === "pie" || kinds[spec.x] === "text"
    ? "band" : kinds[spec.x] === "time" ? "time" : "linear";
  const xName = t.columns[spec.x] ?? "";
  const yName = t.columns[spec.y] ?? "";

  let dropped = 0;
  const groups = new Map<string, { x: string; xv: number; y: number }[]>();
  for (const r of rows) {
    const y = toNumber(r[spec.y]);
    const raw = r[spec.x];
    const xv = xKind === "time" ? toTime(raw) : xKind === "linear" ? toNumber(raw) : 0;
    if (y === null || xv === null || (xKind === "band" && (raw === undefined))) { dropped += 1; continue; }
    const name = spec.group === null ? yName : (r[spec.group] ?? "null");
    const list = groups.get(name) ?? [];
    list.push({ x: raw === null || raw === undefined ? "null" : raw, xv, y });
    groups.set(name, list);
  }
  if (dropped > 0) notes.push(`${plural(dropped, "row was", "rows were")} left out because its x or y was not a value the chart can draw.`);

  let names = [...groups.keys()];
  if (names.length > MAX_SERIES) {
    notes.push(`${plural(names.length - MAX_SERIES, "more group is", "more groups are")} not drawn (the limit is ${MAX_SERIES}).`);
    names = names.slice(0, MAX_SERIES);
  }

  if (xKind === "band") {
    let categories: string[] = [];
    const seen = new Set<string>();
    for (const n of names) for (const p of groups.get(n) ?? []) if (!seen.has(p.x)) { seen.add(p.x); categories.push(p.x); }
    const limit = spec.kind === "pie" ? MAX_SLICES : MAX_CATEGORIES;
    let added = false;
    const series = names.map((name) => {
      const sums = new Map<string, number>();
      for (const p of groups.get(name) ?? []) {
        if (sums.has(p.x)) added = true;
        sums.set(p.x, (sums.get(p.x) ?? 0) + p.y);
      }
      return { name, sums };
    });
    if (added) notes.push("Rows with the same x are added together.");
    if (spec.kind === "pie") {
      // One ring: every series is folded into it, the biggest slices first, and the rest become "Other".
      const total = new Map<string, number>();
      for (const s of series) for (const [k, v] of s.sums) total.set(k, (total.get(k) ?? 0) + v);
      const sliced = [...total.entries()].filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]);
      if (sliced.length < total.size) notes.push(`${plural(total.size - sliced.length, "slice is", "slices are")} left out because its value is zero or negative.`);
      const keep = sliced.slice(0, limit);
      const rest = sliced.slice(limit).reduce((a, [, v]) => a + v, 0);
      if (rest > 0) { keep.push(["Other", rest]); notes.push(`The smallest ${sliced.length - limit} slices are drawn together as Other.`); }
      categories = keep.map(([k]) => k);
      return { kind: spec.kind, xKind, categories, notes, xName, yName,
        series: [{ name: yName, points: keep.map(([k, v], i) => ({ x: i, label: k, y: v })) }] };
    }
    if (categories.length > limit) {
      notes.push(`Only the first ${limit} of ${categories.length.toLocaleString("en-US")} categories are drawn.`);
      categories = categories.slice(0, limit);
    }
    const index = new Map(categories.map((c, i) => [c, i]));
    return { kind: spec.kind, xKind, categories, notes, xName, yName, series: series.map((s) => ({
      name: s.name,
      points: categories.filter((c) => s.sums.has(c)).map((c) => ({ x: index.get(c) ?? 0, label: c, y: s.sums.get(c) ?? 0 })),
    })) };
  }

  const sortIt = spec.kind === "line" || spec.kind === "area";
  return { kind: spec.kind, xKind, categories: [], notes, xName, yName, series: names.map((name) => {
    const pts = (groups.get(name) ?? []).map((p) => ({ x: p.xv, label: p.x, y: p.y }));
    return { name, points: sortIt ? pts.sort((a, b) => a.x - b.x) : pts };
  }) };
}

/* ---- the geometry ------------------------------------------------------------------------------- */

export type Mark =
  | { t: "rect"; x: number; y: number; w: number; h: number; series: number; title: string }
  | { t: "path"; d: string; series: number; area: boolean }
  | { t: "dot"; x: number; y: number; r: number; series: number; title: string }
  | { t: "slice"; d: string; series: number; title: string };

export interface Scene {
  width: number;
  height: number;
  plot: { x: number; y: number; w: number; h: number };
  marks: Mark[];
  xTicks: { at: number; label: string; full: string }[];
  yTicks: { at: number; label: string }[];
  /** What each colour is: a series, or a pie slice. */
  legend: { name: string; series: number; detail?: string }[];
  empty: boolean;
}

export const WIDTH = 640;
export const HEIGHT = 300;
const M = { left: 56, right: 14, top: 12, bottom: 38 };

/** Round numbers to put ticks on: 1, 2, 5 times a power of ten. */
export function niceTicks(lo: number, hi: number, count = 5): number[] {
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return [0];
  if (lo === hi) { const d = lo === 0 ? 1 : Math.abs(lo) * 0.1; lo -= d; hi += d; }
  const raw = (hi - lo) / Math.max(1, count);
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? 10 * mag;
  const start = Math.floor(lo / step) * step;
  const out: number[] = [];
  // The last tick is at or past `hi`, so the axis always covers the data.
  for (let v = start; out.length < 50; v += step) {
    out.push(Math.round(v / step) * step);
    if (v >= hi - step * 1e-9) break;
  }
  return out;
}

export function compact(n: number): string {
  const a = Math.abs(n);
  if (a >= 1e9) return `${+(n / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${+(n / 1e6).toFixed(2)}M`;
  if (a >= 1e4) return `${+(n / 1e3).toFixed(1)}k`;
  return n.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

const dayOf = (ms: number) => new Date(ms).toISOString().slice(0, 10);
const timeOf = (ms: number) => new Date(ms).toISOString().slice(0, 16).replace("T", " ");
const short = (s: string, n = 12) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

export function scene(m: Model, width = WIDTH, height = HEIGHT): Scene {
  const empty = m.series.every((s) => s.points.length === 0);
  const base: Scene = { width, height, plot: { x: M.left, y: M.top, w: width - M.left - M.right, h: height - M.top - M.bottom },
    marks: [], xTicks: [], yTicks: [], legend: [], empty };
  if (empty) return base;
  if (m.kind === "pie") return pie(m, base);

  const { plot } = base;
  const ys = m.series.flatMap((s) => s.points.map((p) => p.y));
  let lo = Math.min(...ys);
  let hi = Math.max(...ys);
  if (m.kind === "bar" || m.kind === "area") { lo = Math.min(lo, 0); hi = Math.max(hi, 0); }
  const yt = niceTicks(lo, hi);
  const y0 = yt[0];
  const y1 = yt[yt.length - 1];
  const sy = (v: number) => plot.y + plot.h - ((v - y0) / (y1 - y0 || 1)) * plot.h;
  base.yTicks = yt.map((v) => ({ at: sy(v), label: compact(v) }));
  base.legend = m.series.length > 1 ? m.series.map((s, i) => ({ name: s.name, series: i })) : [];

  let sx: (p: Point) => number;
  if (m.xKind === "band") {
    const n = Math.max(1, m.categories.length);
    const bw = plot.w / n;
    sx = (p) => plot.x + bw * (p.x + 0.5);
    const every = Math.ceil(n / 12);
    base.xTicks = m.categories.map((c, i) => ({ at: plot.x + bw * (i + 0.5), label: short(c), full: c })).filter((_, i) => i % every === 0);
    if (m.kind === "bar") {
      const k = m.series.length;
      const inner = (bw * 0.8) / k;
      m.series.forEach((s, si) => s.points.forEach((p) => {
        const top = sy(Math.max(p.y, 0));
        const bottom = sy(Math.min(p.y, 0));
        base.marks.push({ t: "rect", x: plot.x + bw * p.x + bw * 0.1 + inner * si, y: top, w: Math.max(1, inner - 1), h: Math.max(0.5, bottom - top),
          series: si, title: `${m.series.length > 1 ? `${s.name} · ` : ""}${p.label}: ${compact(p.y)}` });
      }));
      return base;
    }
  } else {
    const xs = m.series.flatMap((s) => s.points.map((p) => p.x));
    let xlo = Math.min(...xs);
    let xhi = Math.max(...xs);
    if (xlo === xhi) { xlo -= 1; xhi += 1; }
    const sxv = (v: number) => plot.x + ((v - xlo) / (xhi - xlo)) * plot.w;
    sx = (p) => sxv(p.x);
    if (m.xKind === "time") {
      const span = xhi - xlo;
      const fmt = span < 2 * 86_400_000 ? timeOf : dayOf;
      base.xTicks = [0, 1, 2, 3, 4].map((i) => xlo + (span * i) / 4).map((v) => ({ at: sxv(v), label: fmt(v), full: fmt(v) }));
    } else {
      base.xTicks = niceTicks(xlo, xhi).filter((v) => v >= xlo - 1e-9 && v <= xhi + 1e-9).map((v) => ({ at: sxv(v), label: compact(v), full: String(v) }));
    }
  }

  m.series.forEach((s, si) => {
    if (m.kind === "scatter") {
      for (const p of s.points) base.marks.push({ t: "dot", x: sx(p), y: sy(p.y), r: 3.2, series: si, title: `${s.name} · ${p.label}: ${compact(p.y)}` });
      return;
    }
    const pts = s.points.map((p) => [sx(p), sy(p.y)] as const);
    if (pts.length === 0) return;
    const line = pts.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
    if (m.kind === "area") {
      const floor = sy(Math.max(y0, Math.min(0, y1)));
      base.marks.push({ t: "path", area: true, series: si,
        d: `${line} L${pts[pts.length - 1][0].toFixed(1)},${floor.toFixed(1)} L${pts[0][0].toFixed(1)},${floor.toFixed(1)} Z` });
    }
    base.marks.push({ t: "path", area: false, d: line, series: si });
    if (pts.length <= 60) s.points.forEach((p, i) => base.marks.push({ t: "dot", x: pts[i][0], y: pts[i][1], r: 2.4, series: si, title: `${s.name} · ${p.label}: ${compact(p.y)}` }));
  });
  return base;
}

function pie(m: Model, base: Scene): Scene {
  const pts = m.series[0].points;
  const total = pts.reduce((a, p) => a + p.y, 0);
  const cx = base.width / 2;
  const cy = base.height / 2;
  const r = Math.min(base.plot.w, base.plot.h) / 2 - 4;
  let angle = -Math.PI / 2;
  pts.forEach((p, i) => {
    const sweep = (p.y / total) * Math.PI * 2;
    const a1 = angle + sweep;
    const pct = `${((p.y / total) * 100).toFixed(1)}%`;
    base.legend.push({ name: p.label, series: i, detail: `${compact(p.y)} · ${pct}` });
    if (pts.length === 1) {
      base.marks.push({ t: "slice", series: i, title: `${p.label}: ${compact(p.y)} (${pct})`,
        d: `M${cx - r},${cy} a${r},${r} 0 1,0 ${2 * r},0 a${r},${r} 0 1,0 ${-2 * r},0 Z` });
    } else {
      const [x0, y0] = [cx + r * Math.cos(angle), cy + r * Math.sin(angle)];
      const [x1, y1] = [cx + r * Math.cos(a1), cy + r * Math.sin(a1)];
      base.marks.push({ t: "slice", series: i, title: `${p.label}: ${compact(p.y)} (${pct})`,
        d: `M${cx},${cy} L${x0.toFixed(1)},${y0.toFixed(1)} A${r},${r} 0 ${sweep > Math.PI ? 1 : 0},1 ${x1.toFixed(1)},${y1.toFixed(1)} Z` });
    }
    angle = a1;
  });
  return base;
}

/** One sentence for a screen reader: what is charted, without reading every mark. */
export function describe(m: Model): string {
  const n = m.series.reduce((a, s) => a + s.points.length, 0);
  const kind = m.kind === "pie" ? "Pie chart" : `${m.kind[0].toUpperCase()}${m.kind.slice(1)} chart`;
  return `${kind} of ${m.yName} by ${m.xName}: ${plural(n, "point", "points")}${m.series.length > 1 ? ` in ${m.series.length} groups` : ""}.`;
}
