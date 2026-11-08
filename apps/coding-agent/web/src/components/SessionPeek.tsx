/** The conversation, in one strip, for when the assistant is not on screen.
 *
 * A document is open and the assistant is hidden (a drawer below 1136 px, or hidden by choice): the
 * user typed a request in the notebook's own composer and the conversation lives somewhere they
 * cannot see. This strip is the answer to "where did my request go?": what the agent is doing right
 * now, whether it needs the user, how it ended, and one button to open the thread.
 */
import { peekOf } from "../domain/peek";
import type { SessionView } from "../domain/events";
import { Alert, Check } from "./Icons";
import { LogoMark } from "./Logo";

export function SessionPeek({ session, onOpen, onStop }: {
  session: SessionView; onOpen: () => void; onStop: () => void;
}) {
  const p = peekOf(session);
  return (
    <div className={`session-peek is-${p.state}`} role="status" aria-live="polite" aria-label="Conversation status">
      <span className="session-peek-ico" aria-hidden>
        {p.state === "working" ? <span className="spin" /> : p.state === "done" ? <Check size={13} />
          : p.state === "idle" ? <LogoMark size={13} /> : <Alert size={13} />}
      </span>
      <span className="session-peek-text">
        <strong>{p.headline}</strong>
        {p.detail && <span className="session-peek-detail"> · {p.detail}</span>}
      </span>
      {p.state === "working" && <button className="btn ghost session-peek-stop" onClick={onStop}>Stop</button>}
      <button className="btn session-peek-open" onClick={onOpen}>
        {p.state === "waiting" ? "Review" : "Show conversation"}
      </button>
    </div>
  );
}
