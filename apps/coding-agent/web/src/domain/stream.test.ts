/** The stream state machine, with no browser in sight.
 *
 * The three failures this pins down, each of which produced a permanent "reconnecting…":
 *   - 404 (a session archived or reaped — routine) was treated as transient;
 *   - 409 (a replay cursor ahead of the journal) was treated as transient;
 *   - nothing bounded the retry, so the state was indistinguishable from a loop.
 */
import { describe, expect, it } from "vitest";
import {
  afterFailure, afterOpen, afterRetry, afterSwitch, backoff, describe as describeState,
  IDLE, isLive, isRecovering, RETRY_BASE_MS, RETRY_MAX_MS, type StreamState,
} from "./stream";

describe("backoff: bounded, doubling, and never above the cap", () => {
  it("starts at one second", () => {
    expect(backoff(0)).toBe(RETRY_BASE_MS);
    expect(backoff(1)).toBe(2000);
    expect(backoff(2)).toBe(4000);
    expect(backoff(3)).toBe(8000);
  });

  it("caps at fifteen seconds and stays there", () => {
    expect(backoff(4)).toBe(RETRY_MAX_MS);
    expect(backoff(10)).toBe(RETRY_MAX_MS);
    expect(backoff(100)).toBe(RETRY_MAX_MS);
  });

  it("is not negative for a negative attempt, which a reset counter could produce", () => {
    expect(backoff(-3)).toBe(RETRY_BASE_MS);
  });
});

describe("afterFailure: the terminal set is data, not a chain of comparisons", () => {
  it("closes on 404 — the session is gone and a retry repeats the 404", () => {
    expect(afterFailure(404, 1, true)).toEqual({ kind: "closed", reason: "not-found" });
  });

  it("closes on 409 — the cursor is ahead, so a retry from the same cursor repeats it", () => {
    expect(afterFailure(409, 1, true)).toEqual({ kind: "closed", reason: "cursor-ahead" });
  });

  it("closes on 422, 401 and 403, which are all 'the request is wrong'", () => {
    for (const s of [422, 401, 403]) {
      expect(afterFailure(s, 1, true).kind).toBe("closed");
    }
  });

  it("retries a 5xx and a 503 is the common case after a platform restart", () => {
    const s = afterFailure(503, 1, true);
    expect(s).toEqual({ kind: "reconnecting", attempt: 1, nextInMs: 2000 });
  });

  it("retries when there is no status at all and the browser is online", () => {
    expect(afterFailure(null, 0, true).kind).toBe("reconnecting");
  });

  it("retries when offline, because offline is transient by definition", () => {
    const s = afterFailure(null, 2, false);
    expect(s.kind).toBe("reconnecting");
    if (s.kind === "reconnecting") expect(s.nextInMs).toBe(4000);
  });

  it("retries rather than closing when the browser is offline, because a status learned offline is untrusted", () => {
    // A 404 seen while `navigator.onLine` is false is far more likely a captive portal or a proxy
    // error page than the server's own answer. Closing on it would tell the user their session is
    // gone when it is not, which is the worse of the two errors: a retry costs one second, a wrong
    // "your session is gone" costs the user their confidence in the app.
    expect(afterFailure(404, 1, false).kind).toBe("reconnecting");
  });
});

describe("transitions", () => {
  it("opens to live", () => {
    expect(afterOpen()).toEqual({ kind: "live" });
  });

  it("a manual retry resets the attempt counter, so the second click is not punished", () => {
    const failed = afterFailure(503, 3, true);
    expect(failed.kind).toBe("reconnecting");
    expect(afterRetry()).toEqual({ kind: "connecting" });
  });

  it("switching sessions knows nothing about the new one", () => {
    expect(afterSwitch()).toEqual({ kind: "connecting" });
  });
});

describe("predicates", () => {
  const states: StreamState[] = [
    IDLE, { kind: "connecting" }, { kind: "live" },
    { kind: "reconnecting", attempt: 1, nextInMs: 1000 }, { kind: "closed", reason: "not-found" },
  ];

  it("isLive is true for exactly one state", () => {
    expect(states.filter(isLive)).toEqual([{ kind: "live" }]);
  });

  it("isRecovering distinguishes 'still trying' from 'gave up'", () => {
    expect(states.filter(isRecovering).map((s) => s.kind)).toEqual(["connecting", "reconnecting"]);
  });
});

describe("describe: the only place a stream state becomes words", () => {
  it("says nothing for idle and live, because a healthy stream needs no announcement", () => {
    expect(describeState(IDLE).word).toBe("");
    expect(describeState({ kind: "live" }).word).toBe("");
  });

  it("offers no action while connecting: it resolves in milliseconds", () => {
    expect(describeState({ kind: "connecting" }).action).toBe("none");
  });

  it("offers exactly one action while reconnecting", () => {
    const d = describeState({ kind: "reconnecting", attempt: 1, nextInMs: 2000 });
    expect(d.action).toBe("retry");
    expect(d.word).toBe("reconnecting…");
    expect(d.urgent).toBe(false);
  });

  it("treats closed as urgent, with two actions, because work may be gone", () => {
    const d = describeState({ kind: "closed", reason: "not-found" });
    expect(d.urgent).toBe(true);
    expect(d.action).toBe("retry-or-new");
    expect(d.detail).toMatch(/archived|restarted/);
  });

  it("gives each closed reason its own sentence, because they need different next steps", () => {
    const reasons = ["not-found", "cursor-ahead", "rejected", "offline"] as const;
    const details = reasons.map((r) => describeState({ kind: "closed", reason: r }).detail);
    expect(new Set(details).size).toBe(reasons.length);
  });
});
