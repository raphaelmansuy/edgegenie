/** A conflict is a choice, never a verdict (spec 003 CX-3).
 *
 * The workspace API cannot promise "no lost writes"; it has no conditional write. So the product
 * promises something it can keep: **a lost write is always recoverable, and you are always told.**
 * This panel is that promise with buttons. It never says "your changes were discarded".
 */
import { Warning } from "./Icons";

export interface ConflictInfo {
  path: string;
  /** The server's version token, or null when it would not say. */
  current: string | null;
  /** The version this buffer was based on. */
  yours: string | null;
  reason: string;
}

interface Props {
  conflict: ConflictInfo;
  /** The text the user has, so "keep mine" is concrete. */
  mine: string;
  /** The server's text when it is known; null when the panel cannot fetch it. */
  theirs: string | null;
  onKeepMine: () => void;
  onTakeTheirs: () => void;
  onDismiss: () => void;
}

/** The reason, unless it only repeats the heading. */
function explain(c: { reason: string; yours: string | null; current: string | null }): string {
  const generic = /somebody else changed this file/i.test(c.reason);
  if (!generic && c.reason.trim()) {
    return c.reason.trim().replace(/\.?$/, ".").replace(/^./, (m) => m.toUpperCase());
  }
  // Say which version is on disk and which is in the buffer: the two facts a person needs.
  if (c.current && c.yours && c.current !== c.yours) {
    return "This file was written by someone else after you opened it.";
  }
  return "This file changed while you were editing it.";
}

export function ConflictPanel({ conflict, mine, theirs, onKeepMine, onTakeTheirs, onDismiss }: Props) {
  return (
    <div className="conflict-panel" role="alert">
      <div className="conflict-head">
        <Warning size={15} />
        <strong>Somebody else changed this file</strong>
        <button className="icon-btn conflict-dismiss" aria-label="Dismiss" onClick={onDismiss}>×</button>
      </div>
      {/* The heading already says "somebody else changed this file", and the server sends exactly
          that sentence as a fallback reason — so printing it again read as a stutter. Show the
          reason only when it adds something, and always say the one thing that matters: nothing is
          lost yet. */}
      <p className="conflict-note">
        {explain(conflict)} Your text is safe: pick what should be on disk.
      </p>
      <div className="conflict-actions">
        <button className="btn primary sm" onClick={onKeepMine}>
          Keep mine ({mine.split("\n").length} lines)
        </button>
        <button className="btn sm" onClick={onTakeTheirs}>
          Take theirs{theirs === null ? "" : ` (${theirs.split("\n").length} lines)`}
        </button>
      </div>
      <p className="conflict-hint">
        Keeping yours writes your text over theirs and keeps a draft of both.
      </p>
    </div>
  );
}
