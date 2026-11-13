/** Bounded ID-addressed protocol projections, independent of transcript length. */
export interface AgentNotice { type: string; text: string; description?: string; severity?: string }
export interface Compaction {
  id: string; status: string; summary: unknown[]; error?: string | null; firstSequence: number; turnId?: string;
  meta?: unknown; truncated: boolean;
}
const MAX_BLOCKS = 100, MAX_CHARS = 65536, MAX_COMPACTIONS = 20;
function bounded(blocks: unknown[]) {
  const summary: unknown[] = [];
  let size = 0;
  for (const block of blocks.slice(0, MAX_BLOCKS)) {
    const length = JSON.stringify(block)?.length ?? 0;
    if (size + length > MAX_CHARS) break;
    summary.push(block); size += length;
  }
  return { summary, truncated: summary.length < blocks.length };
}
export function patchCompaction(rows: Compaction[] = [], event: Record<string, unknown>): Compaction[] {
  if (typeof event.compactionId !== "string" || !event.compactionId) return rows;
  const index = rows.findIndex(r => r.id === event.compactionId);
  const prior: Compaction = index < 0
    ? { id: event.compactionId, status: "in_progress", summary: [], truncated: false, firstSequence: Number(event.seq ?? 0), turnId: typeof event.turnId === "string" ? event.turnId : undefined }
    : rows[index];
  let next = { ...prior };
  if (typeof event.status === "string") next.status = event.status;
  if ("summary" in event) {
    next = { ...next, ...bounded(Array.isArray(event.summary) ? event.summary : []) };
  } else if ("content" in event) {
    const value = bounded([...prior.summary, event.content]);
    next = { ...next, ...value, truncated: prior.truncated || value.truncated };
  }
  if ("error" in event) next.error = typeof event.error === "string" ? event.error.slice(0, 4096) : null;
  if (!("content" in event) && "_meta" in event) next.meta = event._meta === null ? null : bounded([event._meta]).summary[0] ?? null;
  return (index < 0 ? [...rows, next] : rows.map((r, i) => i === index ? next : r)).slice(-MAX_COMPACTIONS);
}
