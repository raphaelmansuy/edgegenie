import { patchCompaction, type Compaction, type AgentNotice } from "./agentupdates";
/**
 * The event vocabulary. Mirrors api/domain/events.py — a test asserts the lists match.
 * The reducer is a pure function over these, which is what makes replay and reconnection free.
 */
export type EventType =
  | "question.requested" | "question.decided"
  | "session.recovery_required" | "session.checkpoint"
  | "session.created" | "session.ready" | "session.degraded" | "session.archived" | "document.saved"
  | "turn.started" | "turn.queued" | "thought.delta" | "message.delta"
  | "tool_call.started" | "tool_call.updated" | "plan.updated"
  | "approval.requested" | "approval.decided"
  | "evidence.proposed" | "turn.auditing"
  | "turn.completed" | "turn.blocked" | "turn.cancelled" | "turn.interrupted"
  | "turn.failed" | "turn.retrying" | "session.compacted" | "usage.updated"
  | "capabilities.reported"
  | "mode.changed"
  | "budget.updated"
  | "budget.reached"
  | "turn.paused"
  | "change.proposed"
  | "change.decided"
  | "change.applied"
  | "change.settled"
  | "operation.started"
  | "operation.progress"
  | "operation.settled"
  | "run.review_required"
  | "resource.updated"
  | "approval.linked"
  | "blob.attached"
  | "turn.declined"
  | "turn.refused"
  | "turn.truncated"
  | "commands.updated"
  | "config.updated"
  | "session.info"
  | "agent.notice" | "sql.changed";

export const EVENT_TYPES: EventType[] = [
  "question.requested", "question.decided", "sql.changed",
  "session.recovery_required", "session.checkpoint",
  "session.created", "session.ready", "session.degraded", "session.archived", "document.saved",
  "turn.started", "turn.queued", "thought.delta", "message.delta",
  "tool_call.started", "tool_call.updated", "plan.updated",
  "approval.requested", "approval.decided",
  "evidence.proposed", "turn.auditing",
  "turn.completed", "turn.blocked", "turn.cancelled", "turn.interrupted",
  "turn.failed", "turn.retrying", "session.compacted", "usage.updated",
  "blob.attached",
  "capabilities.reported",
  "mode.changed",
  "budget.updated",
  "budget.reached",
  "turn.paused",
  "change.proposed",
  "change.decided",
  "change.applied",
  "change.settled",
  "operation.started",
  "operation.progress",
  "operation.settled",
  "run.review_required",
  "resource.updated",
  "approval.linked",

  "turn.declined",
  "turn.refused",
  "turn.truncated",
  "commands.updated",
  "config.updated",
  "session.info",
  "agent.notice",

];

export interface AgentQuestion { id: string; message: string; state: string; agent: string; schema: { properties: Record<string, {type: string; title?: string; description?: string; enum?: (string|number)[]; default?: unknown; minimum?: number; maximum?: number; minLength?: number; maxLength?: number}>; required?: string[] } }

export interface AgentEvent {
  seq: number;
  sessionId: string;
  turnId?: string | null;
  type: EventType | string;
  actor?: string;
  at?: string;
  [key: string]: unknown;
}

/** Tool states include an explicit owner rejection. The server says `failed` (the agent protocol's word) and the
 *  card says `error`; anything unrecognised was once treated as "still running", which left a failed
 *  call spinning forever under a finished turn. Only an explicit in-flight word means running. */
export function toolState(status: string | undefined): "running" | "completed" | "error" | "declined" {
  switch ((status ?? "").toLowerCase()) {
    case "completed": case "complete": case "done": case "success": case "succeeded": return "completed";
    case "declined": case "rejected": return "declined";
    case "error": case "failed": case "failure": case "cancelled": case "canceled": return "error";
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
  diffs?: { type: "diff"; path: string; oldText?: string; newText: string }[];
  locations?: { path: string; line?: number }[];
}

export interface Approval {
  approvalId: string;
  changeId?: string;
  callId?: string;
  action: string;
  target: string;
  reason: string;
  blastRadius?: string;
  options: { optionId: string; kind: string; name: string }[];
  outcome?: string;
  input?: Record<string, unknown>;
  argumentsKnown?: boolean;
  validationError?: string;
}

export interface EvidenceRow {
  requirement: string;
  toolCallId: string;
  tool: string;
  summary: string;
  verified: boolean;
  grade?: string; observed?: string; reason?: string;
}

export type TurnStatus =
  | "paused" | "queued" | "running" | "auditing" | "completed" | "blocked" | "cancelled" | "interrupted" | "failed" | "declined" | "refused" | "truncated";

/** `cell` is a fragment on a notebook path (`/path#3`); the server renders only that cell (006 FX-3). */
export interface Attachment {
  /** `blob` is bytes the user handed us (paste, drop, picker); the rest are references to the workspace. */
  kind: "notebook" | "file" | "folder" | "table" | "cell" | "blob" | "query" | "query-draft" | "job" | "job_run" | "pipeline" | "pipeline_update" | "app" | "instance" | "job_task_run" | "lineage" | "column_lineage" | "compute_usage" | "query_history";
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
  evidenceSources?: ToolCall[];
  blocked?: { reason: string; missing: string[]; attempted: { tool: string; status: string; summary?: string }[] };
  auditPasses: number;
  seconds?: number;
  usage?: { input: number; output: number; cached: number };
}

export interface SessionView {
  sqlChanges?: Record<string,import("./query").SqlChange>;
  resumeReason?: string;
  writeMode?: string;
  agentWork?: boolean;
  mode?: "plan" | "review" | "auto";
  workVersion?: number;
  changedAssets?: { key: string; kind: string; id: string }[];
  questions?: AgentQuestion[];
  notices?: AgentNotice[];
  compactions?: Compaction[];
  approvalLinks?: Record<string, string>;
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
  requiresResume?: boolean;
  meter?: { used: number; size: number; cost?: { amount: number; currency: string } };
  commands?: { name: string; description?: string }[];
  execution?: import("./mission").Execution;
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

const indexes = new WeakMap<Turn[], Map<string, number>>();
function indexOfTurn(turns: Turn[], id: string): number {
  let index=indexes.get(turns);
  if(!index){index=new Map();turns.forEach((t,i)=>{if(!index!.has(t.id))index!.set(t.id,i);});indexes.set(turns,index);}
  return index.get(id) ?? -1;
}
const patchTurn = (s: SessionView, turnId: string | null | undefined, fn: (t: Turn) => Turn): SessionView => {
  const at=turnId ? indexOfTurn(s.turns,turnId) : s.turns.length-1;
  if(at<0)return s;
  const turns=s.turns.slice();turns[at]=fn(turns[at]);
  const index=indexes.get(s.turns);if(index)indexes.set(turns,index);
  return {...s,turns};
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
    case "sql.changed": {
      const id=String(e.draftId??""),previous=s.sqlChanges?.[id];
      if(!id||(previous&&previous.seq>=e.seq))return s;
      return {...s,sqlChanges:{...s.sqlChanges,[id]:{version:Number(e.version),runId:String(e.runId??""),seq:e.seq}}};
    }
    case "question.requested":
      return { ...s, questions: [...(s.questions ?? []).filter(q => q.id !== e.id), { ...e, state: "pending" } as unknown as AgentQuestion] };
    case "question.decided":
      return { ...s, questions: (s.questions ?? []).map(q => q.id === e.id ? { ...q, state: String(e.state) } : q) };
    case "session.compacted":
      return { ...s, compactions: patchCompaction(s.compactions, e) };
    case "session.info": case "agent.notice": case "config.updated":
      return { ...s, notices: [...(s.notices ?? []), { type: e.type, text: String(e.message ?? e.title ?? e.modeId ?? "Agent configuration updated").slice(0, 2000), description: typeof e.description === "string" ? e.description.slice(0, 4000) : undefined, severity: typeof e.severity === "string" ? e.severity : undefined }].slice(-20) };
    case "approval.linked":
      return { ...s, workVersion: (s.workVersion ?? 0) + 1, approvalLinks: { ...s.approvalLinks, [String(e.approvalId)]: String(e.changeId) }, approvals: s.approvals.map(a => a.approvalId === e.approvalId ? { ...a, changeId: String(e.changeId) } : a) };
    case "turn.paused":
      return { ...patchTurn(s, e.turnId, t => ({ ...t, status: "paused" })), status: "ready", workVersion: (s.workVersion ?? 0) + 1 };
    case "mode.changed":
      return { ...s, mode: e.mode as SessionView["mode"], workVersion: (s.workVersion ?? 0) + 1 };
    case "capabilities.reported": case "budget.updated": case "budget.reached":
    case "change.applied": case "change.settled": {
      const change = e.change as { id?: string; version?: number; state?: string; asset?: { kind: string; id: string } } | undefined;
      const asset = change?.asset;
      const changes = asset && ["applied", "verified", "reverted"].includes(change?.state ?? "")
        ? [...(s.changedAssets ?? []).filter(a => a.kind !== asset.kind || a.id !== asset.id), { ...asset, key: `${change?.id}:${change?.version}:${change?.state}` }].slice(-100)
        : s.changedAssets;
      return { ...s, changedAssets: changes, workVersion: (s.workVersion ?? 0) + 1 };
    }
    case "change.proposed": case "change.decided":
    case "operation.started": case "operation.progress": case "operation.settled":
    case "run.review_required": case "resource.updated":
      return { ...s, workVersion: (s.workVersion ?? 0) + 1 };
    case "session.created":
      return { ...s, folder: String(e.folder ?? s.folder), model: String(e.model ?? s.model),
        schema: (e.schema as string | null) ?? s.schema, status: "provisioning" };
    case "session.ready":
      return { ...s, requiresResume: false, status: "ready", tools: Number(e.toolCount ?? 0),
        agent: String(e.agent ?? ""), agentVersion: String(e.agentVersion ?? "") };
    case "session.recovery_required":
      return { ...s, requiresResume: true, status: "blocked", approvals: s.approvals.map((a) => ({ ...a, outcome: a.outcome || "expired" })) };
    case "session.checkpoint":
      return s;
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
    case "turn.retrying":
      return { ...patchTurn(s, e.turnId, (t) => ({ ...t, status: "running" })), status: "streaming" };
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
    case "tool_call.updated": {
      const raw = e.rawInput as Record<string, unknown> | undefined;
      const enriched = raw && Object.keys(raw).length ? { ...s, approvals: s.approvals.map((a) => a.callId === e.callId && !a.outcome
        ? { ...a, input: raw, argumentsKnown: true, target: String(raw.path ?? raw.id ?? raw.full_name ?? raw.name ?? raw.sql ?? a.target) } : a) } : s;
      return patchTurn(enriched, e.turnId, (t) => ({
        ...t,
        tools: t.tools.map((c) => (c.callId === e.callId
          ? { ...c, status: e.status ? toolState(String(e.status)) : c.status,
              args: e.args ? String(e.args) : c.args,
              seconds: typeof e.seconds === "number" ? e.seconds : c.seconds,
              summary: e.summary ? String(e.summary) : c.summary,
              error: e.error ? String(e.error) : c.error,
              name: e.name ? String(e.name) : c.name,
              diffs: e.diffs ? (e.diffs as ToolCall["diffs"]) : c.diffs,
              locations: e.locations ? (e.locations as ToolCall["locations"]) : c.locations,
              table: e.table ? (e.table as ToolCall["table"]) : c.table }
          : c)),
      }));
    }
    case "approval.requested":
      return { ...s, approvals: [...s.approvals, {
        approvalId: String(e.approvalId), changeId: s.approvalLinks?.[String(e.approvalId)], callId: String(e.callId ?? ""), action: String(e.action ?? "write"),
        target: String(e.target ?? ""), reason: String(e.reason ?? ""),
        blastRadius: e.blastRadius ? String(e.blastRadius) : undefined,
        options: (e.options as Approval["options"]) ?? [],
        input: e.input as Approval["input"], argumentsKnown: e.argumentsKnown as boolean | undefined,
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
      return patchTurn(s, e.turnId, (t) => ({ ...t, evidence: (e.rows as EvidenceRow[]) ?? [], evidenceSources: (e.sources as ToolCall[]) ?? t.evidenceSources }));
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
    case "turn.declined":
    case "turn.refused":
    case "turn.truncated":
      return { ...s, status: "ready", turns: s.turns.map((t) => t.id === e.turnId
        ? { ...t, status: e.type.slice(5) as TurnStatus, blocked: { reason: String(e.reason), missing: [], attempted: [] } } : t) };
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
    case "commands.updated":
      return { ...s, commands: (e.availableCommands as SessionView["commands"]) ?? [] };
    case "usage.updated": {
      const u = (e.usage ?? {}) as Record<string, unknown>;
      return { ...s, meter: { used: Number(u.used ?? s.meter?.used ?? 0), size: Number(u.size ?? s.meter?.size ?? 0),
        cost: (u.cost ?? s.meter?.cost) as { amount: number; currency: string } | undefined } };
    }
    default:
      return s;
  }
}
