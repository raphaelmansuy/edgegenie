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
  kind: "notebook" | "file" | "table";
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
  return !!d && typeof d.path === "string" && d.path.startsWith("/")
    && typeof d.name === "string" && (d.kind === "notebook" || d.kind === "file" || d.kind === "table");
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
  return kind === "table" ? path.split(".").pop() ?? path : path.split("/").pop() ?? path;
}
