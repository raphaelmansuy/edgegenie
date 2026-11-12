/** The assistant dock: the conversation, beside the document it is about.
 *
 * Spec 006 04. The whole point is in the header: it states the binding (`in context: …`), so the
 * subject of the next prompt is data on screen rather than a coincidence of the viewport.
 *
 * Deliberate choices, each with a document behind it:
 *  - **it renders `TurnView`**, the same component the Chat tab uses, so the two surfaces cannot
 *    disagree about how a turn looks (spec 006 R-2);
 *  - **it renders `Composer`** with `variant="dock"`, so there is one composer, not two (D6);
 *  - **the approval is inline**, because the modal sheet covers the code the approval is about (D4);
 *  - **it never opens itself**: below 1180 px it is a drawer that only `⌘J` or the toggle opens (AD-4).
 */
import { useState } from "react";
import { useFollowScroll } from "../hooks/useFollowScroll";
import type { Approval, Attachment, SessionView, Turn } from "../domain/events";
import { dockState, dockStateWord, dockTitle, suggestionsFor, type DockState, type Suggestion } from "../domain/dock";
import { focusLabel, type Focus } from "../domain/focus";
import type { CatalogueResponse } from "../domain/models";
import { Alert, PanelRight, Plus, Sparkle } from "./Icons";
import { LogoMark } from "./Logo";
import { DockHistory, DockMenu } from "./DockTools";
import { followUps } from "../domain/followups";
import { conversationMarkdown, exportName } from "../domain/transcript";
import type { SessionSummary } from "../api/client";
import { RunStatus } from "./RunStatus";
import { Composer } from "./Composer";
import { TurnView } from "./Transcript";
import type { Doc } from "../domain/docs";

export interface DockProps {
  focus: Focus;
  session: SessionView;
  /** False until a session exists: the dock still works, it just has no turns yet (AD-5). */
  hasSession: boolean;
  running: boolean;
  conn: "idle" | "connecting" | "live" | "reconnecting" | "lost";
  error: string | null;
  /** The model control, rendered by the App so both placements use one component (MC-2). */
  modelSlot?: React.ReactNode;
  /** Called with the text and the binding, exactly as the composer produced them. */
  onSend: (text: string, attachments: Attachment[]) => Promise<void>;
  onStop: () => Promise<void>;
  onRestore: () => Promise<void>;
  onSuggestion: (s: Suggestion) => void;
  onApprove: (a: Approval, outcome: "allow_once" | "allow_session" | "deny") => Promise<void>;
  onRetry: () => void;
  onNewSession: () => void;
  onHide?: () => void;
  onAttach: (a: Attachment) => void;
  onRemoveAttachment: (a: Attachment) => void;
  attachments: Attachment[];
  openDocs: Doc[];
  searchRoot: string;
  /** The session the dock writes into: blobs are scoped to it and the fence judges by it. */
  sessionId?: string | null;
  /** Whether the active model can consume an image, so an impossible attachment is refused up front. */
  modelSeesImages?: boolean;
  modelName?: string;
  onOpenDoc: (d: Doc) => void;
  /** Below 1180 px the dock is a drawer; the header then offers a close control that returns focus. */
  overlay: boolean;
  className?: string;
  edge?: React.ReactNode;
  catalogue: CatalogueResponse | null;
  onAddKey?: () => void;
  onRefreshModels?: () => void;
  onChooseModel?: (id: string) => Promise<void>;
  currentModel: string;
  /** The model the last turn actually used, when it differs from the next turn's. */
  lastTurnModel?: string;
  composerRef?: { current: HTMLTextAreaElement | null };
  placeholder?: string;
  /** The user's conversations, for the history popover. Absent in a test that does not need it. */
  sessions?: SessionSummary[];
  activeId?: string | null;
  onOpenSession?: (s: SessionSummary) => void;
  onDeleteSession?: (s: SessionSummary) => Promise<void>;
}

export function AssistantDock(p: DockProps) {
  const turns = p.session.turns ?? [];
  const pending = (p.session.approvals ?? []).filter((a) => !a.outcome);
  const state: DockState = dockState({
    hasSession: p.hasSession,
    status: p.session.status,
    last: turns.at(-1) ? { status: turns.at(-1)!.status } : null,
    pendingApprovals: pending.length,
  });
  const last = turns.at(-1);
  const canSend = p.session.status !== "archived" && !p.session.requiresResume && (!p.hasSession || p.conn === "live");
  /* Follow the stream while the reader is at the tail, and let go the moment they move up — by wheel,
     finger, key or scrollbar. The decision is `domain/follow.ts`; the panel-wide wheel and focus
     contract is the hook's (spec 012 §3). */
  const { scroller, region, behind, toEnd, forwardWheel, claimFocus } = useFollowScroll(
    p.session.id ?? "", [turns.length, last?.answer.length, last?.tools.length, last?.status, state, p.error, pending.length]);

  const empty = state === "empty" && turns.length === 0;
  // The dock says READY after a turn that ended blocked: true of the connection, false of the work.
  const tone = state === "empty" && last && ["blocked", "interrupted", "cancelled"].includes(last.status) ? "blocked" : state;

  return (
    /* `id="dock"` + tabIndex=-1: the skip link's target (007 KB-7). Named "Assistant" for a screen
       reader because that is what the region IS; the link says "the conversation" because that is
       what the user calls it. Both names are stated in the e2e (E-33). */
    <aside id="dock" tabIndex={-1} className={`pane assistant${p.className ? ` ${p.className}` : ""}`} aria-label="Assistant"
      data-state={state} onWheel={forwardWheel} onMouseDown={claimFocus}>
      {p.edge}
      {/* The header answers two questions in one line: what is happening, and what it is about.
          A separate bold title competed with the binding for the 380 px available and truncated the
          one string that must be readable (AD-6), so the state is a glyph plus a word only when it
          needs action. */}
      <header className="dock-head">
        <span className={`dock-state tone-${p.session.status === "archived" ? "archived" : tone}`} title={p.session.status === "archived" ? "Archived conversation — saved work is available for review." : dockTitle(state, p.hasSession, turns.length > 0)}>
          {state === "streaming" ? <span className="spin" aria-hidden /> : <span className="dock-state-dot" aria-hidden />}
          <span className="dock-state-word">{p.session.status === "archived" ? "archived" : dockStateWord(state, p.hasSession, turns.length > 0, last?.status)}</span>
        </span>
        <span className="dock-context" title={p.focus.doc?.ref ?? "nothing is open"}>
          <LogoMark size={12} />
          <span className="dock-context-label">in context:</span>
          <span className="dock-context-value">{focusLabel(p.focus)}</span>
        </span>
        <span className="dock-head-spacer" />
        {p.conn !== "live" && p.hasSession && (
          <span className={`pill ${p.conn}`} title="The event stream is reconnecting">
            {p.conn === "reconnecting" ? "reconnecting…" : p.conn}
          </span>
        )}
        {p.sessions && p.onOpenSession && p.onDeleteSession && (
          <DockHistory sessions={p.sessions} activeId={p.activeId ?? null} onOpen={p.onOpenSession} onDelete={p.onDeleteSession} />
        )}
        <button className="icon-btn dock-new" onClick={p.onNewSession}
          title="New conversation (⌘⇧N)" aria-label="New conversation"><Plus size={14} /></button>
        <DockMenu hasTurns={turns.length > 0} onNew={p.onNewSession}
          fileName={exportName(p.session.title === "New session" ? "conversation" : p.session.title)}
          markdown={() => conversationMarkdown(p.session.title === "New session" ? "Conversation" : p.session.title, turns, new Date())} />
        {p.onHide && (
          <button className="icon-btn dock-close" onClick={p.onHide}
            title={`Hide the assistant (⌘J)`} aria-label="Hide the assistant"><PanelRight size={14} /></button>
        )}
      </header>

      <RunStatus key={p.session.id} session={p.session} conn={p.conn} onRestore={p.onRestore} onStop={p.onStop} />

      {/* `tabIndex={0}`: a region that scrolls must be reachable by keyboard (axe: scrollable-region-focusable),
          and it is what a click on the panel's dead space focuses, so PageUp / Space / ↑↓ scroll it. */}
      <div className="dock-body" ref={scroller} tabIndex={0} {...region} role="log"
        aria-label="Conversation" aria-live="polite" aria-busy={state === "streaming"}>
        {empty && <Start focus={p.focus} onSuggestion={p.onSuggestion} hasSession={p.hasSession} />}

        {turns.map((t) => (
          // Retry is offered on the last turn only, and only when it is not the thing already running.
          <TurnView key={t.id} turn={t} onRetry={canSend && t === last && state !== "streaming" && state !== "asking" && t.status !== "interrupted" ? p.onRetry : undefined} />
        ))}

        {/* The next step, derived from what this turn actually did. Only on the last turn, and only when
            nothing is running or waiting: a chip beside a pending approval is a second place to look. */}
        {last && canSend && state === "empty" && (
          <FollowUps items={followUps(last)} onPick={p.onSuggestion} />
        )}

        {state === "asking" && pending.map((a) => (
          <InlineApproval key={a.approvalId} approval={a} disabled={!canSend} onDecide={p.onApprove} />
        ))}

        {state === "failed" && canSend && (
          <FailedTurn error={p.error} turn={last} onRetry={p.onRetry} />
        )}

        {p.error && state !== "failed" && (
          <p className="dock-error" role="alert"><Alert size={13} /> {p.error}</p>
        )}

        {/* Only when the reader has left the tail and there is more below: the way back to following. */}
        {behind && (
          <button type="button" className="dock-jump"
            onClick={() => { toEnd(); scroller.current?.focus({ preventScroll: true }); }}>
            <span aria-hidden>↓</span> {state === "streaming" ? "Follow the work" : "Latest"}
          </button>
        )}
      </div>

      {/* A switch applies to the NEXT turn, and a toast that disappears leaves the user guessing
          which model will answer. This line is the pin, stated where the message is written: it only
          appears when the answer on screen came from a different model (006 MC-5). */}
      {p.lastTurnModel && p.lastTurnModel !== p.currentModel && (
        <p className="dock-pin" role="status">
          next message uses <strong>{shortLabel(p.currentModel)}</strong>
          <span className="dock-pin-was"> · the answer above came from {shortLabel(p.lastTurnModel)}</span>
        </p>
      )}
      <Composer
        variant="dock"
        disabled={!canSend}
        busy={state === "streaming"}
        onSend={(text, mine = []) => p.onSend(text, [...p.attachments, ...mine])}
        onStop={p.onStop}
        attachments={p.attachments}
        auto={null}
        onAdd={p.onAttach}
        onRemove={p.onRemoveAttachment}
        openDocs={p.openDocs}
        inputRef={p.composerRef}
        searchRoot={p.searchRoot}
        sessionId={p.sessionId ?? null}
        modelSeesImages={p.modelSeesImages ?? true}
        modelName={p.modelName}
        modelSlot={p.modelSlot}
        placeholder={p.placeholder ?? (p.focus.doc ? `Ask about ${p.focus.doc.name}…` : "Ask anything…")}
      />
    </aside>
  );
}

/** The name a user recognises: the last path segment, with gemini's dash spelled out. */
function shortLabel(id: string): string {
  const tail = (id || "").split("/").pop() ?? id;
  return tail.replace(/^gemini-/, "gemini ");
}

function Start({ focus, onSuggestion, hasSession }: {
  focus: Focus; onSuggestion: (s: Suggestion) => void; hasSession: boolean;
}) {
  const suggestions = suggestionsFor(focus);
  if (!hasSession && !focus.doc) return <div className="dock-start">
    <p className="dock-start-lead">Your assistant</p>
    <p className="dock-start-note">Ask a question below. Open a document to bring it into context.</p>
  </div>;
  return (
    <div className="dock-start">
      <p className="dock-start-lead">
        {hasSession ? "Ready for the next question." : "Ask about what you have open, or start anywhere."}
      </p>
      <div className="dock-suggestions" role="list">
        {suggestions.map((s) => (
          <button key={s.label} role="listitem" className="dock-suggestion" onClick={() => onSuggestion(s)}>
            <span className="dock-suggestion-label">{s.label}</span>
            <span className="dock-suggestion-go" aria-hidden>→</span>
          </button>
        ))}
      </div>
      {!hasSession && (
        <p className="dock-start-note">
          A conversation starts when you send the first message. The agent can write only in your
          working folder; anything else asks you first.
        </p>
      )}
    </div>
  );
}

function FollowUps({ items, onPick }: { items: { label: string; prompt: string }[]; onPick: (s: Suggestion) => void }) {
  if (items.length === 0) return null;
  return (
    <div className="followups" role="group" aria-label="Suggested next steps">
      {items.map((f) => (
        <button key={f.label} type="button" className="followup" onClick={() => onPick(f)}>
          <Sparkle size={12} /> {f.label}
        </button>
      ))}
    </div>
  );
}

export function InlineApproval({ approval, onDecide, disabled = false }: {
  approval: Approval; disabled?: boolean;
  onDecide: (a: Approval, outcome: "allow_once" | "allow_session" | "deny") => Promise<void>;
}) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const decide = async (outcome: "allow_once" | "allow_session" | "deny") => {
    setPending(true); setError("");
    try { await onDecide(approval, outcome); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not record the decision. Try again."); }
    finally { setPending(false); }
  };
  // Deliberately not dismissible with Escape: refusing an action must be a decision, not an accident.
  return (
    <section className="dock-approval" role="alert" aria-label="Approval required">
      <header>
        <Alert size={14} />
        <strong>Needs your decision</strong>
      </header>
      <p className="dock-approval-action">
        it wants to <strong>{approval.action}</strong> something outside your working folder
      </p>
      <p className="dock-approval-target"><code>{approval.target}</code></p>
      {approval.reason && <p className="dock-approval-reason">{approval.reason}</p>}
      {approval.blastRadius && <p className="dock-approval-reason">Blast radius: {approval.blastRadius}</p>}
      <div className="dock-approval-actions">
        <button className="btn sm primary" disabled={disabled || pending || !approval.options.some((o) => o.kind === "allow_once")}
          onClick={() => void decide("allow_once")}>Allow once</button>
        <button className="btn sm" disabled={disabled || pending || !approval.options.some((o) => o.kind === "allow_always")}
          onClick={() => void decide("allow_session")}>Allow this session</button>
        <button className="btn sm ghost stop" disabled={disabled || pending} onClick={() => void decide("deny")}>Deny</button>
      </div>
      {error && <p className="dock-error" role="alert">{error}</p>}
      <p className="dock-approval-note">Recorded in the audit log with your name and the object.</p>
    </section>
  );
}

function FailedTurn({ error, turn, onRetry }: { error: string | null; turn?: Turn; onRetry: () => void }) {
  return (
    <section className="dock-failed" role="alert">
      <p className="dock-failed-head"><Alert size={14} /> That turn failed</p>
      {error && <p className="dock-failed-detail">{error}</p>}
      {turn?.model && <p className="dock-failed-model">the turn kept its model: <code>{turn.model}</code></p>}
      <button className="btn sm" onClick={onRetry}>Retry</button>
    </section>
  );
}

