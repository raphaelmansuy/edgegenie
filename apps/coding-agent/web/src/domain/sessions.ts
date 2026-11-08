/** The conversation history, the way a person looks for one: by day, and by a word they remember.
 *
 * Pure, no React. The rail used to be a flat list in server order, which is fine for five sessions and
 * unusable for fifty (Databricks groups its assistant history by day and searches it). This module is
 * the one place that decides which bucket a session belongs to, so the rail only draws.
 */
export interface SessionLike {
  id: string;
  title: string;
  folder?: string;
  status?: string;
  /** Epoch seconds. Absent for a session created before the field existed. */
  createdAt?: number;
}

export interface SessionGroup<T extends SessionLike = SessionLike> { label: string; items: T[] }

/** What the list shows for a session: its title, or a short id while the title is still the default. */
export function sessionLabel(s: SessionLike): string {
  return !s.title || s.title === "New session" ? s.id.slice(0, 8) : s.title;
}

const DAY = 86_400;

/** Local midnight of the day containing `epoch` seconds. Buckets follow the reader's calendar, not UTC:
 *  a session from 23:50 last night is "Yesterday" at 00:10, whatever the server's clock says. */
function startOfDay(epoch: number): number {
  const d = new Date(epoch * 1000);
  d.setHours(0, 0, 0, 0);
  return d.getTime() / 1000;
}

export function bucketOf(createdAt: number | undefined, now: number): string {
  if (typeof createdAt !== "number" || !Number.isFinite(createdAt) || createdAt <= 0) return "Earlier";
  const today = startOfDay(now);
  if (createdAt >= today) return "Today";               // also covers a clock skewed slightly ahead
  if (createdAt >= today - DAY) return "Yesterday";
  if (createdAt >= today - 7 * DAY) return "Previous 7 days";
  return "Earlier";
}

const ORDER = ["Today", "Yesterday", "Previous 7 days", "Earlier"];

/** A session matches when every word of the query appears in its label or its folder. */
export function matches(s: SessionLike, query: string): boolean {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return true;
  const hay = `${sessionLabel(s)} ${s.folder ?? ""}`.toLowerCase();
  return words.every((w) => hay.includes(w));
}

/** Newest first within a day; days in calendar order; empty days omitted. */
export function groupSessions<T extends SessionLike>(list: T[], query: string, now: number = Date.now() / 1000): SessionGroup<T>[] {
  const by = new Map<string, T[]>();
  for (const s of list) {
    if (!matches(s, query)) continue;
    const key = bucketOf(s.createdAt, now);
    by.set(key, [...(by.get(key) ?? []), s]);
  }
  return ORDER.filter((k) => by.has(k)).map((label) => ({
    label,
    items: [...by.get(label)!].sort((a, b) => (b.createdAt ?? 0) - (a.createdAt ?? 0)),
  }));
}

/** Two letters for an avatar: first and last word of a name, or the part of an e-mail before the `@`. */
export function initials(user: string | null | undefined): string {
  const local = (user ?? "").split("@")[0].trim();
  const words = local.split(/[\s._-]+/).filter(Boolean);
  if (!words.length) return "?";
  const first = words[0][0];
  const last = words.length > 1 ? words[words.length - 1][0] : (words[0][1] ?? "");
  return `${first}${last}`.toUpperCase();
}
