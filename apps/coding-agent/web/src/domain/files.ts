/** The Files list: sort, filter, breadcrumb, column labels. Pure.
 *
 * Databricks offers tree *and* list (spec 006 FL-1/FL-2): a tree answers "where", a list answers
 * "which". The list's four columns are the ones that decide what to open — name, type, owner, and
 * when it last changed.
 */
import type { WsNode } from "../components/WorkspaceTree";

export type FilesView = "tree" | "list";

export const VIEW_KEY = "coding-agent.files-view";

export function readView(raw: string | null | undefined): FilesView {
  return raw === "list" ? "list" : "tree";
}

const FOLDER = new Set(["directory", "repo"]);

export const isFolder = (kind: string) => FOLDER.has(kind);

/** Folders first, then by name, case-insensitively. Stable within a name so a refresh cannot shuffle. */
export function sortNodes(nodes: WsNode[]): WsNode[] {
  return [...nodes].sort((a, b) => {
    const fa = isFolder(a.kind) ? 0 : 1;
    const fb = isFolder(b.kind) ? 0 : 1;
    if (fa !== fb) return fa - fb;
    return a.name.localeCompare(b.name, undefined, { sensitivity: "base", numeric: true });
  });
}

export function filterNodes(nodes: WsNode[], query: string): WsNode[] {
  const q = query.trim().toLowerCase();
  if (!q) return nodes;
  return nodes.filter((n) => n.name.toLowerCase().includes(q) || n.path.toLowerCase().includes(q));
}

/** What the Type column says, in the same words Databricks uses. */
export function typeLabel(kind: string): string {
  switch (kind) {
    case "directory": return "Folder";
    case "repo": return "Repo";
    case "notebook": return "Notebook";
    case "library": return "Library";
    default: return "File";
  }
}

/** The row's secondary text: language for a notebook, nothing for a folder. */
export function typeDetail(node: WsNode): string {
  if (node.kind === "notebook" || node.kind === "file") {
    return node.language ? node.language.toUpperCase() : "";
  }
  return "";
}

export interface Crumb { name: string; path: string }

/**
 * A breadcrumb for a folder inside a named root.
 *
 * The root's label replaces the segments it already names: the root "My home" IS
 * `/Users/raphael.mansuy@gmail.com`, so showing both read "My home / raphael.mansuy@gmail.com" — the
 * same place said twice, which is exactly the kind of noise a breadcrumb exists to remove.
 */
export function crumbsFor(rootName: string, path: string, rootPath = ""): Crumb[] {
  const base = rootPath.replace(/\/+$/, "");
  const insideRoot = Boolean(base) && (path === base || path.startsWith(base + "/"));
  // Inside the root: only the segments below it. Outside it: every segment, because the root's label
  // would otherwise name a place that does not contain the folder being shown.
  const rest = (insideRoot ? path.slice(base.length) : path).split("/").filter(Boolean);
  const head: Crumb = { name: rootName || "Workspace", path: base || path || "/" };
  let acc = insideRoot ? base : "";
  return [head, ...rest.map((p) => { acc += `/${p}`; return { name: p, path: acc }; })];
}

/** The "Folder" column: where the item lives, relative to the root being browsed. */
export function whereLabel(path: string, rootPath: string): string {
  const dir = path.slice(0, path.lastIndexOf("/")) || "/";
  const base = rootPath.replace(/\/+$/, "");
  if (base && dir === base) return "·";
  if (base && dir.startsWith(base + "/")) return dir.slice(base.length + 1);
  return dir;
}

/** The parent folder of a path, or null at a root. */
export function parentOf(path: string): string | null {
  const trimmed = path.replace(/\/+$/, "");
  const cut = trimmed.lastIndexOf("/");
  if (cut <= 0) return null;
  return trimmed.slice(0, cut);
}

/** Empty-state copy that names an action rather than saying "nothing here". */
export function emptyCopy(query: string, canCreate: boolean): string {
  if (query.trim()) return `No item in this folder matches “${query.trim()}”.`;
  return canCreate ? "No items in this folder. Use + to create one." : "No items in this folder.";
}
