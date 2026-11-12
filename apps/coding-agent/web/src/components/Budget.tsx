/** The two phase-2 surfaces a user needs to SEE: what this conversation may change, and what it spent.
 *
 *  `[R-9]` and `[R-24]`. Both are small and deliberately quiet, because the point is that a user can find
 *  out without having to try:
 *
 *   - a `read-only` session shows a warning chip. A user must not discover the mode by making a request
 *     that is refused.
 *   - a budget meter appears ONLY when a ceiling exists. A meter over an unlimited conversation is a
 *     warning about nothing, and people stop reading bars that are always empty.
 */
import { useEffect, useState } from "react";
import { api } from "../api/client";
import {
  budgetFraction, budgetLine, budgetTone, hasCeiling, tokens, type BudgetState,
} from "../domain/budget";
import { writeModeChip, writeModeHint } from "../domain/writemode";

/** What this conversation may change. Renders nothing for `fenced`, which is the default and needs no
 *  announcement — a chip on every session is noise that hides the one that matters. */
export function WriteModeChip({ mode, onOpen }: { mode?: string; onOpen?: () => void }) {
  const chip = writeModeChip(mode);
  const hint = writeModeHint(mode);
  if (!hint) return null;
  return (
    <button
      type="button"
      className={`pill write-mode ${chip.tone}`}
      onClick={onOpen}
      title={hint}
      aria-label={`Write mode: ${chip.label}. ${hint}`}
    >
      {chip.label}
    </button>
  );
}

/** What this conversation has spent. Hidden entirely when there is no ceiling. */
export function BudgetMeter({ sessionId }: { sessionId: string | null }) {
  const [b, setB] = useState<BudgetState | null>(null);

  useEffect(() => {
    if (!sessionId) {
      setB(null);
      return;
    }
    let live = true;
    // Refresh on the session's turns changing is the caller's job (`turns` prop would be simpler, but this
    // component must also work in the inspector, where no turn list is passed). A failing read leaves the
    // meter absent rather than showing a wrong number.
    api.budget(sessionId).then((r) => { if (live) setB(r); }).catch(() => { if (live) setB(null); });
    return () => { live = false; };
  }, [sessionId]);

  if (!hasCeiling(b)) return null;
  const tone = budgetTone(b);
  const line = budgetLine(b);
  return (
    <div className={`budget ${tone}`} role="group" aria-label="Token budget">
      <div className="budget-head">
        <span>Budget</span>
        <span className="budget-count">
          {tokens(b!.used)} / {tokens(b!.limit)}
        </span>
      </div>
      <div className="budget-bar" aria-hidden>
        <span style={{ width: `${Math.round(budgetFraction(b) * 100)}%` }} />
      </div>
      {line && <p className="budget-line">{line}</p>}
    </div>
  );
}
