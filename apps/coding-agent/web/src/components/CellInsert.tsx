/** The seam between two cells: add one here. Code, text, or let the agent write it.
 *
 * Databricks shows `+ Code  + Text  ✦ Genie Code` in the gap under a cell. The gap is the natural
 * place to add a cell, and it needs no toolbar travel. The controls are always in the tab order and
 * appear on hover or focus, so a keyboard user can reach them and a mouse user is not shown clutter.
 * The row after the last cell is always visible: it is the first thing a person looks for.
 */
import { insertLabel } from "../domain/cellprompt";
import { Plus, Sparkle } from "./Icons";

export function CellInsert({ after, total, always, onCode, onText, onAgent }: {
  /** Number of cells above this seam: 0 is the top, `total` is the end. */
  after: number;
  total: number;
  always?: boolean;
  onCode: () => void;
  onText: () => void;
  onAgent?: () => void;
}) {
  const where = insertLabel(after, total);
  return (
    <div className={`cell-insert${always ? " is-always" : ""}`} role="group" aria-label={where}>
      <span className="cell-insert-rule" aria-hidden />
      <span className="cell-insert-actions">
        <button type="button" className="cell-insert-btn" onClick={onCode} aria-label={`${where}: code`}><Plus size={12} /> Code</button>
        <button type="button" className="cell-insert-btn" onClick={onText} aria-label={`${where}: text`}><Plus size={12} /> Text</button>
        {onAgent && (
          <button type="button" className="cell-insert-btn is-agent" onClick={onAgent} aria-label={`${where}: generate with the agent`}>
            <Sparkle size={12} /> Generate
          </button>
        )}
      </span>
      <span className="cell-insert-rule" aria-hidden />
    </div>
  );
}
