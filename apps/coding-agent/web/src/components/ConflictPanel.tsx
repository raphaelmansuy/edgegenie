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

export function ConflictPanel({ conflict, mine, theirs, onKeepMine, onTakeTheirs, onDismiss }: Props) {
  return (
    <div className="conflict-panel" role="alert">
      <div className="conflict-head">
        <Warning size={15} />
        <strong>Somebody else changed this file</strong>
        <button className="icon-btn conflict-dismiss" aria-label="Dismiss" onClick={onDismiss}>×</button>
      </div>
      <p className="conflict-note">
        {conflict.reason}. Your text is safe: pick what should be on disk.
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
