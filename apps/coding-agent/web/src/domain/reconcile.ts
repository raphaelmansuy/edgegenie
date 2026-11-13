/** Keep cell identities across a reload. Pure.
 *
 * A cell's `id` is what React keys it by, and a key change is a remount: the editor is destroyed and
 * rebuilt, the caret and focus are gone, and the page scrolls because every cell collapses to
 * nothing for a frame. When the assistant rewrites a notebook the user is reading, almost every cell
 * is unchanged — so the new cells must inherit the ids of the old ones that are the same.
 *
 * Match by content in order (a longest common subsequence, so an inserted or deleted cell does not
 * shift every id after it); then, inside each gap between matches, pair the leftover old and new
 * cells by position so an EDITED cell keeps its identity and only its text is replaced. Cells that
 * are genuinely new get fresh ids.
 */
import type { Cell } from "./notebook";

let seq = 0;
const fresh = () => `r${Date.now().toString(36)}-${(seq += 1).toString(36)}`;
const same = (a: Cell, b: Cell) => a.kind === b.kind && a.source === b.source;

export function reconcileIds(before: readonly Cell[], after: readonly Cell[]): Cell[] {
  const n = before.length, m = after.length;
  // Bound quadratic work on very large notebooks; preserve identities by exact content queues.
  if (n * m > 250_000) {
    const buckets=new Map<string,string[]>();
    for(const cell of before){const key=cell.kind+"\0"+cell.source;const ids=buckets.get(key) ?? [];ids.push(cell.id);buckets.set(key,ids);}
    const used=new Set<string>();
    return after.map((cell,index)=>{const key=cell.kind+"\0"+cell.source;let id=buckets.get(key)?.shift();if(!id && before[index]?.kind===cell.kind && !used.has(before[index].id))id=before[index].id;if(!id || used.has(id))id=fresh();used.add(id);return {...cell,id};});
  }
  // LCS lengths, suffix form so the walk below goes forward.
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = same(before[i], after[j]) ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const ids: (string | null)[] = new Array(m).fill(null);
  const pairs: [number, number][] = [];
  for (let i = 0, j = 0; i < n && j < m;) {
    if (same(before[i], after[j])) { ids[j] = before[i].id; pairs.push([i, j]); i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) i++;
    else j++;
  }
  // Gaps: leftovers between consecutive matches, paired by position.
  const anchors: [number, number][] = [[-1, -1], ...pairs, [n, m]];
  for (let k = 0; k + 1 < anchors.length; k++) {
    const [i0, j0] = anchors[k], [i1, j1] = anchors[k + 1];
    const olds: number[] = [], news: number[] = [];
    for (let i = i0 + 1; i < i1; i++) olds.push(i);
    for (let j = j0 + 1; j < j1; j++) news.push(j);
    for (let t = 0; t < Math.min(olds.length, news.length); t++) ids[news[t]] = before[olds[t]].id;
  }
  const used = new Set<string>();
  return after.map((c, j) => {
    let id = ids[j];
    if (!id || used.has(id)) id = fresh();
    used.add(id);
    return { ...c, id };
  });
}
