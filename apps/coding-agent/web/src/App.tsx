/** App shell: session rail, transcript, inspector. All state comes from the reducer. */
import { useCallback, useEffect, useRef, useState } from "react";
import { api, type ModelOption, type SessionSummary } from "./api/client";
import { ApprovalSheet, Composer, EmptyState, Inspector } from "./components/Chrome";
import { TurnView } from "./components/Transcript";
import { useSessionStream } from "./hooks/useSessionStream";

export function App() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [models, setModels] = useState<ModelOption[]>([]);
  const [defaultModel, setDefaultModel] = useState("");
  const [scratch, setScratch] = useState("");
  const [active, setActive] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  const { session, conn, error, send, stop, setSession } = useSessionStream(active);

  // stable identity: this is called from a mount effect, so it must not change per render
  const refresh = useCallback(async () => {
    const [s, m, me] = await Promise.all([
      api.sessions(), api.models(), fetch("/api/me").then((r) => r.json()).catch(() => ({}))]);
    setSessions(s.sessions);
    setModels(m.available);
    setDefaultModel(m.default);
    setScratch(me.scratch ?? "");
  }, [setSessions, setModels, setDefaultModel]);

  useEffect(() => { void refresh(); }, [refresh]);
  const lastLen = session.turns.at(-1)?.answer.length ?? 0;
  useEffect(() => {
    const id = window.setTimeout(() => bottom.current?.scrollIntoView({ block: "end" }), 60);
    return () => window.clearTimeout(id);
  }, [session.turns.length, lastLen]);

  const starting = useRef(false);
  const start = async (prompt: string, folder: string, model: string) => {
    if (starting.current) return;          // a double click must not create two sessions
    starting.current = true;
    try {
      const created = await api.create(folder, model);
      setActive(created.id);
      await api.send(created.id, prompt, `${created.id}:1`);
      await refresh();
    } finally {
      starting.current = false;
    }
  };

  const busy = session.status === "streaming";
  const toolCalls = session.turns.reduce((n, t) => n + t.tools.length, 0);
  const pending = session.approvals.find((a) => !a.outcome);
  const turns = session.turns;

  return (
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
        <nav className="pane rail" aria-label="Sessions">
          <div className="rail-head">
            <span className="rail-title">Sessions</span>
            <button className="btn" onClick={() => setActive(null)}>+ New</button>
          </div>
          <div className="rail-list">
            <div className="rail-group">Recent</div>
            {sessions.length === 0 && (
              <p style={{ color: "var(--ink-3)", fontSize: 12.5, padding: "4px 10px" }}>
                No sessions yet. Start with what you want to build.
              </p>
            )}
            {sessions.map((s) => (
              <button key={s.id} className="rail-item" aria-current={s.id === active}
                onClick={() => setActive(s.id)}>
                <span className={`dot${s.status === "streaming" ? " busy" : ""}`} aria-hidden />
                {s.title === "New session" ? s.id.slice(0, 8) : s.title}
              </button>
            ))}
          </div>
        </nav>

        <main className="pane">
          {!active ? (
            <EmptyState models={models} defaultModel={defaultModel || models[0]?.id || ""}
              scratch={scratch} onStart={start} />
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
                <span>{session.folder}</span>
                {error && <span style={{ color: "var(--pink-700)", marginLeft: "auto" }}>{error}</span>}
              </div>
              <div className="transcript" aria-live="polite" aria-busy={busy}>
                {turns.length === 0 && (
                  <p style={{ color: "var(--ink-3)" }}>Starting the agent… (usually 3–8 s)</p>
                )}
                {turns.map((t) => <TurnView key={t.id} turn={t} />)}
                <div ref={bottom} />
              </div>
              <Composer disabled={session.status === "archived"} busy={busy} onSend={send} onStop={stop} />
            </>
          )}
        </main>

        {active && <Inspector session={session} />}
      </div>

      {pending && active && (
        <ApprovalSheet approval={pending} sessionId={active} onDecided={() => void refresh()} />
      )}
    </div>
  );
}
