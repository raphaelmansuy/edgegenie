/** Open documents, quick-action prompts and "which object did this tool touch". Pure, no React. */
import type { Attachment } from "./events";
import { projectRef } from "./lakebase";

/** What can be open in a tab. `lakebase` and `app` are read-only viewers of infrastructure the agent
 *  built (spec 013 [UI-1]); adding a member here is what makes the compiler point at every place
 *  that must handle it — the tab icon, the actions map, the palette, the `@` hint. */
export type DocKind = "notebook" | "file" | "table" | "lakebase" | "app";
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

export const docId = (kind: DocKind, ref: string, name?: string) =>
  `${kind}:${keyOf(kind, ref, name)}`;

/** The identity a kind uses to decide "is this the same object as that one".
 *
 *  A project is `projects/pg_tickets` however it is spelled ([LB-5]); an app is its name; a
 *  workspace object is its canonical path. One function, so `docId` and `makeDoc` cannot disagree. */
function keyOf(kind: DocKind, ref: string, name?: string): string {
  if (kind === "lakebase") {
    try { return projectRef(ref); } catch { return ref; }
  }
  if (kind === "app") {
    // An app is its name; a resource path or a URL is accepted and reduced to that name.
    const bare = (name || ref || "").trim().replace(/^https?:\/\//, "").split("/")[0];
    return bare.split(".")[0];
  }
  return canonicalPath(ref);
}

export function makeDoc(kind: DocKind, ref: string, name?: string): Doc {
  const key = keyOf(kind, ref, name);
  const display = name
    || (kind === "table" ? key.split(".").pop()
      : kind === "lakebase" ? key.split("/").pop()
        : kind === "app" ? key
          : key.split("/").pop()) || key;
  return { id: docId(kind, ref, name), kind, ref: kind === "lakebase" ? key : ref, name: display, rev: 0 };
}

export const asAttachment = (d: Doc): Attachment | null => {
  // A notebook, file or table is a reference the server can re-read with the user's own token. A
  // Lakebase project and an app are not: they are management objects, not content, and the server
  // has no resolver for them (spec 013 [UI-5] offers them in the palette, not as attachments).
  if (d.kind === "lakebase" || d.kind === "app") return null;
  return { kind: d.kind, ref: d.ref, name: d.name };
};

/** Whether a kind can ride along with a message. One predicate, used by the composer and the chip. */
export const canAttach = (kind: DocKind): kind is "notebook" | "file" | "table" =>
  kind === "notebook" || kind === "file" || kind === "table";

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
/** The two infrastructure tools that name an object worth opening (spec 013 [UI-5]). */
const LAKEBASE_TOOLS = /^dbx_lakebase_(create|status|branch|database)$/;
const APP_TOOLS = /^dbx_(create_app|app_health)$/;

/**
 * The workspace object a tool call touched, read from its (possibly truncated) argument summary and,
 * failing that, from its result. The arguments are cut at a couple of hundred characters, and a write's
 * `cells` come first, so the path is usually NOT in them; the tool's own answer names it
 * (`{"path": ..., "cells": 2}`), and without it the notebook the agent just made never opened.
 * Returns null when nothing openable is named: we never guess a path.
 */
export function touched(name: string, args?: string, result?: string): { doc: Doc; mutates: boolean } | null {
  // A Lakebase project's identity is in the RESULT, not the arguments: the create call asks for a
  // name and the platform answers with the canonical resource path, which is the one key ([LB-5]).
  if (LAKEBASE_TOOLS.test(name)) {
    const found = projectFrom(result) ?? projectFrom(args);
    if (!found) return null;
    return { doc: makeDoc("lakebase", found), mutates: /create|branch|database/.test(name) };
  }
  if (APP_TOOLS.test(name)) {
    const app = appFrom(result) ?? appFrom(args);
    if (!app) return null;
    return { doc: makeDoc("app", app), mutates: /create_app/.test(name) };
  }
  const m = (args && PATH_ARG.exec(args)) || (result && PATH_ARG.exec(result)) || null;
  if (!m) return null;
  const mutates = MUTATING.test(name);
  if (NOTEBOOK_TOOLS.test(name)) return { doc: makeDoc("notebook", m[1]), mutates };
  if (FILE_TOOLS.test(name)) return { doc: makeDoc("file", m[1]), mutates };
  return null;
}

/** `"projects/pg_tickets"` out of a tool's JSON reply or its arguments. */
function projectFrom(text?: string): string | null {
  if (!text) return null;
  const m = /"project"\s*:\s*"([^"]+)"/.exec(text);
  return m ? m[1] : null;
}

/** An app's name, from `"app": "tickets_app"` or the arguments' `"name"`. */
function appFrom(text?: string): string | null {
  if (!text) return null;
  const m = /"app"\s*:\s*"([^"]+)"/.exec(text);
  return m ? m[1] : null;
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
  // A project and an app are read-only viewers of something the agent built, so there is no quick
  // action that changes them. An empty list is the honest answer: a button that cannot act is the
  // inert control spec 011 [N5] removed.
  lakebase: [],
  app: [],
};
