/** The working-folder picker: a real tree, not a text box.
 *
 * The first-run screen used to ask for the write fence by typing an absolute path into an input. That
 * is the single most consequential field in the app — everything the agent may change lives under it —
 * and it was a free-text box with a placeholder: a typo meant a session that could write nowhere, and
 * nobody could see which folders were even available.
 *
 * So: the same lazily-loaded workspace tree the Files pane uses (one request per folder opened, folders
 * first, unreadable folders say so), inside a popover, with a search that walks by name. Choose a
 * folder and it becomes the fence. The path stays visible and editable as a fallback for a path the
 * tree cannot reach (another user's home, a path not yet created).
 *
 * Deliberate choices:
 *  - **the trigger reads as the answer**, not as an action: it shows the folder name and its path, so
 *    the fence is legible without opening anything;
 *  - **"Use this folder" is on the row**, so choosing is one click, not select-then-confirm;
 *  - **the current folder is marked**, so reopening the picker answers "where am I?" at a glance;
 *  - **Escape closes and returns focus**, and the popover never traps focus.
 */
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api, type WsHit } from "../api/client";
import { canonicalPath, parentOf } from "../domain/docs";
import { ChevronRight, Folder, Refresh, Search } from "./Icons";
import { useReturnFocus } from "../hooks/useReturnFocus";

interface Node {
  path: string;
  name: string;
  kind: string;
  hasChildren: boolean;
  language?: string;
}

const POPOVER_WIDTH = 420;
const POPOVER_MAX = 400;

async function listFolder(path: string): Promise<Node[]> {
  const r = await fetch(`/api/workspace?path=${encodeURIComponent(path)}&depth=1`);
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail ?? detail; } catch { /* not JSON */ }
    throw new Error(detail);
  }
  return ((await r.json()).node?.children ?? []) as Node[];
}

/** One folder row. Children load the first time it opens, then stay: the picker is short-lived, so a
 *  cache would outlive its usefulness and a stale tree is worse than a re-fetch. */
function Branch({ node, depth, current, expanded, onToggle, onPick }: {
  node: Node; depth: number; current: string;
  expanded: Set<string>; onToggle: (path: string) => void; onPick: (path: string) => void;
}) {
  const open = expanded.has(node.path);
  const [kids, setKids] = useState<Node[] | null>(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);
  const mine = canonicalPath(node.path) === current;

  useEffect(() => {
    if (!open || kids || loading) return;
    let live = true;
    setLoading(true);
    listFolder(node.path)
      .then((k) => { if (live) { setKids(k.filter((c) => c.kind === "directory" || c.kind === "repo")); setErr(""); } })
      .catch((e) => { if (live) setErr(e instanceof Error ? e.message : "cannot read this folder"); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, node.path]);

  return (
    <div role="none">
      <div className={`fp-row${mine ? " is-current" : ""}`} style={{ paddingLeft: 8 + depth * 14 }}>
        <button type="button" className="fp-twisty" aria-expanded={node.hasChildren ? open : undefined}
          aria-label={open ? `Collapse ${node.name}` : `Expand ${node.name}`}
          disabled={!node.hasChildren}
          onClick={() => { onToggle(node.path); }}>
          {node.hasChildren ? <ChevronRight size={12} className={open ? "is-open" : ""} /> : null}
        </button>
        <button type="button" className="fp-name" onClick={() => { onToggle(node.path); }} title={node.path}>
          <Folder size={13} /> <span>{node.name}</span>
        </button>
        {mine
          ? <span className="fp-badge">current</span>
          : <button type="button" className="fp-use" onClick={() => onPick(node.path)}>Use</button>}
      </div>
      {open && (
        <div role="group">
          {loading && !kids && <p className="fp-note" style={{ paddingLeft: 30 + depth * 14 }}>loading…</p>}
          {err && <p className="fp-note is-err" style={{ paddingLeft: 30 + depth * 14 }}>{err}</p>}
          {kids?.length === 0 && !err && !loading && (
            <p className="fp-note" style={{ paddingLeft: 30 + depth * 14 }}>no sub-folders</p>
          )}
          {kids?.map((k) => (
            <Branch key={k.path} node={k} depth={depth + 1} current={current}
              expanded={expanded} onToggle={onToggle} onPick={onPick} />
          ))}
        </div>
      )}
    </div>
  );
}

export function FolderPicker({ value, onChange, disabled }: {
  value: string;
  onChange: (path: string) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [roots, setRoots] = useState<Node[]>([]);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");
  /** A free-text path, for somewhere the tree does not reach. Toggled, not always shown: a text box
   *  beside a tree invites typing a path that the tree could have given in one click. */
  const [typing, setTyping] = useState(false);
  const [draft, setDraft] = useState(value);
  const [hits, setHits] = useState<WsHit[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState("");
  /** Bumped by Refresh: the roots (and every open branch, via a remount) are fetched again. */
  const [manual, setManual] = useState(0);
  /** The row of the current folder, scrolled to after the ancestors have loaded. */
  const listRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    let tries = 0;
    const find = () => {
      const el = listRef.current?.querySelector<HTMLElement>(".fp-row.is-current");
      if (el) { el.scrollIntoView({ block: "center" }); return; }
      if (tries++ < 12) window.setTimeout(find, 150);
    };
    const id = window.setTimeout(find, 120);
    return () => window.clearTimeout(id);
  }, [open]);
  const trigger = useRef<HTMLButtonElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const baseId = useId();

  const current = canonicalPath(value);
  const label = current.split("/").filter(Boolean).pop() ?? current;

  useEffect(() => { setDraft(value); }, [value]);

  // Open: fetch the roots, and start with the current folder's ancestors expanded so the answer is in
  // place rather than somewhere to walk to.
  useEffect(() => {
    if (!open) return;
    let live = true;
    setError("");
    fetch("/api/workspace/roots")
      .then(async (r) => {
        const d = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(d.detail ?? `the server answered ${r.status}`);
        return (d.roots ?? []) as { path: string; name: string }[];
      })
      .then((rs) => {
        if (!live) return;
        setRoots(rs.map((r) => ({ ...r, kind: "directory", hasChildren: true })));
        // Expand the current folder and every folder above it, so opening the picker ANSWERS
        // "where am I?" instead of asking the user to walk to their own location. Only paths at or
        // below a root are kept: a prefix the tree cannot show would expand nothing.
        const parts = current.split("/").filter(Boolean);
        const chain = new Set<string>();
        for (let i = 1; i <= parts.length; i++) chain.add("/" + parts.slice(0, i).join("/"));
        for (const c of [...chain]) {
          if (!rs.some((r) => c === r.path || c.startsWith(r.path + "/"))) chain.delete(c);
        }
        setExpanded(chain);
      })
      .catch((e) => { if (live) setError(`cannot reach the workspace: ${e.message}`); });
    return () => { live = false; };
  }, [open, current, manual]);

  // Focus the search on open: the first thing anyone does here is look for a folder.
  useEffect(() => {
    if (!open) return;
    const id = window.setTimeout(() => search.current?.focus(), 30);
    return () => window.clearTimeout(id);
  }, [open]);

  // KB-1: closing the tree puts focus back on the trigger. The hook does it, so a click-outside and an
  // Escape behave the same and neither can forget.
  useReturnFocus(open);

  const close = useCallback((returnFocus = true) => {
    setOpen(false);
    setQuery("");
    setHits(null);
    setTyping(false);
    if (returnFocus) trigger.current?.focus();
  }, []);

  // Escape from anywhere, and a click outside. The popover is portalled, so "inside" is two checks.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || e.defaultPrevented) return;
      e.preventDefault();
      close();
    };
    const onDown = (e: MouseEvent) => {
      const t = e.target as HTMLElement | null;
      if (!t) return;
      if (t.closest(".folder-picker") || t.closest(".fp-pop")) return;
      close(false);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onDown);
    return () => { window.removeEventListener("keydown", onKey); window.removeEventListener("mousedown", onDown); };
  }, [open, close]);

  // Search by name, the same bounded walk the Files pane uses. Debounced; a newer query wins.
  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) { setHits(null); setSearching(false); return; }
    let live = true;
    const id = window.setTimeout(async () => {
      setSearching(true);
      try {
        const r = await api.search(q, roots[0]?.path);
        if (live) setHits(r.results.filter((h) => h.kind === "directory" || h.kind === "repo"));
      } catch (e) {
        if (live) setError(e instanceof Error ? e.message : "search failed");
      } finally { if (live) setSearching(false); }
    }, 320);
    return () => { live = false; window.clearTimeout(id); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);

  const toggle = (path: string) => {
    setExpanded((cur) => {
      const next = new Set(cur);
      if (next.has(path)) next.delete(path); else next.add(path);
      return next;
    });
  };

  const pick = (path: string) => {
    onChange(canonicalPath(path));
    close();
  };

  /** Placement, measured after mount so a popover near the bottom edge flips up instead of leaving
   *  the viewport. Fixed positioning: it is portalled, so no ancestor can clip it. */
  const [placement, setPlacement] = useState<{ top: number; left: number; width: number } | null>(null);
  useEffect(() => {
    if (!open) { setPlacement(null); return; }
    const r = trigger.current?.getBoundingClientRect();
    if (!r) return;
    const width = Math.min(POPOVER_WIDTH, window.innerWidth - 24);
    const below = window.innerHeight - r.bottom - 12;
    const top = below > 260 ? r.bottom + 6 : Math.max(12, r.top - POPOVER_MAX - 6);
    setPlacement({ top, left: Math.max(12, Math.min(r.left, window.innerWidth - width - 12)), width });
  }, [open]);

  return (
    <div className="folder-picker">
      <button ref={trigger} type="button" className="fp-trigger" disabled={disabled}
        aria-haspopup="dialog" aria-expanded={open} aria-controls={open ? `${baseId}-pop` : undefined}
        onClick={() => (open ? close(false) : setOpen(true))}
        title={value ? `The agent may write only in ${value}` : "Choose the folder the agent may write in"}>
        <span className="fp-trigger-ico" aria-hidden><Folder size={14} /></span>
        <span className="fp-trigger-text">
          <span className="fp-trigger-name">{label || "Choose a working folder"}</span>
          <span className="fp-trigger-path">{value || "the agent can write only there"}</span>
        </span>
        <ChevronRight size={13} className="fp-trigger-caret" />
      </button>

      {open && placement && createPortal(
        <div className="fp-pop" id={`${baseId}-pop`} role="dialog" aria-modal="false"
          aria-label="Choose the working folder" ref={box}
          style={{ top: placement.top, left: placement.left, width: placement.width }}>
          <div className="fp-head">
            <Search size={13} />
            <input ref={search} className="fp-search" value={query} placeholder="Find a folder…"
              aria-label="Find a folder by name" spellCheck={false}
              onChange={(e) => { setQuery(e.target.value); setError(""); }} />
            <button type="button" className="icon-btn" title="Refresh the folder list" aria-label="Refresh"
              onClick={() => { setExpanded(new Set()); setManual((n) => n + 1); }}>
              <Refresh size={14} />
            </button>
          </div>

          <p className="fp-hint">
            The agent can write <strong>only here</strong>. Everything else asks you first.
          </p>

          {error && <p className="fp-note is-err">{error}</p>}

          {query.trim().length >= 2 ? (
            <div className="fp-list" role="list" aria-label="Folder matches">
              {searching && <p className="fp-note"><span className="spin" aria-hidden /> searching the workspace by name…</p>}
              {!searching && hits?.length === 0 && <p className="fp-note">No folder matches “{query.trim()}”.</p>}
              {hits?.map((h) => (
                <div key={h.path} className={`fp-row${canonicalPath(h.path) === current ? " is-current" : ""}`}>
                  <span className="fp-twisty" />
                  <button type="button" className="fp-name" onClick={() => pick(h.path)} title={h.path}>
                    <Folder size={13} /> <span>{h.name}</span>
                    <span className="fp-where">{parentOf(h.path)}</span>
                  </button>
                  <button type="button" className="fp-use" onClick={() => pick(h.path)}>Use</button>
                </div>
              ))}
            </div>
          ) : (
            <div className="fp-list" role="tree" aria-label="Workspace folders" ref={listRef}>
              {roots.length === 0 && !error && <p className="fp-note">loading your workspace…</p>}
              {roots.map((r) => (
                <Branch key={`${r.path}:${manual}`} node={r} depth={0} current={current}
                  expanded={expanded} onToggle={toggle} onPick={pick} />
              ))}
            </div>
          )}

          <div className="fp-foot">
            {typing ? (
              <form className="fp-type" onSubmit={(e) => { e.preventDefault(); if (draft.trim().startsWith("/")) pick(draft.trim()); }}>
                <input autoFocus value={draft} onChange={(e) => setDraft(e.target.value)}
                  placeholder="/Users/you/agent_scratch" aria-label="Working folder path" spellCheck={false} />
                <button className="btn primary sm" type="submit" disabled={!draft.trim().startsWith("/")}>Use</button>
                <button className="btn ghost sm" type="button" onClick={() => { setTyping(false); setDraft(value); }}>Cancel</button>
              </form>
            ) : (
              <>
                <span className="fp-foot-note">Everything under it, nothing outside it.</span>
                {/* A fallback, not the primary path: reachable when the folder cannot be walked to. */}
                <button type="button" className="btn ghost sm" onClick={() => setTyping(true)}>Type a path…</button>
              </>
            )}
          </div>
        </div>,
        document.body,
      )}
    </div>
  );
}
