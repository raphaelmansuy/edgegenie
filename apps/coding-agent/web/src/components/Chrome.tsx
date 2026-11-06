/** Composer, approval sheet, inspector and the empty state. */
import { useEffect, useRef, useState } from "react";
import type { Approval, SessionView } from "../domain/events";
import { api } from "../api/client";
import { WorkspaceTree } from "./WorkspaceTree";

export function Composer({ disabled, busy, onSend, onStop }: {
  disabled?: boolean; busy: boolean; onSend: (text: string) => Promise<void>; onStop: () => void;
}) {
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [text]);

  const submit = async () => {
    const value = text.trim();
    if (!value || sending || disabled) return;
    setSending(true);
    setText("");
    try { await onSend(value); } finally { setSending(false); }
  };

  return (
    <div className="composer">
      <div className="composer-box">
        <textarea
          ref={ref}
          value={text}
          placeholder="Ask for a notebook, a job, a fix, an investigation…"
          aria-label="Message the agent"
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); void submit(); }
            if (e.key === "Escape" && busy) { e.preventDefault(); onStop(); }
          }}
          disabled={disabled}
        />
        <div className="composer-actions">
          <button className="btn ghost" aria-label="Attach a file" title="Attach a file" disabled>📎</button>
          {busy ? (
            <button className="btn stop" onClick={onStop}>⏹ Stop</button>
          ) : (
            <button className="btn primary" onClick={() => void submit()} disabled={!text.trim() || disabled}>
              Send
            </button>
          )}
          <span className="hint"><kbd>⌘</kbd><kbd>⏎</kbd> send · <kbd>Esc</kbd> stop</span>
        </div>
      </div>
    </div>
  );
}

export function ApprovalSheet({ approval, sessionId, onDecided }: {
  approval: Approval; sessionId: string; onDecided: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { ref.current?.focus(); }, []);
  if (approval.outcome) return null;

  const decide = async (outcome: "allow_once" | "allow_session" | "deny") => {
    const pick = approval.options.find((o) => o.kind === (outcome === "deny" ? "reject_once" : "allow_once"))
      ?? approval.options[0];
    await api.decide(sessionId, approval.approvalId, outcome, pick?.optionId);
    onDecided();
  };

  return (
    <div className="scrim" role="dialog" aria-modal="true" aria-labelledby="approval-title">
      <div className="sheet" ref={ref} tabIndex={-1}>
        <header>
          <h2 id="approval-title">⏸ The agent is waiting for your decision</h2>
          <p>It wants to {approval.action} something outside your working scope.</p>
        </header>
        <div className="body">
          <div className="target">{approval.target}</div>
          <dl>
            <dt>Why</dt><dd>{approval.reason || "the agent asked for permission"}</dd>
            {approval.blastRadius && (<><dt>Blast radius</dt><dd>{approval.blastRadius}</dd></>)}
          </dl>
          <p style={{ color: "var(--ink-3)", fontSize: 12.5, margin: 0 }}>
            If you deny, the agent gets a clear refusal and will try another way.
          </p>
        </div>
        <div className="actions">
          <button className="btn" onClick={() => void decide("allow_once")}>Allow once</button>
          <button className="btn" onClick={() => void decide("allow_session")}>Allow this session</button>
          <button className="btn primary" onClick={() => void decide("deny")}>Deny</button>
        </div>
        <p className="note">ⓘ Recorded in the audit log with your name, the session and the object.</p>
      </div>
    </div>
  );
}

export function Inspector({ session }: { session: SessionView }) {
  const [tab, setTab] = useState<"context" | "files" | "audit">("context");
  const calls = session.turns.flatMap((t) => t.tools);
  return (
    <aside className="pane inspector">
      <div className="insp-head" role="tablist" aria-label="Inspector">
        <button className="tab" role="tab" aria-selected={tab === "context"} onClick={() => setTab("context")}>Context</button>
        <button className="tab" role="tab" aria-selected={tab === "files"} onClick={() => setTab("files")}>Files</button>
        <button className="tab" role="tab" aria-selected={tab === "audit"} onClick={() => setTab("audit")}>Audit</button>
      </div>
      <div className="insp-body">
        {tab === "files" ? (
          <WorkspaceTree selected={session.folder} />
        ) : tab === "context" ? (
          <>
            <div className="fieldset">
              <legend>Working scope</legend>
              <div className="fence">
                <strong>This agent can write here and nowhere else.</strong>
                <div style={{ marginTop: 6 }}>
                  folder <code>{session.scope?.folder ?? session.folder}</code><br />
                  schema <code>{session.scope?.schema ?? "none"}</code><br />
                  job prefix <code>{session.scope?.jobPrefix ?? "—"}</code>
                </div>
              </div>
            </div>
            <div className="fieldset">
              <legend>Session</legend>
              <dl className="kv">
                <dt>agent</dt><dd>{session.agent || "starting"} {session.agentVersion && `v${session.agentVersion}`}</dd>
                <dt>tools</dt><dd>{session.tools > 0 ? `${session.tools} available` : "none configured"}</dd>
                <dt>model</dt><dd>{session.model}</dd>
                <dt>turns</dt><dd>{session.turns.length}</dd>
              </dl>
            </div>
            <div className="fieldset">
              <legend>Skill reads</legend>
              <p style={{ color: "var(--ink-3)", fontSize: 12.5, margin: 0 }}>
                Skills are read on demand, so the context only pays for what the task needs.
              </p>
            </div>
          </>
        ) : (
          <div className="fieldset">
            <legend>Tool calls in this session</legend>
            {calls.length === 0 && <p style={{ color: "var(--ink-3)", fontSize: 12.5 }}>No tool calls yet.</p>}
            {calls.map((c, i) => (
              <div key={c.callId} className="audit-row">
                <span className="n">{i + 1}</span>
                <span style={{ flex: 1 }}>{c.name.replace(/^dbxnb_/, "")}</span>
                <span className={`pill ${c.status === "error" ? "blocked" : "ready"}`}>{c.status}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}

const CARDS = [
  { icon: "📓", bg: "var(--blue-100)", t: "Build a notebook", d: "Revenue by month, a chart, a written summary",
    scenario: "notebook",
    prompt: "Build a notebook that shows revenue by month from samples.nyctaxi.trips with a chart, then run it and report the exit value." },
  { icon: "🧪", bg: "var(--yellow-100)", t: "Investigate a number", d: "Why did revenue drop on the 10th?",
    scenario: "blocked",
    prompt: "Investigate why revenue dropped on the 10th. Show the SQL you used and name the most likely cause." },
  { icon: "⚙", bg: "var(--green-100)", t: "Create a job", d: "Daily recompute at 06:00, with a dependency",
    scenario: "slow",
    prompt: "Create a job that recomputes daily revenue at 06:00 after a dependency task, run it once, and prove the run succeeded." },
  { icon: "🗄", bg: "var(--teal-100)", t: "Lakebase and an app", d: "Postgres, then a small web page",
    scenario: "notebook",
    prompt: "Create a Lakebase database with one table and a small app that reads it. Show me the connection details." },
  { icon: "📚", bg: "var(--purple-100)", t: "Document tables", d: "Comments grounded in real values",
    scenario: "injection",
    prompt: "Document the tables in my schema: add a comment to each table and column based on the real values you observe." },
  { icon: "🔍", bg: "var(--pink-100)", t: "Debug a failing job", d: "Find the cause and prove the fix",
    scenario: "blocked",
    prompt: "A job is failing. Read its last run, find the cause, fix the notebook, re-run the job and show me the successful run." },
];

export function EmptyState({ models, defaultModel, onStart }: {
  models: { id: string; name: string }[]; defaultModel: string;
  onStart: (prompt: string, folder: string, model: string) => Promise<void>;
}) {
  const [folder, setFolder] = useState("/tmp/agent-work");
  const [model, setModel] = useState(defaultModel);
  const [starting, setStarting] = useState(false);
  return (
    <div className="empty">
      <h1>What should we build today?</h1>
      <p className="sub">A coding agent works in your workspace: it writes, runs and proves.</p>
      <div className="cards">
        {CARDS.map((c) => (
          <button key={c.t} className="card" disabled={starting}
            onClick={async () => {
              setStarting(true);
              // Demo mode only: the marker tells the reference agent which behaviour to play.
              // A real agent ignores it; it is plain text in the prompt.
              try { await onStart(`${c.prompt} [[scenario:${c.scenario}]]`, folder, model); }
              finally { setStarting(false); }
            }}>
            <span className="t"><span className="ico" style={{ background: c.bg }} aria-hidden>{c.icon}</span>{c.t}</span>
            <span className="d">{c.d}</span>
          </button>
        ))}
      </div>
      <div className="setup">
        <label>Working folder<input value={folder} onChange={(e) => setFolder(e.target.value)} spellCheck={false} /></label>
        <label>Model
          <select value={model} onChange={(e) => setModel(e.target.value)}>
            {models.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
          </select>
        </label>
        <p style={{ color: "var(--ink-3)", fontSize: 12.5, margin: "6px 0 0 130px" }}>
          It can write only to this folder and its schema. Anything else asks you first.
        </p>
      </div>
    </div>
  );
}
