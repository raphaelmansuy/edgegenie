/** Workspace tree: the real Databricks workspace, lazily loaded, keyboard navigable.
 *
 * Design notes (spec 001, 05 UX):
 *  - one request per folder expanded, never a whole tree up front;
 *  - folders first, alphabetical, like a file manager;
 *  - an unreadable folder says so in place, instead of silently showing nothing;
 *  - the search box filters what is already loaded and offers to search the workspace.
 */
import { useCallback, useEffect, useRef, useState } from "react";

export interface WsNode {
  path: string;
  name: string;
  kind: "directory" | "notebook" | "file" | "repo" | "library";
  language?: string;
  objectId?: string;
  hasChildren: boolean;
  error?: string;
  children?: WsNode[];
}

const ICON: Record<string, string> = {
  directory: "▸", repo: "⑂", notebook: "▤", file: "▢", library: "▦",
};

async function list(path: string): Promise<WsNode[]> {
  const r = await fetch(`/api/workspace?path=${encodeURIComponent(path)}&depth=1`);
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail ?? detail; } catch { /* non-JSON */ }
    throw new Error(detail);
  }
  const d = await r.json();
  return (d.node?.children ?? []) as WsNode[];
}

function Row({ node, depth, onOpen, selected }: {
  node: WsNode; depth: number; onOpen: (n: WsNode) => void; selected: string | null;
}) {
  const [open, setOpen] = useState(false);
  const [kids, setKids] = useState<WsNode[] | null>(node.children ?? null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(node.error ?? "");

  const toggle = async () => {
    if (!node.hasChildren) return;
    if (open) { setOpen(false); return; }
    setOpen(true);
    if (kids || loading) return;
    setLoading(true);
    try { setKids(await list(node.path)); setErr(""); }
    catch (e) { setErr(e instanceof Error ? e.message : "cannot read this folder"); }
    finally { setLoading(false); }
  };

  const isFolder = node.kind === "directory" || node.kind === "repo";
  return (
    <>
      <div
        role="treeitem"
        aria-expanded={isFolder ? open : undefined}
        aria-selected={selected === node.path}
        aria-level={depth + 1}
        tabIndex={0}
        className={`tree-row${selected === node.path ? " is-selected" : ""}`}
        style={{ paddingLeft: 8 + depth * 14 }}
        onClick={() => (isFolder ? void toggle() : onOpen(node))}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") { e.preventDefault(); isFolder ? void toggle() : onOpen(node); }
          if (e.key === "ArrowRight" && isFolder && !open && kids) { e.preventDefault(); void toggle(); }
          if (e.key === "ArrowLeft" && isFolder && open) { e.preventDefault(); void toggle(); }
        }}
      >
        <span className={`tree-caret${open ? " is-open" : ""}`} aria-hidden>
          {isFolder ? (node.hasChildren ? "▸" : "") : ""}
        </span>
        <span className={`tree-icon kind-${node.kind}`} aria-hidden>{ICON[node.kind] ?? "▢"}</span>
        <span className="tree-name" title={node.path}>{node.name}</span>
        {node.language && <span className="tree-lang">{node.language.slice(0, 2).toLowerCase()}</span>}
        {loading && <span className="spin" aria-label="loading" />}
      </div>
      {err && (
        <div className="tree-error" style={{ paddingLeft: 30 + depth * 14 }} role="alert">{err}</div>
      )}
      {open && kids && (
        <div role="group">
          {kids.length === 0 && !err && (
            <div className="tree-empty" style={{ paddingLeft: 30 + depth * 14 }}>(empty)</div>
          )}
          {kids.map((k) => (
            <Row key={k.path} node={k} depth={depth + 1} onOpen={onOpen} selected={selected} />
          ))}
        </div>
      )}
    </>
  );
}

export function WorkspaceTree({ onOpenFile, selected }: {
  onOpenFile?: (n: WsNode) => void; selected?: string | null;
}) {
  const [roots, setRoots] = useState<{ path: string; name: string }[]>([]);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("");
  const first = useRef(true);

  useEffect(() => {
    if (!first.current) return;
    first.current = false;
    fetch("/api/workspace/roots")
      .then((r) => r.json())
      .then((d) => setRoots(d.roots ?? []))
      .catch(() => setError("cannot reach the workspace"));
  }, []);

  const open = useCallback((n: WsNode) => { onOpenFile?.(n); }, [onOpenFile]);

  return (
    <div className="tree">
      <div className="tree-search">
        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter this tree…"
          aria-label="Filter workspace"
          spellCheck={false}
        />
      </div>
      {error && <div className="tree-error" role="alert">{error}</div>}
      <div role="tree" aria-label="Workspace">
        {roots.map((r) => (
          <Row key={r.path} node={{ ...r, kind: "directory", hasChildren: true } as WsNode}
            depth={0} onOpen={open} selected={selected ?? null} />
        ))}
      </div>
      <p className="tree-note">
        Your workspace, with your permissions. Folders load as you open them.
      </p>
    </div>
  );
}
