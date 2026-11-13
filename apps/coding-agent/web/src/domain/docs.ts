/** Open documents, quick-action prompts and "which object did this tool touch". Pure, no React. */
import type { Attachment } from "./events";
import { projectRef } from "./lakebase";
import { asId } from "./jobs";

export type DocKind = "lakebase" | "app" | "job" | "run" | "pipeline" | "notebook" | "file" | "table" | "query" | "query-draft";
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
 *  A project is `projects/pg_tickets` however it is spelled ([LB-5]); an app is its name; a job and a run
 *  are their numeric ids; a pipeline is its UUID; a workspace object is its canonical path. One function,
 *  so `docId` and `makeDoc` cannot disagree. */
function keyOf(kind: DocKind, ref: string, name?: string): string {
  if (kind === "lakebase") {
    try { return projectRef(ref); } catch { return ref; }
  }
  if (kind === "app") {
    // An app is its name; a resource path or a URL is accepted and reduced to that name.
    const bare = (name || ref || "").trim().replace(/^https?:\/\//, "").split("/")[0];
    return bare.split(".")[0];
  }
  if (kind === "job" || kind === "run") {
    // A numeric id either way: the JSON carries a number, a URL a string, and one object must be one tab
    // (spec 014 [JOB-1]). A value that is not a number keeps its text so the page can refuse it in words
    // rather than opening `job:NaN`.
    const n = asId(ref);
    return n === null ? String(ref) : String(n);
  }
  if (kind === "pipeline") return String(ref).trim();
  return canonicalPath(ref);
}

export function makeDoc(kind: DocKind, ref: string, name?: string): Doc {
  const key = keyOf(kind, ref, name);
  const display = name
    || (kind === "table" ? key.split(".").pop()
      : kind === "lakebase" ? key.split("/").pop()
        : kind === "app" ? key
          : kind === "job" ? `job ${key}`
            : kind === "run" ? `run ${key}`
              : kind === "pipeline" ? key.slice(0, 8)
                : key.split("/").pop()) || key;
  return {
    id: docId(kind, ref, name),
    kind,
    // The key IS the reference for the three new kinds: a job and a run are their id, a pipeline its UUID.
    ref: kind === "lakebase" || kind === "job" || kind === "run" || kind === "pipeline" ? key : ref,
    name: display,
    rev: 0,
  };
}

export const asAttachment = (d: Doc): Attachment | null => {
  // A notebook, file or table is a reference the server can re-read with the user's own token. A
  // Lakebase project, an app, a job, a pipeline and a run are not: they are management objects, not
  // content, and the server has no resolver for them (spec 013 [UI-5], spec 014 [UI-1] offers them in the
  // palette and as a dock binding, not as attachments).
  if (!canAttach(d.kind)) return null;
  return { kind: d.kind, ref: d.ref, name: d.name };
};

/** Whether a kind can ride along with a message. One predicate, used by the composer and the chip. */
export const canAttach = (kind: DocKind): kind is "notebook" | "file" | "table" | "query" | "query-draft" =>
  kind === "notebook" || kind === "file" || kind === "table" || kind === "query" || kind === "query-draft";

/** Opening a list entry (workspace node kinds) as a document. Folders are not documents. */
export function docForNode(kind: string, path: string): Doc | null {
  if (kind === "notebook") return makeDoc("notebook", path);
  if (kind === "file" || kind === "library") return makeDoc("file", path);
  return null;
}

const PATH_ARG = /"path"\s*:\s*"(\/[^"]+)"/;

/** How one family of tool calls names an object: the shape a new OBJECT TYPE becomes.
 *
 *  Before spec 014 this reducer was five `if` branches, one per kind, and adding a sixth meant editing a
 *  chain that was already long. A table makes a kind a ROW, and `Record<DocKind, …>` on `ACTIONS_FOR`
 *  makes the compiler insist the new row exists ([UI-5], the full-stack lens's argument).
 *
 *  `extract` returns `{ ref, name }` or null. It reads the RESULT before the arguments, because a create's
 *  identity is something the platform GRANTED — the arguments only asked for a name (013's ordering for a
 *  Lakebase project, applied to three more kinds).
 */
interface TouchRule {
  /** The tool names this rule answers. A regex because the families differ by one verb. */
  tools: RegExp;
  kind: DocKind;
  /** Which tools in the family CHANGE something. A read opens an object without making it stale. */
  mutates: RegExp;
  extract: (args?: string, result?: string) => { ref: string; name?: string } | null;
}

/** A string field of a tool's JSON reply, tolerating truncation. The id is written first by every tool
 *  here, so a reply cut at the token cap still yields it. */
function field(text: string | undefined, name: string): string | null {
  if (!text) return null;
  const quoted = new RegExp(`"${name}"\\s*:\\s*"([^"]+)"`).exec(text);
  if (quoted) return quoted[1];
  const bare = new RegExp(`"${name}"\\s*:\\s*(\\d+)`).exec(text);
  return bare ? bare[1] : null;
}

/** A workspace path out of a reply, canonicalised so two spellings are one tab. */
function pathIn(args?: string, result?: string): { ref: string; name?: string } | null {
  const m = (args && PATH_ARG.exec(args)) || (result && PATH_ARG.exec(result)) || null;
  return m ? { ref: m[1] } : null;
}

const TOUCHED: TouchRule[] = [
  {
    // A Lakebase project's identity is in the RESULT: the create call asks for a name and the platform
    // answers with the canonical resource path, which is the one key ([LB-5]).
    tools: /^dbx_lakebase_(create|status|branch|database)$/,
    kind: "lakebase",
    mutates: /create|branch|database/,
    extract: (args, result) => {
      const ref = field(result, "project") ?? field(args, "project");
      return ref ? { ref } : null;
    },
  },
  {
    tools: /^dbx_(create_app|app_health)$/,
    kind: "app",
    mutates: /create_app/,
    extract: (args, result) => {
      const ref = field(result, "app") ?? field(args, "app") ?? field(args, "name");
      return ref ? { ref } : null;
    },
  },
  {
    // A JOB is named by the tools that create, list or explain one. Note what is NOT here: `run_job` and
    // `job_run_status` carry a `run_id` only, so they name a RUN — and a family that matched them here
    // would return null and swallow the call (found by this table's own test, not by a screenshot).
    tools: /^dbx_(create_job|list_jobs|job_failure_context)$/,
    kind: "job",
    mutates: /create_job/,
    extract: (args, result) => {
      const id = field(result, "job_id") ?? field(args, "job_id");
      return id ? { ref: id } : null;
    },
  },
  {
    // A run is its own document: `dbx_run_job` and `dbx_job_run_status` name one, and it is what a user
    // pastes into a ticket ([RUN-1]).
    tools: /^dbx_(run_job|job_run_status)$/,
    kind: "run",
    mutates: /run_job/,
    extract: (args, result) => {
      const id = field(result, "run_id") ?? field(args, "run_id");
      return id ? { ref: id } : null;
    },
  },
  {
    tools: /^dbx_(create_pipeline|pipeline_status|start_pipeline|stop_pipeline|pipeline_edit)$/,
    kind: "pipeline",
    mutates: /create_pipeline|start_pipeline|stop_pipeline|pipeline_edit/,
    extract: (args, result) => {
      const id = field(result, "pipeline_id") ?? field(args, "pipeline_id");
      return id ? { ref: id } : null;
    },
  },
  {
    tools: /(write|read|run|grep)_notebook/,
    kind: "notebook",
    mutates: /write_notebook/,
    extract: pathIn,
  },
  { tools: /write_file/, kind: "file", mutates: /write_file/, extract: pathIn },
];

/**
 * The object a tool call touched, read from its (possibly truncated) argument summary and, failing that,
 * from its result — through the table above, so a new kind is a row.
 *
 * The arguments are cut at a couple of hundred characters, and a write's `cells` come first, so the path
 * is usually NOT in them; the tool's own answer names it, and without it the notebook the agent just made
 * never opened. Returns null when nothing openable is named: we never guess.
 */
export function touched(name: string, args?: string, result?: string):
  { doc: Doc; mutates: boolean } | null {
  for (const rule of TOUCHED) {
    if (!rule.tools.test(name)) continue;
    const found = rule.extract(args, result);
    // A rule owns a tool NAME, not merely a matching prefix. Returning null here (rather than falling
    // through) is deliberate — a call that names nothing openable must not be attributed to a different
    // kind by a later row — which is why the `job` and `run` families are disjoint above.
    if (!found) return null;
    return { doc: makeDoc(rule.kind, found.ref, found.name), mutates: rule.mutates.test(name) };
  }
  return null;
}

/** Which rule answers a tool name. Exported for the table's own test, so "the families are disjoint"
 *  can be asserted instead of hoped for. */
export const touchedKinds = (): { kind: DocKind; tools: RegExp }[] =>
  TOUCHED.map((r) => ({ kind: r.kind, tools: r.tools }));

/** An app's name, from `"app": "tickets_app"` or the arguments' `"name"`. */
function appFrom(text?: string): string | null {
  if (!text) return null;
  const m = /"app"\s*:\s*"([^"]+)"/.exec(text);
  return m ? m[1] : null;
}
void appFrom;  // retained for a caller outside this module; the table above is the one the reducer uses

const SQL_WRITE = /\b(?:create\s+(?:or\s+replace\s+)?(?:temp\w*\s+)?table(?:\s+if\s+not\s+exists)?|insert\s+(?:into|overwrite)(?:\s+table)?|merge\s+into|update|delete\s+from|truncate\s+table|alter\s+table|drop\s+table(?:\s+if\s+exists)?|create\s+(?:or\s+replace\s+)?view)\s+`?([\w]+(?:`?\.`?[\w]+){0,2})`?/gi;

/** The tables a SQL tool call wrote, as lowercase `catalog.schema.table` names, from its (possibly
 *  truncated) arguments. A table open on screen is stale after one of these. Never invents a name. */
export function tablesWritten(name: string, args?: string): string[] {
  if (!/run_sql|lakebase_sql/.test(name) || !args) return [];
  const out = new Set<string>();
  for (const m of args.matchAll(SQL_WRITE)) out.add(m[1].replace(/`/g, "").toLowerCase());
  return [...out];
}

/** The document an `opengenie:open-*` window event names, or null.
 *
 *  A read-only page cannot navigate the shell itself, so it dispatches an event and the shell opens the
 *  document. The mapping lives here, next to `touched()` and `makeDoc`, so `App.tsx`'s listener is three
 *  lines and this test can call the SAME function rather than a copy of it.
 *
 *  Why it needs a test at all: two of these events were dispatched for months with no listener at all
 *  (`open-lakebase` from 013's app page, `open-job` from 014's run page). A dead dispatch renders a
 *  perfectly ordinary button, so only a test finds it — the inert-control defect 011 [N5] removed.
 */
export const OPEN_EVENTS: Record<string, DocKind> = {
  "opengenie:open-lakebase": "lakebase",
  "opengenie:open-job": "job",
};

export function docFromOpenEvent(event: string, detail: unknown): Doc | null {
  const kind = OPEN_EVENTS[event];
  if (!kind) return null;
  const ref = typeof detail === "string" ? detail.trim() : "";
  if (!ref) return null;
  return makeDoc(kind, ref);
}

export type Action = "explain" | "fix" | "document" | "optimize" | "profile" | "query";

/**
 * Quick actions preserve the fence and ask for revisioned review before an in-place edit.
 */
export const ACTIONS: Record<Action, { label: string; prompt: string }> = {
  explain: { label: "Explain", prompt: "Explain what the attached notebook does, cell by cell, in plain English. Do not change anything." },
  fix: { label: "Fix errors", prompt: "Review the attached notebook for bugs. Check every table and column name with describe_table before judging it. For an asset inside the working folder, read its revision and propose minimal cell or range edits for review. For an outside asset, propose a copy inside the working folder. Run the approved result as my identity and show the evidence." },
  document: { label: "Document", prompt: "Add clear markdown documentation to the attached notebook: a title, one short note per step, and the assumptions. Read the revision and propose cell edits for review if it is inside the working folder; otherwise propose a new notebook inside the working folder." },
  optimize: { label: "Optimize", prompt: "Find the performance problems in the attached notebook (shuffles, repeated reads, collect(), row-wise UDFs). Propose revisioned edits inside the working folder, or an inside copy of an outside asset. Run the approved result as my identity and show measured timings." },
  profile: { label: "Profile", prompt: "Profile the attached table: row count, null rate per column, distinct counts for likely keys, and anything that looks wrong. Show the SQL you used." },
  query: { label: "Write a query", prompt: "Suggest three useful queries on the attached table and run the first one. Check the real column names before writing SQL." },
};

export const ACTIONS_FOR: Record<DocKind, Action[]> = {
  lakebase: ["explain"], app: ["explain"], job: ["explain"], run: ["explain"], pipeline: ["explain"],
  notebook: ["explain", "fix", "document", "optimize"],
  file: ["explain"],
  table: ["profile", "query"],
  query: ["explain"],
  "query-draft": ["explain"],
};

/** Which kinds a page renders as a viewer rather than an editor. One predicate, read by the dock, the
 *  palette and the tab strip, so a sixth read-only kind cannot be offered an editor by accident. */
export const isRunObject = (kind: DocKind): kind is "job" | "pipeline" | "run" =>
  kind === "job" || kind === "pipeline" || kind === "run";
