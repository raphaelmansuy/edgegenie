/** What the conversation is doing, in one line a person can read from across the room. Pure.
 *
 * The conversation lives in the assistant, and the assistant is not always on screen: below 1136 px
 * it is a drawer, and a user can hide it anywhere. Before this, sending a message from the notebook's
 * own composer at that width cleared the box and showed NOTHING — no thread, no progress, no sign a
 * session existed. The peek is that sign: it says whether the agent is working, waiting for the
 * user, finished or failed, and what it is doing right now.
 */
import { toolState, type SessionView } from "./events";
import { toolLabel } from "./toolview";

export type PeekState = "working" | "waiting" | "done" | "failed" | "idle";
export interface Peek { state: PeekState; headline: string; detail: string }

const present = (past: string) => past
  .replace(/^wrote /, "Writing ").replace(/^ran /, "Running ").replace(/^read /, "Reading ")
  .replace(/^looked at /, "Looking at ").replace(/^listed /, "Listing ").replace(/^searched /, "Searching ")
  .replace(/^created /, "Creating ");

const firstLine = (text: string, max = 140): string => {
  const line = text.replace(/[#*`>_-]+/g, " ").split("\n").map((l) => l.trim()).find(Boolean) ?? "";
  return line.length > max ? `${line.slice(0, max - 1)}…` : line;
};

export function peekOf(session: Pick<SessionView, "status" | "turns" | "approvals">): Peek {
  const turn = session.turns.at(-1);
  if (!turn) return { state: "idle", headline: "Starting the agent…", detail: "" };
  if (session.approvals.some((a) => !a.outcome))
    return { state: "waiting", headline: "Waiting for your approval", detail: "The agent paused before changing something." };
  if (session.status === "streaming") {
    const running = [...turn.tools].reverse().find((t) => toolState(t.status) === "running");
    const last = turn.tools.at(-1);
    return {
      state: "working",
      headline: running ? present(toolLabel(running.name)) + "…" : last ? "Thinking about the result…" : "Thinking…",
      detail: `${turn.tools.length} tool ${turn.tools.length === 1 ? "call" : "calls"} so far`,
    };
  }
  if (turn.status === "failed" || turn.status === "blocked" || turn.status === "interrupted")
    return { state: "failed", headline: turn.status === "blocked" ? "The agent could not finish" : "The turn did not finish", detail: firstLine(turn.answer) };
  const failed = turn.tools.filter((t) => toolState(t.status) === "error").length;
  return {
    state: "done",
    headline: failed ? `Done, with ${failed} failed tool ${failed === 1 ? "call" : "calls"}` : "Done",
    detail: firstLine(turn.answer),
  };
}
