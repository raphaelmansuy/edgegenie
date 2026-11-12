/** Documents this browser has opened, most recent first. Pure + a tiny store.
 *
 * The home screen offers a way IN ("change something I already have") beside a way to start. Search
 * covers "I know the name"; this covers "the one I was just looking at", which is the commoner case
 * and the one that costs a user a search every time.
 *
 * Local to the browser on purpose: it is a convenience, not a record of the user's work, and it must
 * never imply the app tracks them. Paths only — never content.
 */
export interface RecentDoc {
  path: string;
  name: string;
  kind: import("./docs").DocKind;
}

const KEY = "coding-agent:recent-docs:v1";
const MAX = 6;
let loadedKey = "";
let memory: RecentDoc[] = [];

function load(scope = ""): void {
  const key = scope ? `${KEY}:${encodeURIComponent(scope)}` : KEY;
  if (loadedKey === key) return;
  loadedKey = key;
  try {
    const raw = typeof localStorage !== "undefined" ? localStorage.getItem(key) : null;
    const parsed = raw ? (JSON.parse(raw) as unknown) : [];
    memory = Array.isArray(parsed) ? parsed.filter(valid).slice(0, MAX) : [];
  } catch { memory = []; }
}

function valid(v: unknown): v is RecentDoc {
  const d = v as RecentDoc;
  const kinds = ["notebook", "file", "table", "lakebase", "app", "job", "pipeline", "run", "query", "query-draft"];
  return !!d && typeof d.path === "string" && d.path.length > 0
    && typeof d.name === "string" && kinds.includes(d.kind);
}

function save(): void {
  try {
    if (typeof localStorage !== "undefined") localStorage.setItem(loadedKey, JSON.stringify(memory));
  } catch { /* private mode: the list still works for this page */ }
}

export function recentDocs(scope = ""): RecentDoc[] {
  load(scope);
  return [...memory];
}

/** Put a document at the front, once. Returns the new list, so a caller can render without a re-read. */
export function rememberDoc(doc: RecentDoc, scope = ""): RecentDoc[] {
  load(scope);
  memory = [doc, ...memory.filter((d) => !(d.path === doc.path && d.kind === doc.kind))].slice(0, MAX);
  save();
  return [...memory];
}

export function forgetDocs(scope = ""): void {
  load(scope);
  memory = [];
  save();
}

/** Tables are named `catalog.schema.table`, so a "name" is the last part, not the last path segment.
 *  A job and a run are named by their id (a job's *name* is not unique in a workspace, so it is not an
 *  identity); a pipeline is its UUID's first segment. */
export function nameOf(kind: RecentDoc["kind"], path: string): string {
  if (kind === "table") return path.split(".").pop() ?? path;
  if (kind === "lakebase") return path.split("/").pop() ?? path;
  if (kind === "job") return `job ${path}`;
  if (kind === "run") return `run ${path}`;
  if (kind === "pipeline") return path.slice(0, 8);
  if (kind === "app") return path;
  return path.split("/").pop() ?? path;
}
