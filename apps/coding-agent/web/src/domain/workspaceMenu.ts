/** The workspace right-click menu. One definition, shared by the tree and the tests.
 *
 * The labels and the grouping follow the Databricks workspace menu: open, copy, create, rename,
 * move, clone, import, download, share, favorites, trash. Two actions are ours, and they come
 * first: attach the object to the chat, and use a folder as the working folder.
 */

export interface MenuNode { path: string; name: string; kind: string }

export interface MenuItem {
  id: string;
  label: string;
  enabled: boolean;
  reason?: string;
  danger?: boolean;
  children?: MenuItem[];
}

export interface Favorite { path: string; name: string; kind: string; objectId?: string }

const FOLDER = new Set(["directory", "repo"]);

export const isFolder = (kind: string) => FOLDER.has(kind);

/** A workspace root, the signed-in home, or the Repos folder the tree shows first. Children are not. */
export function isProtected(path: string, home: string): boolean {
  const p = path.replace(/\/+$/, "") || "/";
  const guarded = new Set(["/", "/Users", "/Shared", "/Repos", "/Workspace"]);
  const h = (home || "").replace(/\/+$/, "");
  if (h) guarded.add(h);
  const owner = h.replace(/^\/Users\//, "").split("@")[0]?.split(".").join("_") ?? "";
  if (owner) guarded.add(`/Repos/${owner}`);
  return guarded.has(p);
}

export function parentPath(path: string): string {
  const i = path.lastIndexOf("/");
  return i <= 0 ? "/" : path.slice(0, i);
}

/** One path segment, or null when the text could escape the folder. */
export function objectName(raw: string): string | null {
  const name = raw.trim();
  if (!name || name === "." || name === ".." || /[/\\\u0000]/.test(name) || name.length > 200) return null;
  return name;
}

export function childPath(parent: string, name: string): string | null {
  const leaf = objectName(name);
  if (!leaf) return null;
  return `${parent.replace(/\/+$/, "")}/${leaf}`;
}

export function cloneName(name: string): string {
  return `${name} (1)`;
}

export function importFormat(filename: string): { format: string; language?: string } {
  const ext = filename.toLowerCase().split(".").pop() ?? "";
  if (ext === "ipynb") return { format: "JUPYTER" };
  if (ext === "html" || ext === "htm") return { format: "HTML" };
  if (ext === "dbc") return { format: "DBC" };
  if (ext === "rmd") return { format: "R_MARKDOWN" };
  return { format: "AUTO" };
}

const DOWNLOADS: Record<string, string> = {
  "download-source": "SOURCE",
  "download-html": "HTML",
  "download-jupyter": "JUPYTER",
  "download-dbc": "DBC",
};

export function downloadFormat(id: string): string | null {
  return DOWNLOADS[id] ?? null;
}

export function downloadName(name: string, format: string, language?: string): string {
  if (format === "DBC") return name.toLowerCase().endsWith(".dbc") ? name : `${name}.dbc`;
  if (format === "HTML") return `${name}.html`;
  if (format === "JUPYTER") return `${name}.ipynb`;
  if (name.includes(".")) return name;
  const ext = ({ PYTHON: "py", SQL: "sql", SCALA: "scala", R: "r" } as Record<string, string>)[(language ?? "").toUpperCase()] ?? "py";
  return `${name}.${ext}`;
}

function noun(kind: string): string {
  if (kind === "notebook") return "notebook";
  if (kind === "file" || kind === "library") return "file";
  if (kind === "repo") return "repo";
  return "folder";
}

/** Sections of the menu, in the order they are drawn. A section is one group between separators. */
export function menuFor(node: MenuNode, o: { home: string; favorite: boolean }): MenuItem[][] {
  const dir = isFolder(node.kind);
  const repo = node.kind === "repo";
  const locked = isProtected(node.path, o.home);
  const lock = locked ? "This is a workspace root." : undefined;
  const git = repo ? "A Git folder keeps its history in Databricks. Open it there." : undefined;
  const blocked = (reason?: string) => ({ enabled: !reason, reason });

  const app: MenuItem[] = [{ id: "attach", label: "Attach to chat", enabled: true }];
  if (dir) app.push({ id: "use-folder", label: "Use as working folder", enabled: true });

  const downloads: MenuItem[] = [];
  if (node.kind === "notebook" || node.kind === "file" || node.kind === "library") {
    downloads.push({ id: "download-source", label: "Source", enabled: true });
  }
  if (node.kind === "notebook") {
    downloads.push(
      { id: "download-html", label: "HTML", enabled: true },
      { id: "download-jupyter", label: "IPython notebook", enabled: true },
      { id: "download-dbc", label: "DBC archive", enabled: true },
    );
  } else if (dir) {
    downloads.push({ id: "download-dbc", label: "DBC archive", enabled: true });
  }

  const edit: MenuItem[] = [
    { id: "rename", label: "Rename", ...blocked(lock || git) },
    { id: "move", label: "Move", ...blocked(lock || git) },
    { id: "clone", label: "Clone", ...blocked(lock || git) },
  ];
  if (dir) edit.push({ id: "import", label: "Import", ...blocked(lock) });

  return [
    app,
    [{ id: "open", label: "Open in new browser tab", enabled: true }],
    [{
      id: "copy", label: "Copy URL/path", enabled: true,
      children: [
        { id: "copy-url", label: "URL", enabled: true },
        { id: "copy-path", label: "Full path", enabled: true },
      ],
    }],
    ...(dir ? [[{
      id: "create", label: "Create", enabled: true,
      children: [
        { id: "create-notebook", label: "Notebook", enabled: true },
        { id: "create-file", label: "File", enabled: true },
        { id: "create-folder", label: "Folder", enabled: true },
      ],
    }]] : []),
    edit,
    [{ id: "download", label: "Download as", enabled: downloads.length > 0, children: downloads }],
    [
      { id: "share", label: "Share (Permissions)", enabled: true },
      { id: "favorite", label: o.favorite ? "Remove from favorites" : "Add to favorites", enabled: true },
    ],
    [{ id: "trash", label: `Move this ${noun(node.kind)} to Trash`, enabled: !locked, reason: lock, danger: true }],
  ];
}

export function readFavorites(raw: string | null): Favorite[] {
  try {
    const parsed = JSON.parse(raw ?? "[]") as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((x): x is Favorite =>
      !!x && typeof x.path === "string" && typeof x.name === "string" && typeof x.kind === "string").slice(0, 50);
  } catch {
    return [];
  }
}

export function toggleFavorite(list: Favorite[], item: Favorite): Favorite[] {
  const next = list.some((f) => f.path === item.path) ? list.filter((f) => f.path !== item.path) : [item, ...list];
  return next.slice(0, 50);
}
