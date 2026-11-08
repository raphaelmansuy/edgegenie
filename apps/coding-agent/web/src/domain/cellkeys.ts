/** The notebook's keyboard model, as data. Pure.
 *
 * Two modes, as in Databricks and Jupyter:
 *   EDIT     the caret is in a cell. Typing is text; only a few chords act on the cell.
 *   COMMAND  the cell itself is selected (Esc, or a click beside the text). Single letters act.
 *
 * Keeping the table here — not in an onKeyDown ladder — is what makes it testable and what stops the
 * two modes from disagreeing about what Shift+Enter means.
 */
export type Advance = "stay" | "next" | "insert";

export type CellCommand =
  | { type: "select"; to: "prev" | "next" | "first" | "last" }
  | { type: "edit" }
  | { type: "insert"; where: "above" | "below" }
  | { type: "delete" }
  | { type: "convert"; kind: "code" | "markdown" }
  | { type: "move"; by: -1 | 1 }
  | { type: "undo" }
  | { type: "run"; advance: Advance }
  | { type: "ask" };

export interface KeyLike { key: string; shiftKey: boolean; metaKey: boolean; ctrlKey: boolean; altKey: boolean }

/** The run chords, shared by both modes. Databricks: Shift+Enter run & next, ⌘/Ctrl+Enter run,
 *  Alt+Enter run & insert below. */
export function runChord(e: KeyLike): CellCommand | null {
  if (e.key !== "Enter") return null;
  if (e.shiftKey && !e.metaKey && !e.ctrlKey && !e.altKey) return { type: "run", advance: "next" };
  if ((e.metaKey || e.ctrlKey) && !e.shiftKey && !e.altKey) return { type: "run", advance: "stay" };
  if (e.altKey && !e.shiftKey && !e.metaKey && !e.ctrlKey) return { type: "run", advance: "insert" };
  return null;
}

/** Command-mode keys. `armed` is "D was pressed once": DD deletes, as in Databricks and Jupyter. */
export function commandKey(e: KeyLike, armed: boolean): { command: CellCommand | null; armed: boolean } {
  const none = { command: null, armed: false };
  const run = runChord(e);
  if (run) return { command: run, armed: false };
  const mod = e.metaKey || e.ctrlKey;
  const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;

  if (e.altKey && !mod && !e.shiftKey && (k === "ArrowUp" || k === "ArrowDown")) {
    return { command: { type: "move", by: k === "ArrowUp" ? -1 : 1 }, armed: false };
  }
  if (mod && !e.shiftKey && !e.altKey) {
    if (k === "z") return { command: { type: "undo" }, armed: false };
    if (k === "i") return { command: { type: "ask" }, armed: false };
    return none;               // every other chord belongs to the browser or the app
  }
  if (e.altKey || e.shiftKey) return none;

  switch (k) {
    case "ArrowUp": case "k": return { command: { type: "select", to: "prev" }, armed: false };
    case "ArrowDown": case "j": return { command: { type: "select", to: "next" }, armed: false };
    case "Home": return { command: { type: "select", to: "first" }, armed: false };
    case "End": return { command: { type: "select", to: "last" }, armed: false };
    case "Enter": return { command: { type: "edit" }, armed: false };
    case "a": return { command: { type: "insert", where: "above" }, armed: false };
    case "b": return { command: { type: "insert", where: "below" }, armed: false };
    case "m": return { command: { type: "convert", kind: "markdown" }, armed: false };
    case "y": return { command: { type: "convert", kind: "code" }, armed: false };
    case "z": return { command: { type: "undo" }, armed: false };
    case "d": return armed ? { command: { type: "delete" }, armed: false } : { command: null, armed: true };
    default: return none;
  }
}
