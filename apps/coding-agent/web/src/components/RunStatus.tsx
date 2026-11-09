import { useState } from "react";
import type { SessionView } from "../domain/events";
import { missionStatus } from "../domain/mission";
import { EMPTY_ROUTE, linkTo } from "../domain/route";

/** One status surface for the dock and full conversation. No fabricated percentage or ETA. */
export function RunStatus({ session, conn, onRestore, onStop }: {
  session: SessionView; conn: string; onRestore: () => Promise<void>; onStop: () => Promise<void>;
}) {
  const [pending, setPending] = useState(false);
  const [notice, setNotice] = useState("");
  if (!session.id || !session.turns.length) return null;
  const status = missionStatus(session, conn);
  const queued = session.turns.filter((t) => t.status === "queued").length;
  const active = session.status === "streaming" || session.approvals.some((a) => !a.outcome);
  const connected = conn === "live";
  const act = async (fn: () => Promise<void>) => {
    setPending(true); setNotice("");
    try { await fn(); } catch (e) { setNotice(e instanceof Error ? e.message : "Could not complete that action. Try again."); }
    finally { setPending(false); }
  };
  return (
    <section className={`run-status is-${status.tone}`} aria-label="Server session status">
      <div className="run-status-heading" role="status" aria-atomic="true">
        <span className={`run-status-icon${status.tone === "running" ? " is-active" : ""}`} aria-hidden="true" />
        <strong>{status.title}</strong>
        {queued > 0 && <span className="run-queued">{queued} queued</span>}
      </div>
      <p>{status.detail}</p>
      <div className="run-status-footer">
        <span className="run-durability">{session.execution?.persistence === "durable" ? "Progress saved" : "Temporary history"}</span>
        <div className="run-status-actions">
          <button type="button" className="btn sm ghost" onClick={() => void act(async () => {
            await navigator.clipboard.writeText(linkTo({ ...EMPTY_ROUTE, session: session.id }, window.location));
            setNotice("Conversation link copied. Sign in with the same account to return.");
          })} disabled={pending}>Copy return link</button>
          {session.requiresResume && <button type="button" className="btn sm primary"
            disabled={pending || !connected} onClick={() => void act(onRestore)}>
            {pending ? "Restoring…" : "Restore agent"}
          </button>}
          {active && !session.requiresResume && <button type="button" className="btn sm ghost stop"
            disabled={pending || !connected} onClick={() => void act(onStop)}>Stop work</button>}
        </div>
      </div>
      {session.execution?.persistence !== "durable" && <p className="run-storage-note">History lasts until this server restarts.</p>}
      {notice && <p className="run-action-notice" role="status">{notice}</p>}
    </section>
  );
}
