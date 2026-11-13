/** Slash commands and prompt history for the composer. Pure, no React.
 *
 * Genie Code offers `/` for commands and Up/Down for history. Both are cheap, both are what people
 * reach for, and neither should require remembering a menu.
 */

export interface Command { name: string; hint: string; insert: string; source?: "Template" | "Agent" | "Skill" }

export const COMMANDS: Command[] = [
  { name: "/explain", hint: "what the open notebook does, cell by cell", insert: "Explain the attached notebook, cell by cell, in plain English. Do not change anything." },
  { name: "/fix", hint: "find bugs, propose focused changes, prove it", insert: "Review the attached notebook for bugs. Check every table and column name first, read the base revision and propose focused cell operations, run it, and show the evidence." },
  { name: "/chart", hint: "aggregate, plot, and write the summary", insert: "Build a notebook that aggregates the data and draws a chart, with one markdown cell explaining what it shows. Check the column names before writing." },
  { name: "/sql", hint: "answer a question with SQL, show the rows", insert: "Answer this question with SQL: " },
  { name: "/document", hint: "add grounded comments to tables", insert: "Document the tables in the attached context: for each one, a short comment grounded in the real values you sample. Do not change data." },
  { name: "/profile", hint: "row count, nulls, ranges, surprises", insert: "Profile the attached table: row count, null rates, the range of each numeric column, and anything surprising. Show the numbers." },
  { name: "/optimize", hint: "make it faster, prove the result is the same", insert: "Review the attached notebook for slow or wasteful steps. Make the smallest changes that speed it up, propose focused cell operations against the base revision, and show that the output is unchanged." },
  { name: "/prettify", hint: "format and name things clearly", insert: "Tidy the attached notebook: consistent formatting, clear names, one idea per cell, a short markdown heading for each section. Do not change what it computes. Propose focused cell operations against the base revision." },
  { name: "/rename", hint: "better names for variables and columns", insert: "Suggest clearer names for the variables, aliases and columns in the attached notebook, propose cell operations against the base revision, and list every rename you made." },
  { name: "/findtables", hint: "find tables that match what you describe", insert: "Find tables in Unity Catalog that match this description, and for each give its full name and one line on why it fits: " },
  { name: "/test", hint: "add checks that would catch a regression", insert: "Propose focused cell operations against the base revision to add checks to the attached notebook that would catch a wrong result (row counts, nulls, ranges, a known value), run them, and show the results." },
  { name: "/help", hint: "what this agent can do", insert: "What can you do here, in two short paragraphs, and what are your limits?" },
];

const SLASH = /(^|\s)\/([a-z]*)$/;

/** The command being typed at the caret, if any (matched on the text before the caret). */
export function commandAt(text: string, caret: number): { query: string; open: boolean } {
  const m = SLASH.exec(text.slice(0, caret));
  return { query: m ? m[2] : "", open: Boolean(m) };
}

export function matchCommands(query: string, additional: Command[] = []): Command[] {
  const q = query.toLowerCase();
  const combined=new Map<string,Command>(COMMANDS.map(c => [c.name,{...c,source:"Template" as const}]));
  for(const command of additional) combined.set(command.name,command);
  return [...combined.values()].filter((c) => c.name.slice(1).startsWith(q));
}

/** Replaces the half-typed command with the command's prompt. Returns the new text and caret. */
export function applyCommand(text: string, caret: number, c: Command): { text: string; caret: number } {
  const before = text.slice(0, caret).replace(SLASH, `$1${c.insert}`);
  return { text: before + text.slice(caret), caret: before.length };
}

/** A tiny ring of recent prompts. Local to this browser: it is a convenience, not a record. */
export function pushHistory(prev: string[], prompt: string, max = 50): string[] {
  const p = prompt.trim();
  if (!p) return prev;
  return [p, ...prev.filter((x) => x !== p)].slice(0, max);
}

/** Up/Down through history. `at` is the index being shown, -1 meaning "not browsing". */
export function stepHistory(history: string[], at: number, key: "ArrowUp" | "ArrowDown"): { at: number; text?: string } {
  if (history.length === 0) return { at: -1 };
  if (key === "ArrowUp") {
    const next = Math.min(at + 1, history.length - 1);
    return { at: next, text: history[next] };
  }
  if (at <= 0) return { at: -1, text: "" };
  return { at: at - 1, text: history[at - 1] };
}
