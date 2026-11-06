/** Fuzzy matching for the command palette. Pure, no React.
 *
 * A palette is judged by whether the thing you meant comes first after four keystrokes. Substring
 * search fails that test: "opn nb" should find "Open notebook", and "sess" should outrank a session
 * whose *title* happens to contain those letters. So: subsequence matching with bonuses for word
 * boundaries, plus a stable tiebreak that prefers shorter, more specific entries.
 */

export interface Candidate {
  id: string;
  /** What the person reads and matches against. */
  title: string;
  /** Extra searchable text: a path, a session id, a command's synonyms. Matched, never shown as a hit. */
  keywords?: string;
  group: string;
  hint?: string;
  /** Lower sorts first among equally good matches. */
  weight?: number;
  run: () => void;
}

const SEPARATORS = /[\s\-_/.:]/;

/**
 * Score `text` against `query`, or -1 when it does not match at all.
 *
 * Rules, in order of weight:
 *  - a contiguous run of matched characters beats scattered ones (so "note" beats "n-o-t-e");
 *  - a match at a word boundary beats one inside a word (so "nb" finds "New notebook");
 *  - matching at the very start beats matching later.
 */
export function score(text: string, query: string): number {
  if (!query) return 0;
  const t = text.toLowerCase();
  const q = query.toLowerCase().trim();
  if (!q) return 0;

  const direct = t.indexOf(q);
  if (direct !== -1) {
    // An exact substring is always better than a scatter, and earlier is better than later.
    const boundary = direct === 0 || SEPARATORS.test(t[direct - 1] ?? " ");
    return 1000 - direct * 2 + (boundary ? 120 : 0) + (t.length === q.length ? 200 : 0);
  }

  // Subsequence: every query character in order, scoring where it landed.
  let ti = 0;
  let total = 0;
  let streak = 0;
  for (const ch of q) {
    if (ch === " ") { streak = 0; continue; }
    let found = -1;
    while (ti < t.length) {
      if (t[ti] === ch) { found = ti; ti += 1; break; }
      ti += 1;
    }
    if (found === -1) return -1;
    const atBoundary = found === 0 || SEPARATORS.test(t[found - 1] ?? " ");
    streak = streak > 0 && found > 0 && t[found - 1] === q[q.indexOf(ch) - 1] ? streak + 1 : 1;
    total += 10 + (atBoundary ? 25 : 0) + Math.min(streak, 4) * 6 - Math.min(found, 20) / 2;
  }
  return total - t.length / 40;
}

export interface Ranked<T extends Candidate> { candidate: T; score: number }

/** Best matches first. Ties break on weight, then on title length, so the list never jitters. */
export function rank<T extends Candidate>(items: T[], query: string, limit = 12): Ranked<T>[] {
  const q = query.trim();
  // No query is not a search: keep the caller's order, which is curated (recent, then important).
  if (!q) return items.slice(0, limit).map((candidate) => ({ candidate, score: 0 }));
  const out: Ranked<T>[] = [];
  for (const candidate of items) {
    // -1 means "no match"; a discounted keyword score must not become a weak match of its own.
    const title = score(candidate.title, q);
    const keyword = candidate.keywords ? score(candidate.keywords, q) : -1;
    if (title < 0 && keyword < 0) continue;
    const best = Math.max(title, keyword >= 0 ? keyword * 0.8 : -1);
    out.push({ candidate, score: best + (candidate.weight ?? 0) });
  }
  out.sort((a, b) =>
    b.score - a.score
    || (a.candidate.weight ?? 0) - (b.candidate.weight ?? 0)
    || a.candidate.title.length - b.candidate.title.length
    || a.candidate.title.localeCompare(b.candidate.title));
  return out.slice(0, limit);
}

/**
 * Wrap the matched characters so the UI can highlight them.
 *
 * Returns runs of text with a `hit` flag. With no query, one run, no hits. This is what makes a
 * palette feel fast: you can see *why* each row matched.
 */
export function highlight(text: string, query: string): { text: string; hit: boolean }[] {
  const q = query.trim().toLowerCase();
  if (!q) return [{ text, hit: false }];
  const low = text.toLowerCase();
  const runs: { text: string; hit: boolean }[] = [];
  const direct = low.indexOf(q);
  if (direct !== -1) {
    if (direct > 0) runs.push({ text: text.slice(0, direct), hit: false });
    runs.push({ text: text.slice(direct, direct + q.length), hit: true });
    if (direct + q.length < text.length) runs.push({ text: text.slice(direct + q.length), hit: false });
    return runs;
  }
  const marks = new Set<number>();
  let ti = 0;
  for (const ch of q) {
    if (ch === " ") continue;
    while (ti < low.length && low[ti] !== ch) ti += 1;
    if (ti >= low.length) break;
    marks.add(ti);
    ti += 1;
  }
  let current = "";
  let currentHit: boolean | null = null;
  for (let i = 0; i < text.length; i += 1) {
    const hit = marks.has(i);
    if (currentHit === null || hit === currentHit) {
      current += text[i];
      currentHit = hit;
    } else {
      runs.push({ text: current, hit: currentHit });
      current = text[i];
      currentHit = hit;
    }
  }
  if (current) runs.push({ text: current, hit: Boolean(currentHit) });
  return runs;
}
