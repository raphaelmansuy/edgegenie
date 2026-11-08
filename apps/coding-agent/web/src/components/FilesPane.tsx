/** Files: the tree and the list, over one folder, with one menu (spec 006 FL-1..FL-6).
 *
 * A tree answers *where*, a list answers *which*. Databricks offers both and so does this, because
 * the two questions are different: "show me my folders" and "which of these is the notebook I edited
 * yesterday" cannot be answered by the same control.
 *
 * One `list()` call feeds both views. That is the DRY decision in this file: a second fetch path would
 * mean the two views could show different folders after a refresh.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { Attachment } from "../domain/events";
import {
  crumbsFor, emptyCopy, filterNodes, parentOf, readView, sortNodes, typeLabel, typeDetail, whereLabel,
  VIEW_KEY, type FilesView,
} from "../domain/files";
import { importFormat, readFavorites, toggleFavorite, type Favorite } from "../domain/workspaceMenu";
import { PaneError } from "./PaneError";
import { Icon, ListIcon, Refresh } from "./Icons";
import { WorkspaceMenu } from "./WorkspaceMenu";
import { WorkspaceTree, type WsNode } from "./WorkspaceTree";

export interface FilesPaneProps {
  selected?: string | null;
  /** Bumped by the app when the agent has written something: both views reload. */
  revision?: number;
  onOpenFile: (n: WsNode) => void;
  onAttach: (a: Attachment) => void;
  onUseFolder: (path: string) => void;
}

async function fetchDir(path: string): Promise<WsNode[]> {
  const r = await fetch(`/api/workspace?path=${encodeURIComponent(path)}&depth=1`);
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail ?? detail; } catch { /* non-JSON */ }
    throw new Error(detail);
  }
  return ((await r.json()).node?.children ?? []) as WsNode[];
}

export function FilesPane({ selected, revision = 0, onOpenFile, onAttach, onUseFolder }: FilesPaneProps) {
  const [view, setView] = useState<FilesView>(() => {
    try { return readView(localStorage.getItem(VIEW_KEY)); } catch { return "tree"; }
  });
  const [root, setRoot] = useState<{ path: string; name: string } | null>(null);
  const [here, setHere] = useState("");
  const [nodes, setNodes] = useState<WsNode[] | null>(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [menu, setMenu] = useState<{ x: number; y: number; node: WsNode } | null>(null);
  const [drag, setDrag] = useState(false);
  const [note, setNote] = useState("");
  const [favorites, setFavorites] = useState<Favorite[]>(() => {
    try { return readFavorites(localStorage.getItem("coding-agent.workspace-favorites")); } catch { return []; }
  });
  const dropRef = useRef<HTMLDivElement>(null);

  const persistView = (v: FilesView) => {
    setView(v);
    try { localStorage.setItem(VIEW_KEY, v); } catch { /* private mode */ }
  };

  // The roots are the ones the tree already computes: home, Shared, Repos. One request, once.
  useEffect(() => {
    let live = true;
    fetch("/api/workspace/roots").then(async (r) => {
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.detail ?? `the server answered ${r.status}`);
      const roots = d.roots ?? [];
      const first = roots[0];
      if (!live) return;
      if (!first) { setError("this workspace has no folders your account can see"); return; }
      setRoot(first);
      setHere((h) => h || first.path);
    }).catch((e) => { if (live) setError(`cannot reach the workspace: ${e.message}`); });
    return () => { live = false; };
  }, []);

  // One loader for both views. A folder that fails says so and keeps the previous listing: an empty
  // list would read as "this folder is empty", which is a different and false statement.
  const load = useCallback(async (path: string) => {
    if (!path) return;
    setBusy(true);
    try {
      setNodes(sortNodes(await fetchDir(path)));
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "cannot read this folder");
    } finally { setBusy(false); }
  }, []);

  /* Loading is keyed on the FOLDER and the view, not on the roots. The first version also waited for
     `here`, which is seeded from the roots response — so switching to the list before the roots
     arrived left the pane saying "reading…" forever. A folder that is not known yet is a reason to
     show nothing, not a reason to never ask. */
  useEffect(() => {
    if (view !== "list" || !here) return;
    void load(here);
  }, [view, here, revision, load]);

  const crumbs = root ? crumbsFor(root.name, here, root.path) : [];
  const shown = nodes ? filterNodes(nodes, query) : null;

  const open = (n: WsNode) => {
    if (n.kind === "directory" || n.kind === "repo") { setHere(n.path); return; }
    onOpenFile(n);
  };

  const up = () => { const p = parentOf(here); if (p) setHere(p); };

  // Dropping files imports them into the folder on screen, using the existing route (FL-6).
  const onDrop = async (files: FileList) => {
    if (!here) return;
    for (const file of Array.from(files)) {
      if (file.size > 8_000_000) { setNote(`${file.name} is too large to import here`); continue; }
      try {
        const bytes = new Uint8Array(await file.arrayBuffer());
        let bin = "";
        for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
        const spec = importFormat(file.name);
        await api.importObject(here, file.name, btoa(bin), spec.format, spec.language);
        setNote(`imported ${file.name}`);
      } catch (e) { setNote(e instanceof Error ? e.message : `could not import ${file.name}`); }
    }
    void load(here);
  };

  const header = (
    <div className="files-head">
      <div className="files-head-row">
        <span className="files-title">FILES</span>
        <span className="files-head-spacer" />
        <button className="icon-btn" aria-pressed={view === "tree"} aria-label="Tree view"
          title="Tree view" onClick={() => persistView("tree")}><ListIcon size={14} /></button>
        <button className="icon-btn" aria-pressed={view === "list"} aria-label="List view"
          title="List view" onClick={() => persistView("list")}><span aria-hidden>☰</span></button>
        {view === "list" && (
          <button className="icon-btn" aria-label="Refresh this folder" title="Refresh"
            onClick={() => { void load(here); setNote(""); }}><Refresh size={14} className={busy ? "spin" : ""} /></button>
        )}
      </div>
      {view === "list" && (
        <input className="files-search" value={query} onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter this folder…" aria-label="Filter this folder" spellCheck={false} />
      )}
      {view === "list" && (
        <nav className="files-crumbs" aria-label="Folder">
          {parentOf(here) && (
            <button className="crumb-up" onClick={up} title="Go up one folder" aria-label="Go up one folder">↑</button>
          )}
          {crumbs.map((c, i) => (
            <span key={c.path}>
              {i > 0 && <span className="crumb-sep" aria-hidden>/</span>}
              <button className="crumb" onClick={() => setHere(c.path)} title={c.path}>{c.name}</button>
            </span>
          ))}
        </nav>
      )}
      {note && <div className="tree-note-line" role="status">{note}</div>}
    </div>
  );

  return (
    <div className="files-pane" ref={dropRef}
      onDragOver={(e) => { if (view === "list") { e.preventDefault(); setDrag(true); } }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => { if (view === "list") { e.preventDefault(); setDrag(false); void onDrop(e.dataTransfer.files); } }}>
      {header}

      {view === "tree" ? (
        <div className="rail-tree">
          <WorkspaceTree selected={selected ?? null} revision={revision}
            onOpenFile={(n) => onOpenFile(n as WsNode)} onAttach={onAttach} onUseFolder={onUseFolder} />
        </div>
      ) : (
        <>
          {error && <PaneError message={error} onRetry={() => void load(here)} />}
          {!error && shown === null && <p className="files-note"><span className="spin" /> reading…</p>}
          {!error && shown && (
            <div className={`file-list${drag ? " is-drop" : ""}`} role="table" aria-label={`Contents of ${here}`}>
              <div className="file-row file-row-head" role="row">
                <span role="columnheader">Name</span>
                <span role="columnheader">Type</span>
                <span role="columnheader">Folder</span>
              </div>
              {shown.length === 0 && <p className="tree-empty">{emptyCopy(query, true)}</p>}
              {shown.map((n) => (
                <div key={n.path} role="row" tabIndex={0}
                  className={`file-row${selected === n.path ? " is-selected" : ""}${n.name.startsWith(".") ? " is-dim" : ""}`}
                  onClick={() => open(n)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(n); }
                    if (e.key === "ArrowDown") { e.preventDefault(); (e.currentTarget.nextElementSibling as HTMLElement | null)?.focus(); }
                    if (e.key === "ArrowUp") { e.preventDefault(); (e.currentTarget.previousElementSibling as HTMLElement | null)?.focus(); }
                  }}
                  onContextMenu={(e) => { e.preventDefault(); setMenu({ x: e.clientX, y: e.clientY, node: n }); }}
                  title={n.path}>
                  <span className="file-name" role="cell">
                    <span className={`tree-icon kind-${n.kind}`} aria-hidden><Icon kind={n.kind} /></span>
                    <span className="file-name-text">{n.name}</span>
                    {typeDetail(n) && <span className="tree-lang">{typeDetail(n).slice(0, 2).toLowerCase()}</span>}
                  </span>
                  <span className="file-type" role="cell">{typeLabel(n.kind)}</span>
                  <span className="file-where" role="cell" title={n.path}>
                    {whereLabel(n.path, root?.path ?? "")}
                  </span>
                </div>
              ))}
              <p className="files-note">
                {shown.length} item{shown.length === 1 ? "" : "s"}
                {query ? ` matching “${query}”` : ""} · right-click for actions
              </p>
            </div>
          )}
        </>
      )}

      {favorites.length > 0 && (
        <div className="files-favorites">
          <div className="files-favorites-head">Favorites</div>
          {favorites.slice(0, 6).map((f) => (
            <button key={f.path} className="files-favorite" title={f.path}
              onClick={() => onOpenFile({ ...f, kind: f.kind as WsNode["kind"], hasChildren: false } as WsNode)}>
              <Icon kind={f.kind} /> {f.name}
            </button>
          ))}
        </div>
      )}

      {menu && (
        <WorkspaceMenu x={menu.x} y={menu.y} node={menu.node} home={root?.path ?? ""}
          favorite={favorites.some((f) => f.path === menu.node.path)}
          onPick={(id) => {
            const node = menu.node;
            setMenu(null);
            if (id === "favorite") {
              const next = toggleFavorite(favorites, { path: node.path, name: node.name, kind: node.kind });
              setFavorites(next);
              try { localStorage.setItem("coding-agent.workspace-favorites", JSON.stringify(next)); } catch { /* private */ }
            }
          }}
          onClose={() => setMenu(null)} />
      )}
    </div>
  );
}

export type { FilesView };
