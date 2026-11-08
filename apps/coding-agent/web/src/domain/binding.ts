/** What a message carries, derived from one focus. Pure.
 *
 * One function decides this for both composers (the centre's and the dock's), so the two placements
 * cannot disagree about what the next prompt contains (spec 006 FX-4).
 *
 * The rule that matters most: a cell binding **supersedes** its document. Sending the notebook and
 * one of its cells sends the same text twice and spends the context budget on a duplicate.
 */
import type { Attachment } from "./events";
import { cellRef, type Focus } from "./focus";

export function attachmentsFor(focus: Focus): Attachment[] {
  const doc = focus.doc;
  if (!doc) return [];
  if (focus.cell) {
    const ref = cellRef(focus);
    if (ref) {
      return [{ kind: "cell", ref, name: `${doc.name} · cell ${focus.cell}` }];
    }
  }
  return [{ kind: doc.kind, ref: doc.ref, name: doc.name }];
}

/** The auto chip shown in a composer: the focus, when there is one. */
export function autoAttachment(focus: Focus): Attachment | null {
  const items = attachmentsFor(focus);
  return items.length === 1 ? items[0] : null;
}
