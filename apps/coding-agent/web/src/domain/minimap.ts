/** The execution map: one bar per code cell, named, so a long notebook is navigable.
 *
 * Databricks draws this in the right margin (notebook editor, 27 Oct 2026). The tones are theirs:
 * idle, skipped or queued, running, succeeded, failed. Markdown is not a bar — it does not run.
 * Pure: the component only paints what this returns.
 */

export type MapTone = "idle" | "skip" | "queued" | "running" | "ok" | "failed";

export interface MapCell {
  id: string;
  kind: string;
  source: string;
}

export interface MapRun { state: string }

export interface MapRow {
  id: string;
  /** 1-based, matching the cell number in the gutter. */
  index: number;
  label: string;
  tone: MapTone;
}

export interface ExecutionMap {
  rows: MapRow[];
  /** 1-based cell of the first failure, or null. */
  firstFailed: number | null;
  /** 1-based cell of the latest settled run, or null. */
  lastSettled: number | null;
}

const TONE_WORD: Record<MapTone, string> = {
  idle: "not run",
  skip: "skipped",
  queued: "queued",
  running: "running",
  ok: "done",
  failed: "failed",
};

export function toneWord(tone: MapTone): string {
  return TONE_WORD[tone];
}

function clip(s: string): string {
  const t = s.replace(/\s+/g, " ").trim();
  return t.length > 48 ? `${t.slice(0, 47)}…` : t;
}

/** A name a person can scan: a heading, else a comment, else the first line of code. */
export function cellLabel(cell: { source: string }, index: number): string {
  const lines = (cell.source || "").split("\n").map((s) => s.trim()).filter(Boolean);
  const heading = lines.find((l) => /^#{1,6}\s+\S/.test(l));
  if (heading) return clip(heading.replace(/^#{1,6}\s+/, ""));
  const comment = lines.find((l) => /^(#(?!#)|--|\/\/)\s+\S/.test(l));
  if (comment) return clip(comment.replace(/^(#|--|\/\/)\s+/, ""));
  const code = lines.find((l) => !l.startsWith("%"));
  if (code) return clip(code);
  return `Cell ${index + 1}`;
}

export function executionMap(
  cells: readonly MapCell[],
  runs: Record<string, MapRun | undefined>,
  runnable: readonly string[],
  batch: readonly string[] | null,
): ExecutionMap {
  const can = new Set(runnable);
  const waiting = new Set(batch ?? []);
  const rows: MapRow[] = [];
  let firstFailed: number | null = null;
  let lastSettled: number | null = null;

  cells.forEach((c, i) => {
    if (c.kind === "markdown") return;
    const run = runs[c.id];
    let tone: MapTone;
    if (run?.state === "running") tone = "running";
    else if (run?.state === "succeeded") tone = "ok";
    else if (run?.state === "failed") tone = "failed";
    else if (!can.has(c.id)) tone = "skip";
    else if (waiting.has(c.id) && !run) tone = "queued";
    else tone = "idle";
    const index = i + 1;
    if (tone === "failed" && firstFailed === null) firstFailed = index;
    if (run && run.state !== "running") lastSettled = index;
    rows.push({ id: c.id, index, label: cellLabel(c, i), tone });
  });

  return { rows, firstFailed, lastSettled };
}
