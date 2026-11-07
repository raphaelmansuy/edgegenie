/** Line and cell diffs, and applying a chosen set of hunks.
 *
 * Spec 003 DF-2 makes this module's contract strict: applying **all** hunks yields the proposal
 * exactly, applying **none** yields the base exactly, and applying a random subset yields something
 * that is still a well-formed document. Those three are property tests, because a diff that is
 * right for the example in the docs and wrong for a real notebook is worse than no diff.
 *
 * Why hand-written rather than a library: the algorithm here is a plain LCS over lines, ~60 lines,
 * with no dependency and a shape we control. `@codemirror/merge` gives the *view*; this gives the
 * data the view renders and the operations a button performs.
 */

export type Op = "same" | "add" | "del";

export interface Line {
  op: Op;
  /** Present on "same" and "del". */
  base?: string;
  /** Present on "same" and "add". */
  next?: string;
  /** 1-based line number in the base, for a gutter. */
  baseNo?: number;
  nextNo?: number;
}

export interface Hunk {
  id: string;
  /** Index into `lines` where this hunk starts. */
  at: number;
  /** The changed lines, in order. */
  lines: Line[];
}

export interface Diff {
  lines: Line[];
  hunks: Hunk[];
}

const linesOf = (text: string) => text.replace(/\r\n/g, "\n").split("\n");

/** Longest common subsequence table. O(n·m) memory, bounded by a cap so a pathological pair cannot
 *  hang the tab — beyond the cap we fall back to "whole file replaced", which is honest. */
const MAX_CELLS = 2_000_000;

function lcs(a: string[], b: string[]): number[][] {
  const n = a.length;
  const m = b.length;
  if (n * m > MAX_CELLS) return [];
  const t: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i -= 1) {
    for (let j = m - 1; j >= 0; j -= 1) {
      t[i][j] = a[i] === b[j] ? t[i + 1][j + 1] + 1 : Math.max(t[i + 1][j], t[i][j + 1]);
    }
  }
  return t;
}

/** A line diff, with 1-based numbers on both sides. */
export function diffLines(base: string, next: string): Diff {
  const a = linesOf(base);
  const b = linesOf(next);
  const t = lcs(a, b);

  const lines: Line[] = [];
  let i = 0;
  let j = 0;
  let baseNo = 1;
  let nextNo = 1;

  // No table (too large): present it as a full replacement rather than pretending to be granular.
  if (!t.length) {
    for (const s of a) lines.push({ op: "del", base: s, baseNo: baseNo++ });
    for (const s of b) lines.push({ op: "add", next: s, nextNo: nextNo++ });
    return { lines, hunks: groupHunks(lines) };
  }

  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      lines.push({ op: "same", base: a[i], next: b[j], baseNo: baseNo++, nextNo: nextNo++ });
      i += 1;
      j += 1;
    } else if (t[i + 1][j] >= t[i][j + 1]) {
      lines.push({ op: "del", base: a[i], baseNo: baseNo++ });
      i += 1;
    } else {
      lines.push({ op: "add", next: b[j], nextNo: nextNo++ });
      j += 1;
    }
  }
  while (i < a.length) lines.push({ op: "del", base: a[i++], baseNo: baseNo++ });
  while (j < b.length) lines.push({ op: "add", next: b[j++], nextNo: nextNo++ });

  return { lines, hunks: groupHunks(lines) };
}

/** Consecutive changed lines form one hunk, so the UI offers "accept this change", not "accept this
 *  line". Unchanged lines between two changes split them. */
function groupHunks(lines: Line[]): Hunk[] {
  const hunks: Hunk[] = [];
  let at = -1;
  for (let k = 0; k < lines.length; k += 1) {
    if (lines[k].op === "same") {
      at = -1;
      continue;
    }
    if (at === -1) {
      at = k;
      hunks.push({ id: `h${hunks.length}`, at, lines: [] });
    }
    hunks[hunks.length - 1].lines.push(lines[k]);
  }
  return hunks;
}

/** Apply the chosen hunks to `base`, producing a document.
 *
 * The reason this is not `applyAll`-only: DF-3 requires that rejecting leaves the base untouched,
 * and CX-3 requires a *subset* to be meaningful. Walking the operations in order with a set of
 * accepted hunk ids gives both, and "accept nothing" degenerates to the base automatically.
 */
export function applyHunks(diff: Diff, accepted: ReadonlySet<string>): string {
  const byLine = new Map<number, string>();
  for (const h of diff.hunks) {
    if (!accepted.has(h.id)) continue;
    h.lines.forEach((_, k) => byLine.set(h.at + k, h.id));
  }

  const out: string[] = [];
  diff.lines.forEach((line, k) => {
    const accepting = byLine.has(k);
    if (line.op === "same") out.push(line.next ?? "");
    else if (line.op === "del") {
      if (accepting) { /* a deletion in an accepted hunk is applied: emit nothing */ }
      else out.push(line.base ?? "");
    } else if (line.op === "add") {
      if (accepting) out.push(line.next ?? "");
    }
  });
  return out.join("\n");
}

export function acceptAll(diff: Diff): Set<string> {
  return new Set(diff.hunks.map((h) => h.id));
}

export function acceptNone(): Set<string> {
  return new Set();
}

/** Cell-level changes, so a move reads as a move rather than a delete plus an insert (DF-4). */
export interface CellChange {
  id: string;
  op: "added" | "removed" | "changed" | "moved";
  /** Human sentence, already past tense: "moved to position 2". */
  summary: string;
}

export function diffCells(
  base: readonly { id: string; source: string }[],
  next: readonly { id: string; source: string }[],
): CellChange[] {
  const out: CellChange[] = [];
  const baseIds = new Set(base.map((c) => c.id));
  const nextIds = new Set(next.map((c) => c.id));

  for (const c of next) {
    if (!baseIds.has(c.id)) out.push({ id: c.id, op: "added", summary: "added" });
  }
  for (const c of base) {
    if (!nextIds.has(c.id)) out.push({ id: c.id, op: "removed", summary: "removed" });
  }
  for (const c of next) {
    const before = base.find((b) => b.id === c.id);
    if (before && before.source !== c.source) out.push({ id: c.id, op: "changed", summary: "edited" });
  }
  // A move: same set of ids, different order.
  if (out.length === 0 && base.length === next.length) {
    const order = (cs: readonly { id: string }[]) => cs.map((c) => c.id).join("|");
    if (order(base) !== order(next)) {
      out.push({ id: next[0]?.id ?? "", op: "moved", summary: "cells reordered" });
    }
  }
  return out;
}
