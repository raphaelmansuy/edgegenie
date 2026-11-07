/** Approval sheet, inspector and the empty state. */
import { useEffect, useRef, useState } from "react";
import type { Approval, SessionView } from "../domain/events";
import { api } from "../api/client";

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
  const [tab, setTab] = useState<"context" | "audit">("context");
  const calls = session.turns.flatMap((t) => t.tools);
  return (
    <aside className="pane inspector">
      <div className="insp-head" role="tablist" aria-label="Inspector">
        <button id="insp-tab-context" className="tab" role="tab" aria-selected={tab === "context"}
          aria-controls="insp-panel-context" tabIndex={tab === "context" ? 0 : -1}
          onClick={() => setTab("context")}
          onKeyDown={(e) => { if (e.key === "ArrowRight") { e.preventDefault(); setTab("audit"); document.getElementById("insp-tab-audit")?.focus(); } }}>Context</button>
        <button id="insp-tab-audit" className="tab" role="tab" aria-selected={tab === "audit"}
          aria-controls="insp-panel-audit" tabIndex={tab === "audit" ? 0 : -1}
          onClick={() => setTab("audit")}
          onKeyDown={(e) => { if (e.key === "ArrowLeft") { e.preventDefault(); setTab("context"); document.getElementById("insp-tab-context")?.focus(); } }}>Audit</button>
      </div>
      <div className="insp-body" id={`insp-panel-${tab}`} role="tabpanel" aria-labelledby={`insp-tab-${tab}`}>
        {tab === "context" ? (
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

/** The default working folder: a real workspace path under the user's home. */
export const USER_SCRATCH = "/Users/me/agent_scratch";

export function EmptyState({ models, folder, onFolder, model, onModel, onStart, demo, notice }: {
  models: { id: string; name: string }[];
  folder: string; onFolder: (v: string) => void;
  model: string; onModel: (v: string) => void;
  demo: boolean;
  notice?: string;
  onStart: (prompt: string) => Promise<void>;
}) {
  const [starting, setStarting] = useState(false);
  return (
    <div className="empty">
      <h2 className="empty-title">What should we build today?</h2>
      <p className="sub">A coding agent that works in your workspace: it reads, writes, runs and proves.
        Open a notebook or table on the left and ask about it.</p>
      <div className="cards">
        {CARDS.map((c) => (
          <button key={c.t} className="card" disabled={starting}
            onClick={async () => {
              setStarting(true);
              // Demo mode only: the marker tells the reference agent which behaviour to play.
              // A real agent never sees it: sending it would put noise in a real prompt.
              try { await onStart(demo ? `${c.prompt} [[scenario:${c.scenario}]]` : c.prompt); }
              finally { setStarting(false); }
            }}>
            <span className="t"><span className="ico" style={{ background: c.bg }} aria-hidden>{c.icon}</span>{c.t}</span>
            <span className="d">{c.d}</span>
          </button>
        ))}
      </div>
      <div className="setup">
        <label>Working folder<input value={folder} onChange={(e) => onFolder(e.target.value)} spellCheck={false}
          aria-label="Working folder" placeholder="/Users/you/agent_scratch" /></label>
        <label>Model
          <select value={model} onChange={(e) => onModel(e.target.value)}>
            {models.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
          </select>
        </label>
        <p className="setup-note">
          It can write only to this folder and its schema. Anything else asks you first.
          Hover a folder in <strong>Files</strong> and press ⌂ to work there.
        </p>
        {notice && <p className="setup-notice" role="status">{notice}</p>}
      </div>
    </div>
  );
}
