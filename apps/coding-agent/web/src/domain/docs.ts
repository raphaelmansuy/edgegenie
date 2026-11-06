/** Open documents, quick-action prompts and "which object did this tool touch". Pure, no React. */
import type { Attachment } from "./events";

export type DocKind = "notebook" | "file" | "table";
export interface Doc { id: string; kind: DocKind; ref: string; name: string; rev: number }

export const docId = (kind: DocKind, ref: string) => `${kind}:${ref}`;

export function makeDoc(kind: DocKind, ref: string): Doc {
  return { id: docId(kind, ref), kind, ref, name: kind === "table" ? ref.split(".").pop() ?? ref : ref.split("/").pop() ?? ref, rev: 0 };
}

export const asAttachment = (d: Doc): Attachment => ({ kind: d.kind, ref: d.ref, name: d.name });

/** Opening a list entry (workspace node kinds) as a document. Folders are not documents. */
export function docForNode(kind: string, path: string): Doc | null {
  if (kind === "notebook") return makeDoc("notebook", path);
  if (kind === "file" || kind === "library") return makeDoc("file", path);
  return null;
}

const NOTEBOOK_TOOLS = /(write|read|run|grep)_notebook/;
const FILE_TOOLS = /write_file/;
const MUTATING = /(write_notebook|write_file)/;
const PATH_ARG = /"path"\s*:\s*"(\/[^"]+)"/;

/**
 * The workspace object a tool call touched, read from its (possibly truncated) argument summary.
 * Returns null when nothing openable is named: we never guess a path.
 */
export function touched(name: string, args?: string): { doc: Doc; mutates: boolean } | null {
  if (!args) return null;
  const m = PATH_ARG.exec(args);
  if (!m) return null;
  const mutates = MUTATING.test(name);
  if (NOTEBOOK_TOOLS.test(name)) return { doc: makeDoc("notebook", m[1]), mutates };
  if (FILE_TOOLS.test(name)) return { doc: makeDoc("file", m[1]), mutates };
  return null;
}

export type Action = "explain" | "fix" | "document" | "optimize" | "profile" | "query";

/**
 * Quick actions. Every one that changes something says "in your working folder, leave the original
 * alone": the write fence is the product's promise, and the prompt must not talk the agent around it.
 */
export const ACTIONS: Record<Action, { label: string; prompt: string }> = {
  explain: { label: "Explain", prompt: "Explain what the attached notebook does, cell by cell, in plain English. Do not change anything." },
  fix: { label: "Fix errors", prompt: "Review the attached notebook for bugs. Check every table and column name with describe_table before judging it. Write a corrected copy in your working folder (never modify the original), run it, and show the evidence that it works." },
  document: { label: "Document", prompt: "Add clear markdown documentation to the attached notebook: a title, one short note per step, and the assumptions. Write it as a new notebook in your working folder; leave the original untouched." },
  optimize: { label: "Optimize", prompt: "Find the performance problems in the attached notebook (shuffles, repeated reads, collect(), row-wise UDFs). Write an optimized copy in your working folder (leave the original untouched), run both, and show the timings side by side." },
  profile: { label: "Profile", prompt: "Profile the attached table: row count, null rate per column, distinct counts for likely keys, and anything that looks wrong. Show the SQL you used." },
  query: { label: "Write a query", prompt: "Suggest three useful queries on the attached table and run the first one. Check the real column names before writing SQL." },
};

export const ACTIONS_FOR: Record<DocKind, Action[]> = {
  notebook: ["explain", "fix", "document", "optimize"],
  file: ["explain"],
  table: ["profile", "query"],
};
