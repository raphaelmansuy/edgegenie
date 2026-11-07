/** Relative time, of the kind a session list needs.
 *
 * A list of sessions with identical truncated titles is unusable: you cannot tell which one you
 * were working in an hour ago. A short relative stamp — "12m", "3h", "Tue" — is the cheapest
 * disambiguator there is, and every mature list (mail, Slack, Linear) carries one.
 *
 * Pure and clock-injectable so the output is testable at fixed instants rather than by mocking a
 * global. Deliberately compact: the rail is 276px wide and the stamp shares a line with a title.
 */

const MINUTE = 60;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/** `now` and `at` are epoch seconds. Returns "" for a missing or nonsensical timestamp, so the
 *  caller can skip the element rather than render "Invalid Date" or a stamp from 1970. */
export function relativeTime(at: number | null | undefined, now: number = Date.now() / 1000): string {
  if (typeof at !== "number" || !Number.isFinite(at) || at <= 0) return "";
  const delta = now - at;
  // A clock skew can put a fresh session slightly in the future; treat that as "just now" rather
  // than printing "-1m".
  if (delta < 0) return "now";
  if (delta < 45) return "now";
  if (delta < HOUR) return `${Math.max(1, Math.round(delta / MINUTE))}m`;
  if (delta < DAY) return `${Math.round(delta / HOUR)}h`;
  if (delta < 7 * DAY) return `${Math.round(delta / DAY)}d`;
  // Past a week a relative number is less useful than the day it happened.
  return new Date(at * 1000).toLocaleDateString(undefined, { weekday: "short" });
}

/** The full value for a `title` attribute: the exact local date and time.
 *  The visible stamp is deliberately imprecise, so the hover has to carry the precise answer. */
export function exactTime(at: number | null | undefined): string {
  if (typeof at !== "number" || !Number.isFinite(at) || at <= 0) return "";
  return new Date(at * 1000).toLocaleString(undefined, {
    weekday: "short", year: "numeric", month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}
