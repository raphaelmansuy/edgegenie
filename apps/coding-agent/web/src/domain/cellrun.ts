/** A cell's execution, as the UI sees it. Pure: one union, one set of words.
 *
 * The server returns a `state` plus either data or a reason. This module decides what that means to a
 * person — the badge, the sentence, whether a control is offered — so the component only renders.
 *
 * The rule that matters: **every state names what happened and, when it went wrong, what to do.** A
 * run that says "failed" and nothing else is the thing this whole surface exists to avoid.
 */

export type RunState = "succeeded" | "failed" | "running" | "cancelled" | "refused";

export interface CellRun {
  state: RunState;
  seconds: number;
  columns?: string[];
  rows?: (string | null)[][];
  truncated?: boolean;
  totalRows?: number;
  error?: string;
  statement?: string;
  /** Where it ran: a warehouse for SQL; for Python, the compute and the identity ("Serverless · as the app"). */
  warehouse?: string;
  /** What a Python cell printed, plus the value of its last expression. */
  output?: string;
}

/** May the signed-in user run Python cells? Decided by the server (`/api/me`), shown here. */
export interface PythonPolicy { enabled: boolean; reason: string }
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

/** The one-line summary under the cell: rows and time, or nothing to summarise. */
export function summary(run: CellRun | undefined): string {
  if (!run) return "";
  const secs = run.seconds >= 1 ? `${run.seconds.toFixed(1)}s` : `${Math.round(run.seconds * 1000)}ms`;
  if (run.state === "succeeded") {
    // Python that only printed has no rows to count; "0 rows" would read as an empty result.
    if (!run.columns || run.columns.length === 0) return secs;
    const n = run.totalRows ?? run.rows?.length ?? 0;
    const rows = `${n} ${n === 1 ? "row" : "rows"}`;
    return run.truncated ? `${rows} (first ${run.rows?.length ?? 0} shown) · ${secs}` : `${rows} · ${secs}`;
  }
  return secs;
}

/** Should this run show a table? A refusal with no data has nothing to draw. */
export function showsTable(run: CellRun | undefined): boolean {
  return Boolean(run && run.state === "succeeded" && run.columns && run.columns.length > 0);
}

/** Should this run show what the cell printed? A run in flight has nothing yet. */
export function showsOutput(run: CellRun | undefined): boolean {
  return Boolean(run && run.state !== "running" && run.output && run.output.trim());
}

/** Should this run show an explanation box? Every non-success that has words does. */
export function showsMessage(run: CellRun | undefined): boolean {
  return Boolean(run && run.state !== "succeeded" && run.error);
}

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
        title: "Runs on serverless compute as the app, not as you. The Python cells above it run first, so it has their variables.",
      };
    }
    return { enabled: false, title: python?.reason || `python cell: ask the agent to run it, or write SQL` };
  }
  if (name) return { enabled: false, title: `%${name} cells cannot run here; only SQL and Python do` };
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
}

export function runPlan(
  cells: { id: string; kind: string; language: string; source: string }[], python?: PythonPolicy,
): RunPlan {
  const plan: RunPlan = { runnable: [], skipped: [], python: [] };
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
  return plan;
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
  return ids.filter((id) => {
    if (span === "these") return these.includes(id);
    const i = cells.findIndex((c) => c.id === id);
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
  if (done === 0) return `${plan.runnable.length} ${plan.runnable.length === 1 ? "cell" : "cells"} can run${skipped}`;
  if (failed) return `${done - failed} ran · ${failed} failed${skipped}`;
  return `${done} ran${skipped}`;
}
