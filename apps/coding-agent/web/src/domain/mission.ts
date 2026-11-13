/** Execution and observation are different states. A disconnected tab cannot claim fresh progress. */
import { toolState, type EvidenceRow, type SessionView, type ToolCall, type Turn } from "./events";
import { artifactsOf } from "./artifacts";
import { isLive, isRecovering, type StreamState } from "./stream";

export interface Execution {
  persistence: "durable" | "memory";
  state: string;
  queued: number;
  pendingApprovals: number;
  maxRunSeconds: number;
}

export function missionLabel(s: { status?: string; requiresResume?: boolean; execution?: Execution }): string {
  if (s.requiresResume) return "Needs attention";
  if (s.execution?.pendingApprovals) return "Needs approval";
  if (s.status === "streaming" || s.execution?.state === "running") return "Running";
  switch (s.execution?.state) {
    case "completed": return "Completed";
    case "cancelled": return "Stopped";
    case "declined": return "Stopped by your decision";
    case "refused": return "Model declined";
    case "truncated": return "Model limit reached";
    case "failed": case "interrupted": case "blocked": return "Needs attention";
    default: return s.status === "blocked" || s.status === "failed" ? "Needs attention" : "Ready";
  }
}

export function missionStatus(s: SessionView, conn: StreamState): { title: string; detail: string; tone: string } {
  if (s.status === "archived") return {
    title: "Archived session", detail: "Saved work is available for review. Start a new conversation for another mission.", tone: "quiet",
  };
  if (s.requiresResume) return {
    title: "Your progress is saved",
    detail: "Restore the agent, then review progress before continuing. Unfinished actions were not repeated.",
    tone: "attention",
  };
  /* The connection branch reads the state machine, not a string. `closed` is a different animal
     from `reconnecting`: one resolves, the other needs the user. They used to share a word, which is
     specs/012 [F2]; `StreamNotice` now owns the announcement and the action, so this returns a plain
     connection tone and lets that component say which. */
  if (conn.kind === "closed") return {
    title: "Session closed",
    detail: "This conversation is no longer reachable. Start a new one, or retry below.",
    tone: "attention",
  };
  if (isRecovering(conn)) return {
    title: conn.kind === "reconnecting" ? "Reconnecting to your session" : "Connecting to your session",
    detail: "The server runs independently. We’ll catch up on saved progress when the connection returns.",
    tone: "connection",
  };
  if (s.questions?.some(q => q.state === "pending")) return { title: "Waiting for your answer", detail: "The agent asked a question. Answer, skip, or cancel in the conversation.", tone: "attention" };
  if (s.approvals.some((a) => !a.outcome)) return {
    title: "Waiting for your decision",
    detail: "The agent will wait. Returning later never approves an action automatically.",
    tone: "attention",
  };
  const last = currentMission(s);
  if (last?.status === "paused") return { title: "Waiting for review or run", detail: "Review saved proposals or follow Runs. No action is approved automatically.", tone: "attention" };
  if (last?.status === "declined" || last?.status === "refused" || last?.status === "truncated") return {
    title: last.status === "declined" ? "Stopped by your decision" : last.status === "refused" ? "Model declined" : "Model limit reached",
    detail: last.blocked?.reason || "Review the saved result before continuing.", tone: "quiet",
  };
  if (last?.status === "blocked" || last?.status === "failed") return {
    title: last.status === "blocked" ? "Work blocked" : "Work failed",
    detail: last.blocked?.reason || "Review saved tool results before continuing. Some changes may already have completed.",
    tone: "attention",
  };
  if (s.status === "streaming") return {
    title: last?.status === "auditing" ? "Checking the work" : "Working on the server",
    detail: "You can close this tab. Return to this conversation to review progress.",
    tone: "running",
  };
  if (last?.status === "completed") return {
    title: "Ready for your review",
    detail: "The turn finished. Review the answer, tool results, and evidence below.",
    tone: "complete",
  };
  if (last?.status === "cancelled") return {
    title: "Work stopped",
    detail: "The accepted queue was stopped. Completed changes remain available to review.",
    tone: "quiet",
  };
  if (last?.status === "interrupted") return {
    title: "Ready to continue",
    detail: "The agent is restored. Review the interrupted turn before asking it to continue.",
    tone: "quiet",
  };
  return {
    title: "Server session",
    detail: "Your agent keeps working when you leave this page. Decisions still wait for you.",
    tone: "quiet",
  };
}

/** A mission is an accepted turn. A queued follow-up must never displace its foreground. */
export function currentMission(s: Pick<SessionView, "turns">): Turn | undefined {
  return s.turns.find((t) => t.status === "running" || t.status === "auditing")
    ?? s.turns.find((t) => t.status === "queued") ?? s.turns.at(-1);
}

export interface MissionProof {
  row: EvidenceRow;
  source?: ToolCall;
  verified: boolean;
}

/** Server verdict AND a successful source in this same turn. Never join proof across missions. */
export function missionProof(turn: Turn): MissionProof[] {
  const calls = new Map([...turn.tools, ...(turn.evidenceSources ?? [])].map((c) => [c.callId, c]));
  return turn.evidence.map((row) => {
    const source = calls.get(row.toolCallId);
    return { row, source,
      verified: row.verified && Boolean(source && source.name === row.tool && toolState(source.status) === "completed") };
  });
}

export function isAchieved(turn: Turn): boolean {
  return turn.status === "completed" && turn.evidence.length > 0 && missionProof(turn).every((p) => p.verified);
}

export function lastAchieved(s: Pick<SessionView, "turns">): Turn | undefined {
  return [...s.turns].reverse().find(isAchieved);
}

export type MissionState = "asking" | "paused" | "starting" | "ready" | "queued" | "running" | "auditing" | "waiting" | "achieved"
  | "declined" | "refused" | "truncated" | "review" | "blocked" | "failed" | "cancelled" | "interrupted" | "recovery" | "archived";

export const MISSION_STATES: Record<MissionState, { label: string; tone: string; detail: string }> = {
  asking: { label: "Needs your input", tone: "attention", detail: "Answer the agent’s question in the conversation, or skip it to continue." },
  paused: { label: "Waiting for review or run", tone: "attention", detail: "Review the proposed changes or follow the saved run. No action is approved automatically." },
  declined: { label: "Stopped by your decision", tone: "quiet", detail: "You rejected the action. The agent was told once." },
  refused: { label: "Model declined", tone: "attention", detail: "The model declined to continue." },
  truncated: { label: "Model limit reached", tone: "attention", detail: "The answer stopped at the model limit. Review saved work." },
  starting: { label: "Starting", tone: "quiet", detail: "Your session is opening. Accepted work will appear here." },
  ready: { label: "Ready", tone: "quiet", detail: "Send an instruction to start your first mission." },
  queued: { label: "Queued", tone: "quiet", detail: "This instruction is accepted and waiting for its turn." },
  running: { label: "In progress", tone: "active", detail: "The agent is working. Its plan and results appear as they arrive." },
  auditing: { label: "Checking work", tone: "active", detail: "The agent is checking the result against your request." },
  waiting: { label: "Needs approval", tone: "attention", detail: "Work is waiting for your decision in the conversation." },
  achieved: { label: "Achieved", tone: "success", detail: "The turn finished and every reported requirement has verified tool evidence." },
  review: { label: "Ready for review", tone: "quiet", detail: "The turn finished. Review the outcome; complete verified evidence is not available." },
  blocked: { label: "Blocked", tone: "attention", detail: "The agent could not finish. Review what is missing before continuing." },
  failed: { label: "Failed", tone: "danger", detail: "This mission did not finish. Review saved activity before trying again." },
  cancelled: { label: "Stopped", tone: "quiet", detail: "Work was stopped. Completed changes are still available to review." },
  interrupted: { label: "Interrupted", tone: "attention", detail: "Work was interrupted. Review saved activity before continuing." },
  recovery: { label: "Restore needed", tone: "attention", detail: "Progress is saved. Restore the agent before sending another instruction." },
  archived: { label: "Archived", tone: "quiet", detail: "This session is archived. Its saved missions are available for review." },
};

/** Strip only the local demo selector; the full real request remains available in the UI. */
export const missionRequest = (prompt: string): string => prompt.replace(/\s*\[\[scenario:\w+\]\]/g, "").trim();

export function missionView(s: SessionView, turn: Turn | undefined, conn: StreamState) {
  const current = currentMission(s);
  const isCurrent = !turn || turn.id === current?.id;
  let state: MissionState = !turn ? (s.status === "ready" ? "ready" : "starting") : turn.status === "completed"
    ? (isAchieved(turn) ? "achieved" : "review") : turn.status;
  if (isCurrent) {
    if (s.status === "archived") state = "archived";
    else if (s.requiresResume) state = "recovery";
    else if (s.questions?.some(q => q.state === "pending")) state = "asking";
    else if (s.approvals.some((a) => !a.outcome)) state = "waiting";
    else if (!turn && (s.status === "failed" || s.status === "blocked")) state = s.status;
  }
  const presentation = MISSION_STATES[state] ?? MISSION_STATES.starting;
  const request = missionRequest(turn?.prompt || s.title || "");
  const objective = (request.split("\n").map((l) => l.trim()).find(Boolean) || "Your next mission").replace(/^(?:[-*]|\d+[.)])\s+/, "");
  const compact = objective.replace(/\/(?:Workspace\/)?(?:Users|Shared|Repos)\/[^\s]+/g, path => path.split("/").at(-1) || path);
  const title = compact.length > 110 ? `${compact.slice(0, 109)}…` : compact;
  const proof = turn ? missionProof(turn) : [];
  return {
    state, ...presentation, isCurrent, request, title,
    paused: isCurrent && !isLive(conn) && conn.kind !== "idle",
    queued: s.turns.filter((t) => t.status === "queued").length,
    plan: turn?.plan ?? [],
    planDone: turn?.plan?.filter((p) => p.status === "completed").length ?? 0,
    proof, proven: proof.filter((p) => p.verified).length,
    /* What the turn could not prove. The mission header says "blocked" because of this list, so the
       evidence panel must be able to show the same list — otherwise a reader sees "Blocked" above
       "3 of 3 verified" and has no way to tell what is missing. Found by inspecting a screenshot. */
    missing: turn?.blocked?.missing ?? [],
    blockedReason: turn?.blocked?.reason ?? "",
    failedCalls: turn?.tools.filter((c) => toolState(c.status) === "error").length ?? 0,
    artifacts: turn ? artifactsOf([turn]) : [],
    model: turn?.model || s.model,
    seconds: typeof turn?.seconds === "number" && Number.isFinite(turn.seconds) && turn.seconds > 0 ? turn.seconds : undefined,
  };
}
