/** A notebook's Python session, as the person sees it. Pure: no React, no network.
 *
 * A session is what makes a variable made by one cell exist in the next. It lives on serverless compute,
 * so it costs something while it is up, and it can end (idle, stopped, lost). The chip says which of
 * those it is, in words, and offers the two things a person can do about it: restart it and stop it.
 */
import { outputsOf, type CellRun, type Output } from "./cellrun";

export type SessionState = "none" | "off" | "starting" | "idle" | "busy" | "stopping" | "ended";

export interface SessionStatus {
  state: SessionState;
  id?: string;
  /** Why it ended or was stopped, in words. */
  reason?: string;
  idleSeconds?: number;
}

export const NO_SESSION: SessionStatus = { state: "none" };

export interface Chip {
  label: string;
  tone: "idle" | "ok" | "busy" | "warn";
  title: string;
  canRestart: boolean;
  canStop: boolean;
}

const minutes = (s?: number) => (s ? Math.max(1, Math.round(s / 60)) : 20);

/** The chip for a session. `fallback` is the reason sessions could not be used, when the app has fallen
 *  back to one-shot runs: it is shown, not hidden, because that mode forgets variables between runs. */
export function chipFor(status: SessionStatus, fallback: string | null): Chip {
  if (fallback) {
    return {
      label: "One-shot runs", tone: "warn", canRestart: true, canStop: false,
      title: `Variables do not stay between runs: ${fallback}. Restart session tries again.`,
    };
  }
  switch (status.state) {
    case "starting":
      return { label: "Session starting…", tone: "busy", canRestart: false, canStop: true,
        title: "Starting serverless compute for this notebook's Python session. The first cell waits for it." };
    case "busy":
      return { label: "Session running", tone: "busy", canRestart: true, canStop: true,
        title: "A cell is running in the session. Stop on the cell interrupts it." };
    case "idle":
      return { label: "Session ready", tone: "ok", canRestart: true, canStop: true,
        title: `Variables stay between cells. It ends after ${minutes(status.idleSeconds)} minutes without use, and when you stop it.` };
    case "stopping":
      return { label: "Session stopping…", tone: "idle", canRestart: false, canStop: false, title: "The session is ending." };
    case "ended":
      return { label: "Session ended", tone: "warn", canRestart: true, canStop: false,
        title: `${cap(status.reason || "the session ended")}. Variables from earlier cells are gone; the next cell starts a new session.` };
    default:
      return { label: "No session yet", tone: "idle", canRestart: false, canStop: false,
        title: "The first Python cell you run starts a session. Variables then stay between cells." };
  }
}

function cap(s: string): string {
  return s ? s[0].toUpperCase() + s.slice(1) : s;
}

/** The result with one sentence put before everything else it printed, drawn as a notice. */
export function withNotice(run: CellRun, text: string): CellRun {
  const notice: Output = { type: "text", stream: "notice", text: text.endsWith("\n") ? text : `${text}\n` };
  return { ...run, outputs: [notice, ...outputsOf(run)] };
}

/** What to tell the person when a cell started a new session in place of one that ended. */
export function replacedNotice(reason: string): string {
  return `A new session was started because the last one ended (${reason}). Variables from earlier cells are gone: run them again.`;
}

/** What to tell the person when a cell had to run as a one-shot. */
export function fallbackNotice(reason: string): string {
  return `Ran as a one-shot, so variables from other cells are not kept: ${reason}.`;
}
