/** What a paged tool result means to a reader. Pure, no React.
 *
 *  Mirrors `api/domain/payload.py`. A tool reply is either whole, or a **window** that says how much of
 *  the world it contains (`returned`, `total`, `next_offset`). Before `[R-3]` a reply over the budget was
 *  a byte-slice of serialised JSON — unparseable — so a card had nothing to say and an agent reported a
 *  fragment as the truth.
 *
 *  The one sentence this module exists to produce: **"38 of 200 tables"**. A number without its total is
 *  how a page implies it showed everything.
 */

export interface PageInfo {
  /** How many items this reply carries. */
  returned: number;
  /** How many exist. Equal to `returned` when the reply is whole. */
  total: number;
  /** Where the next page starts, or `null` when this is everything. */
  nextOffset: number | null;
  /** True when a single item exceeded the budget and was returned whole. */
  oversize?: boolean;
}

/** Read a window out of a tool result, tolerating a reply that has none. */
export function pageOf(payload: unknown): PageInfo | null {
  if (!payload || typeof payload !== "object") return null;
  const p = payload as Record<string, unknown>;
  const returned = Number(p.returned);
  const total = Number(p.total);
  if (!Number.isFinite(returned) || !Number.isFinite(total)) return null;
  const next = p.next_offset;
  return {
    returned,
    total,
    nextOffset: next === null || next === undefined ? null : Number(next),
    oversize: p.truncated === true && next === null,
  };
}

/** The sentence beside a tool card. Empty when the reply is whole, because "200 of 200" is noise. */
export function pageLabel(info: PageInfo | null): string {
  if (!info) return "";
  if (info.oversize) return "1 item, larger than the page limit";
  if (info.nextOffset === null) return "";
  const noun = info.total === 1 ? "item" : "items";
  return `${info.returned} of ${info.total} ${noun}`;
}

/** Does this reply leave the agent (and the reader) knowing it has not seen everything? */
export function isPartial(info: PageInfo | null): boolean {
  return Boolean(info && info.nextOffset !== null);
}

/** How far through the data this page is, for a progress bar. `null` when it is whole. */
export function progress(info: PageInfo | null): number | null {
  if (!info || info.total <= 0 || info.nextOffset === null) return null;
  return Math.min(1, Math.max(0, info.returned / info.total));
}
