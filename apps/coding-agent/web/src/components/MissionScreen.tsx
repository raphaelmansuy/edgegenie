/** Mission is a read model of a turn, never a second execution or persistence path. Spec 011. */
import { useId, useRef, useState, type KeyboardEvent } from "react";
import type { SessionView } from "../domain/events";
import type { Doc } from "../domain/docs";
import { currentMission, lastAchieved, missionView, type MissionProof } from "../domain/mission";
import { modelTail } from "../domain/models";
import { stripEvidence } from "../domain/toolview";
import { EMPTY_ROUTE, linkTo } from "../domain/route";
import { Alert, ArrowUpRight, Check, Chat, ChevronDown, Clock, FileIcon, Folder, ListIcon, Lock, Notebook, Ring, Sparkle, Square } from "./Icons";
import { CopyButton } from "./CopyButton";
import { Markdown } from "./Markdown";
import { MAX_MARKDOWN, ToolCard, TurnView } from "./Transcript";
import { RunStatus } from "./RunStatus";
import type { StreamState } from "../domain/stream";

interface Props {
  session: SessionView;
  conn: StreamState;
  dockVisible: boolean;
  error?: string | null;
  onOpen: (doc: Doc) => void;
  onConversation: () => void;
  onStop: () => Promise<void>;
  onRestore: () => Promise<void>;
}

function Proof({ proof }: { proof: MissionProof }) {
  const { row, source, verified } = proof;
  return <details className={`mission-proof${verified ? " is-verified" : ""}`}>
    <summary>
      <span className="mission-proof-mark" aria-hidden>{verified ? <Check size={14} /> : <Alert size={14} />}</span>
      <span className="mission-proof-text"><strong>{row.requirement || "Unnamed requirement"}</strong>
        <small>{verified ? "Verified" : "Not verified"} <span aria-hidden>·</span> Inspect source</small></span>
      <ArrowUpRight size={13} />
    </summary>
    <div className="mission-proof-source">
      {row.summary && <p>{row.summary}</p>}
      {!verified && <p className="mission-proof-warning">{!source ? "No source tool call was found in this mission."
        : source.name !== row.tool ? "The cited tool does not match this source call."
          : "This evidence has not been verified against a successful tool result."}</p>}
      {source && <ToolCard {...source} />}
    </div>
  </details>;
}

function MissionPlan({ view }: { view: ReturnType<typeof missionView> }) {
  return <section className="mission-section mission-plan" aria-labelledby="mission-plan-heading">
    <div className="mission-section-head"><h3 id="mission-plan-heading"><ListIcon size={15} /> Plan</h3>
      {view.plan.length > 0 && <span>{view.planDone} of {view.plan.length} complete</span>}</div>
    {view.plan.length ? <>
      <progress className="mission-progress" aria-label="Completed plan steps" max={view.plan.length} value={view.planDone} />
      <ol className="mission-steps">{view.plan.map((entry, i) => {
        const active = entry.status === "in_progress";
        const done = entry.status === "completed";
        return <li key={i} className={done ? "is-done" : active ? "is-active" : ""}>
          <span className="mission-step-mark" aria-hidden>{done ? <Check size={13} /> : active ? <span className="mission-active-dot" /> : <Ring size={14} />}</span>
          <span>{entry.content}</span>
          <small>{done ? "Complete" : active ? "In progress" : entry.status === "pending" ? "Pending" : entry.status || "Status unavailable"}</small>
        </li>;
      })}</ol>
      {view.planDone < view.plan.length && ["review", "achieved", "cancelled", "failed", "blocked", "interrupted"].includes(view.state)
        && <p className="mission-note">The turn ended before every plan step was marked complete.</p>}
    </> : <p className="mission-empty">No plan was reported for this mission. Activity and results remain available as they arrive.</p>}
  </section>;
}

export function MissionScreen({ session, conn, dockVisible, error, onOpen, onConversation, onStop, onRestore }: Props) {
  // App keys this surface by session ID. A pin refers only to a turn in that session.
  const [selected, setSelected] = useState<string | null>(null);
  const [tab, setTab] = useState<"overview" | "activity">("overview");
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  const scroll = useRef<HTMLDivElement>(null);
  const uid = useId();
  const current = currentMission(session);
  const turn = session.turns.find((t) => t.id === selected) ?? current;
  const v = missionView(session, turn, conn);
  const achieved = lastAchieved(session);
  const completed = [...session.turns].reverse().find((t) => t.status === "completed");
  const previous = achieved ?? completed;
  const choose = (id: string | null) => { setSelected(id); setTab("overview"); if (scroll.current) scroll.current.scrollTop = 0; };
  const answer = turn?.evidence.length ? stripEvidence(turn.answer) : turn?.answer;
  const ended = Boolean(turn && !["running", "auditing", "queued"].includes(turn.status));
  const fullRequest = v.request !== v.title || v.request.length > 45;
  const needsControls = session.requiresResume || session.status === "streaming" || session.approvals.some((a) => !a.outcome);
  const stateIcon = v.tone === "success" ? <Check size={14} /> : v.tone === "attention" || v.tone === "danger" ? <Alert size={14} />
    : v.state === "cancelled" ? <Square size={13} /> : v.tone === "active" ? <span className="mission-active-dot" /> : <Ring size={14} />;

  function tabKeys(e: KeyboardEvent<HTMLButtonElement>, index: number) {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
    e.preventDefault();
    const next = e.key === "Home" ? 0 : e.key === "End" ? 1 : 1 - index;
    setTab(next === 0 ? "overview" : "activity"); tabs.current[next]?.focus();
  }

  return <div className="mission-screen" aria-label="Agent mission" role="region">
    {!dockVisible && needsControls && <RunStatus session={session} conn={conn} onRestore={onRestore} onStop={onStop} compact />}
    <div className="mission-scroll" ref={scroll}>
      <div className="mission-content">
        <div className="mission-breadcrumb"><span><Sparkle size={14} /> Missions <span aria-hidden>/</span> {turn ? String(turn.index).padStart(2, "0") : "New"}</span>
          <CopyButton className="copy-btn quiet" text={() => linkTo({ ...EMPTY_ROUTE, session: session.id }, window.location)} label="Copy mission link" title="Copy a link to this session’s current mission" />
        </div>
        <header className="mission-header">
          <div className="mission-eyebrow"><span className={`mission-state tone-${v.tone}`} role="status" aria-atomic="true">{stateIcon}{v.label}</span>
            <span className="mission-kicker">{!turn ? "No mission yet" : v.isCurrent ? "Current mission" : "Mission history"}</span>
            {v.queued > 0 && <span className="mission-queue">{v.queued} queued</span>}
          </div>
          <h2 className="mission-title">{v.title}</h2>
          <p className="mission-description">{v.paused ? `Updates paused. Last known state: ${v.label.toLowerCase()}. Reconnect to catch up on saved progress.`
            : turn?.blocked?.reason || v.detail}</p>
          <div className="mission-facts">
            <span title={v.model}><Sparkle size={13} /> {v.model ? modelTail(v.model) : "Model not recorded"}</span>
            <span><ListIcon size={13} /> {turn?.tools.length ?? 0} tool {turn?.tools.length === 1 ? "call" : "calls"}</span>
            {v.seconds !== undefined && <span><Clock size={13} /> {v.seconds.toFixed(1)}s</span>}
            <span><Lock size={12} /> {session.execution?.persistence === "durable" ? "Progress saved" : "Temporary history"}</span>
          </div>
          {fullRequest && <details className="mission-request"><summary>Full request</summary><p>{v.request}</p></details>}
          {v.failedCalls > 0 && <p className="mission-caution"><Alert size={13} />{v.failedCalls} tool {v.failedCalls === 1 ? "call failed" : "calls failed"}. Review activity for details.</p>}
          {!dockVisible && error && <p className="mission-caution" role="alert">{error}</p>}
        </header>

        <div className="mission-navigation">
          <label className="mission-picker"><span className="sr-only">Choose mission</span><select value={turn?.id ?? ""} disabled={!session.turns.length}
            onChange={(e) => choose(e.target.value === current?.id ? null : e.target.value)}>
            {!session.turns.length && <option value="">Awaiting first mission</option>}
            {[...session.turns].reverse().map((t) => <option key={t.id} value={t.id}>Mission {t.index} · {missionView(session, t, conn).label}{t.id === current?.id ? " · Current" : ""}</option>)}
          </select><ChevronDown size={14} /></label>
          {!v.isCurrent ? <button type="button" className="btn ghost" onClick={() => choose(null)}>Return to current mission</button>
            : previous && previous.id !== turn?.id && <button type="button" className="btn ghost" onClick={() => choose(previous.id)}>{achieved ? "Last achieved" : "Last completed"}<ArrowUpRight size={12} /></button>}
        </div>
        <div className="mission-tabbar"><div className="mission-tabs" role="tablist" aria-label="Mission views">
          {(["overview", "activity"] as const).map((name, i) => <button type="button" key={name} role="tab" ref={(el) => { tabs.current[i] = el; }}
            id={`${uid}-tab-${name}`} aria-controls={`${uid}-panel-${name}`} aria-selected={tab === name} tabIndex={tab === name ? 0 : -1}
            onClick={() => setTab(name)} onKeyDown={(e) => tabKeys(e, i)}>{name === "overview" ? "Overview" : "Activity"}
            {name === "activity" && <span>{turn?.tools.length ?? 0}</span>}</button>)}
        </div><button type="button" className="mission-conversation" aria-label="Open conversation" onClick={onConversation}><Chat size={13} /><span>Conversation</span><ArrowUpRight size={12} /></button></div>

        <div role="tabpanel" id={`${uid}-panel-activity`} aria-labelledby={`${uid}-tab-activity`} tabIndex={0} className="mission-panel" hidden={tab !== "activity"}>
          {tab === "activity" && (turn ? <TurnView key={turn.id} turn={turn} /> : <p className="mission-empty">Activity will appear when a mission is accepted.</p>)}
        </div>
        <div role="tabpanel" id={`${uid}-panel-overview`} aria-labelledby={`${uid}-tab-overview`} tabIndex={0} className="mission-panel" hidden={tab !== "overview"}>
          {tab === "overview" && <>
            {!ended && <MissionPlan view={v} />}
            {answer && <section className="mission-section mission-outcome" aria-labelledby="mission-outcome-heading">
              <div className="mission-section-head"><h3 id="mission-outcome-heading">{v.state === "running" || v.state === "auditing" ? "Response so far" : "Outcome"}</h3>
                <CopyButton className="copy-btn quiet" text={answer} label="Copy outcome" /></div>
              <div className="mission-outcome-text">{answer.length > MAX_MARKDOWN ? <p className="streaming-plain">{answer}</p>
                : <Markdown text={answer} streaming={turn?.status === "running" || turn?.status === "auditing"} />}</div>
            </section>}
            {turn?.blocked?.missing && turn.blocked.missing.length > 0 && <section className="mission-section mission-missing">
              <div className="mission-section-head"><h3>What is missing</h3></div><ul>{turn.blocked.missing.map((m, i) => <li key={i}>{m}</li>)}</ul>
            </section>}
            <div className="mission-results">
              <section className="mission-section mission-outputs" aria-labelledby="mission-outputs-heading">
                <div className="mission-section-head"><h3 id="mission-outputs-heading"><FileIcon size={15} /> Outputs & references</h3><span>{v.artifacts.length}</span></div>
                {v.artifacts.length > 0 ? <ul>{v.artifacts.map((a) => <li key={a.doc.id}><button type="button" onClick={() => onOpen(a.doc)} className="mission-output" title={a.doc.ref}>
                  <span className="mission-output-icon" aria-hidden>{a.doc.kind === "notebook" ? <Notebook size={18} /> : <FileIcon size={18} />}</span>
                  <span className="mission-output-text"><strong>{a.doc.name}</strong><small>{a.wrote ? "Written" : "Read"} · {a.doc.kind}</small></span><ArrowUpRight size={14} />
                </button></li>)}</ul> : <p className="mission-empty">No files reported{v.state === "running" || v.state === "auditing" ? " yet" : ""}. Results can also appear in the response.</p>}
              </section>
              <section className="mission-section mission-evidence" aria-labelledby="mission-evidence-heading">
                <div className="mission-section-head"><h3 id="mission-evidence-heading"><Check size={15} /> Evidence</h3><span>{v.proof.length ? `${v.proven} of ${v.proof.length} verified` : "Not reported"}</span></div>
                {v.proof.length ? v.proof.map((p, i) => <Proof key={`${turn?.id}:${i}`} proof={p} />)
                  : <p className="mission-empty">No verified tool evidence reported. A finished response alone does not verify the work.</p>}
              </section>
            </div>
            {ended && <MissionPlan view={v} />}
          </>}
        </div>
        <footer className="mission-footer"><Folder size={13} /><span>Working folder <code>{session.scope?.folder || session.folder || "Not selected"}</code>
          {session.execution?.persistence !== "durable" && <small>History lasts until this server restarts.</small>}</span></footer>
      </div>
    </div>
  </div>;
}
