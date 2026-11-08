/** What a cell-level request says to the agent. Pure: no React, no DOM.
 *
 * Genie Code lets you type an instruction on the cell itself (`⌘I`), insert a generated cell between
 * two others, and fix a failed cell in one click. All three are the same act (a message bound to one
 * cell) with different words, so the words live here, once, and are tested. The binding (which cell)
 * travels as an attachment; the text only says what to do with it and what NOT to touch.
 *
 * The rule in every prompt: **say what must stay unchanged.** An instruction scoped to one cell that
 * does not say so is an invitation to rewrite the notebook.
 */

export interface CellIntent { id: "explain" | "fix" | "optimize" | "comment"; label: string; instruction: string }

/** The four things people do to one cell, offered as chips so the common case is one click. */
export const CELL_INTENTS: CellIntent[] = [
  { id: "explain", label: "Explain", instruction: "Explain what this cell does, in plain English. Do not change anything." },
  { id: "fix", label: "Fix", instruction: "Find what is wrong with this cell (check every table and column name it uses), fix it, and show the evidence that the fix works." },
  { id: "optimize", label: "Optimise", instruction: "Make this cell faster or simpler without changing its result, and show that the result is the same." },
  { id: "comment", label: "Comment", instruction: "Add short, accurate comments to this cell. Do not change its behaviour." },
];

/** An instruction aimed at an existing cell. `n` is 1-based, as the notebook numbers its cells. */
export function editPrompt(n: number, instruction: string): string {
  const say = instruction.trim();
  return `Cell ${n}: ${say}\n\nChange only cell ${n}.`;
}

/** A new cell after cell `after` (0 means "at the top"). The instruction describes the new cell. */
export function insertPrompt(after: number, instruction: string): string {
  const say = instruction.trim();
  const where = after <= 0 ? "as the first cell" : `right after cell ${after}`;
  return `Add a new cell ${where}: ${say}\n\nDo not change any existing cell.`;
}

const MAX_ERROR = 1200;

/** Keep the head of an error: the engine puts the cause first and a long search path after it. */
export function clipError(error: string, max = MAX_ERROR): string {
  const e = (error ?? "").trim();
  return e.length <= max ? e : `${e.slice(0, max).trimEnd()} …`;
}

/** Diagnose and repair a failed cell, quoting the engine's own words so the agent starts from the cause. */
export function fixPrompt(n: number, error: string): string {
  const err = clipError(error);
  const quote = err ? `\n\nThe engine said:\n${err.split("\n").map((l) => `> ${l}`).join("\n")}` : "";
  return `Cell ${n} failed.${quote}\n\n`
    + "Find the cause (check the names it refers to against the real tables), fix this cell only, "
    + "and run it again to prove it works.";
}

/** The label an insert control shows for its position: never an index the user has to translate. */
export function insertLabel(after: number, total: number): string {
  if (after <= 0) return "Add a cell at the top";
  if (after >= total) return "Add a cell at the end";
  return `Add a cell after cell ${after}`;
}
