/** Local drafts: the answer to "my unsaved work must outrank the server's convenience" (A4).
 *
 * Every buffer is written here on a debounce, before any save is attempted. That single rule is
 * what makes the promise in spec 003 CX-5 true: **a lost write is always recoverable**, even though
 * the workspace API cannot offer a conditional write. The draft is the guarantee we can keep.
 *
 * Design notes that matter:
 *  - keyed by document id, not by tab, so reopening the same document finds the draft;
 *  - stores the *version it was based on*, so a recovered draft can be diffed against the server's
 *    current content rather than silently overwriting it;
 *  - bounded: a TTL and a hard cap, with the oldest evicted first, so a long-lived tab cannot fill
 *    `localStorage` and start throwing on every keystroke.
 */

export interface Draft {
  docId: string;
  /** The text the user has. */
  text: string;
  /** The version the buffer was based on, so a recovery knows what it diverged from. */
  basedOn: string;
  /** Epoch ms, for TTL and for "recovered 3 minutes ago". */
  at: number;
}

export const PREFIX = "coding-agent:draft:v1:";
export const TTL_MS = 30 * 24 * 60 * 60 * 1000;   // 30 days: long enough to be a safety net
export const MAX_DRAFTS = 50;

const key = (docId: string) => `${PREFIX}${docId}`;

/** Every draft key currently stored. Tolerates a `localStorage` that throws (private mode). */
export function keys(): string[] {
  try {
    const out: string[] = [];
    for (let i = 0; i < window.localStorage.length; i += 1) {
      const k = window.localStorage.key(i);
      if (k?.startsWith(PREFIX)) out.push(k);
    }
    return out;
  } catch {
    return [];
  }
}

export function read(docId: string, now = Date.now()): Draft | null {
  try {
    const raw = window.localStorage.getItem(key(docId));
    if (!raw) return null;
    const d = JSON.parse(raw) as Draft;
    if (!d || typeof d.text !== "string" || typeof d.at !== "number") return null;
    if (now - d.at > TTL_MS) {
      window.localStorage.removeItem(key(docId));
      return null;
    }
    return d;
  } catch {
    return null;                      // unreadable or disabled storage is not an error to the user
  }
}

export function write(draft: Draft): void {
  try {
    window.localStorage.setItem(key(draft.docId), JSON.stringify(draft));
    evictIfNeeded();
  } catch {
    // Quota or private mode: the editor still works, it just loses the safety net. Never throw from
    // a keystroke path.
  }
}

export function clear(docId: string): void {
  try {
    window.localStorage.removeItem(key(docId));
  } catch { /* ignore */ }
}

/** Keep at most MAX_DRAFTS, dropping the oldest. Called on every write, so it is O(n) over a small
 *  n and never a surprise. */
function evictIfNeeded(now = Date.now()): void {
  const all = keys()
    .map((k) => {
      try { return JSON.parse(window.localStorage.getItem(k) || "null") as Draft | null; }
      catch { return null; }
    })
    .filter((d): d is Draft => !!d);
  const stale = all.filter((d) => now - d.at > TTL_MS);
  for (const d of stale) clear(d.docId);
  const live = all.filter((d) => now - d.at <= TTL_MS).sort((a, b) => b.at - a.at);
  for (const d of live.slice(MAX_DRAFTS)) clear(d.docId);
}

/** A debounce that survives re-renders. The editor calls `schedule` on every change; only the last
 *  one within `ms` reaches storage. */
export function debounce<T>(fn: (v: T) => void, ms: number): ((v: T) => void) & { flush: () => void } {
  let timer: number | undefined;
  let pending: T;
  const flush = () => {
    if (timer === undefined) return;
    window.clearTimeout(timer);
    timer = undefined;
    fn(pending);
  };
  const wrapped = (v: T) => {
    pending = v;
    if (timer !== undefined) window.clearTimeout(timer);
    timer = window.setTimeout(() => {
      timer = undefined;
      fn(v);
    }, ms);
  };
  return Object.assign(wrapped, { flush });
}
