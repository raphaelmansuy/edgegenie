/** The notebook's keyboard model, as data. Pure.
 *
 * Two modes, as in Databricks and Jupyter (docs, 27 Oct 2026):
 *   EDIT     the caret is in a cell. Typing is text; only chords act on the cell.
 *   COMMAND  the cell itself is selected (Esc, or a click in the gutter). Single letters act.
 *
 * The table lives here, not in an onKeyDown ladder, so the two modes cannot disagree about what
 * Shift+Enter means, and a double-tap (DD, GG, II, 00) is a value the tests can hold.
 */
export type Advance = "stay" | "next" | "insert";
export type RunSpan = "all" | "above" | "below";

export type CellCommand =
  | { type: "select"; to: "prev" | "next" | "first" | "last"; extend?: boolean }
  | { type: "edit" }
  | { type: "insert"; where: "above" | "below" }
  | { type: "delete" }
  | { type: "convert"; kind: "code" | "markdown" }
  | { type: "move"; by: -1 | 1 }
  | { type: "undo" }
  | { type: "run"; advance: Advance }
  | { type: "runSpan"; span: RunSpan }
  | { type: "ask" }
  | { type: "output" }
  | { type: "merge" }
  | { type: "split" }
  | { type: "clipboard"; op: "copy" | "cut" | "paste" }
  | { type: "selectAll" }
  | { type: "clearOutputs" }
  | { type: "stop" }
  | { type: "scroll"; by: 1 | -1 }
  | { type: "shortcuts" };

/** What command mode does, in the order a person scans a sheet. One list, rendered by the sheet. */
export const COMMAND_HELP: { keys: string; label: string }[] = [
  { keys: "Enter", label: "Edit the selected cell" },
  { keys: "Esc", label: "Leave the text and select the cell" },
  { keys: "A / B", label: "Insert a code cell above / below" },
  { keys: "D D", label: "Delete the selected cell" },
  { keys: "M / Y", label: "Convert to markdown / code" },
  { keys: "Shift+M", label: "Merge with the cell below" },
  { keys: "O", label: "Show or hide this cell's output" },
  { keys: "J K  or  ↑ ↓", label: "Select the next or previous cell" },
  { keys: "Shift+↑ ↓", label: "Add the next cell to the selection" },
  { keys: "G G", label: "Go to the first cell" },
  { keys: "Shift+G", label: "Go to the last cell" },
  { keys: "⌘C ⌘X ⌘V", label: "Copy, cut or paste cells" },
  { keys: "⌘A", label: "Select every cell" },
  { keys: "Shift+Enter", label: "Run, then move to the next cell" },
  { keys: "⌘Enter", label: "Run the selected cells" },
  { keys: "Alt+Enter", label: "Run, then insert a cell below" },
  { keys: "Alt+Shift+Enter", label: "Run all" },
  { keys: "Alt+Shift+↑", label: "Run all above (not this cell)" },
  { keys: "Alt+Shift+↓", label: "Run this cell and everything below" },
  { keys: "I I", label: "Stop the run" },
  { keys: "0 0", label: "Clear every output" },
  { keys: "Space", label: "Scroll down (Shift+Space scrolls up)" },
  { keys: "H", label: "Keyboard shortcuts" },
];

export interface KeyLike { key: string; shiftKey: boolean; metaKey: boolean; ctrlKey: boolean; altKey: boolean }

const ARMS = new Set(["d", "g", "0", "i"]);

/** The run chords, shared by both modes. Databricks: Shift+Enter run and next, ⌘/Ctrl+Enter run,
 *  Alt+Enter run and insert below. */
export function runChord(e: KeyLike): CellCommand | null {
  if (e.key !== "Enter") return null;
  if (e.shiftKey && !e.metaKey && !e.ctrlKey && !e.altKey) return { type: "run", advance: "next" };
  if ((e.metaKey || e.ctrlKey) && !e.shiftKey && !e.altKey) return { type: "run", advance: "stay" };
  if (e.altKey && !e.shiftKey && !e.metaKey && !e.ctrlKey) return { type: "run", advance: "insert" };
  return null;
}

/** Run a range. Databricks (shared shortcuts): Alt+Shift+Enter all, Alt+Shift+Up above, Alt+Shift+Down
 *  below. Above does not include the current cell; below does. */
export function rangeChord(e: KeyLike): CellCommand | null {
  if (!e.altKey || !e.shiftKey || e.metaKey || e.ctrlKey) return null;
  if (e.key === "Enter") return { type: "runSpan", span: "all" };
  if (e.key === "ArrowUp") return { type: "runSpan", span: "above" };
  if (e.key === "ArrowDown") return { type: "runSpan", span: "below" };
  return null;
}

/** Command-mode keys. `armed` is the first tap of a double (`d`, `g`, `0`, `i`); "" means unarmed. */
export function commandKey(e: KeyLike, armed: string): { command: CellCommand | null; armed: string } {
  const hit = (command: CellCommand) => ({ command, armed: "" });
  const none = (next = "") => ({ command: null as CellCommand | null, armed: next });

  const run = runChord(e);
  if (run) return hit(run);
  const range = rangeChord(e);
  if (range) return hit(range);

  const mod = e.metaKey || e.ctrlKey;
  const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;

  if (e.altKey && !mod && !e.shiftKey && (e.key === "ArrowUp" || e.key === "ArrowDown")) {
    return hit({ type: "move", by: e.key === "ArrowUp" ? -1 : 1 });
  }
  if (mod && !e.shiftKey && !e.altKey) {
    if (k === "z") return hit({ type: "undo" });
    if (k === "i") return hit({ type: "ask" });
    if (k === "a") return hit({ type: "selectAll" });
    if (k === "c") return hit({ type: "clipboard", op: "copy" });
    if (k === "x") return hit({ type: "clipboard", op: "cut" });
    if (k === "v") return hit({ type: "clipboard", op: "paste" });
    return none();
  }
  if (e.shiftKey && !mod && !e.altKey) {
    if (k === "g") return hit({ type: "select", to: "last" });
    if (k === "m") return hit({ type: "merge" });
    if (e.key === " ") return hit({ type: "scroll", by: -1 });
    if (e.key === "ArrowUp" || e.key === "ArrowDown") {
      return hit({ type: "select", to: e.key === "ArrowUp" ? "prev" : "next", extend: true });
    }
    return none();
  }
  if (e.altKey || e.shiftKey) return none();

  if (armed && k === armed && ARMS.has(armed)) {
    if (armed === "d") return hit({ type: "delete" });
    if (armed === "g") return hit({ type: "select", to: "first" });
    if (armed === "0") return hit({ type: "clearOutputs" });
    return hit({ type: "stop" });
  }

  switch (k) {
    case "ArrowUp": case "k": case "p": return hit({ type: "select", to: "prev" });
    case "ArrowDown": case "j": case "n": return hit({ type: "select", to: "next" });
    case "Home": return hit({ type: "select", to: "first" });
    case "End": return hit({ type: "select", to: "last" });
    case "Enter": return hit({ type: "edit" });
    case "a": return hit({ type: "insert", where: "above" });
    case "b": return hit({ type: "insert", where: "below" });
    case "m": return hit({ type: "convert", kind: "markdown" });
    case "y": return hit({ type: "convert", kind: "code" });
    case "z": return hit({ type: "undo" });
    case "o": return hit({ type: "output" });
    case "h": return hit({ type: "shortcuts" });
    case " ": return hit({ type: "scroll", by: 1 });
    case "d": case "g": case "0": case "i": return none(k);
    default: return none();
  }
}

/** The sheet and the editor agree on the event that opens shortcuts from command mode (H). */
export const OPEN_SHORTCUTS = "opengenie:shortcuts";
