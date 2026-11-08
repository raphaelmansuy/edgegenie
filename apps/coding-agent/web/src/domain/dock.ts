/** The assistant dock's state and the words it uses. Pure: one function, four states.
 *
 * Four states, not five. Every other condition is a detail of one of them — a fifth state is how a
 * dock acquires an unreachable screen (spec 006 AD-7, 04 §the state machine).
 *
 * The precedence is load-bearing and asserted: **an approval outranks streaming.** A run waiting for
 * a human is not making progress, and showing "streaming" would hide the one thing the user must do.
 */
import type { DocKind } from "./docs";
import type { Focus } from "./focus";
import { ACTIONS, type Action } from "./docs";

export type DockState = "empty" | "streaming" | "asking" | "failed";

export interface DockInput {
  /** Is a session loaded at all? `false` shows the start-from-nothing state. */
  hasSession: boolean;
  /** The session's status string, as the server reports it. */
  status: string;
  /** The last turn, when there is one. */
  last?: { status: string } | null;
  /** Approvals with no outcome yet. */
  pendingApprovals: number;
}

export function dockState(input: DockInput): DockState {
  if (!input.hasSession) return "empty";
  // An approval is a decision *about* a turn, so it is checked before the turn's own status: a turn
  // blocked on a human is not "running" from the user's point of view.
  if (input.pendingApprovals > 0) return "asking";
  const last = input.last?.status;
  if (last === "failed" || input.status === "failed") return "failed";
  if (input.status === "streaming" || last === "running" || last === "queued" || last === "auditing") {
    return "streaming";
  }
  return "empty";
}

/** The header line. A state names what it is, in the user's language.
 *
 * `hasTurns` matters: a dock that says "new conversation" while a finished turn is on screen is
 * simply wrong, and the header is the one place a user checks to see what this panel is doing.
 */
export function dockTitle(state: DockState, hasSession: boolean, hasTurns = false): string {
  switch (state) {
    case "asking": return "needs your decision";
    case "failed": return "that turn failed";
    case "streaming": return "working";
    default: return hasSession && hasTurns ? "conversation" : "new conversation";
  }
}

/** The word next to the state glyph. Short on purpose: the header's width belongs to the binding. */
export function dockStateWord(state: DockState, hasSession: boolean, hasTurns = false, lastStatus?: string): string {
  switch (state) {
    case "asking": return "decide";
    case "failed": return "failed";
    case "streaming": return "working";
    default:
      // Four states stay four; the last turn's outcome only changes the word. "ready" after a blocked
      // turn told the user the one thing that was not true.
      if (lastStatus === "blocked") return "blocked";
      if (lastStatus === "interrupted") return "interrupted";
      if (lastStatus === "cancelled") return "stopped";
      return hasSession && hasTurns ? "ready" : "new";
  }
}

export interface Suggestion { label: string; prompt: string; action?: Action }

/** Three things to do, derived from what is open. Never marketing copy (spec 006 04 §starting). */
export function suggestionsFor(focus: Focus): Suggestion[] {
  const doc: { kind: DocKind; name: string } | null = focus.doc;
  if (!doc) {
    return [
      { label: "What can you do here?", prompt: "What can you do in this workspace? Be concrete and brief." },
      { label: "Open something from Files", prompt: "Summarise what I have in my home folder." },
      { label: "Start a scratch notebook", prompt: "Create a notebook in my working folder that I can experiment in." },
    ];
  }
  const n = focus.cell;
  if (doc.kind === "table") {
    return [
      { label: "Profile this table", prompt: ACTIONS.profile.prompt, action: "profile" },
      { label: "Suggest three queries", prompt: ACTIONS.query.prompt, action: "query" },
      { label: "Document the columns", prompt: `Document the columns of the attached table based on the real values you observe.`, action: "profile" },
    ];
  }
  if (n) {
    return [
      { label: `Explain cell ${n}`, prompt: `Explain what cell ${n} of the attached notebook does, in plain English. Do not change anything.`, action: "explain" },
      { label: `Fix cell ${n}`, prompt: `Find the bug in cell ${n} of the attached notebook. Check every table and column name with describe_table first. Write a corrected copy in your working folder and show the evidence it runs.`, action: "fix" },
      { label: `Add a null guard to cell ${n}`, prompt: `Add a null guard to cell ${n} of the attached notebook. Write the change in your working folder, never to the original.` },
    ];
  }
  if (doc.kind === "file") {
    return [
      { label: "Explain this file", prompt: ACTIONS.explain.prompt, action: "explain" },
      { label: "Find a bug in this file", prompt: `Review the attached file for bugs. Check every name it uses, then write a corrected copy in your working folder and run it.`, action: "fix" },
      { label: "Rewrite it in my folder", prompt: `Rewrite the attached file in my working folder with the same behaviour and clearer structure. Leave the original alone.` },
    ];
  }
  return [
    { label: "Explain this notebook", prompt: ACTIONS.explain.prompt, action: "explain" },
    { label: "Find the bug in this notebook", prompt: `Review the attached notebook for bugs. Check every table and column name with describe_table before judging it. Write a corrected copy in your working folder, run it, and show the evidence.`, action: "fix" },
    { label: "Document it in my folder", prompt: ACTIONS.document.prompt, action: "document" },
  ];
}

/** Announcing a streamed answer: once, when a turn ends. Never per token. */
export function announce(previous: { turns: number; running: boolean }, next: { turns: number; running: boolean }): string {
  if (previous.running && !next.running && next.turns >= previous.turns) return "the answer is ready";
  if (!previous.running && next.running) return "the agent is working";
  return "";
}

/** The dock's width bounds live in layout.ts; this is only the label for its handle. */
export const DOCK_LABEL = "Resize the assistant";
