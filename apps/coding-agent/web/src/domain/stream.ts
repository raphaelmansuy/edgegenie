/** Stream state: the machine `useSessionStream` was missing.
 *
 * The bug this exists for is not that a stream can fail — it is that the hook could only say "live or
 * not", so two very different failures looked identical:
 *
 *   reconnecting   the connection dropped and will be retried. Transient.
 *   closed         the server refused, permanently. Retrying the same request repeats the refusal.
 *
 * `EventSource` retries only a connection that dropped AFTER a 200. A non-200 is final: the browser
 * sets `readyState = CLOSED` and stops. So 404 (the session was archived or reaped — routine), 409
 * (this tab's replay cursor is ahead of the journal, because another tab advanced it) and 422 were
 * all rendered as "reconnecting…" forever, with every control gated on `conn === "live"` disabled.
 * A user was told to wait for something that was never coming, and offered nothing to do.
 *
 * Three properties, each of which is a test in `stream.test.ts`:
 *
 *   1. The retryable set is DATA (a table), not a chain of comparisons in an effect.
 *   2. `nextInMs` is part of the state, so the UI can show "Retry now" and mean it, and a test can
 *      assert the schedule without a clock.
 *   3. `online` is an input, because offline is a different reason than a 5xx and the copy differs.
 *
 * Pure: no React, no timers, no `EventSource`. See specs/012-ux-improve 07 §2.
 */

export type ClosedReason =
  /** 404: the session no longer exists. Retry cannot help; the copy must not pretend otherwise. */
  | "not-found"
  /** 409: this tab's cursor is ahead of the journal. A retry from 0 is the correct recovery. */
  | "cursor-ahead"
  /** 422: the request is malformed. A retry would be identical. */
  | "rejected"
  /** No HTTP status at all and the browser is offline. Transient. */
  | "offline";

export type StreamState =
  | { kind: "idle" }
  | { kind: "connecting" }
  | { kind: "live" }
  | { kind: "reconnecting"; attempt: number; nextInMs: number }
  | { kind: "closed"; reason: ClosedReason };

/** First retry after one second, doubling, capped. The cap matters: a platform restart must not
 *  produce a herd of tabs reconnecting in lockstep for ten minutes. */
export const RETRY_BASE_MS = 1000;
export const RETRY_MAX_MS = 15_000;

export const backoff = (attempt: number): number =>
  Math.min(RETRY_BASE_MS * 2 ** Math.max(0, attempt), RETRY_MAX_MS);

/** Statuses where repeating the request produces the same answer. */
const TERMINAL: Record<number, ClosedReason> = {
  404: "not-found",
  409: "cursor-ahead",
  422: "rejected",
  401: "rejected",
  403: "rejected",
};

export const IDLE: StreamState = { kind: "idle" };
export const CONNECTING: StreamState = { kind: "connecting" };
export const LIVE: StreamState = { kind: "live" };

export const afterOpen = (): StreamState => LIVE;

/** What to do after an attempt failed.
 *
 *  `status` is the HTTP status learned from a probe request, or null when there was none (offline,
 *  DNS, a closed port). `attempt` is how many consecutive failures have happened, including this one.
 *
 *  OFFLINE WINS over a terminal status. A 404 observed while `navigator.onLine` is false is far more
 *  likely a captive portal or a proxy error page than the server's own answer, and the two mistakes
 *  are not equal: a wrong retry costs a second, a wrong "your session is gone" costs the user their
 *  confidence in the app.
 */
export function afterFailure(status: number | null, attempt: number, online: boolean): StreamState {
  if (!online) return { kind: "reconnecting", attempt, nextInMs: backoff(attempt) };
  if (status !== null) {
    const reason = TERMINAL[status];
    if (reason) return { kind: "closed", reason };
  }
  return { kind: "reconnecting", attempt, nextInMs: backoff(attempt) };
}

/** A user pressed Retry. The attempt counter resets: a manual retry must not be punished for the
 *  failures that preceded it, or the second click waits fifteen seconds for no reason. */
export const afterRetry = (): StreamState => ({ kind: "connecting" });

/** A session was switched. Nothing is known about the new one yet. */
export const afterSwitch = (): StreamState => ({ kind: "connecting" });

export const isLive = (s: StreamState): boolean => s.kind === "live";

/** Is the app still trying, as opposed to having given up? The distinction the old hook could not
 *  make, and the one the UI needs. */
export const isRecovering = (s: StreamState): boolean =>
  s.kind === "connecting" || s.kind === "reconnecting";

/** What to show, and whether to offer an action. The ONLY place a stream state becomes words — the
 *  dock had a pill, `mission.ts` had a paragraph and `RunStatus` had a heading, three vocabularies
 *  for one fact. */
export interface Description {
  /** The word shown next to the dot. Empty means "say nothing": a live stream needs no announcement. */
  word: string;
  /** The sentence under it. Empty when the word says everything. */
  detail: string;
  /** What the user can do. `none` when the state resolves itself. */
  action: "none" | "retry" | "retry-or-new";
  /** `alert` for a terminal state about lost work; `status` for something that resolves. */
  urgent: boolean;
}

const CLOSED_DETAIL: Record<ClosedReason, string> = {
  "not-found": "The server no longer has this session. It was archived or restarted.",
  "cursor-ahead": "This conversation moved on in another tab. Reopen it to catch up.",
  rejected: "The server refused the connection to this conversation.",
  offline: "You are offline. The server keeps working; we will catch up when you are back.",
};

export function describe(s: StreamState): Description {
  switch (s.kind) {
    case "idle":
      return { word: "", detail: "", action: "none", urgent: false };
    case "connecting":
      // No action: it resolves in milliseconds. A spinner with a button beside it is noise.
      return { word: "connecting", detail: "", action: "none", urgent: false };
    case "live":
      return { word: "", detail: "", action: "none", urgent: false };
    case "reconnecting":
      return {
        word: "reconnecting…",
        detail: "Your work is saved on the server. We will catch up automatically.",
        action: "retry",
        urgent: false,
      };
    case "closed":
      return {
        word: "session closed",
        detail: CLOSED_DETAIL[s.reason],
        action: "retry-or-new",
        urgent: true,
      };
  }
}

/** Total over `StreamState` by construction: the `switch` has no `default`, so adding a state is a
 *  compile error here rather than a screen that silently says nothing. */
