/** One block of a read-only infrastructure page: a title, its own loading state, its own failure.
 *
 * This is the whole isolation story in spec 013 [06 §5] expressed as a component. A project page
 * makes four independent calls; `return_exceptions=True` on the server keeps one denial from
 * blanking the other three, and this keeps the same promise in the DOM — a failed block renders its
 * own error in place and cannot affect a sibling.
 *
 * It is deliberately not generic machinery. Three pages use it, it has four states, and a smaller
 * component would push the states back into every caller.
 */
import type { ReactNode } from "react";
import { Alert, Refresh } from "./Icons";

export type BlockState = "loading" | "ready" | "empty" | "error";

export interface BlockProps {
  title: string;
  /** A count or a one-word state, shown beside the title. Omitted when there is nothing to say. */
  note?: string;
  state: BlockState;
  error?: string;
  /** Rendered only when `state === "ready"`. */
  children?: ReactNode;
  /** What "empty" means HERE: an empty list and a zero count are different sentences. */
  empty?: string;
  onRetry?: () => void;
  /** The action's label, when retrying can help. A refusal gets none ([UI-6], [E-1]). */
  retryLabel?: string;
  /** Extra controls for the block's header, right-aligned. */
  actions?: ReactNode;
}

/** A refusal that a second identical click cannot fix: a permission wall, a missing scope, a name the
 *  platform excludes. Retrying those is a dead end dressed as an action (spec 013 [UI-6], [E-1]).
 *  A transient failure (a 502, a timeout) is the opposite and does offer the button. */
export function isPermanent(error: string): boolean {
  return /PERMISSION_DENIED|CAN MANAGE|required scopes|not granted|does not have access|invalid name|must be/i.test(error);
}

export function Block(p: BlockProps) {
  const permanent = p.state === "error" && p.error ? isPermanent(p.error) : false;
  return (
    <section className="infra-block" data-state={p.state} aria-label={p.title}>
      <header className="infra-block-head">
        <h3 className="infra-block-title">{p.title}</h3>
        {p.note && <span className="infra-block-note">{p.note}</span>}
        <span className="infra-block-spacer" />
        {p.actions}
      </header>
      <div className="infra-block-body">
        {p.state === "loading" && (
          <div className="infra-skeleton" role="status" aria-label={`Loading ${p.title}`}>
            <span className="sk a" /><span className="sk b" />
          </div>
        )}
        {p.state === "error" && (
          <div className="infra-block-error" role="alert">
            <Alert size={14} />
            <div>
              {/* The platform's sentence, verbatim: a paraphrase of a refusal sends the user to the
                  wrong person ([E-1], [E-2]). */}
              <span>{p.error}</span>
              {p.onRetry && !permanent && (
                <button className="btn sm ghost" onClick={p.onRetry}>
                  <Refresh size={12} /> {p.retryLabel ?? "Try again"}
                </button>
              )}
            </div>
          </div>
        )}
        {p.state === "empty" && (
          <>
            <p className="infra-block-empty">{p.empty ?? "Nothing here yet."}</p>
            {/* A note can accompany an empty list: "no resources" and "why that matters" are two
                different sentences, and the second is the useful one (spec 013 [E-15]). */}
            {p.children}
          </>
        )}
        {p.state === "ready" && p.children}
      </div>
    </section>
  );
}

/** A fact, as a label and a value. `—` for a value that could not be read, never `0`
 *  (spec 013 [UI-3], [E-11]). */
export function Fact({ label, value, mono = true }: { label: string; value: ReactNode; mono?: boolean }) {
  return (
    <div className="infra-fact">
      <span className="infra-fact-label">{label}</span>
      <span className={`infra-fact-value${mono ? " is-mono" : ""}`}>{value === "" || value === null || value === undefined ? "—" : value}</span>
    </div>
  );
}

/** A state as a word with a tone. The word is always present: colour is never the only carrier
 *  (spec 013 [UI-4], and [012]'s rule for the dock). */
export function StatePill({ state, tone = "quiet" }: { state: string; tone?: "good" | "busy" | "bad" | "quiet" }) {
  return <span className={`infra-pill tone-${tone}`}>{state}</span>;
}
