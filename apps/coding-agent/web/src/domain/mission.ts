/** Execution and observation are different states. A disconnected tab cannot claim fresh progress. */
import type { SessionView } from "./events";

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
    case "failed": case "interrupted": case "blocked": return "Needs attention";
    default: return s.status === "blocked" || s.status === "failed" ? "Needs attention" : "Ready";
  }
}

export function missionStatus(s: SessionView, conn: string): { title: string; detail: string; tone: string } {
  if (s.requiresResume) return {
    title: "Your progress is saved",
    detail: "Restore the agent, then review progress before continuing. Unfinished actions were not repeated.",
    tone: "attention",
  };
  if (conn === "lost" || conn === "reconnecting" || conn === "connecting") return {
    title: conn === "lost" ? "You’re offline" : "Reconnecting to your session",
    detail: "The server runs independently. We’ll catch up on saved progress when the connection returns.",
    tone: "connection",
  };
  if (s.approvals.some((a) => !a.outcome)) return {
    title: "Waiting for your decision",
    detail: "The agent will wait. Returning later never approves an action automatically.",
    tone: "attention",
  };
  const last = s.turns.at(-1);
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
