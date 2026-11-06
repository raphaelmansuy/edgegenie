/** App shell: a left rail (sessions, files, catalog), a main pane (chat and open documents), an inspector.
 *
 * The three things that make this a Genie-Code-class assistant rather than a chat box:
 *  1. you browse the real workspace and catalog and OPEN what you find;
 *  2. what you are looking at, and what you @-mention, goes to the agent as context;
 *  3. when the agent writes something, the tree refreshes and the result opens in one click.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { api, type ModelOption, type SessionSummary } from "./api/client";
import { ApprovalSheet, EmptyState, Inspector } from "./components/Chrome";
import { CatalogTree } from "./components/CatalogTree";
import { Composer } from "./components/Composer";
import { OpenDoc } from "./components/DocContext";
import { TurnView } from "./components/Transcript";
import { NotebookViewer, TableViewer } from "./components/Viewer";
import { WorkspaceTree } from "./components/WorkspaceTree";
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
  const bottom = useRef<HTMLDivElement>(null);

  const { session, conn, error, send, stop, setSession } = useSessionStream(active);

  // stable identity: this is called from a mount effect, so it must not change per render
  const refresh = useCallback(async () => {
    const [s, m, me] = await Promise.all([
      api.sessions(), api.models(), api.me().catch(() => ({ scratch: "", demo: false, user: "" }))]);
    setSessions(s.sessions);
    setModels(m.available);
    setDefaultModel(m.default);
    setScratch(me.scratch ?? "");
    setDemo(Boolean(me.demo));
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => { if (!folder && scratch) setFolder(scratch); }, [scratch, folder]);
  useEffect(() => { if (!model && defaultModel) setModel(defaultModel); }, [defaultModel, model]);

  const lastLen = session.turns.at(-1)?.answer.length ?? 0;
  useEffect(() => {
    if (view !== CHAT) return;
    const id = window.setTimeout(() => bottom.current?.scrollIntoView({ block: "end" }), 60);
    return () => window.clearTimeout(id);
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

  const busy = session.status === "streaming";
  const toolCalls = session.turns.reduce((n, t) => n + t.tools.length, 0);
  const pending = session.approvals.find((a) => !a.outcome);
  const turns = session.turns;
  const selectedRef = viewDoc?.ref ?? null;
  const viewerActions = { onAsk: ask, onAttach: (d: Doc) => addContext(asAttachment(d)) };

  return (
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
            <button className="btn ghost" onClick={() => void refresh()} aria-label="Refresh sessions">⟳</button>
          </span>
        </header>

        <div className={`layout${active ? "" : " no-inspector"}`}>
          <nav className="pane rail" aria-label="Navigator">
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
          </nav>

          <main className="pane main">
            {docs.length > 0 && (
              <div className="doc-tabs" role="tablist" aria-label="Open items">
                <button className="doc-tab" role="tab" aria-selected={view === CHAT} onClick={() => setView(CHAT)}>
                  <span aria-hidden>💬</span> Chat
                </button>
                {docs.map((d) => (
                  <span key={d.id} className="doc-tab-wrap">
                    <button className="doc-tab" role="tab" aria-selected={view === d.id} onClick={() => setView(d.id)} title={d.ref}>
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
                  <span>{session.turns.length} {session.turns.length === 1 ? "turn" : "turns"}</span>
                  <span>·</span>
                  <span>{toolCalls} tool {toolCalls === 1 ? "call" : "calls"}</span>
                  <span>·</span>
                  <span>{session.tools > 0 ? `${session.tools} tools available` : "no tool server"}</span>
                  <span>·</span>
                  <span title="The agent can write only here">{session.folder}</span>
                  {error && <span style={{ color: "var(--pink-700)", marginLeft: "auto" }}>{error}</span>}
                </div>
                <div className="transcript" aria-live="polite" aria-busy={busy}>
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
                {viewDoc ? "Asking starts a new session" : "Type below to start a session"} in <code>{folder || scratch}</code>.
                The agent can write only there.
              </p>
            )}
            <Composer
              disabled={session.status === "archived"} busy={busy} onSend={message} onStop={stop}
              attachments={attachments} auto={viewDoc ? asAttachment(viewDoc) : null}
              onAdd={addContext} onRemove={(a) => setAttachments((cur) => cur.filter((x) => x !== a))}
              openDocs={docs}
              placeholder={viewDoc ? `Ask about ${viewDoc.name}…` : !active ? "Describe what you want to build, or pick an example above…" : undefined}
            />
          </main>

          {active && <Inspector session={session} />}
        </div>

        {pending && active && (
          <ApprovalSheet approval={pending} sessionId={active} onDecided={() => void refresh()} />
        )}
      </div>
    </OpenDoc.Provider>
  );
}
