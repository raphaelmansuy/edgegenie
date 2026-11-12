import { useState } from "react";
import type { SessionView } from "../domain/events";
import { missionStatus } from "../domain/mission";
import { EMPTY_ROUTE, linkTo } from "../domain/route";
import { canRestore, canStop } from "../domain/compose";
import type { StreamState } from "../domain/stream";

/** One status surface for the dock and full conversation. No fabricated percentage or ETA.
 *
 *  The controls here used to be gated on `conn === "live"` (`const connected = conn === "live"`,
 *  then `disabled={pending || !connected}`). That disabled "Restore agent" and "Stop work" precisely
 *  in the state where a user needs them: a refused stream. A control that could help was switched
 *  off by the symptom, which is specs/012 [F3].
 *
 *  The gate is now `canAct(session)` — is this session writable — because that is the actual
 *  question. Restoring an agent does not need a live stream; it needs a session that can be
 *  restored. Stop is a `POST`; it does not travel over the `EventSource` either.
 */
export function RunStatus({ session, conn, onRestore, onStop, compact = false }: {
  session: SessionView; conn: StreamState; onRestore: () => Promise<void>; onStop: () => Promise<void>;
  compact?: boolean;
}) {
  const [pending, setPending] = useState(false);
  const [notice, setNotice] = useState("");
  if (!session.id || !session.turns.length) return null;
  const status = missionStatus(session, conn);
  const queued = session.turns.filter((t) => t.status === "queued").length;
  const archived = session.status === "archived";
  const active = !archived && (session.status === "streaming" || session.approvals.some((a) => !a.outcome));
  /* One predicate per control, because they are genuinely different questions. `canAct` was a single
     answer for all three, and it disabled Restore exactly when Restore was what the user needed —
     caught by this file's own test. */
  const gate = { status: session.status, requiresResume: session.requiresResume };
  const mayRestore = canRestore(gate);
  const mayStop = canStop(gate);
  const act = async (fn: () => Promise<void>) => {
    setPending(true); setNotice("");
    try { await fn(); } catch (e) { setNotice(e instanceof Error ? e.message : "Could not complete that action. Try again."); }
    finally { setPending(false); }
  };
  return (
    <section className={`run-status is-${status.tone}${compact ? " is-compact" : ""}`} aria-label="Server session status">
      <div className="run-status-heading" role="status" aria-atomic="true">
        <span className={`run-status-icon${status.tone === "running" ? " is-active" : ""}`} aria-hidden="true" />
        <strong>{status.title}</strong>
        {queued > 0 && <span className="run-queued">{queued} queued</span>}
      </div>
      {!compact && <p>{status.detail}</p>}
      <div className="run-status-footer">
        <span className="run-durability">{session.execution?.persistence === "durable" ? "Progress saved" : "Temporary history"}</span>
        <div className="run-status-actions">
          {!compact && <button type="button" className="btn sm ghost" onClick={() => void act(async () => {
            await navigator.clipboard.writeText(linkTo({ ...EMPTY_ROUTE, session: session.id }, window.location));
            setNotice("Conversation link copied. Sign in with the same account to return.");
          })} disabled={pending}>Copy return link</button>}
          {session.requiresResume && !archived && <button type="button" className="btn sm primary"
            disabled={pending || !mayRestore} onClick={() => void act(onRestore)}>
            {pending ? "Restoring…" : "Restore agent"}
          </button>}
          {active && !session.requiresResume && <button type="button" className="btn sm ghost stop"
            disabled={pending || !mayStop} onClick={() => void act(onStop)}>Stop work</button>}
        </div>
      </div>
      {!compact && session.execution?.persistence !== "durable" && <p className="run-storage-note">History lasts until this server restarts.</p>}
      {notice && <p className="run-action-notice" role="status">{notice}</p>}
    </section>
  );
}
