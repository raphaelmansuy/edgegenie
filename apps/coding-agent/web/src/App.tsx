/** App shell: a left rail (sessions, files, catalog), a main pane (chat and open documents), an inspector.
 *
 * The three things that make this a Genie-Code-class assistant rather than a chat box:
 *  1. you browse the real workspace and catalog and OPEN what you find;
 *  2. what you are looking at, and what you @-mention, goes to the agent as context;
 *  3. when the agent writes something, the tree refreshes and the result opens in one click.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type ModelOption, type SessionSummary } from "./api/client";
import { ApprovalSheet, EmptyState, Inspector } from "./components/Chrome";
import { Palette, PaletteActions } from "./components/Palette";
import { ShortcutSheet } from "./components/ShortcutSheet";
import { CatalogTree } from "./components/CatalogTree";
import { Composer } from "./components/Composer";
import { OpenDoc, WorkspaceLinks } from "./components/DocContext";
import { ExtLink } from "./components/ExtLink";
import type { Workspace } from "./domain/links";
import { TurnView } from "./components/Transcript";
import { NotebookViewer, TableViewer } from "./components/Viewer";
import { WorkspaceTree } from "./components/WorkspaceTree";
import { tabKeys } from "./components/Tree";
import type { Candidate } from "./domain/fuzzy";
import { caps, display } from "./domain/keys";
import { useHotkeys } from "./hooks/useHotkeys";
import { ACTIONS, asAttachment, docForNode, makeDoc, touched, type Action, type Doc } from "./domain/docs";
import type { Attachment } from "./domain/events";
import { useSessionStream } from "./hooks/useSessionStream";

type Rail = "sessions" | "files" | "catalog";
const CHAT = "chat";

const dedupe = (items: Attachment[]) => {
  const seen = new Set<string>();
  return items.filter((a) => (seen.has(`${a.kind}:${a.ref}`) ? false : (seen.add(`${a.kind}:${a.ref}`), true)));
};

export function App() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [models, setModels] = useState<ModelOption[]>([]);
  const [defaultModel, setDefaultModel] = useState("");
  const [scratch, setScratch] = useState("");
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [demo, setDemo] = useState(false);
  const [active, setActive] = useState<string | null>(null);
  const [folder, setFolder] = useState("");
  const [model, setModel] = useState("");
  const [notice, setNotice] = useState("");
  const [rail, setRail] = useState<Rail>("sessions");
  const [docs, setDocs] = useState<Doc[]>([]);
  const [view, setView] = useState<string>(CHAT);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [treeRev, setTreeRev] = useState(0);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [keysOpen, setKeysOpen] = useState(false);
  const [railShown, setRailShown] = useState(true);
  const [inspShown, setInspShown] = useState(true);
  const bottom = useRef<HTMLDivElement>(null);
  const composerBox = useRef<HTMLTextAreaElement | null>(null);

  const { session, conn, error, send, stop, setSession } = useSessionStream(active);

  // stable identity: this is called from a mount effect, so it must not change per render
  const refresh = useCallback(async () => {
    const [s, m, me] = await Promise.all([
      api.sessions(), api.models(), api.me().catch(() => ({ scratch: "", demo: false, user: "", workspace: undefined }))]);
    setSessions(s.sessions);
    setModels(m.available);
    setDefaultModel(m.default);
    setScratch(me.scratch ?? "");
    setWorkspace(me.workspace?.host ? me.workspace : null);
    setDemo(Boolean(me.demo));
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => { if (!folder && scratch) setFolder(scratch); }, [scratch, folder]);
  useEffect(() => { if (!model && defaultModel) setModel(defaultModel); }, [defaultModel, model]);

  // Auto-follow the stream, but only when the reader is already at the bottom and at most once per
  // frame: a forced scroll per token is layout work the page cannot afford during a long answer.
  const lastLen = session.turns.at(-1)?.answer.length ?? 0;
  const follow = useRef(true);
  const pane = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = pane.current;
    if (!el) return;
    const onScroll = () => {
      follow.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, []);
  useEffect(() => {
    if (view !== CHAT || !follow.current) return;
    const id = window.requestAnimationFrame(() => bottom.current?.scrollIntoView({ block: "end" }));
    return () => window.cancelAnimationFrame(id);
  }, [session.turns.length, lastLen, view]);

  // -- documents --------------------------------------------------------------------------
  const openDoc = useCallback((doc: Doc) => {
    setDocs((cur) => (cur.some((d) => d.id === doc.id) ? cur : [...cur, doc]));
    setView(doc.id);
  }, []);
  const closeDoc = (id: string) => {
    setDocs((cur) => cur.filter((d) => d.id !== id));
    setView((v) => (v === id ? CHAT : v));
  };
  const viewDoc = docs.find((d) => d.id === view) ?? null;

  // The palette opens objects; it does not know how the shell renders them.
  PaletteActions.onOpenTable = (ref: string) => openDoc(makeDoc("table", ref));
  PaletteActions.onOpenFile = (kind: string, path: string) => {
    const d = docForNode(kind as never, path);
    if (d) openDoc(d);
  };
  const addContext = useCallback((a: Attachment) => setAttachments((cur) => dedupe([...cur, a])), []);

  // The agent wrote something: refresh the tree and reload any open copy. Each call counts once.
  const seen = useRef(new Set<string>());
  useEffect(() => {
    const written: Doc[] = [];
    for (const t of session.turns) for (const c of t.tools) {
      if (c.status !== "completed" || seen.current.has(c.callId)) continue;
      seen.current.add(c.callId);
      const hit = touched(c.name, c.args);
      if (hit?.mutates) written.push(hit.doc);
    }
    if (!written.length) return;
    setTreeRev((n) => n + 1);
    setDocs((cur) => cur.map((d) => (written.some((w) => w.id === d.id) ? { ...d, rev: d.rev + 1 } : d)));
  }, [session.turns]);
  useEffect(() => { seen.current = new Set(); }, [active]);

  // -- sending ----------------------------------------------------------------------------
  const starting = useRef(false);
  const start = async (prompt: string, ctx: Attachment[] = []) => {
    if (starting.current) return;          // a double click must not create two sessions
    starting.current = true;
    try {
      const created = await api.create(folder || scratch, model || defaultModel);
      setActive(created.id);
      setView(CHAT);
      await api.send(created.id, prompt, `${created.id}:1`, ctx);
      await refresh();
    } finally {
      starting.current = false;
    }
  };

  const message = async (text: string, extra: Attachment[] = []) => {
    const ctx = dedupe([...attachments, ...(viewDoc ? [asAttachment(viewDoc)] : []), ...extra]);
    setAttachments([]);
    setView(CHAT);
    if (!active) await start(text, ctx);
    else await send(text, ctx);
  };

  const ask = (action: Action, doc: Doc) => { void message(ACTIONS[action].prompt, [asAttachment(doc)]); };

  const useFolder = (path: string) => {
    setFolder(path);
    setActive(null);
    setView(CHAT);
    setNotice(`The next session will work in ${path}`);
  };
  useEffect(() => { if (notice) { const id = window.setTimeout(() => setNotice(""), 6000); return () => window.clearTimeout(id); } }, [notice]);

  const newSession = useCallback(() => {
    setActive(null);
    setView(CHAT);
    setAttachments([]);
    requestAnimationFrame(() => composerBox.current?.focus());
  }, []);

  const focusComposer = useCallback(() => {
    composerBox.current?.focus();
  }, []);

  /** Everything reachable without the mouse: objects, panels, tabs and actions. */
  const paletteItems = useMemo<Candidate[]>(() => {
    const items: Candidate[] = [];
    const add = (id: string, title: string, group: string, run: () => void, hint?: string, weight = 0) =>
      items.push({ id, title, group, run, hint, weight });

    add("act:new", "New session", "Actions", newSession, display("mod+shift+n"), 5);
    add("act:keys", "Keyboard shortcuts", "Actions", () => setKeysOpen(true), display("mod+slash"));
    add("act:refresh", "Refresh sessions and models", "Actions", () => void refresh());
    for (const r of ["sessions", "files", "catalog"] as Rail[]) {
      const key = r === "sessions" ? "mod+1" : r === "files" ? "mod+2" : "mod+3";
      add(`rail:${r}`, `${r[0].toUpperCase()}${r.slice(1)} panel`, "Panels",
        () => { setRail(r); setRailShown(true); }, display(key), 2);
    }
    add("panel:rail", railShown ? "Hide the left panel" : "Show the left panel", "Panels",
      () => setRailShown((v) => !v), display("mod+b"));
    add("panel:insp", inspShown ? "Hide the inspector" : "Show the inspector", "Panels",
      () => setInspShown((v) => !v), display("mod+i"));

    add("tab:chat", "Chat", "Open", () => setView(CHAT), undefined, 1);

    // Actions on what is on screen. A palette that only navigates is a menu; this is the useful part.
    const open = docs.find((d) => d.id === view);
    if (open) {
      add("act:attach", `Add ${open.name} to the message`, "Actions",
        () => addContext(asAttachment(open)), undefined, 2);
      for (const a of ["explain", "fix", "document", "optimize"] as Action[]) {
        add(`act:${a}:${open.id}`, `${ACTIONS[a].label} ${open.name}`, "Actions",
          () => ask(a, open), a, 3);
      }
    }
    for (const d of docs) {
      add(`doc:${d.id}`, d.name, d.kind === "table" ? "Tables" : "Files",
        () => setView(d.id), d.ref, 1);
    }
    for (const s of sessions.slice(0, 40)) {
      const title = s.title === "New session" ? s.id.slice(0, 8) : s.title;
      items.push({
        id: `session:${s.id}`, title, group: "Sessions", hint: s.folder,
        keywords: s.id, weight: 3,
        run: () => { setActive(s.id); setView(CHAT); },
      });
    }
    return items;
  }, [docs, sessions, railShown, inspShown, newSession, refresh, view, addContext, ask]);

  const busy = session.status === "streaming";

  const handlers = useMemo(() => {
    const go = (r: Rail) => () => { setRail(r); setRailShown(true); };
    const cycle = (step: number) => () => {
      const ids = [CHAT, ...docs.map((d) => d.id)];
      const at = ids.indexOf(view);
      setView(ids[(at + step + ids.length) % ids.length]);
    };
    return {
      "mod+k": () => setPaletteOpen((v) => !v),
      "mod+slash": () => { setKeysOpen((v) => !v); },
      "mod+shift+n": newSession,
      "mod+l": focusComposer,
      "mod+1": go("sessions"),
      "mod+2": go("files"),
      "mod+3": go("catalog"),
      "mod+b": () => setRailShown((v) => !v),
      "mod+i": () => setInspShown((v) => !v),
      "mod+p": () => { setRail("files"); setRailShown(true); focusComposer(); },
      "ctrl+tab": cycle(1),
      "ctrl+shift+tab": cycle(-1),
      "mod+w": () => {
        if (view === CHAT) return false;      // never close someone's only view by accident
        closeDoc(view);
        return true;
      },
      escape: () => {
        if (paletteOpen || keysOpen) { setPaletteOpen(false); setKeysOpen(false); return true; }
        return false;                          // the composer handles Esc as "stop"
      },
    };
  }, [docs, view, paletteOpen, keysOpen, newSession, focusComposer]);

  useHotkeys(handlers);
  const toolCalls = session.turns.reduce((n, t) => n + t.tools.length, 0);
  const pending = session.approvals.find((a) => !a.outcome);
  const turns = session.turns;
  const selectedRef = viewDoc?.ref ?? null;
  const viewerActions = { onAsk: ask, onAttach: (d: Doc) => addContext(asAttachment(d)) };

  return (
    <WorkspaceLinks.Provider value={workspace}>
    <OpenDoc.Provider value={openDoc}>
      <div className="app">
        <header className="topbar">
          <span className="brand"><span className="mark" aria-hidden>◧</span> Databricks Coding Agents</span>
          <span className="meta">
            {active && (
              <span className="chip">
                <span aria-hidden>model</span>
                <select
                  aria-label="Model"
                  value={session.model}
                  onChange={async (e) => {
                    const r = await api.setModel(active, e.target.value);
                    setSession((s) => ({ ...s, model: r.current }));
                  }}
                >
                  {(models.length ? models.map((m) => m.id) : [session.model]).map((id) => (
                    <option key={id} value={id}>{id.split("/").pop()}</option>
                  ))}
                </select>
              </span>
            )}
            {active && <span className={`pill ${session.status}`}>{session.status}</span>}
            <button className="search-trigger" onClick={() => setPaletteOpen(true)}
              aria-label={`Search or run a command (${display("mod+k")})`} title={`Search or run a command — ${display("mod+k")}`}>
              <span aria-hidden>⌕</span>
              <span className="search-trigger-label">Search or run a command</span>
              <span className="kbd-hint">{caps("mod+k").map((c) => <kbd key={c}>{c}</kbd>)}</span>
            </button>
            <button className="btn ghost" onClick={() => setKeysOpen(true)} aria-label="Keyboard shortcuts" title="Keyboard shortcuts (⌘/)">⌘</button>
            <button className="btn ghost" onClick={() => void refresh()} aria-label="Refresh sessions" title="Refresh">⟳</button>
          </span>
        </header>

        <div className={`layout${active && inspShown ? "" : " no-inspector"}${railShown ? "" : " no-rail"}`}>
          {railShown && <nav className="pane rail" aria-label="Navigator">
            <button className="rail-collapse" onClick={() => setRailShown(false)}
              title="Hide this panel (⌘B)" aria-label="Hide the left panel">‹</button>
            <div className="rail-tabs" role="tablist" aria-label="Navigator">
              {(["sessions", "files", "catalog"] as Rail[]).map((r) => (
                <button key={r} className="rail-tab" role="tab" aria-selected={rail === r} onClick={() => setRail(r)}>
                  {r === "sessions" ? "Sessions" : r === "files" ? "Files" : "Catalog"}
                </button>
              ))}
            </div>
            {rail === "sessions" && (
              <>
                <div className="rail-head">
                  <span className="rail-title">Recent</span>
                  <button className="btn" onClick={() => { setActive(null); setView(CHAT); }}>+ New</button>
                </div>
                <div className="rail-list">
                  {sessions.length === 0 && (
                    <p style={{ color: "var(--ink-3)", fontSize: 12.5, padding: "4px 10px" }}>
                      No sessions yet. Start with what you want to build.
                    </p>
                  )}
                  {sessions.map((s) => (
                    <button key={s.id} className="rail-item" aria-current={s.id === active}
                      onClick={() => { setActive(s.id); setView(CHAT); }}>
                      <span className={`dot${s.status === "streaming" ? " busy" : ""}`} aria-hidden />
                      {s.title === "New session" ? s.id.slice(0, 8) : s.title}
                    </button>
                  ))}
                </div>
              </>
            )}
            {rail === "files" && (
              <div className="rail-tree">
                <WorkspaceTree selected={selectedRef} revision={treeRev}
                  onOpenFile={(n) => { const d = docForNode(n.kind, n.path); if (d) openDoc(d); }}
                  onAttach={addContext} onUseFolder={useFolder} />
              </div>
            )}
            {rail === "catalog" && (
              <div className="rail-tree">
                <CatalogTree selected={selectedRef} onAttach={addContext} onOpenTable={(ref) => openDoc(makeDoc("table", ref))} />
              </div>
            )}
          </nav>}

          {!railShown && (
            <button className="rail-reveal" onClick={() => setRailShown(true)}
              title="Show the left panel (⌘B)" aria-label="Show the left panel">›</button>
          )}

          <main className="pane main">
            {docs.length > 0 && (
              <div className="doc-tabs" role="tablist" aria-label="Open items"
                onKeyDown={tabKeys([CHAT, ...docs.map((d) => d.id)], view, setView)}>
                <button id={`tab-${CHAT}`} className="doc-tab" role="tab" aria-selected={view === CHAT}
                  tabIndex={view === CHAT ? 0 : -1} onClick={() => setView(CHAT)}>
                  <span aria-hidden>💬</span> Chat
                </button>
                {docs.map((d) => (
                  <span key={d.id} className="doc-tab-wrap">
                    <button id={`tab-${d.id.replace(/[^\w-]/g, "_")}`} className="doc-tab" role="tab"
                      aria-selected={view === d.id} tabIndex={view === d.id ? 0 : -1}
                      onClick={() => setView(d.id)} title={d.ref}>
                      <span aria-hidden>{d.kind === "table" ? "▦" : "▤"}</span> {d.name}
                    </button>
                    <button className="doc-close" aria-label={`Close ${d.name}`} onClick={() => closeDoc(d.id)}>×</button>
                  </span>
                ))}
              </div>
            )}

            {viewDoc ? (
              viewDoc.kind === "table"
                ? <TableViewer key={viewDoc.id} doc={viewDoc} actions={viewerActions} />
                : <NotebookViewer key={viewDoc.id} doc={viewDoc} actions={viewerActions} />
            ) : !active ? (
              <EmptyState models={models} folder={folder} onFolder={setFolder} model={model} onModel={setModel}
                demo={demo} notice={notice} onStart={(p) => start(p, attachments).then(() => setAttachments([]))} />
            ) : (
              <>
                <div className="strip">
                  {conn !== "live" && <span className={`pill ${conn}`}>{conn === "reconnecting" ? "reconnecting…" : conn}</span>}
                  <span className="strip-path" title="The agent can write only here">
                    {session.folder}
                    <ExtLink target={{ kind: "directory", ref: session.folder }} label="Open the working folder in Databricks" />
                  </span>
                  <span className="strip-counts">
                    {session.turns.length} {session.turns.length === 1 ? "turn" : "turns"} · {toolCalls} tool {toolCalls === 1 ? "call" : "calls"}
                    {session.tools > 0 ? ` · ${session.tools} tools` : ""}
                  </span>
                  {error && <span className="strip-error">{error}</span>}
                </div>
                <div className="transcript" ref={pane} aria-live="polite" aria-busy={busy}>
                  {turns.length === 0 && (
                    <p style={{ color: "var(--ink-3)" }}>Starting the agent… (usually 3–8 s)</p>
                  )}
                  {turns.map((t) => <TurnView key={t.id} turn={t} />)}
                  <div ref={bottom} />
                </div>
              </>
            )}

            {!active && (
              <p className="composer-note">
                {viewDoc ? "New session" : "Session"} in <code>{folder || scratch}</code> — <strong>the agent can write only there</strong>.
              </p>
            )}
            <Composer
              inputRef={composerBox}
              disabled={session.status === "archived"} busy={busy} onSend={message} onStop={stop}
              attachments={attachments} auto={viewDoc ? asAttachment(viewDoc) : null}
              onAdd={addContext} onRemove={(a) => setAttachments((cur) => cur.filter((x) => x !== a))}
              openDocs={docs}
              placeholder={viewDoc ? `Ask about ${viewDoc.name}…` : !active ? "Describe what you want to build, or pick an example above…" : undefined}
            />
          </main>

          {active && inspShown && <Inspector session={session} />}
        </div>

        {paletteOpen && <Palette items={paletteItems} onClose={() => setPaletteOpen(false)} />}
        {keysOpen && <ShortcutSheet onClose={() => setKeysOpen(false)} />}

        {pending && active && (
          <ApprovalSheet approval={pending} sessionId={active} onDecided={() => void refresh()} />
        )}
      </div>
    </OpenDoc.Provider>
    </WorkspaceLinks.Provider>
  );
}
