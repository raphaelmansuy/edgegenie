/** StreamNotice: the one place a non-live connection state becomes words and an action.
 *
 * Before this, three components answered the same question with three vocabularies: the dock had a
 * passive `.pill`, `mission.ts` had a paragraph, and `RunStatus` had its own heading. None of them
 * offered anything to do, so "reconnecting…" was a dead end dressed as a transition — and the four
 * controls that could have helped were disabled by the same flag that produced the word
 * (specs/012 02 §F2, §F3).
 *
 * Two rules, both requirements:
 *
 *   P2  every persistent state names its exit, next to the word that announces it.  [ST-4] [ST-5]
 *   P4  the wording and the action come from `describe()`, so a new state cannot be silent.
 *
 * The `connecting` case renders a word and NO action on purpose: it resolves in milliseconds, and a
 * Retry button beside a spinner teaches the user to press it.
 */
import { describe as describeState, type StreamState } from "../domain/stream";
import { Alert, Refresh } from "./Icons";

export function StreamNotice({ state, onRetry, onNew, compact = false }: {
  state: StreamState;
  /** Re-open the stream. Always available for `reconnecting` and `closed`. */
  onRetry: () => void;
  /** Start a fresh conversation. The only genuine way out of a session the server no longer has. */
  onNew?: () => void;
  compact?: boolean;
}) {
  const d = describeState(state);
  // `idle` and `live` say nothing: a healthy stream needs no announcement, and a permanent green
  // badge is noise that trains people to stop reading the one indicator that matters.
  if (!d.word) return null;

  // `closed` is assertive because it is a terminal state that may mean lost work; the others are
  // polite because they resolve on their own. That is the difference between an interruption and a
  // background note. [ST-7]
  const role = d.urgent ? "alert" : "status";

  return (
    <div className={`stream-notice is-${state.kind}${compact ? " is-compact" : ""}`}
      role={role} aria-atomic="true" data-state={state.kind}>
      <span className="stream-notice-dot" aria-hidden="true" />
      <span className="stream-notice-word">{d.word}</span>
      {/* The action sits IMMEDIATELY after the word, not elsewhere in the header: one control group,
          so "what is wrong" and "what to do" are read together. [ST-4] [ST-5] */}
      {d.action !== "none" && (
        <span className="stream-notice-actions">
          <button type="button" className="btn sm ghost stream-retry" onClick={onRetry}
            title="Try the connection again now">
            <Refresh size={12} /> Retry
          </button>
          {d.action === "retry-or-new" && onNew && (
            <button type="button" className="btn sm primary stream-new" onClick={onNew}
              title="Start a new conversation">
              New conversation
            </button>
          )}
        </span>
      )}
      {!compact && d.detail && (
        <p className="stream-notice-detail">
          {d.urgent && <Alert size={11} aria-hidden />} {d.detail}
        </p>
      )}
    </div>
  );
}
