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
  /** The five document kinds. A project and an app are "recently looked at" too (spec 013 [UI-1]). */
  kind: "notebook" | "file" | "table" | "lakebase" | "app";
}

const KEY = "coding-agent:recent-docs:v1";
const MAX = 6;
let loaded = false;
let memory: RecentDoc[] = [];

function load(): void {
  if (loaded) return;
  loaded = true;
  try {
    const raw = typeof localStorage !== "undefined" ? localStorage.getItem(KEY) : null;
    const parsed = raw ? (JSON.parse(raw) as unknown) : [];
    memory = Array.isArray(parsed) ? parsed.filter(valid).slice(0, MAX) : [];
  } catch { memory = []; }
}

function valid(v: unknown): v is RecentDoc {
  const d = v as RecentDoc;
  const kinds = ["notebook", "file", "table", "lakebase", "app"];
  return !!d && typeof d.path === "string" && d.path.length > 0
    && typeof d.name === "string" && kinds.includes(d.kind);
}

function save(): void {
  try {
    if (typeof localStorage !== "undefined") localStorage.setItem(KEY, JSON.stringify(memory));
  } catch { /* private mode: the list still works for this page */ }
}

export function recentDocs(): RecentDoc[] {
  load();
  return [...memory];
}

/** Put a document at the front, once. Returns the new list, so a caller can render without a re-read. */
export function rememberDoc(doc: RecentDoc): RecentDoc[] {
  load();
  memory = [doc, ...memory.filter((d) => !(d.path === doc.path && d.kind === doc.kind))].slice(0, MAX);
  save();
  return [...memory];
}

export function forgetDocs(): void {
  load();
  memory = [];
  save();
}

/** Tables are named `catalog.schema.table`, so a "name" is the last part, not the last path segment. */
export function nameOf(kind: RecentDoc["kind"], path: string): string {
  if (kind === "table") return path.split(".").pop() ?? path;
  if (kind === "lakebase") return path.split("/").pop() ?? path;
  if (kind === "app") return path;
  return path.split("/").pop() ?? path;
}
