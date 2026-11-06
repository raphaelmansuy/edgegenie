/** Workspace tree: the real Databricks workspace, lazily loaded, searchable, keyboard navigable.
 *
 * Design notes (spec 001, 05 UX and 18 gap analysis):
 *  - one request per folder expanded, never a whole tree up front;
 *  - folders first, alphabetical, like a file manager;
 *  - an unreadable folder says so in place, instead of silently showing nothing;
 *  - the filter box searches the workspace by name (bounded server side, and it says when it stopped);
 *  - opening a notebook shows its cells; "@" attaches it to the next message;
 *  - the tree refreshes itself when the agent writes something, keeping what you had open.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { api, type WsHit } from "../api/client";
import type { Attachment } from "../domain/events";
import { Icon } from "./Icons";
import { focusFirstChild, focusParent, TreeRow, treeKeys, type RowAction } from "./Tree";

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

const isFolder = (k: string) => k === "directory" || k === "repo";

async function list(path: string): Promise<WsNode[]> {
  const r = await fetch(`/api/workspace?path=${encodeURIComponent(path)}&depth=1`);
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail ?? detail; } catch { /* non-JSON */ }
    throw new Error(detail);
  }
  return ((await r.json()).node?.children ?? []) as WsNode[];
}

interface Shared {
  expanded: React.MutableRefObject<Set<string>>;
  selected: string | null;
  onOpen: (n: WsNode) => void;
  onAttach: (a: Attachment) => void;
  onUseFolder: (path: string) => void;
  onFocusFolder: (path: string) => void;
}

function Row({ node, depth, sh }: { node: WsNode; depth: number; sh: Shared }) {
  const folder = isFolder(node.kind);
  const [open, setOpen] = useState(false);
  const [kids, setKids] = useState<WsNode[] | null>(node.children ?? null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(node.error ?? "");

  const load = useCallback(async () => {
    setLoading(true);
    try { setKids(await list(node.path)); setErr(""); }
    catch (e) { setErr(e instanceof Error ? e.message : "cannot read this folder"); }
    finally { setLoading(false); }
  }, [node.path]);

  // After a refresh the tree remounts; folders the user had open open again by themselves.
  const restored = useRef(false);
  useEffect(() => {
    if (restored.current || !folder || !sh.expanded.current.has(node.path)) return;
    restored.current = true;
    setOpen(true);
    if (!kids) void load();
  }, [folder, kids, load, node.path, sh.expanded]);

  const toggle = async () => {
    if (!node.hasChildren) return;
    sh.onFocusFolder(node.path);
    if (open) { setOpen(false); sh.expanded.current.delete(node.path); return; }
    setOpen(true);
    sh.expanded.current.add(node.path);
    if (!kids && !loading) await load();
  };

  const actions: RowAction[] = folder
    ? [{ label: `Work in ${node.name}`, glyph: "⌂", run: () => sh.onUseFolder(node.path) },
       { label: `Attach folder ${node.name}`, glyph: "@", run: () => sh.onAttach({ kind: "folder", ref: node.path, name: node.name }) }]
    : [{ label: `Attach ${node.name}`, glyph: "@",
         run: () => sh.onAttach({ kind: node.kind === "notebook" ? "notebook" : "file", ref: node.path, name: node.name }) }];

  return (
    <>
      <TreeRow
        depth={depth} expanded={folder ? open : undefined} selected={sh.selected === node.path} loading={loading}
        caret={folder && node.hasChildren} icon={node.kind} iconClass={`kind-${node.kind}`} dim={node.name.startsWith(".")}
        name={node.name} title={node.path}
        badge={node.language && <span className="tree-lang">{node.language.slice(0, 2).toLowerCase()}</span>}
        actions={actions}
        onActivate={() => (folder ? void toggle() : sh.onOpen(node))}
        onKeyDown={(e) => {
          if (e.key === "ArrowRight" && folder) { e.preventDefault(); if (!open) void toggle(); else focusFirstChild(e.currentTarget); }
          if (e.key === "ArrowLeft") { e.preventDefault(); if (folder && open) void toggle(); else focusParent(e.currentTarget); }
          treeKeys(e);
        }}
      />
      {err && <div className="tree-error" style={{ paddingLeft: 30 + depth * 14 }} role="alert">{err}</div>}
      {open && kids && (
        <div role="group">
          {kids.length === 0 && !err && <div className="tree-empty" style={{ paddingLeft: 30 + depth * 14 }}>(empty)</div>}
          {kids.map((k) => <Row key={k.path} node={k} depth={depth + 1} sh={sh} />)}
        </div>
      )}
    </>
  );
}

export function WorkspaceTree({ onOpenFile, onAttach, onUseFolder, selected, revision = 0 }: {
  onOpenFile: (n: WsNode | WsHit) => void;
  onAttach: (a: Attachment) => void;
  onUseFolder: (path: string) => void;
  selected?: string | null;
  /** Bumped by the app when the agent has written something: the tree reloads, keeping open folders. */
  revision?: number;
}) {
  const [roots, setRoots] = useState<{ path: string; name: string }[]>([]);
  const [error, setError] = useState("");
  const [manual, setManual] = useState(0);
  const [filter, setFilter] = useState("");
  const [hits, setHits] = useState<{ results: WsHit[]; complete: boolean; root: string } | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchErr, setSearchErr] = useState("");
  const [focusFolder, setFocusFolder] = useState("");
  const [making, setMaking] = useState(false);
  const [newName, setNewName] = useState("");
  const [note, setNote] = useState("");
  const expanded = useRef(new Set<string>());
  const first = useRef(true);

  useEffect(() => {
    if (!first.current) return;
    first.current = false;
    fetch("/api/workspace/roots").then(async (r) => {
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.detail ?? `the server answered ${r.status}`);
      setRoots(d.roots ?? []);
    }).catch((e) => setError(`cannot reach the workspace: ${e.message}`));
  }, []);

  // search: debounced, and a newer query always wins over an older, slower one
  useEffect(() => {
    const q = filter.trim();
    if (q.length < 2) { setHits(null); setSearchErr(""); return; }
    let live = true;
    setSearching(true);
    const id = window.setTimeout(async () => {
      try {
        const r = await api.search(q, focusFolder || roots[0]?.path);
        if (live) { setHits(r); setSearchErr(""); }
      } catch (e) {
        if (live) { setHits(null); setSearchErr(e instanceof Error ? e.message : "search failed"); }
      } finally { if (live) setSearching(false); }
    }, 350);
    return () => { live = false; window.clearTimeout(id); };
  }, [filter, focusFolder, roots]);

  const sh: Shared = {
    expanded, selected: selected ?? null, onOpen: onOpenFile, onAttach, onUseFolder, onFocusFolder: setFocusFolder,
  };

  const parent = focusFolder || roots[0]?.path || "";
  const createFolder = async () => {
    const name = newName.trim().replace(/^\/+|\/+$/g, "");
    if (!name || name.includes("..")) { setNote("a folder name, without .."); return; }
    try {
      await api.mkdir(`${parent}/${name}`);
      expanded.current.add(parent);
      setNewName(""); setMaking(false); setNote(`created ${name}`); setManual((n) => n + 1);
    } catch (e) { setNote(e instanceof Error ? e.message : "could not create the folder"); }
  };

  return (
    <div className="tree">
      <div className="tree-search">
        <input
          value={filter} onChange={(e) => setFilter(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Escape") setFilter(""); }}
          placeholder="Search notebooks and files…" aria-label="Search workspace" spellCheck={false}
        />
        <button className="btn ghost sm" title="Refresh" aria-label="Refresh tree" onClick={() => setManual((n) => n + 1)}>⟳</button>
        <button className="btn ghost sm" title={`New folder in ${parent}`} aria-label="New folder" onClick={() => setMaking((m) => !m)}>＋</button>
      </div>
      {making && (
        <form className="tree-new" onSubmit={(e) => { e.preventDefault(); void createFolder(); }}>
          <div className="tree-new-where" title={parent}>in {parent.split("/").slice(-2).join("/")}</div>
          <input autoFocus value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="folder name"
            aria-label="New folder name" spellCheck={false} />
          <button className="btn sm" type="submit" disabled={!newName.trim()}>Create</button>
        </form>
      )}
      {note && <div className="tree-note-line" role="status">{note}</div>}
      {error && <div className="tree-error" role="alert">{error}</div>}

      {filter.trim().length >= 2 ? (
        <div className="tree-results" role="list" aria-label="Search results">
          {searching && <div className="tree-empty"><span className="spin" /> searching…</div>}
          {searchErr && <div className="tree-error" role="alert">{searchErr}</div>}
          {!searching && hits && hits.results.length === 0 && <div className="tree-empty">No match under {hits.root}.</div>}
          {hits?.results.map((h) => (
            <button key={h.path} role="listitem" className="result" onClick={() => onOpenFile(h)} title={h.path}>
              <span className={`tree-icon kind-${h.kind}`} aria-hidden><Icon kind={h.kind} /></span>
              <span className="result-main">
                <span className="result-name">{h.name}</span>
                <span className="result-path">{h.path.split("/").slice(0, -1).join("/")}</span>
              </span>
            </button>
          ))}
          {hits && !hits.complete && !searching && (
            <div className="tree-note-line">Showing the first matches. Open a folder, then search again to narrow it.</div>
          )}
        </div>
      ) : (
        <div role="tree" aria-label="Workspace" className="tree-body">
          {roots.map((r) => (
            <Row key={`${r.path}:${revision}:${manual}`} node={{ ...r, kind: "directory", hasChildren: true } as WsNode} depth={0} sh={sh} />
          ))}
        </div>
      )}
      <p className="tree-note">Your workspace, with your permissions. Folders load as you open them.</p>
    </div>
  );
}
