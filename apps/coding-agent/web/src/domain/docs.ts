/** Open documents, quick-action prompts and "which object did this tool touch". Pure, no React. */
import type { Attachment } from "./events";

export type DocKind = "notebook" | "file" | "table" | "query" | "query-draft";
export interface Doc { id: string; kind: DocKind; ref: string; name: string; rev: number }

/** One path, two spellings, one object.
 *
 * The workspace API accepts `/Workspace/Users/me/x` and returns `/Users/me/x`; a deep link can carry
 * either, and so can a tool call. Without this, the same notebook opened twice made TWO tabs (seen on
 * the deployed app), and a write reported against one spelling never refreshed a tab opened with the
 * other — the agent said "wrote the notebook" over a document that never changed.
 */
export function canonicalPath(path: string): string {
  const trimmed = path.length > 1 ? path.replace(/\/+$/, "") : path;
  if (trimmed === "/Workspace") return "/";
  return trimmed.startsWith("/Workspace/") ? trimmed.slice("/Workspace".length) : trimmed;
}

/** The folder a path lives in, for saying where something went ("agent_scratch", "demo"). */
export function parentOf(path: string): string {
  const parts = canonicalPath(path).split("/").filter(Boolean);
  return parts.length > 1 ? parts[parts.length - 2] : parts[0] ?? "";
}

export const docId = (kind: DocKind, ref: string) => `${kind}:${canonicalPath(ref)}`;

export function makeDoc(kind: DocKind, ref: string): Doc {
  const canon = canonicalPath(ref);
  return { id: docId(kind, canon), kind, ref: canon, name: kind === "table" ? canon.split(".").pop() ?? canon : canon.split("/").pop() ?? canon, rev: 0 };
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
 * The workspace object a tool call touched, read from its (possibly truncated) argument summary and,
 * failing that, from its result. The arguments are cut at a couple of hundred characters, and a write's
 * `cells` come first, so the path is usually NOT in them; the tool's own answer names it
 * (`{"path": ..., "cells": 2}`), and without it the notebook the agent just made never opened.
 * Returns null when nothing openable is named: we never guess a path.
 */
export function touched(name: string, args?: string, result?: string): { doc: Doc; mutates: boolean } | null {
  const m = (args && PATH_ARG.exec(args)) || (result && PATH_ARG.exec(result)) || null;
  if (!m) return null;
  const mutates = MUTATING.test(name);
  if (NOTEBOOK_TOOLS.test(name)) return { doc: makeDoc("notebook", m[1]), mutates };
  if (FILE_TOOLS.test(name)) return { doc: makeDoc("file", m[1]), mutates };
  return null;
}

const SQL_WRITE = /\b(?:create\s+(?:or\s+replace\s+)?(?:temp\w*\s+)?table(?:\s+if\s+not\s+exists)?|insert\s+(?:into|overwrite)(?:\s+table)?|merge\s+into|update|delete\s+from|truncate\s+table|alter\s+table|drop\s+table(?:\s+if\s+exists)?|create\s+(?:or\s+replace\s+)?view)\s+`?([\w]+(?:`?\.`?[\w]+){0,2})`?/gi;

/** The tables a SQL tool call wrote, as lowercase `catalog.schema.table` names, from its (possibly
 *  truncated) arguments. A table open on screen is stale after one of these. Never invents a name. */
export function tablesWritten(name: string, args?: string): string[] {
  if (!/run_sql|lakebase_sql/.test(name) || !args) return [];
  const out = new Set<string>();
  for (const m of args.matchAll(SQL_WRITE)) out.add(m[1].replace(/`/g, "").toLowerCase());
  return [...out];
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
  query: ["explain"],
  "query-draft": ["explain"],
};
