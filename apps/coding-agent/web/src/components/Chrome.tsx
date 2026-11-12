/** Approval sheet, inspector and the empty state. */
import { useEffect, useRef, useState } from "react";
import type { Approval, SessionView } from "../domain/events";
import { api, type CatalogueResponse } from "../api/client";
import { useReturnFocus } from "../hooks/useReturnFocus";
import { ModelPicker } from "./ModelPicker";
import { FolderPicker } from "./FolderPicker";
import { LogoMark } from "./Logo";
import { ModelFacts } from "./ModelFacts";
import { BudgetMeter } from "./Budget";
import { DOCS_URL, versionLabel, versionTitle } from "../domain/version";
import { ArrowUpRight, Bug, ChevronRight, Clock, Database, FileIcon, Layers, ListIcon, Monitor, Notebook, Play, Search, Sparkle, Table } from "./Icons";
import type { RecentDoc } from "../domain/recent";

export function ApprovalSheet({ approval, sessionId, onDecided }: {
  approval: Approval; sessionId: string; onDecided: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { ref.current?.focus(); }, []);
  // KB-1: approving or denying returns focus to where the user was, not to <body>.
  useReturnFocus();
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

export function Inspector({ session, edge, onHide, className = "", activeId, onAddKey, folder }: {
  session: SessionView; edge?: React.ReactNode; onHide?: () => void; className?: string;
  /** The folder a NEW session would use, so the fence can name it before one exists. */
  folder?: string;
  /** The session id, so the model-facts block can read the turn pins (FR-10). */
  activeId?: string | null;
  onAddKey?: () => void;
}) {
  const [tab, setTab] = useState<"context" | "audit">("context");
  const calls = session.turns.flatMap((t) => t.tools);
  /* One string for one path, resolved once. The three facts used raw `??` fallbacks inline, which is
     why the block could grow a line mid-load and shift everything below it by 40 px (measured CLS
     0.0024): `not chosen yet` is 14 characters, the real path is 43. Naming it here also lets the
     path carry a `title`, since it is now displayed on one line with an ellipsis. */
  const scopedFolder = session.scope?.folder || session.folder || folder || "not chosen yet";
  return (
    <aside className={`pane inspector${className ? ` ${className}` : ""}`}>
      {/* The resize handle belongs to this pane and sits on the edge facing the work area. */}
      {edge}
      <div className="insp-head" role="tablist" aria-label="Inspector">
        <button id="insp-tab-context" className="tab" role="tab" aria-selected={tab === "context"}
          aria-controls="insp-panel-context" tabIndex={tab === "context" ? 0 : -1}
          onClick={() => setTab("context")}
          onKeyDown={(e) => { if (e.key === "ArrowRight") { e.preventDefault(); setTab("audit"); document.getElementById("insp-tab-audit")?.focus(); } }}>Context</button>
        {/* The navigator has an in-panel collapse control; without a matching one here the two side
            zones are not symmetric, and the only way to close this pane is the top bar. */}
        {onHide && (
          <button className="rail-collapse insp-collapse" onClick={onHide}
            title="Hide this panel (⌘I)" aria-label="Hide the right panel"><ChevronRight size={15} /></button>
        )}
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
                <dl className="fence-facts">
                  <dt>folder</dt>
                  <dd><code title={scopedFolder}>{scopedFolder}</code></dd>
                  <dt>schema</dt>
                  <dd><code>{session.scope?.schema ?? "none"}</code></dd>
                  <dt>job prefix</dt>
                  <dd><code>{session.scope?.jobPrefix ?? "—"}</code></dd>
                </dl>
              </div>
            </div>
            {activeId && (
              <ModelFacts sessionId={activeId} current={session.model}
                turns={session.turns.length} lastStatus={session.turns.at(-1)?.status}
                onAddKey={onAddKey} />
            )}
            {/* What this conversation has spent ([R-24]). The WRITE MODE chip is deliberately NOT here:
                the inspector is closed by default, so a mode that matters only when a write is refused
                belongs in the top bar where it is always on screen. One chip, one place. */}
            {activeId && <BudgetMeter sessionId={activeId} />}
            <div className="fieldset">
              <legend>Session</legend>
              {activeId ? (
                <dl className="kv">
                  <dt>agent</dt><dd>{session.agent || "starting"} {session.agentVersion && `v${session.agentVersion}`}</dd>
                  <dt>tools</dt><dd>{session.tools > 0 ? `${session.tools} available` : "none configured"}</dd>
                  <dt>model</dt><dd>{session.model}</dd>
                  <dt>turns</dt><dd>{session.turns.length}</dd>
                </dl>
              ) : (
                /* No session is a real state (a document opened straight from a link or the Files
                   tree), not an error: say what that means for the fence and how to get one. An empty
                   panel would read as broken, which is how this audit started. */
                <p className="insp-empty">
                  No session yet. The agent starts one when you send a message; until then a save asks
                  for approval — that is the fence, not a failure. <kbd>⌘⇧N</kbd> starts one now.
                </p>
              )}
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
            {calls.length === 0 && (
              <p className="insp-empty">
                {activeId ? "No tool calls yet." : "No session, so no tool calls. The audit log fills as the agent works."}
              </p>
            )}
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

/* Glyphs, not emoji. An emoji is coloured by the font and ignores `color`, so a dark pictogram
   lands on a dark tint in dark mode — the audit measured 🗄 at 1.06:1, i.e. invisible. These are
   text glyphs that inherit currentColor, so they follow the theme and the accent per card.
   `fg` is the ink for the glyph; the tile keeps a soft wash of the same hue. */
const CARDS = [
  { icon: Notebook, fg: "var(--blue-600)", bg: "var(--blue-100)", t: "Build a notebook", d: "Revenue by month, a chart, a written summary",
    scenario: "notebook",
    prompt: "Build a notebook that shows revenue by month from samples.nyctaxi.trips with a chart, then run it and report the exit value." },
  { icon: Sparkle, fg: "var(--yellow-800)", bg: "var(--yellow-100)", t: "Investigate a number", d: "Why did revenue drop on the 10th?",
    scenario: "blocked",
    prompt: "Investigate why revenue dropped on the 10th. Show the SQL you used and name the most likely cause." },
  { icon: Clock, fg: "var(--green-700)", bg: "var(--green-100)", t: "Create a job", d: "Daily recompute at 06:00, with a dependency",
    scenario: "slow",
    prompt: "Create a job that recomputes daily revenue at 06:00 after a dependency task, run it once, and prove the run succeeded." },
  { icon: Database, fg: "var(--teal-700)", bg: "var(--teal-100)", t: "Lakebase and an app", d: "Postgres, then a small web page",
    // The card's own scenario, so the demo shows the seven-step scaffold it promises (spec 013
    // [SCF-3]). It said "notebook" until the S6 screenshot showed the card building a taxi notebook.
    scenario: "lakebase",
    prompt: "Create a Lakebase database with one table and a small app that reads it. Show me the connection details." },
  { icon: ListIcon, fg: "var(--purple-700)", bg: "var(--purple-100)", t: "Document tables", d: "Comments grounded in real values",
    scenario: "injection",
    prompt: "Document the tables in my schema: add a comment to each table and column based on the real values you observe." },
  { icon: Bug, fg: "var(--pink-700)", bg: "var(--pink-100)", t: "Debug a failing job", d: "Find the cause and prove the fix",
    scenario: "blocked",
    prompt: "A job is failing. Read its last run, find the cause, fix the notebook, re-run the job and show me the successful run." },
];

/** The default working folder: a real workspace path under the user's home. */
export const USER_SCRATCH = "/Users/me/agent_scratch";

export function EmptyState({ catalogue, folder, onFolder, model, onModel, onAddKey, onStart, demo, notice,
  user, recent, onOpenRecent, onOpenSearch, onOpenCatalog, onAskAssistant, onNewSql, onOpenQueries }: {
  catalogue: CatalogueResponse | null;
  folder: string; onFolder: (v: string) => void;
  model: string; onModel: (v: string) => void;
  onAddKey?: () => void;
  demo: boolean;
  notice?: string;
  onStart: (prompt: string) => Promise<void>;
  /** Who is signed in, so the screen can say whose workspace this is. */
  user?: string;
  /** Notebooks, tables and the objects the agent built, so the first screen is a way IN rather than only
   *  a way to start: the most common task is "change something I already have". The kind is `RecentDoc`'s
   *  own union, imported rather than restated — a second copy of it silently stopped three kinds from
   *  reaching this screen when spec 014 added them. */
  recent?: RecentDoc[];
  onOpenRecent?: (path: string, kind: RecentDoc["kind"]) => void;
  onOpenSearch?: () => void;
  onNewSql?: () => void;
  onOpenQueries?: () => void;
  onOpenCatalog?: () => void;
  onAskAssistant?: () => void;
}) {
  const [starting, setStarting] = useState(false);
  const start = async (prompt: string) => {
    setStarting(true);
    try { await onStart(prompt); } finally { setStarting(false); }
  };
  return (
    <div className="home">
      <div className="home-inner">
        <header className="home-hero">
          <span className="home-glow" aria-hidden />
          <LogoMark size={40} className="home-mark" />
          <h2 className="home-title">Your workspace, ready for what’s next.</h2>
          <p className="home-sub">
            Open existing work, build a notebook, or work through a question with your assistant.
          </p>
        </header>

        {/* Where the agent may write, as the first decision rather than a field at the bottom. The
            fence is the product's promise, so it is shown before anything is suggested. */}
        <section className="home-fence" aria-label="Working folder">
          <div className="home-fence-main">
            <span className="home-fence-label" id="home-fence-label">Working folder</span>
            <FolderPicker value={folder} onChange={onFolder} />
          </div>
          <p className="home-fence-note">
            Everything under it, nothing outside it. A write anywhere else asks you first.
          </p>
        </section>

        {notice && <p className="home-notice" role="status">{notice}</p>}
        <div className="home-starts" aria-label="Start working">
          <button className="home-start is-primary" onClick={onOpenSearch}>
            <Search size={20} /><strong>Open a document</strong><span>Find a notebook, file or table</span>
          </button>
          <button className="home-start" disabled={starting} onClick={() => void start(demo ? `${CARDS[0].prompt} [[scenario:notebook]]` : CARDS[0].prompt)}>
            <Notebook size={20} /><strong>Create a notebook</strong><span>Build with your assistant</span>
          </button>
          <button className="home-start" onClick={onNewSql}>
            <Database size={20} /><strong>New SQL query</strong><span>Write, run and save your SQL</span>
          </button>
          <button className="home-start" onClick={onAskAssistant}>
            <Sparkle size={20} /><strong>Ask the assistant</strong><span>Explore an idea or solve a problem</span>
          </button>
        </div>
        <details className="home-options">
          <summary>More workflows and session settings</summary>
          <div className="home-cards">
            {CARDS.slice(1).map((c) => <button key={c.t} className="home-card" disabled={starting}
              onClick={() => void start(demo ? `${c.prompt} [[scenario:${c.scenario}]]` : c.prompt)}>
              <span className="home-card-ico" style={{ background: c.bg, color: c.fg }} aria-hidden><c.icon size={15} /></span>
              <span className="home-card-t">{c.t}</span><span className="home-card-d">{c.d}</span>
            </button>)}
          </div>
          <section className="home-models" aria-label="Model">
            <ModelPicker catalogue={catalogue} current={model} variant="button" label={`Model for the new session: ${model || "none chosen"}`}
              onChoose={async (id) => onModel(id)} onAddKey={onAddKey} />
          </section>
        </details>

        <div className="home-panels">
          <section className="home-panel" aria-label="Open something">
            <h3 className="home-panel-t">Open something</h3>
            <button className="home-search" onClick={onOpenSearch}>
              <Search size={13} /><span>Search notebooks and tables</span><kbd>⌘K</kbd>
            </button>
            <button className="home-search" onClick={onOpenQueries}><Database size={13} /><span>Open SQL Queries</span></button>
            <button className="home-search" onClick={onOpenCatalog}>
              <Table size={13} /><span>Browse the catalog</span>
            </button>
            {recent && recent.length > 0 && (
              <ul className="home-recent">
                {recent.map((r) => (
                  <li key={`${r.kind}:${r.path}`}>
                    <button className="home-recent-item" onClick={() => onOpenRecent?.(r.path, r.kind)} title={r.path}>
                      <span className={`home-recent-ico is-${r.kind}`} aria-hidden>
                        {r.kind === "table" ? <Table size={12} /> : r.kind === "notebook" ? <Notebook size={12} /> : r.kind === "lakebase" ? <Database size={12} /> : r.kind === "app" ? <Monitor size={12} /> : r.kind === "job" ? <Play size={12} /> : r.kind === "pipeline" ? <Layers size={12} /> : r.kind === "run" ? <Clock size={12} /> : <FileIcon size={12} />}
                      </span>
                      <span className="home-recent-name">{r.name}</span>
                      <ArrowUpRight size={12} className="home-recent-go" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="home-panel home-panel-about" aria-label="About this workspace">
            <h3 className="home-panel-t">This workspace</h3>
            <dl className="home-facts">
              <dt>signed in</dt><dd>{user || "—"}</dd>
              <dt>agent writes</dt><dd><code>{folder || "choose a folder"}</code></dd>
              <dt>model</dt><dd>{model || "none chosen"}</dd>
              {/* The version on the FIRST screen, not only in a menu: someone reporting a problem
                  reads it here, and a reader deciding whether to trust the tour reads the same number. */}
              <dt>version</dt>
              <dd>
                <a className="ext-link-text" href={DOCS_URL} target="_blank" rel="noopener noreferrer"
                  title={versionTitle()}>{versionLabel()}</a>
              </dd>
            </dl>
            <p className="home-fine">
              Ask for a change to an open notebook and OpenGenie edits it in place, then shows you the
              cells it touched. A notebook outside the folder above is never modified: it makes a copy
              and tells you where.
            </p>
          </section>
        </div>
      </div>
    </div>
  );
}
