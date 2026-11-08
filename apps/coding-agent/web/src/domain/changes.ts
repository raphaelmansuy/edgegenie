/** What changed between two versions of a notebook, by cell. Pure.
 *
 * Used when something other than the user wrote the notebook while it was open (the agent, another
 * tab): the editor adopts the new cells and tells the user which ones moved, instead of silently
 * showing a stale copy of a notebook the assistant just said it had changed.
 */
import type { Cell } from "./notebook";

export interface CellChanges {
  /** 1-based positions in the NEW notebook whose content is new or different. */
  changed: number[];
  /** How many cells the notebook lost overall. */
  removed: number;
}

const same = (a: Cell, b: Cell) => a.kind === b.kind && a.source === b.source;

export function sameCells(a: Cell[], b: Cell[]): boolean {
  return a.length === b.length && a.every((c, i) => same(c, b[i]));
}

export function diffCells(before: Cell[], after: Cell[]): CellChanges {
  // A cell that kept its content but moved is not "changed": match by content first, then by position.
  const pool = new Map<string, number>();
  for (const c of before) pool.set(`${c.kind}\u0000${c.source}`, (pool.get(`${c.kind}\u0000${c.source}`) ?? 0) + 1);
  const changed: number[] = [];
  after.forEach((c, i) => {
    const key = `${c.kind}\u0000${c.source}`;
    const left = pool.get(key) ?? 0;
    if (left > 0) pool.set(key, left - 1);
    else changed.push(i + 1);
  });
  // A replaced cell is one change, not a removal plus an addition: only the net loss is a removal.
  return { changed, removed: Math.max(0, before.length - after.length) };
}

/** "2 cells changed", "1 cell added", "a cell removed": the sentence the banner shows. */
export function describeChanges(c: CellChanges, before: number, after: number): string {
  const parts: string[] = [];
  const added = Math.max(0, after - before);
  const edited = Math.max(0, c.changed.length - added);
  if (added) parts.push(`${added} ${added === 1 ? "cell" : "cells"} added`);
  if (edited) parts.push(`${edited} ${edited === 1 ? "cell" : "cells"} changed`);
  if (c.removed) parts.push(`${c.removed} ${c.removed === 1 ? "cell" : "cells"} removed`);
  return parts.join(" · ") || "no visible change";
}
