import { explain } from "../domain/errors";
import { Alert, Refresh } from "./Icons";

/**
 * One way to show a failed workspace call. A title that says what happened, a line that says what to
 * do, and a Retry only when retrying can help: a refusal is not fixed by asking again.
 */
export function PaneError({ message, onRetry, indent = 0 }: {
  message: string; onRetry?: () => void; indent?: number;
}) {
  const e = explain(message);
  return (
    <div className={`pane-error kind-${e.kind}`} role="alert" style={indent ? { marginLeft: indent } : undefined}>
      <Alert size={14} className="pane-error-icon" />
      <div className="pane-error-text">
        <strong>{e.title}</strong>
        <span>{e.detail}</span>
        {/* An action that resolves the cause, before any retry. A stale sign-in cannot be retried
            away — the token is already minted — so a retry button would be the dead end this spec
            keeps removing (spec 013 [UI-6], [E-1]). */}
        {e.action && (
          <a className="btn sm" href={e.action.href} style={{ alignSelf: "flex-start" }}>
            {e.action.label}
          </a>
        )}
        {onRetry && e.retryable && (
          <button className="btn sm ghost" onClick={onRetry}><Refresh size={12} /> Try again</button>
        )}
      </div>
    </div>
  );
}
