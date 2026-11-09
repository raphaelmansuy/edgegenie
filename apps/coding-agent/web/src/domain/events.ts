/**
 * The event vocabulary. Mirrors api/domain/events.py — a test asserts the lists match.
 * The reducer is a pure function over these, which is what makes replay and reconnection free.
 */
export type EventType =
  | "session.created" | "session.ready" | "session.degraded" | "session.archived" | "document.saved"
  | "turn.started" | "turn.queued" | "thought.delta" | "message.delta"
  | "tool_call.started" | "tool_call.updated" | "plan.updated"
  | "approval.requested" | "approval.decided"
  | "evidence.proposed" | "turn.auditing"
  | "turn.completed" | "turn.blocked" | "turn.cancelled" | "turn.interrupted"
  | "turn.failed" | "turn.retrying" | "session.compacted" | "usage.updated"
  | "blob.attached";

export const EVENT_TYPES: EventType[] = [
  "session.created", "session.ready", "session.degraded", "session.archived", "document.saved",
  "turn.started", "turn.queued", "thought.delta", "message.delta",
  "tool_call.started", "tool_call.updated", "plan.updated",
  "approval.requested", "approval.decided",
  "evidence.proposed", "turn.auditing",
  "turn.completed", "turn.blocked", "turn.cancelled", "turn.interrupted",
  "turn.failed", "turn.retrying", "session.compacted", "usage.updated",
  "blob.attached",
];

export interface AgentEvent {
  seq: number;
  sessionId: string;
  turnId?: string | null;
  type: EventType | string;
  actor?: string;
  at?: string;
  [key: string]: unknown;
}

/** The three states a tool card can be in. The server says `failed` (the agent protocol's word) and the
 *  card says `error`; anything unrecognised was once treated as "still running", which left a failed
 *  call spinning forever under a finished turn. Only an explicit in-flight word means running. */
export function toolState(status: string | undefined): "running" | "completed" | "error" {
  switch ((status ?? "").toLowerCase()) {
    case "completed": case "complete": case "done": case "success": case "succeeded": return "completed";
    case "error": case "failed": case "failure": case "cancelled": case "canceled": case "rejected": return "error";
    default: return "running";
  }
}

export interface ToolCall {
  callId: string;
  name: string;
  args?: string;
  status: "running" | "completed" | "error" | string;
  seconds?: number;
  summary?: string;
  error?: string;
  /** A query result, shown as a grid rather than as a sentence. */
  table?: { columns: string[]; rows: string[][]; truncated: boolean };
}

export interface Approval {
  approvalId: string;
  callId?: string;
  action: string;
  target: string;
  reason: string;
  blastRadius?: string;
  options: { optionId: string; kind: string; name: string }[];
  outcome?: string;
}

export interface EvidenceRow {
  requirement: string;
  toolCallId: string;
  tool: string;
  summary: string;
  verified: boolean;
}

export type TurnStatus =
  | "queued" | "running" | "auditing" | "completed" | "blocked" | "cancelled" | "interrupted" | "failed";

/** `cell` is a fragment on a notebook path (`/path#3`); the server renders only that cell (006 FX-3). */
export interface Attachment {
  /** `blob` is bytes the user handed us (paste, drop, picker); the rest are references to the workspace. */
  kind: "notebook" | "file" | "folder" | "table" | "cell" | "blob";
  ref: string;
  name: string;
}
export interface PlanEntry { content: string; status: "pending" | "in_progress" | "completed" | string; priority?: string }

export interface Turn {
  id: string;
  attachments?: Attachment[];
  plan?: PlanEntry[];
  index: number;
  prompt: string;
  model: string;
  status: TurnStatus;
  thought: string;
  answer: string;
  tools: ToolCall[];
  evidence: EvidenceRow[];
  blocked?: { reason: string; missing: string[]; attempted: { tool: string; status: string; summary?: string }[] };
  auditPasses: number;
  seconds?: number;
  usage?: { input: number; output: number; cached: number };
}

export interface SessionView {
  id: string;
  title: string;
  folder: string;
  schema: string | null;
  model: string;
  status: string;
  tools: number;
  agent: string;
  agentVersion: string;
  turns: Turn[];
  approvals: Approval[];
  /** Human writes, in the same stream as the agent's tool calls (WR-4). */
  saves?: { path: string; size: number; by: string; at: string }[];
  scope?: { folder: string; schema: string | null; jobPrefix: string; appPrefix: string };
}

export const emptySession = (id = ""): SessionView => ({
  id, title: "New session", folder: "", schema: null, model: "", status: "provisioning",
  tools: 0, agent: "", agentVersion: "", turns: [], approvals: [],
});

export const newTurn = (id: string, index: number, prompt = "", model = ""): Turn => ({
  id, index, prompt, model, status: "running", thought: "", answer: "", tools: [],
  evidence: [], auditPasses: 0,
});

const findTurn = (s: SessionView, turnId?: string | null): Turn | undefined =>
  turnId ? s.turns.find((t) => t.id === turnId) : s.turns[s.turns.length - 1];

const patchTurn = (s: SessionView, turnId: string | null | undefined, fn: (t: Turn) => Turn): SessionView => {
  const target = findTurn(s, turnId);
  if (!target) return s;
  // One id, one update. Mapping every copy used to paint the answer onto a duplicate turn as well.
  let done = false;
  return { ...s, turns: s.turns.map((t) => {
    if (done || t !== target) return t;
    done = true;
    return fn(t);
  }) };
};

/** Pure reducer. Unknown events are ignored (a newer server must not break an older tab). */
/** Id prefix of a turn shown before the server has confirmed it. */
export const PENDING = "pending:";

/** Streaming text limits. Long enough for any report, short enough that the tab stays alive. */
export const MAX_THOUGHT = 120_000;
export const MAX_ANSWER = 200_000;

/** Append a delta, keeping the newest text and saying so when the start was dropped. */
export function append(current: string, delta: string, max: number): string {
  const next = current + delta;
  if (next.length <= max) return next;
  return "…" + next.slice(next.length - max);
}

export function reduce(state: SessionView, e: AgentEvent): SessionView {
  const s = state.turns ? state : { ...state, turns: [], approvals: state.approvals ?? [] };
  switch (e.type) {
    case "session.created":
      return { ...s, folder: String(e.folder ?? s.folder), model: String(e.model ?? s.model),
        schema: (e.schema as string | null) ?? s.schema, status: "provisioning" };
    case "session.ready":
      return { ...s, status: "ready", tools: Number(e.toolCount ?? 0),
        agent: String(e.agent ?? ""), agentVersion: String(e.agentVersion ?? "") };
    case "session.degraded":
      return { ...s, status: "failed" };
    case "session.archived":
      return { ...s, status: "archived" };
    case "turn.started": {
      const id = String(e.turnId);
      // The detail route inserts this turn before the stream replays it. Appending again made one
      // "Hello" draw as two turns, and both copies then received the same answer.
      const previous = s.turns.find((t) => t.id === id);
      const kept = s.turns.filter((t) => !t.id.startsWith(PENDING) && t.id !== id);
      const next = newTurn(id, previous?.index || kept.length + 1,
        String(e.text ?? previous?.prompt ?? ""), String(e.model ?? previous?.model ?? s.model));
      const turn: Turn = {
        ...(previous ?? next),
        ...next,
        answer: previous?.answer ?? "",
        thought: previous?.thought ?? "",
        tools: previous?.tools ?? [],
        evidence: previous?.evidence ?? [],
        attachments: (e.attachments as Attachment[] | undefined) ?? previous?.attachments ?? [],
        status: e.status === "queued" ? "queued" : (previous?.status === "completed" ? "completed" : "running"),
      };
      const alreadyDone = previous?.status === "completed" || previous?.status === "failed"
        || previous?.status === "cancelled" || previous?.status === "blocked";
      return { ...s, status: alreadyDone ? s.status : "streaming", turns: [...kept, turn] };
    }
    case "turn.queued":
      return patchTurn(s, e.turnId, (t) => ({ ...t, status: "queued" }));
    case "plan.updated":
      // a snapshot, like evidence: the agent re-sends the whole plan each time it changes
      return patchTurn(s, e.turnId, (t) => ({ ...t, plan: (e.entries as PlanEntry[]) ?? [] }));
    case "thought.delta":
      return patchTurn(s, e.turnId, (t) => ({ ...t, thought: append(t.thought, String(e.text ?? ""), MAX_THOUGHT) }));
    case "message.delta":
      return patchTurn(s, e.turnId, (t) => ({ ...t, answer: append(t.answer, String(e.text ?? ""), MAX_ANSWER) }));
    case "tool_call.started":
      return patchTurn(s, e.turnId, (t) => ({
        ...t,
        tools: [...t.tools.filter((c) => c.callId !== e.callId), {
          callId: String(e.callId), name: String(e.name ?? "tool"), args: String(e.args ?? ""),
          status: "running",
        }],
      }));
    case "tool_call.updated":
      return patchTurn(s, e.turnId, (t) => ({
        ...t,
        tools: t.tools.map((c) => (c.callId === e.callId
          ? { ...c, status: e.status ? toolState(String(e.status)) : c.status,
              args: e.args ? String(e.args) : c.args,
              seconds: typeof e.seconds === "number" ? e.seconds : c.seconds,
              summary: e.summary ? String(e.summary) : c.summary,
              error: e.error ? String(e.error) : c.error,
              table: e.table ? (e.table as ToolCall["table"]) : c.table }
          : c)),
      }));
    case "approval.requested":
      return { ...s, approvals: [...s.approvals, {
        approvalId: String(e.approvalId), callId: String(e.callId ?? ""), action: String(e.action ?? "write"),
        target: String(e.target ?? ""), reason: String(e.reason ?? ""),
        blastRadius: e.blastRadius ? String(e.blastRadius) : undefined,
        options: (e.options as Approval["options"]) ?? [],
      }] };
    case "approval.decided":
      return { ...s, approvals: s.approvals.map((a) =>
        a.approvalId === e.approvalId ? { ...a, outcome: String(e.outcome) } : a) };
    case "document.saved": {
      /* A human save belongs in the same record as the agent's tool calls (spec 003 WR-4): the
         transcript is the audit. It appends to a running list rather than creating a turn, because
         a save is not a conversation — it is a fact about a file that happened at a time. */
      const entry = {
        path: String(e.path ?? ""),
        size: Number(e.size ?? 0),
        by: String(e.by ?? "human"),
        at: String(e.at ?? ""),
      };
      return { ...s, saves: [...(s.saves ?? []), entry] };
    }
    case "evidence.proposed":
      // a snapshot for the turn, not an append: the supervisor may report it more than once
      return patchTurn(s, e.turnId, (t) => ({ ...t, evidence: (e.rows as EvidenceRow[]) ?? [] }));
    case "turn.auditing":
      return patchTurn(s, e.turnId, (t) => ({
        ...t, status: "auditing", auditPasses: Number(e.pass ?? t.auditPasses + 1) }));
    case "turn.completed":
      return { ...s, status: "ready", turns: s.turns.map((t) => (t.id === e.turnId
        ? { ...t, status: "completed", seconds: Number(e.seconds ?? 0),
            usage: e.usage ? { input: Number((e.usage as any).inputTokens ?? 0),
              output: Number((e.usage as any).outputTokens ?? 0),
              cached: Number((e.usage as any).cachedReadTokens ?? 0) } : undefined }
        : t)) };
    case "turn.blocked":
      return { ...s, status: "blocked", turns: s.turns.map((t) => (t.id === e.turnId
        ? { ...t, status: "blocked", blocked: {
            reason: String(e.reason ?? ""),
            missing: (e.missing as string[]) ?? [],
            attempted: (e.attempted as { tool: string; status: string; summary?: string }[]) ?? [] } }
        : t)) };
    case "turn.cancelled":
      return { ...s, status: "ready", turns: s.turns.map((t) =>
        t.id === e.turnId ? { ...t, status: "cancelled" } : t) };
    case "turn.interrupted":
    case "turn.failed": {
      // A failed turn must say why: a bare "failed" is the least useful state in the product.
      const reason = String(e.reason ?? e.detail ?? "the agent stopped unexpectedly");
      return { ...s, status: "blocked", turns: s.turns.map((t) =>
        t.id === e.turnId
          ? { ...t, status: e.type === "turn.failed" ? "failed" : "interrupted",
              blocked: { reason, missing: [], attempted: [] } }
          : t) };
    }
    case "usage.updated":
      return s;
    default:
      return s;
  }
}
