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
import { PaneError } from "./PaneError";
import { useCallback, useContext, useEffect, useRef, useState } from "react";
import { api, type WsHit } from "../api/client";
import type { Attachment } from "../domain/events";
import { workspaceUrl, type LinkKind } from "../domain/links";
import {
  childPath, cloneName, downloadFormat, downloadName, importFormat, isFolder as folderKind,
  parentPath, readFavorites, toggleFavorite, type Favorite,
} from "../domain/workspaceMenu";
import { WorkspaceLinks } from "./DocContext";
import { Icon, Plus, Refresh } from "./Icons";
import { focusFirstChild, focusParent, TreeRow, treeKeys, type RowAction } from "./Tree";
import { ActionDialog, WorkspaceMenu, type PromptState } from "./WorkspaceMenu";

const FAV_KEY = "coding-agent.workspace-favorites";

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
  onMenu: (node: WsNode, x: number, y: number) => void;
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

  const ws = useContext(WorkspaceLinks);
  const link = workspaceUrl(ws, { kind: node.kind, ref: node.path, objectId: node.objectId });
  const openIn: RowAction[] = link ? [{ label: `Open ${node.name} in Databricks`, glyph: "↗", href: link }] : [];
  const more: RowAction = { label: `Actions for ${node.name}`, glyph: "⋯", run: (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    sh.onMenu(node, r.left, r.bottom + 4);
  } };
  const actions: RowAction[] = folder
    ? [{ label: `Work in ${node.name}`, glyph: "⌂", run: () => sh.onUseFolder(node.path) },
       { label: `Attach folder ${node.name}`, glyph: "@", run: () => sh.onAttach({ kind: "folder", ref: node.path, name: node.name }) },
       ...openIn, more]
    : [{ label: `Attach ${node.name}`, glyph: "@",
         run: () => sh.onAttach({ kind: node.kind === "notebook" ? "notebook" : "file", ref: node.path, name: node.name }) },
       ...openIn, more];

  return (
    <>
      <TreeRow
        depth={depth} expanded={folder ? open : undefined} selected={sh.selected === node.path} loading={loading}
        caret={folder && node.hasChildren} icon={node.kind} iconClass={`kind-${node.kind}`} dim={node.name.startsWith(".")}
        name={node.name} title={node.path}
        badge={node.language && <span className="tree-lang">{node.language.slice(0, 2).toLowerCase()}</span>}
        actions={actions}
        onContextMenu={(e) => sh.onMenu(node, e.clientX, e.clientY)}
        onActivate={() => (folder ? void toggle() : sh.onOpen(node))}
        onKeyDown={(e) => {
          if (e.key === "ContextMenu" || (e.shiftKey && e.key === "F10")) {
            e.preventDefault();
            const r = e.currentTarget.getBoundingClientRect();
            sh.onMenu(node, r.left + 28, r.bottom);
            return;
          }
          if (e.key === "ArrowRight" && folder) { e.preventDefault(); if (!open) void toggle(); else focusFirstChild(e.currentTarget); }
          if (e.key === "ArrowLeft") { e.preventDefault(); if (folder && open) void toggle(); else focusParent(e.currentTarget); }
          treeKeys(e);
        }}
      />
      {err && <PaneError message={err} indent={30 + depth * 14 - 8} />}
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
  const [menu, setMenu] = useState<{ x: number; y: number; node: WsNode } | null>(null);
  const [prompt, setPrompt] = useState<PromptState | null>(null);
  const [promptError, setPromptError] = useState("");
  const [busy, setBusy] = useState(false);
  const [favorites, setFavorites] = useState<Favorite[]>(() => {
    try { return readFavorites(localStorage.getItem(FAV_KEY)); } catch { return []; }
  });
  const expanded = useRef(new Set<string>());
  const first = useRef(true);
  const fileInput = useRef<HTMLInputElement>(null);
  const importParent = useRef("");
  const links = useContext(WorkspaceLinks);

  useEffect(() => {
    if (!first.current) return;
    first.current = false;
    fetch("/api/workspace/roots").then(async (r) => {
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.detail ?? `the server answered ${r.status}`);
      setRoots(d.roots ?? []);
    }).catch((e) => setError(`cannot reach the workspace: ${e.message}`));
  }, []);

  // Search: debounced, a newer query always wins, and a slow walk narrates itself.
  // The workspace API has no server-side search, so this is a bounded client-driven walk that takes
  // seconds on a real workspace. Honest feedback is the requirement (SH-D1..D3), not speed.
  const abort = useRef<AbortController | null>(null);
  const [startedAt, setStartedAt] = useState(0);
  useEffect(() => {
    const q = filter.trim();
    if (q.length < 2) { setHits(null); setSearchErr(""); setSearching(false); return; }
    let live = true;
    const id = window.setTimeout(async () => {
      abort.current?.abort();
      const ctl = new AbortController();
      abort.current = ctl;
      setSearching(true);
      setStartedAt(Date.now());
      try {
        const r = await api.search(q, focusFolder || roots[0]?.path, ctl.signal);
        if (live && !ctl.signal.aborted) { setHits(r); setSearchErr(""); }
      } catch (e) {
        // A cancelled search keeps whatever results were already shown: emptying the list punishes
        // the user for changing their mind.
        if (live && !ctl.signal.aborted) setSearchErr(e instanceof Error ? e.message : "search failed");
      } finally { if (live) setSearching(false); }
    }, 350);
    return () => { live = false; window.clearTimeout(id); };
  }, [filter, focusFolder, roots]);

  useEffect(() => {
    try { localStorage.setItem(FAV_KEY, JSON.stringify(favorites)); } catch { /* private mode */ }
  }, [favorites]);

  const sh: Shared = {
    expanded, selected: selected ?? null, onOpen: onOpenFile, onAttach, onUseFolder, onFocusFolder: setFocusFolder,
    onMenu: (node, x, y) => { setMenu({ node, x, y }); setPrompt(null); },
  };

  const home = roots.find((r) => r.name === "My home")?.path ?? "";
  const linkFor = (n: { path: string; kind: string; objectId?: string }) =>
    workspaceUrl(links, { kind: n.kind as LinkKind, ref: n.path, objectId: n.objectId });

  const refresh = (parent?: string) => {
    if (parent) expanded.current.add(parent);
    setManual((n) => n + 1);
  };

  const fail = (e: unknown) => setNote(e instanceof Error ? e.message : "that did not work");

  const immediate = async (id: string, node: WsNode) => {
    if (id === "attach") {
      onAttach({ kind: folderKind(node.kind) ? "folder" : node.kind === "notebook" ? "notebook" : "file", ref: node.path, name: node.name });
      setNote(`attached ${node.name}`);
      return;
    }
    if (id === "use-folder") { onUseFolder(node.path); setNote(`working in ${node.name}`); return; }
    if (id === "open") {
      const href = linkFor(node);
      if (href) window.open(href, "_blank", "noopener");
      else setNote("this workspace has no link for that object");
      return;
    }
    if (id === "copy-url" || id === "copy-path") {
      const text = id === "copy-path" ? node.path : (linkFor(node) ?? "");
      if (!text) { setNote("there is no URL for that object"); return; }
      try { await navigator.clipboard.writeText(text); setNote(id === "copy-path" ? "path copied" : "URL copied"); }
      catch { setNote("the clipboard is not available"); }
      return;
    }
    if (id === "import") {
      importParent.current = node.path;
      fileInput.current?.click();
      return;
    }
    if (id === "favorite") {
      setFavorites((list) => toggleFavorite(list, { path: node.path, name: node.name, kind: node.kind, objectId: node.objectId }));
      return;
    }
    const format = downloadFormat(id);
    if (format) {
      try { await api.download(node.path, format, downloadName(node.name, format, node.language)); setNote(`downloaded ${node.name}`); }
      catch (e) { fail(e); }
    }
  };

  const pick = (id: string) => {
    const node = menu?.node;
    setMenu(null);
    if (!node) return;
    if (id === "rename" || id === "clone" || id === "move" || id === "trash" || id === "share"
        || id === "create-notebook" || id === "create-file" || id === "create-folder") {
      setPromptError("");
      setPrompt({
        id, node,
        value: id === "rename" ? node.name : id === "clone" ? cloneName(node.name) : id === "move" ? parentPath(node.path) : "",
        language: "PYTHON",
      });
      return;
    }
    void immediate(id, node);
  };

  const confirm = async () => {
    if (!prompt) return;
    const node = prompt.node as WsNode;
    setBusy(true);
    setPromptError("");
    try {
      if (prompt.id === "trash") {
        await api.removeObject(node.path, folderKind(node.kind));
        setFavorites((list) => list.filter((f) => f.path !== node.path && !f.path.startsWith(node.path + "/")));
        setNote(`moved ${node.name} to Trash`);
        refresh(parentPath(node.path));
      } else if (prompt.id === "rename" || prompt.id === "clone" || prompt.id === "move") {
        const dest = prompt.id === "move"
          ? childPath(prompt.value ?? "", node.name)
          : childPath(parentPath(node.path), prompt.value ?? "");
        if (!dest || (prompt.id === "move" && !(prompt.value ?? "").startsWith("/"))) {
          setPromptError(prompt.id === "move" ? "a folder path, starting with /" : "use a name without slashes");
          return;
        }
        await api.transferObject(node.path, dest, prompt.id === "clone" ? "copy" : "move");
        if (prompt.id !== "clone") {
          setFavorites((list) => list.map((f) => f.path === node.path ? { ...f, path: dest, name: dest.split("/").pop() || f.name } : f));
        }
        setNote(prompt.id === "clone" ? `cloned to ${dest}` : `now at ${dest}`);
        refresh(parentPath(dest));
        if (prompt.id !== "clone") refresh(parentPath(node.path));
      } else if (prompt.id === "create-notebook" || prompt.id === "create-file" || prompt.id === "create-folder") {
        const kind = prompt.id === "create-notebook" ? "notebook" : prompt.id === "create-file" ? "file" : "folder";
        const name = (prompt.value ?? "").trim();
        if (!childPath(node.path, name)) { setPromptError("use a name without slashes"); return; }
        await api.createObject(node.path, name, kind, prompt.language);
        setNote(`created ${name}`);
        refresh(node.path);
      }
      setPrompt(null);
    } catch (e) {
      setPromptError(e instanceof Error ? e.message : "that did not work");
    } finally { setBusy(false); }
  };

  const onImport = async (file: File) => {
    const parent = importParent.current;
    if (!parent) return;
    if (file.size > 8_000_000) { setNote("that file is too large to import here; open it in Databricks"); return; }
    const spec = importFormat(file.name);
    try {
      const raw = new Uint8Array(await file.arrayBuffer());
      let bin = "";
      for (let i = 0; i < raw.length; i += 0x8000) bin += String.fromCharCode(...raw.subarray(i, i + 0x8000));
      await api.importObject(parent, file.name, btoa(bin), spec.format, spec.language);
      setNote(`imported ${file.name}`);
      refresh(parent);
    } catch (e) { fail(e); }
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
        <button className="icon-btn tree-refresh" title="Refresh" aria-label="Refresh the file tree"
          onClick={() => setManual((n) => n + 1)}><Refresh size={15} /></button>
        <button className="icon-btn" title={`New folder in ${parent}`} aria-label="New folder"
          onClick={() => setMaking((m) => !m)}><Plus size={15} /></button>
      </div>
      {making && (
        <form className="tree-new" onSubmit={(e) => { e.preventDefault(); void createFolder(); }}>
          <div className="tree-new-where" title={parent}>in {parent.split("/").slice(-2).join("/")}</div>
          <input autoFocus value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="folder name"
            aria-label="New folder name" spellCheck={false} />
          <button className="btn sm" type="submit" disabled={!newName.trim()}>Create</button>
        </form>
      )}
      <input ref={fileInput} type="file" hidden aria-hidden
        onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void onImport(f); }} />
      {note && <div className="tree-note-line" role="status">{note}</div>}
      {error && <PaneError message={error} onRetry={() => setManual((n) => n + 1)} />}

      {filter.trim().length >= 2 ? (
        <div className="tree-results" role="list" aria-label="Search results">
          {/* Skeleton rows while results are in flight, plus the honest slow hint. The count of
              bars is a placeholder, not a promise: the result count is shown as soon as it is known. */}
          {searching && (
            <div className="sk-list" role="status" aria-label="Searching the workspace">
              {[0, 1, 2, 3].map((i) => (
                <div className="sk-row" key={i}><span className="sk a" /><span className="sk b" /></div>
              ))}
              {Date.now() - startedAt > 1200 && (
                <p className="tree-slow">This workspace is large; folders are walked in order.</p>
              )}
            </div>
          )}
          {searchErr && <PaneError message={searchErr} />}
          {!searching && hits && hits.results.length === 0 && <div className="tree-empty">No match under {hits.root}.</div>}
          {hits && !searching && hits.results.length > 0 && (
            <div className="tree-note-line" role="status">
              {hits.results.length} match{hits.results.length === 1 ? "" : "es"}
              {hits.complete ? "" : " so far"}
            </div>
          )}
          {hits?.results.map((h) => (
            <button key={h.path} role="listitem" className="result" onClick={() => onOpenFile(h)} title={h.path}
              onContextMenu={(e) => { e.preventDefault(); setMenu({ x: e.clientX, y: e.clientY, node: { path: h.path, name: h.name, kind: h.kind as WsNode["kind"], language: h.language, hasChildren: folderKind(h.kind) } }); }}>
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
          {favorites.length > 0 && <div className="tree-label">Favorites</div>}
          {favorites.map((f) => (
            <Row key={`fav:${f.path}:${manual}`} node={{ ...f, kind: f.kind as WsNode["kind"], hasChildren: folderKind(f.kind) }} depth={0} sh={sh} />
          ))}
          {roots.map((r) => (
            <Row key={`${r.path}:${revision}:${manual}`} node={{ ...r, kind: "directory", hasChildren: true } as WsNode} depth={0} sh={sh} />
          ))}
        </div>
      )}
      <p className="tree-note">Right-click a file or folder for the same actions as Databricks. Folders load as you open them.</p>
      {menu && (
        <WorkspaceMenu x={menu.x} y={menu.y} node={menu.node} home={home}
          favorite={favorites.some((f) => f.path === menu.node.path)}
          onPick={pick} onClose={() => setMenu(null)} />
      )}
      {prompt && (
        <ActionDialog prompt={prompt} busy={busy} error={promptError} link={linkFor(prompt.node)}
          onChange={(next) => { setPrompt(next); setPromptError(""); }}
          onCancel={() => { if (!busy) setPrompt(null); }}
          onConfirm={() => void confirm()} />
      )}
    </div>
  );
}
