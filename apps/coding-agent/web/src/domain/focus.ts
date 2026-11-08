/** What a conversation is about. Pure: no React, no DOM.
 *
 * The concept this module exists to make explicit (spec 006 §00 P1): a conversation has a subject,
 * and the subject is data. Before this, "in context" meant "whatever happens to be rendered", which
 * is why the conversation had to occupy the same slot as the document.
 *
 * The rules, each with a reason:
 *  - opening a document sets the document and clears the cell (a new document has no selection);
 *  - selecting a cell sets only the cell (the document is implied);
 *  - closing the document clears everything, because an attachment to a closed file is a lie about
 *    what the next prompt will contain;
 *  - the Chat tab has no focus: it is the general conversation, the dock is the situated one.
 */
import type { Doc, DocKind } from "./docs";

export interface Focus {
  /** `kind:ref` of the open document, or null when nothing is open. */
  docId: string | null;
  /** The document itself, so a binding never needs to look it up in a list. */
  doc: { kind: DocKind; ref: string; name: string } | null;
  /** Index of the selected cell (1-based, as the notebook UI numbers them), or null. */
  cell: number | null;
}

export const NO_FOCUS: Focus = { docId: null, doc: null, cell: null };

export function focusFor(doc: Doc | null | undefined): Focus {
  if (!doc) return NO_FOCUS;
  return { docId: doc.id, doc: { kind: doc.kind, ref: doc.ref, name: doc.name }, cell: null };
}

/** Select a cell, keeping the document. A cell with no document is not a focus. */
export function withCell(focus: Focus, cell: number | null): Focus {
  if (!focus.doc) return NO_FOCUS;
  return { ...focus, cell: cell && cell > 0 ? Math.floor(cell) : null };
}

/** The document closed (or failed to load): nothing is in context any more. */
export function withoutDoc(): Focus {
  return NO_FOCUS;
}

export function sameFocus(a: Focus, b: Focus): boolean {
  return a.docId === b.docId && a.cell === b.cell;
}

/** The folder that contains the focused document — the root an `@` search should start from. */
export function folderOf(focus: Focus): string {
  const ref = focus.doc?.ref ?? "";
  if (!ref.startsWith("/")) return "";
  const cut = ref.lastIndexOf("/");
  return cut <= 0 ? "/" : ref.slice(0, cut);
}

/** A short, human label for the dock header. Never a path: the header is 380 px wide at most. */
export function focusLabel(focus: Focus): string {
  if (!focus.doc) return "nothing open";
  return focus.cell ? `${focus.doc.name} · cell ${focus.cell}` : focus.doc.name;
}

/** The cell reference a binding carries: the path plus the 1-based index as a fragment. */
export function cellRef(focus: Focus): string | null {
  if (!focus.doc || !focus.cell) return null;
  return `${focus.doc.ref}#${focus.cell}`;
}

/** Split a cell reference back into its parts. Returns null for anything else, never guesses. */
export function parseCellRef(ref: string): { path: string; cell: number } | null {
  const at = ref.lastIndexOf("#");
  if (at <= 0) return null;
  const cell = Number(ref.slice(at + 1));
  if (!Number.isInteger(cell) || cell < 1) return null;
  return { path: ref.slice(0, at), cell };
}
