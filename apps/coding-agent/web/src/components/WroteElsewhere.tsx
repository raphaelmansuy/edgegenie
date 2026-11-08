/** "The agent wrote a different file" — said out loud, in the centre, with one click to see it.
 *
 * The failure this exists for (seen on the deployed app): a notebook at `/Repos/.../demo/x` was open,
 * the user asked to add a KPI, and the agent wrote `agent_scratch/x_with_kpi` because it may not write
 * into a repo. The write succeeded — the dock listed it — but the centre, which is where the user is
 * looking, did not change and said nothing. A silent screen reads as "nothing happened", and the user
 * concludes the refresh is broken. It is not the refresh: it is a different file.
 *
 * So the screen says which file, and offers to open it, and can be dismissed.
 */
import { Close, FileIcon } from "./Icons";

interface Props {
  /** One line naming what the agent wrote, e.g. "x_with_kpi". */
  name: string;
  /** The folder it went to, so the user can see it is not where the open file is. */
  folder: string;
  onOpen: () => void;
  onDismiss: () => void;
}

export function WroteElsewhere({ name, folder, onOpen, onDismiss }: Props) {
  return (
    <div className="wrote-elsewhere" role="status">
      <FileIcon size={14} />
      <span>
        <strong>The agent wrote a different file</strong> · <code>{name}</code> in <code>{folder}</code>
        <span className="wrote-elsewhere-why"> — this one is outside the folder the agent may write to, so it made a copy instead.</span>
      </span>
      <button className="btn primary sm" onClick={onOpen}>Open it</button>
      <button className="btn ghost sm" aria-label="Dismiss" onClick={onDismiss}><Close size={12} /></button>
    </div>
  );
}
