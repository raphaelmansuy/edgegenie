/**
 * The event vocabulary. Mirrors api/domain/events.py — a test asserts the lists match.
 * The reducer is a pure function over these, which is what makes replay and reconnection free.
 */
export type EventType =
  | "session.created" | "session.ready" | "session.degraded" | "session.archived"
  | "turn.started" | "turn.queued" | "thought.delta" | "message.delta"
  | "tool_call.started" | "tool_call.updated" | "plan.updated"
  | "approval.requested" | "approval.decided"
  | "evidence.proposed" | "turn.auditing"
  | "turn.completed" | "turn.blocked" | "turn.cancelled" | "turn.interrupted"
  | "turn.failed" | "turn.retrying" | "session.compacted" | "usage.updated";

export const EVENT_TYPES: EventType[] = [
  "session.created", "session.ready", "session.degraded", "session.archived",
  "turn.started", "turn.queued", "thought.delta", "message.delta",
  "tool_call.started", "tool_call.updated", "plan.updated",
  "approval.requested", "approval.decided",
  "evidence.proposed", "turn.auditing",
  "turn.completed", "turn.blocked", "turn.cancelled", "turn.interrupted",
  "turn.failed", "turn.retrying", "session.compacted", "usage.updated",
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

export interface Attachment { kind: "notebook" | "file" | "folder" | "table"; ref: string; name: string }
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
  return { ...s, turns: s.turns.map((t) => (t.id === target.id ? fn(t) : t)) };
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
      // the optimistic copy the composer showed at once is replaced by the server's turn
      const settled = s.turns.filter((t) => !t.id.startsWith(PENDING));
      const next = newTurn(id, settled.length + 1, String(e.text ?? ""), String(e.model ?? s.model));
      return { ...s, status: "streaming",
        turns: [...settled, { ...next, attachments: (e.attachments as Attachment[] | undefined) ?? [],
          status: "queued" === e.status ? "queued" : "running" }] };
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
          ? { ...c, status: String(e.status ?? c.status),
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
