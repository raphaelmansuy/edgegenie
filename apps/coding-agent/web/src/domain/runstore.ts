/** Cell results that outlive the page: kept per notebook so switching tabs or reloading does not lose them.
 *
 * Databricks keeps a command's result with the notebook. Ours lived in React state, and the viewer is
 * mounted per document, so a tab switch or a reload threw every result away. This keeps them in memory
 * (a tab switch) and in `localStorage` (a reload, a new tab).
 *
 * Three rules:
 *  - **a result belongs to the code that produced it.** Results are matched to cells by a hash of the
 *    cell's source, not by position, so inserting a cell above does not hand a result to the wrong cell
 *    and an edited cell does not keep a result it did not produce;
 *  - **a run that was in flight is never restored as running.** Nothing is polling it any more, so a
 *    spinner would never end. It comes back as an interrupted run, with the words to say so;
 *  - **it is bounded.** Plots and HTML go first when a notebook is over its budget, then table rows, then
 *    the oldest notebook, so storage never fills and starts to throw.
 */
import type { CellRun, Output } from "./cellrun";

export interface StoredRun { h: string; run: CellRun }

interface Entry { at: number; runs: StoredRun[] }

export const KEY = "coding-agent:runs:v1:";
export const TTL_MS = 30 * 24 * 60 * 60 * 1000;
export const MAX_NOTEBOOKS = 20;
/** Characters of JSON per notebook, and for all notebooks together (`localStorage` allows about 5 MB). */
export const MAX_NOTEBOOK_CHARS = 900_000;
export const MAX_TOTAL_CHARS = 3_000_000;
export const KEPT_ROWS = 100;

export const INTERRUPTED = "this run was interrupted when the page was left, so there is no result. Run the cell again.";

/** FNV-1a over the source, with its length: cheap, stable, and the same on every load. */
export function hashSource(source: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < source.length; i += 1) {
    h ^= source.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return `${(h >>> 0).toString(36)}.${source.length.toString(36)}`;
}

/** The results worth keeping, in cell order, each with the hash of the code that produced it. */
export function snapshot(cells: readonly { id: string; source: string }[], runs: Record<string, CellRun>): StoredRun[] {
  const out: StoredRun[] = [];
  for (const c of cells) {
    const run = runs[c.id];
    if (run) out.push({ h: hashSource(c.source), run });
  }
  return out;
}

/** What a run that was in flight becomes. */
function interrupted(run: CellRun): CellRun {
  return { state: "cancelled", seconds: run.seconds, error: INTERRUPTED, warehouse: run.warehouse };
}

/** Results for these cells: the stored run whose code is this cell's code. Two cells with the same
 *  source take the stored runs in order. A stored run that no cell claims is dropped. */
export function restore(cells: readonly { id: string; source: string }[], stored: readonly StoredRun[]): Record<string, CellRun> {
  const used = new Set<number>();
  const out: Record<string, CellRun> = {};
  for (const c of cells) {
    const h = hashSource(c.source);
    const pick = stored.findIndex((s, i) => !used.has(i) && s.h === h);
    if (pick < 0) continue;
    used.add(pick);
    const run = stored[pick].run;
    out[c.id] = run.state === "running" ? interrupted(run) : run;
  }
  return out;
}

/* ---- keeping within budget ------------------------------------------------------------------- */

const NOT_KEPT = "Plots and HTML are not kept when you leave a notebook. Run the cell again to see them.";

function withoutHeavy(run: CellRun): CellRun {
  const heavy = (o: Output) => o.type === "image" || o.type === "html";
  const had = (run.images?.length ?? 0) > 0 || (run.outputs ?? []).some(heavy);
  if (!had) return run;
  const { images: _images, ...rest } = run;
  const outputs: Output[] = (run.outputs ?? []).filter((o) => !heavy(o));
  outputs.push({ type: "text", stream: "notice", text: NOT_KEPT });
  // With ordered outputs the notice joins them; a flat (SQL) result gets it as printed text.
  return run.outputs?.length
    ? { ...rest, outputs }
    : { ...rest, output: [run.output, NOT_KEPT].filter(Boolean).join("\n") };
}

function withFewerRows(run: CellRun): CellRun {
  const cut = (rows: (string | null)[][]) => rows.slice(0, KEPT_ROWS);
  if (run.outputs?.length) {
    return { ...run, outputs: run.outputs.map((o) => (o.type === "table" && o.rows.length > KEPT_ROWS
      ? { ...o, rows: cut(o.rows), truncated: true } : o)) };
  }
  if (run.rows && run.rows.length > KEPT_ROWS) return { ...run, rows: cut(run.rows), truncated: true };
  return run;
}

const size = (runs: StoredRun[]) => JSON.stringify(runs).length;

/** The runs, reduced until they fit `limit` characters: plots and HTML first, then rows, then the
 *  results furthest from the top. */
export function fit(runs: StoredRun[], limit = MAX_NOTEBOOK_CHARS): StoredRun[] {
  let cur = runs;
  if (size(cur) <= limit) return cur;
  cur = cur.map((s) => ({ ...s, run: withoutHeavy(s.run) }));
  if (size(cur) <= limit) return cur;
  cur = cur.map((s) => ({ ...s, run: withFewerRows(s.run) }));
  while (cur.length > 0 && size(cur) > limit) cur = cur.slice(0, -1);
  return cur;
}

/* ---- the store ------------------------------------------------------------------------------- */

const memory = new Map<string, Entry>();

const storage = (): Storage | null => {
  try { return typeof localStorage !== "undefined" ? localStorage : null; } catch { return null; }
};

function stored(): { path: string; at: number; chars: number }[] {
  const s = storage();
  if (!s) return [];
  const out: { path: string; at: number; chars: number }[] = [];
  try {
    for (let i = 0; i < s.length; i += 1) {
      const k = s.key(i);
      if (!k?.startsWith(KEY)) continue;
      const raw = s.getItem(k) ?? "";
      let at = 0;
      try { at = (JSON.parse(raw) as Entry).at || 0; } catch { /* unreadable: oldest, evicted first */ }
      out.push({ path: k.slice(KEY.length), at, chars: raw.length });
    }
  } catch { /* storage unavailable */ }
  return out;
}

/** Drop what is over its age, over the count, or over the total, oldest first. */
function evict(now: number): void {
  const s = storage();
  if (!s) return;
  const all = stored().sort((a, b) => b.at - a.at);
  let total = 0;
  all.forEach((e, i) => {
    total += e.chars;
    if (now - e.at > TTL_MS || i >= MAX_NOTEBOOKS || total > MAX_TOTAL_CHARS) {
      try { s.removeItem(KEY + e.path); } catch { /* ignore */ }
    }
  });
}

const valid = (e: unknown): e is Entry => {
  const x = e as Entry;
  return !!x && typeof x.at === "number" && Array.isArray(x.runs)
    && x.runs.every((r) => r && typeof r.h === "string" && r.run && typeof r.run.state === "string");
};

/** The saved results for a notebook, or none. Memory first (a tab switch), then storage (a reload). */
export function recallRuns(path: string, now = Date.now()): StoredRun[] | null {
  const m = memory.get(path);
  if (m) return m.runs;
  try {
    const raw = storage()?.getItem(KEY + path);
    if (!raw) return null;
    const e = JSON.parse(raw) as unknown;
    if (!valid(e) || now - e.at > TTL_MS) return null;
    memory.set(path, e);
    return e.runs;
  } catch {
    return null;                       // a corrupt entry is not worth a crash
  }
}

/** Keep these results for the notebook. An empty list forgets them. Never throws. */
export function rememberRuns(path: string, runs: StoredRun[], now = Date.now()): void {
  if (runs.length === 0) { forgetRuns(path); return; }
  const kept = fit(runs);
  memory.set(path, { at: now, runs: kept });
  try {
    storage()?.setItem(KEY + path, JSON.stringify({ at: now, runs: kept } satisfies Entry));
    evict(now);
  } catch { /* quota or private mode: memory still carries a tab switch */ }
}

export function forgetRuns(path: string): void {
  memory.delete(path);
  try { storage()?.removeItem(KEY + path); } catch { /* ignore */ }
}

/** A result that arrived after its notebook was left (the run was still going when the user switched
 *  tab): it replaces the run that was in flight for that code, or is added. */
export function completeRun(path: string, source: string, run: CellRun, now = Date.now()): void {
  const h = hashSource(source);
  const cur = recallRuns(path, now) ?? [];
  const at = cur.findIndex((s) => s.h === h && s.run.state === "running");
  const next = at >= 0 ? cur.map((s, i) => (i === at ? { h, run } : s)) : [...cur, { h, run }];
  rememberRuns(path, next, now);
}

/** For tests: forget everything held in memory. */
export function resetMemory(): void {
  memory.clear();
}
