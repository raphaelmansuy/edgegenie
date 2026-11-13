/** What this conversation has spent, and whether the next turn may run. Pure. `[R-24]`.
 *
 *  Mirrors `api/domain/budget.py`. Tokens, not money: a token count is a fact the turn pins record, and a
 *  dollar figure depends on a price list this app does not own.
 *
 *  `limit: 0` means no ceiling, which is the default — and the UI must then say NOTHING rather than
 *  "0 of 0", because a budget meter on an unlimited conversation is a warning about nothing.
 */
export interface BudgetState {
  used: number;
  limit: number;
  fraction: number;
  allowed: boolean;
  verdict: "allow" | "blocked" | "unlimited" | string;
  sentence: string;
  message: string;
  turns: number;
  input: number;
  output: number;
  cached: number;
}

/** Is there a ceiling to draw? A meter for an unlimited conversation is noise. */
export function hasCeiling(b: BudgetState | null | undefined): boolean {
  return Boolean(b && b.limit > 0);
}

/** The line under the meter. Empty when unlimited, so the panel does not claim a limit that is not set. */
export function budgetLine(b: BudgetState | null | undefined): string {
  if (!b) return "";
  if (b.limit <= 0) return "";
  if (!b.allowed) return b.message || "This conversation has reached its budget.";
  return b.sentence;
}

/** A clamped fraction for a bar, safe for `0` and for a limit of `0`. */
export function budgetFraction(b: BudgetState | null | undefined): number {
  if (!b || b.limit <= 0) return 0;
  return Math.min(1, Math.max(0, b.used / b.limit));
}

/** Which colour the bar takes. `bad` only when the turn is actually blocked: 95% is a warning, and a
 *  bar that turns red at 95% is one people stop reading. */
export function budgetTone(b: BudgetState | null | undefined): "ok" | "warn" | "bad" {
  if (!b || b.limit <= 0) return "ok";
  if (!b.allowed) return "bad";
  return b.used / b.limit >= 0.85 ? "warn" : "ok";
}

/** Token counts, short enough for a chip. `1.2k`, `412k`, `1.1M`. */
export function tokens(n: number): string {
  if (!Number.isFinite(n) || n <= 0) return "0";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(n >= 10_000 ? 0 : 1)}k`;
  return String(Math.round(n));
}
