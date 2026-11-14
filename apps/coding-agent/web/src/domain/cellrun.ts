/** A cell's execution, as the UI sees it. Pure: one union, one set of words.
 *
 * The server returns a `state` plus either data or a reason. This module decides what that means to a
 * person — the badge, the sentence, whether a control is offered — so the component only renders.
 *
 * The rule that matters: **every state names what happened and, when it went wrong, what to do.** A
 * run that says "failed" and nothing else is the thing this whole surface exists to avoid.
 */

import type { TableView } from "./chart";
import type { Widget } from "./widgets";

export type RunState = "succeeded" | "failed" | "running" | "cancelled" | "refused";

/** One thing a cell produced. A Python cell reports these in the order it produced them, so a print
 *  between two tables appears between them (Databricks and Jupyter both do this). */
export type Output =
  | { type: "text"; stream: "stdout" | "stderr" | "result" | "notice"; text: string }
  | { type: "table"; columns: string[]; rows: (string | null)[][]; truncated?: boolean; types?: string[]; typeTexts?: string[] }
  | { type: "image"; png: string }
  | { type: "html"; html: string }
  | { type: "markdown"; text: string };

export interface CellRun {
  state: RunState;
  seconds: number;
  columns?: string[];
  rows?: (string | null)[][];
  /** One type name per column ("int", "string", "decimal"), lower case. */
  types?: string[];
  /** The full type per column ("ARRAY<INT>"), present when a column is an array, map or struct. */
  typeTexts?: string[];
  /** For each result table (by its position among the tables): drawn as a table or as a chart, and which
   *  chart. Kept with the result so a reload shows what the person chose. */
  views?: Record<string, TableView>;
  /** The widgets the session reported after this cell ran (see `domain/widgets`). Not drawn under the cell. */
  widgets?: Widget[];
  /** The ordered outputs. When present they are the whole result; the flat fields are absent. */
  outputs?: Output[];
  /** When it finished (ISO 8601, UTC) and who asked, as Databricks prints under a command. */
  finishedAt?: string;
  ranBy?: string;
  truncated?: boolean;
  totalRows?: number;
  error?: string;
  statement?: string;
  /** Where it ran: a warehouse for SQL; for Python, the compute and the identity ("Serverless · as the app"). */
  warehouse?: string;
  /** What a Python cell printed, plus the value of its last expression. */
  output?: string;
  /** PNG plots as base64 (no `data:` prefix). Matplotlib figures the cell left open. */
  images?: string[];
}

/** May the signed-in user run Python cells? Decided by the server (`/api/me`), shown here. */
export interface PythonPolicy {
  enabled: boolean; reason: string;
  /** The server can keep a Python session between cells (variables survive). Absent or false: one-shot runs only. */
  session?: boolean;
}
export type Engine = "sql" | "python";

/** `%skip` is a directive, not a language. It drops the cell from Run all / above / below.
 *  A run of that cell alone executes whatever follows the directive (Databricks, run-notebook). */
const SKIP_LINE = /^\s*%skip\b[^\n]*\n?/i;

export function withoutSkip(source: string): { skipped: boolean; source: string } {
  const text = source ?? "";
  const m = SKIP_LINE.exec(text);
  if (!m) return { skipped: false, source: text };
  return { skipped: true, source: text.slice(m[0].length) };
}

export const SKIP_REASON = "Marked %skip — left out of Run all, Run above and Run below. Run the cell on its own to execute it.";

export interface RunBadge { word: string; tone: "ok" | "warn" | "error" | "muted" }

export function badge(run: CellRun | undefined): RunBadge {
  if (!run) return { word: "", tone: "muted" };
  switch (run.state) {
    case "succeeded": return { word: "done", tone: "ok" };
    case "running": return { word: "running", tone: "warn" };
    case "cancelled": return { word: "cancelled", tone: "muted" };
    case "refused": return { word: "not run", tone: "muted" };
    default: return { word: "failed", tone: "error" };
  }
}

/** Everything a run produced, in the order to draw it. Python reports this itself; a SQL run reports
 *  flat fields, which are drawn as text, plots, then the table (the order they were drawn in before). */
export function outputsOf(run: CellRun | undefined): Output[] {
  if (!run) return [];
  if (run.outputs && run.outputs.length > 0) return run.outputs;
  const out: Output[] = [];
  if (run.output && run.output.trim()) out.push({ type: "text", stream: "stdout", text: run.output });
  for (const png of run.images ?? []) out.push({ type: "image", png });
  if (run.state === "succeeded" && run.columns && run.columns.length > 0) {
    out.push({ type: "table", columns: run.columns, rows: run.rows ?? [], truncated: run.truncated, types: run.types, typeTexts: run.typeTexts });
  }
  return out;
}

const tablesOf = (run: CellRun | undefined) => outputsOf(run).filter((o): o is Extract<Output, { type: "table" }> => o.type === "table");

/** The one-line summary under the cell: rows and time, or nothing to summarise. */
export function summary(run: CellRun | undefined): string {
  if (!run) return "";
  const secs = run.seconds >= 1 ? `${run.seconds.toFixed(1)}s` : `${Math.round(run.seconds * 1000)}ms`;
  if (run.state === "succeeded") {
    const bits: string[] = [];
    const tables = tablesOf(run);
    if (tables.length === 1) {
      const t = tables[0];
      // `totalRows` is the engine's count and only the flat (SQL) result carries it.
      const n = run.outputs?.length ? t.rows.length : run.totalRows ?? t.rows.length;
      const rows = `${n.toLocaleString("en-US")} ${n === 1 ? "row" : "rows"}`;
      bits.push(t.truncated ? `${rows} (first ${t.rows.length.toLocaleString("en-US")} shown)` : rows);
    } else if (tables.length > 1) {
      bits.push(`${tables.length} tables`);
    }
    const plots = outputsOf(run).filter((o) => o.type === "image").length;
    if (plots > 0) bits.push(plots === 1 ? "1 plot" : `${plots} plots`);
    // Python that only printed has no rows or plots to count; the duration alone is enough.
    return bits.length ? `${bits.join(" · ")} · ${secs}` : secs;
  }
  return secs;
}

/** "by a@x at 8:02 AM" (or with the date when it was not today), the other half of Databricks'
 *  "Command took 1.2 seconds -- by a@x at 11/12/2026, 8:02:11 AM". Empty when neither is known. */
export function whenRan(run: CellRun | undefined, now: Date = new Date(), timeZone?: string): string {
  if (!run || run.state === "running") return "";
  const who = run.ranBy ? `by ${run.ranBy}` : "";
  let at = "";
  const d = run.finishedAt ? new Date(run.finishedAt) : null;
  if (d && !Number.isNaN(d.getTime())) {
    const day = (x: Date) => x.toLocaleDateString("en-CA", { timeZone });
    const time = d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", second: "2-digit", timeZone });
    at = day(d) === day(now) ? `at ${time}` : `on ${day(d)} at ${time}`;
  }
  return [who, at].filter(Boolean).join(" ");
}

/** The sentence under a table that has more rows than it shows ("Showing the first 1,000 rows"). */
export function truncationNote(rows: number, total?: number): string {
  const shown = rows.toLocaleString("en-US");
  return total && total > rows
    ? `Showing the first ${shown} of ${total.toLocaleString("en-US")} rows`
    : `Showing the first ${shown} rows`;
}

const NUMERIC_TYPES = new Set([
  "tinyint", "smallint", "int", "integer", "bigint", "long", "short", "byte", "float", "double", "real",
  "decimal", "dec", "numeric",
]);

/** Is this column a number? The engine's type decides when it gave one; guessing from the text mislabels
 *  an identifier or a zip code that happens to be all digits. Without types, every cell must look numeric. */
export function numericColumns(columns: readonly string[], rows: readonly (string | null)[][], types?: readonly string[]): boolean[] {
  return columns.map((_, c) => {
    const t = types?.[c];
    if (t) return NUMERIC_TYPES.has(t.toLowerCase());
    let seen = false;
    for (const r of rows) {
      const v = r[c];
      if (v === null || v === undefined || v === "") continue;
      if (!/^-?[\d.,]+$/.test(v)) return false;
      seen = true;
    }
    return seen;
  });
}

/** A short glyph for the header, from the type: Databricks marks number and text columns the same way. */
export function typeGlyph(type: string | undefined): string {
  const t = (type ?? "").toLowerCase();
  if (!t) return "";
  if (NUMERIC_TYPES.has(t)) return "123";
  if (t === "string" || t === "char" || t === "varchar") return "abc";
  if (t === "boolean") return "T/F";
  if (t === "date" || t.startsWith("timestamp")) return "date";
  return "";
}

/** Should this run show a table? A refusal with no data has nothing to draw. */
export function showsTable(run: CellRun | undefined): boolean {
  return Boolean(run && run.state === "succeeded" && tablesOf(run).length > 0);
}

/** Should this run show what the cell printed? A run in flight has nothing yet. */
export function showsOutput(run: CellRun | undefined): boolean {
  return Boolean(run && run.state !== "running"
    && outputsOf(run).some((o) => o.type === "text" && o.text.trim()));
}

/** Should this run show matplotlib (or other) PNG plots under the cell? */
export function showsImages(run: CellRun | undefined): boolean {
  return Boolean(run && run.state !== "running" && outputsOf(run).some((o) => o.type === "image"));
}

/** What to draw under the cell, in order. Nothing while it is still running. A failed cell keeps
 *  whatever it produced before it failed, as Databricks does. */
export function drawn(run: CellRun | undefined): Output[] {
  if (!run) return [];
  // A run in flight shows what its session has printed so far, and nothing else: there is no result yet.
  if (run.state === "running") return run.outputs ?? [];
  return outputsOf(run);
}

/** Should this run show an explanation box? Every non-success that has words does. */
export function showsMessage(run: CellRun | undefined): boolean {
  return Boolean(run && run.state !== "succeeded" && run.error);
}

/** What the run control says for the magics that need the session. */
const SESSION_MAGICS: Record<string, string> = {
  sh: "Runs this shell command on the session's compute, as the app (not as you). It has no keyboard: a command that asks a question gets none.",
  pip: "Installs into this session's Python, on serverless compute as the app. A module already imported keeps its old version until the session is restarted.",
  run: "Runs the cells of another notebook in this session. The app reads it with your access, so you can run only what you can read.",
  md: "Shows this text as markdown",
};

/**
 * What a "run" control should say, and whether it can be pressed at all.
 * A Python cell cannot run here, and a disabled button with a reason beats a button that lies.
 */
export function runAffordance(
  language: string, source: string, python?: PythonPolicy,
): { enabled: boolean; title: string; engine?: Engine } {
  const stripped = withoutSkip(source ?? "");
  const text = stripped.source.trim();
  if (!text) return { enabled: false, title: stripped.skipped ? "This cell is only %skip" : "This cell is empty" };
  const magic = /^\s*%(\w+)/.exec(text);
  const name = magic?.[1].toLowerCase();
  const lang = (language ?? "").toLowerCase();
  if (name === "sql" || (!name && lang === "sql")) {
    return { enabled: true, title: "Run this cell on a SQL warehouse, as you (⌘⏎)", engine: "sql" };
  }
  if (name === "python" || name === "py" || (!name && (lang === "python" || lang === ""))) {
    if (python?.enabled) {
      return {
        enabled: true, engine: "python",
        title: python.session
          ? "Runs in this notebook's Python session, on serverless compute as the app, not as you. Variables stay between cells."
          : "Runs on serverless compute as the app, not as you. The Python cells above it run first, so it has their variables.",
      };
    }
    return { enabled: false, title: python?.reason || `python cell: ask the agent to run it, or write SQL` };
  }
  // A shell command, a library install, a `%run` and a markdown line run only in a session: they act on
  // the process that holds the variables. A cell read from a notebook file has its magic as its language.
  const session = SESSION_MAGICS[name ?? (lang === "shell" ? "sh" : lang)];
  if (session) {
    if (python?.enabled && python.session) return { enabled: true, engine: "python", title: session };
    return { enabled: false, title: `%${name ?? lang} needs the notebook's Python session, which is not available${python?.reason ? `: ${python.reason}` : ""}` };
  }
  if (name) return { enabled: false, title: `%${name} cells cannot run here; only SQL, Python, %sh, %pip and %run do` };
  return { enabled: false, title: `${lang || "this"} cell: ask the agent to run it, or write SQL` };
}

/** A stable key for one cell's output, so a reorder keeps the result with its cell. */
export function runKey(docPath: string, cellId: string): string {
  return `${docPath}::${cellId}`;
}

/** Clear every output: one action, and the map is empty afterwards (X4). */
export function clearAll(_outputs: Record<string, CellRun>): Record<string, CellRun> {
  return {};
}

/** What "Run all" will do, decided before it starts, so the button can say it and the user is not surprised. */
export interface RunPlan {
  /** The runnable cells that run as Python (one serverless job); the rest of `runnable` are SQL. */
  python: string[];
  /** Cell ids to run, in notebook order. */
  runnable: string[];
  /** Cells it will not run, each with the reason the cell's own run control gives. */
  skipped: { id: string; index: number; reason: string }[];
  /** How many separate Python jobs Run all starts. More than one means SQL sits between Python cells,
   *  and each later job re-runs the Python above it to have its variables. */
  blocks: number;
}

export function runPlan(
  cells: { id: string; kind: string; language: string; source: string }[], python?: PythonPolicy,
): RunPlan {
  const plan: RunPlan = { runnable: [], skipped: [], python: [], blocks: 0 };
  cells.forEach((c, index) => {
    if (c.kind === "markdown") return; // prose is not skipped, it is not code
    if (withoutSkip(c.source).skipped) {
      plan.skipped.push({ id: c.id, index, reason: SKIP_REASON });
      return;
    }
    const a = runAffordance(c.language || "python", c.source, python);
    if (a.enabled) { plan.runnable.push(c.id); if (a.engine === "python") plan.python.push(c.id); }
    else plan.skipped.push({ id: c.id, index, reason: a.title });
  });
  // In a session every cell runs where it is, in order, and nothing is re-run: there are no "jobs" to count.
  plan.blocks = python?.session ? 0 : segments(cells, plan.runnable, python).filter((s) => s.engine === "python").length;
  return plan;
}

/** One stretch of cells that run on the same engine. */
export interface Segment { engine: Engine; ids: string[] }

/**
 * `ids` in NOTEBOOK order, grouped into stretches of the same engine.
 *
 * A notebook runs top to bottom: a SQL cell below a Python cell may read the table that cell wrote, and
 * the reverse. Starting the Python job at once and running the SQL cells beside it let the SQL cell win
 * that race. Running the stretches one after another is what makes "Run all" mean what it says. A
 * notebook with all its Python together (or all its SQL) is still one job.
 */
export function segments(
  cells: { id: string; kind: string; language: string; source: string }[],
  ids: readonly string[], python: PythonPolicy | undefined, fallback = "python",
): Segment[] {
  const wanted = new Set(ids);
  const out: Segment[] = [];
  for (const c of cells) {
    if (!wanted.has(c.id)) continue;
    const engine = runAffordance(c.kind === "markdown" ? "markdown" : c.language || fallback, c.source, python).engine;
    if (!engine) continue;
    const last = out[out.length - 1];
    if (last && last.engine === engine) last.ids.push(c.id);
    else out.push({ engine, ids: [c.id] });
  }
  return out;
}

/** Which runnable cells a span covers. Above excludes the anchor; below includes it. */
export function spanIds(
  cells: { id: string; kind: string; language: string; source: string }[],
  python: PythonPolicy | undefined,
  anchor: number,
  span: "all" | "above" | "below" | "these",
  these: readonly string[] = [],
): string[] {
  const ids = runPlan(cells, python).runnable;
  if (span === "all") return ids;
  const indexes = new Map(cells.map((c, i) => [c.id, i]));
  const picked = new Set(these);
  return ids.filter((id) => {
    if (span === "these") return picked.has(id);
    const i = indexes.get(id) ?? -1;
    return span === "above" ? i < anchor : i >= anchor;
  });
}

export interface TableQuery {
  text: string;
  sortCol: number | null;
  sortDir: "asc" | "desc";
}

function asNumber(v: string): number | null {
  const t = v.trim();
  if (!/^-?[\d,]+\.?\d*$/.test(t) && !/^-?\d*\.\d+$/.test(t)) return null;
  const n = Number(t.replace(/,/g, ""));
  return Number.isFinite(n) ? n : null;
}

/** Filter then sort a result. Numbers sort as numbers; empty cells stay last either way. */
export function presentRows(rows: readonly (string | null)[][], q: TableQuery): (string | null)[][] {
  const needle = q.text.trim().toLowerCase();
  const matched = needle
    ? rows.filter((r) => r.some((c) => (c ?? "").toLowerCase().includes(needle)))
    : rows.slice();
  if (q.sortCol === null) return matched;
  const col = q.sortCol;
  const dir = q.sortDir === "desc" ? -1 : 1;
  return matched.slice().sort((a, b) => {
    const av = a[col] ?? null;
    const bv = b[col] ?? null;
    const aEmpty = av === null || av === "";
    const bEmpty = bv === null || bv === "";
    if (aEmpty && bEmpty) return 0;
    if (aEmpty) return 1;
    if (bEmpty) return -1;
    const an = asNumber(av);
    const bn = asNumber(bv);
    const cmp = an !== null && bn !== null
      ? an - bn
      : av.localeCompare(bv, undefined, { numeric: true, sensitivity: "base" });
    return cmp * dir;
  });
}

/** A copy of the visible table. Tabs and newlines in a cell would break the paste, so they become spaces. */
export function toTsv(columns: readonly string[], rows: readonly (string | null)[][]): string {
  const cell = (v: string | null) => (v ?? "").replace(/\t/g, " ").replace(/\r?\n/g, " ");
  const line = (r: readonly (string | null)[]) => columns.map((_, i) => cell(r[i] ?? null)).join("\t");
  return [columns.map(cell).join("\t"), ...rows.map(line)].join("\n");
}

/** The sentence beside the Run all button, from the plan and the results so far.
 *  While a span is running, the count is that span, not the whole notebook. */
export function runAllLabel(
  plan: RunPlan, runs: Record<string, CellRun>, running: boolean, batch?: readonly string[] | null,
): string {
  const ids = running && batch && batch.length ? batch : plan.runnable;
  const done = ids.filter((id) => runs[id] && runs[id].state !== "running").length;
  const failed = ids.filter((id) => runs[id]?.state === "failed").length;
  if (running) return `running ${Math.min(done + 1, ids.length)} of ${ids.length}`;
  if (plan.runnable.length === 0) return plan.skipped.length ? "no cell here can run in the app" : "nothing to run";
  const skipped = plan.skipped.length ? ` · ${plan.skipped.length} skipped` : "";
  const blocks = plan.blocks > 1 ? ` · Python runs in ${plan.blocks} jobs, SQL is in between` : "";
  if (done === 0) return `${plan.runnable.length} ${plan.runnable.length === 1 ? "cell" : "cells"} can run${blocks}${skipped}`;
  if (failed) return `${done - failed} ran · ${failed} failed${skipped}`;
  return `${done} ran${skipped}`;
}
