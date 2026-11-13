/** Links from this app to the same object in the Databricks workspace UI. Pure, no React.
 *
 * With an object id the link goes straight to the editor; without one it uses the workspace's own
 * path redirect (`/#workspace/<path>`), which needs no lookup and so can be built synchronously
 * (a link opened after an `await` is blocked as a pop-up).
 */
export interface Workspace { host: string; orgId?: string }

export type LinkKind = "notebook" | "file" | "directory" | "repo" | "library" | "table" | "query" | "query-draft";

export interface LinkTarget { kind: LinkKind; ref: string; objectId?: string }

/** Absolute workspace paths worth linking in prose. /Volumes is not a workspace path: not matched. */
export const WORKSPACE_PATH = /\/(?:Users|Workspace|Shared|Repos)\/[^\s`"'<>)\]|]+/g;

const trimTrail = (p: string) => p.replace(/[.,;:!?]+$/, "");

export function workspaceUrl(ws: Workspace | null | undefined, t: LinkTarget): string | null {
  if (!ws?.host) return null;
  const host = ws.host.replace(/\/+$/, "");
  const o = ws.orgId ? `?o=${encodeURIComponent(ws.orgId)}` : "";
  if (t.kind === "query") return /^[0-9a-f-]{36}$/i.test(t.ref) ? `${host}/editor/queries/uuid/${encodeURIComponent(t.ref)}${o}` : null;
  if (t.kind === "query-draft") return null;
  if (t.kind === "table") {
    const parts = t.ref.split(".");
    return parts.length === 3 ? `${host}/explore/data/${parts.map(encodeURIComponent).join("/")}${o}` : null;
  }
  if (!t.ref.startsWith("/")) return null;
  if (t.objectId) {
    if (t.kind === "notebook") return `${host}/editor/notebooks/${t.objectId}${o}`;
    if (t.kind === "file") return `${host}/editor/files/${t.objectId}${o}`;
    if (t.kind === "directory" || t.kind === "repo") return `${host}/browse/folders/${t.objectId}${o}`;
  }
  const path = trimTrail(t.ref).replace(/^\/Workspace(?=\/)/, "");
  return `${host}/${o}#workspace${path.split("/").map(encodeURIComponent).join("/")}`;
}

/** Split prose into plain text and workspace paths, so each path can become a link. */
export function splitPaths(text: string): { text: string; path?: string }[] {
  const out: { text: string; path?: string }[] = [];
  let last = 0;
  for (const m of text.matchAll(WORKSPACE_PATH)) {
    const path = trimTrail(m[0]);
    if (m.index! > last) out.push({ text: text.slice(last, m.index) });
    out.push({ text: path, path });
    last = m.index! + path.length;
  }
  if (last < text.length) out.push({ text: text.slice(last) });
  return out;
}
