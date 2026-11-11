/** Parallel conversations: N streams, one per session, in a tab strip. Pure. `[R-14]`.

 *  The gap this closes. `App.tsx` holds exactly one `useSessionStream(active)` (`[G-1]`), so switching
 *  conversations tears down the EventSource and resets the cursor. The journal already supports more: a
 *  stream is a **cursor into committed events**, so N tabs are N cursors and the server needs no change.
 *
 *  **Why this is pure and separate.** The interesting questions are all about *state*, not about React: which
 *  tab is working when you are not looking at it; which tab needs a decision; what happens when the tab you
 *  are on is archived by the reaper. Each is a function of a map of cursors, and each is a test.
 *
 *  The one rule the whole module exists to enforce: **a tab's status is derived from its own events, never
 *  from being the active tab.** A background tab that finished must not look like it is still working, and
 *  a tab you are not looking at must still be able to ask for help.
 */

export type ThreadStatus = "idle" | "working" | "needs-you" | "closed";

export interface Thread {
  /** The session id. The tab's identity, and its cursor's key. */
  id: string;
  title: string;
  /** What this thread is doing, from its OWN events. */
  status: ThreadStatus;
  /** Pending approvals, so a tab can say "needs you" without being opened. */
  approvals: number;
  /** True while the tab holds the foreground. Selection is a UI fact, not a status. */
  active: boolean;
  /** Set when the stream closed and cannot recover (404/409/422). */
  closedReason?: string;
}

/** The minimum a thread needs to be described. Deliberately not the whole `SessionView`: a tab strip does
 *  not need a transcript, and taking one would make this untestable at scale. */
export interface ThreadInput {
  id: string;
  title: string;
  status: string;
  approvals: number;
  requiresResume?: boolean;
}

/** One thread from one session. The ONLY place a session status becomes a tab status. */
export function threadOf(s: ThreadInput, active: boolean): Thread {
  let status: ThreadStatus = "idle";
  if (s.requiresResume) status = "needs-you";       // a restore is a decision for a human
  else if (s.approvals > 0) status = "needs-you";   // so is an approval, and it outranks streaming
  else if (s.status === "streaming" || s.status === "provisioning") status = "working";
  else if (s.status === "failed" || s.status === "blocked") status = "needs-you";
  return { id: s.id, title: s.title || s.id.slice(0, 8), status, approvals: s.approvals, active };
}

export interface Strip {
  threads: Thread[];
  /** How many tabs are working right now, including the ones you cannot see. */
  working: number;
  /** How many need a decision, including the ones you cannot see. */
  needsYou: number;
}

/** The strip, from the sessions the app holds open. Order is the order given: tabs do not reorder
 *  themselves under the user's cursor when a background turn finishes. */
export function strip(sessions: ThreadInput[], activeId: string | null): Strip {
  const threads = sessions.map((s) => threadOf(s, s.id === activeId));
  return {
    threads,
    working: threads.filter((t) => t.status === "working").length,
    needsYou: threads.filter((t) => t.status === "needs-you").length,
  };
}

/** What the browser tab's own title says. A background turn that finishes while you are in another tab
 *  should be visible without opening this one. */
export function documentTitle(s: Strip, appName = "OpenGenie"): string {
  if (s.needsYou > 0) return `(${s.needsYou}) ${appName}`;
  if (s.working > 0) return `(${s.working}) ${appName}`;
  return appName;
}

/** Which tab to select after closing one. Never `null` while tabs remain: closing a tab must land you
 *  somewhere, and the nearest neighbour is the one the user expects. */
export function afterClose(ids: string[], closed: string, activeId: string | null): string | null {
  const rest = ids.filter((id) => id !== closed);
  if (rest.length === 0) return null;
  if (activeId && activeId !== closed) return activeId;
  const at = ids.indexOf(closed);
  return rest[Math.min(Math.max(0, at), rest.length - 1)] ?? rest[0];
}

/** A stable key for one tab's stream cursor, so `useSessionStream` can be keyed by session rather than
 *  being a singleton ([R-14]). The seq itself lives in the hook; this names the slot. */
export const cursorKey = (sessionId: string): string => `stream:${sessionId}`;

/** Is this session already open? A thread strip must not open the same conversation twice — the server
 *  would accept it and two reducers would then disagree about one transcript. */
export function isOpen(sessions: ThreadInput[], id: string): boolean {
  return sessions.some((s) => s.id === id);
}

/** Add a session to the strip, or move it to the front if it is already there. Total: any input yields a
 *  strip, because a session opened twice must not appear twice. */
export function open<T extends ThreadInput>(sessions: T[], session: T): T[] {
  return [session, ...sessions.filter((s) => s.id !== session.id)];
}

/** Close a tab. Pure, so "which tab is active afterwards" is a decision a test can assert. */
export function close<T extends ThreadInput>(sessions: T[], id: string): T[] {
  return sessions.filter((s) => s.id !== id);
}
