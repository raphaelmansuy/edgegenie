/** useSessionStream: SSE with replay. The reducer owns all state changes; `domain/stream` owns the
 * decision of what state comes next.
 *
 * Four things here are load-bearing and each was a real bug:
 *  - switching session must reset the view (a new session used to show the old transcript);
 *  - the stream effect must NOT depend on anything that changes when state changes, or it
 *    reconnects in a loop and the transcript never renders;
 *  - the replay cursor resets on every session change (see 2, below), or a reload shows nothing;
 *  - a refusal must be NAMED. `EventSource` retries only a connection that dropped after a 200; a
 *    non-200 is final, and the old code rendered that final failure as "reconnecting…" forever while
 *    every control gated on `conn === "live"` was disabled. `domain/stream.ts` is the correction and
 *    `retry()` is the manual way out (specs/012-ux-improve 01, 02 §F2).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import { emptySession, newTurn, PENDING, reduce, type AgentEvent, type Attachment, type SessionView, type Turn } from "../domain/events";
import { afterFailure, afterOpen, afterRetry, afterSwitch, IDLE, type StreamState } from "../domain/stream";

/** How long streamed events are collected before one state update. One long answer arrives as
 *  hundreds of deltas; rendering each one re-parses the whole markdown tree and froze the tab. */
const BATCH_MS = 40;

/** The probe that learns WHY a stream failed. `EventSource` does not expose the HTTP status, so a
 *  failed open is followed by one `fetch` to the same URL to learn it. Without this, a 404 and a 503
 *  are indistinguishable — which is precisely the defect (specs/012 02 §F2). */
async function probeStatus(url: string): Promise<number | null> {
  try {
    const r = await fetch(url, { method: "GET", headers: { Accept: "text/event-stream" }, cache: "no-store" });
    // Read a byte and hang up: we want the status, not the stream body.
    void r.body?.cancel().catch(() => {});
    return r.status;
  } catch {
    return null;
  }
}

/** Adapt one server turn into the client's `Turn`.
 *
 *  The server's detail route has always returned the turns; this function did not carry them, so a reload
 *  showed an empty transcript for a session that had four of them (measured: 0 turns after a reload, 2
 *  before). The attachment list is why it matters now — a turn's chips are HISTORY, rendered from what was
 *  sent, and they only come from here (spec 009 [AFC-8], [D6]).
 *
 *  Built from `newTurn` rather than object-literal: a `Turn` has nine fields the reducer reads (`tools`,
 *  `evidence`, `thought`, `answer` …), and spelling them by hand crashed the page with
 *  "Cannot read properties of undefined (reading 'length')" the moment a reload found a turn. Taking the
 *  defaults from the one constructor that already knows them cannot go stale.
 */
function adoptTurn(t: Record<string, unknown>): Turn {
  const base = newTurn(
    String(t.id ?? ""),
    Number(t.index ?? 0),
    String(t.prompt ?? ""),
    String(t.model ?? ""),
  );
  return {
    ...base,
    status: (t.status as Turn["status"]) ?? "completed",
    // Absent on an older session, which is not an error: the turn simply had nothing attached.
    attachments: Array.isArray(t.attachments) ? (t.attachments as Attachment[]) : [],
    usage: (t.usage as Turn["usage"]) ?? base.usage,
  };
}

/** The detail route and the stream both deliver the same turn. The stream has the answer. */
function mergeTurns(streamed: Turn[], server: Turn[]): Turn[] {
  const byId = new Map(streamed.map((t) => [t.id, t]));
  const ids = new Set(server.map((t) => t.id));
  const merged = server.map((t) => {
    const live = byId.get(t.id);
    if (!live) return t;
    const painted = live.answer || live.thought || live.tools.length > 0;
    return {
      ...t,
      answer: live.answer,
      thought: live.thought,
      tools: live.tools.length ? live.tools : t.tools,
      evidence: live.evidence.length ? live.evidence : t.evidence,
      plan: live.plan ?? t.plan,
      seconds: live.seconds ?? t.seconds,
      blocked: live.blocked ?? t.blocked,
      auditPasses: live.auditPasses,
      usage: live.usage ?? t.usage,
      status: painted ? live.status : t.status,
    };
  });
  for (const t of streamed) {
    if (!ids.has(t.id) && !t.id.startsWith(PENDING)) merged.push(t);
  }
  return merged;
}

function hydrate(id: string, d: Partial<SessionView> | undefined): SessionView {
  const base = emptySession(id);
  return {
    ...base,
    id: d?.id ?? base.id,
    title: d?.title ?? base.title,
    folder: d?.folder ?? base.folder,
    schema: d?.schema ?? base.schema,
    model: d?.model ?? base.model,
    status: d?.status ?? base.status,
    tools: d?.tools ?? 0,
    agent: d?.agent ?? "",
    agentVersion: d?.agentVersion ?? "",
    approvals: d?.approvals ?? [],
    scope: d?.scope,
    requiresResume: d?.requiresResume,
    resumeReason: d?.resumeReason,
    writeMode: d?.writeMode,
    execution: d?.execution,
    sqlChanges: d?.sqlChanges,
    // Hydration is what a reload reads. Without the turns it is a session with no history, and every chip
    // the user sent is gone from the screen while the server still has it.
    turns: Array.isArray(d?.turns) ? (d.turns as unknown as Record<string, unknown>[]).map(adoptTurn) : [],
  };
}

export function useSessionStream(sessionId: string | null) {
  const [session, setSession] = useState<SessionView>(() => emptySession());
  const [conn, setConn] = useState<StreamState>(IDLE);
  const [error, setError] = useState<string | null>(null);
  const seq = useRef(0);
  /** Bumped by `retry()` to re-run the stream effect without changing any state it depends on. */
  const [retryNonce, setRetryNonce] = useState(0);

  // 1) reset + hydrate when the session changes
  useEffect(() => {
    if (!sessionId) {
      setSession(emptySession());
      setConn(IDLE);
      return;
    }
    setSession(hydrate(sessionId, undefined));
    setConn(afterSwitch());
    let live = true;
    api.session(sessionId)
      .then((d) => {
        if (!live) return;
        setSession((prev) => {
          const detail = d as Partial<SessionView>;
          const rawTurns = (d as { turns?: unknown }).turns;
          // `hydrate` reads `turns` and would replace the streamed answer with the detail's copy,
          // which has the prompt and not the answer. Keep what the stream already painted.
          const next = hydrate(sessionId, { ...prev, ...detail, turns: undefined });
          // A slow metadata response must not overwrite newer permission/lifecycle events.
          if (seq.current > 0) {
            next.status = prev.status;
            next.requiresResume = prev.requiresResume;
            next.approvals = prev.approvals;
          }
          const server = Array.isArray(rawTurns)
            ? (rawTurns as Record<string, unknown>[]).map(adoptTurn) : [];
          if (prev.id !== sessionId || prev.turns.length === 0) return { ...next, turns: server };
          return { ...next, turns: mergeTurns(prev.turns, server) };
        });
      })
      .catch((e: ApiError) => { if (live) setError(e.message); });
    return () => { live = false; };
  }, [sessionId]);

  // 2) one EventSource per session, reconnecting with the last seen seq
  useEffect(() => {
    if (!sessionId) return;
    /* Always from the start. The view is rebuilt from nothing above, so the replay IS the transcript:
       a cursor kept across page loads (it used to live in localStorage) resumed past events this
       fresh view had never seen, and a reload, a second tab or a pasted session link showed an empty
       conversation. The cursor in this ref only serves reconnects within the page. */
    seq.current = 0;
    let source: EventSource | null = null;
    let stopped = false;
    let queued: AgentEvent[] = [];
    let timer: number | null = null;
    let retryTimer: number | null = null;
    /** Consecutive failures, for the backoff. Reset by a successful open and by a manual retry. */
    let attempt = 0;

    const flush = () => {
      timer = null;
      if (queued.length === 0) return;
      const batch = queued;
      queued = [];
      setSession((s) => batch.reduce(reduce, s));
    };

    const url = () => `/api/sessions/${sessionId}/stream?after=${seq.current}`;

    /** Everything that must be cancelled when the effect tears down. A leaked retry timer keeps a
     *  closed session's connection alive behind the user's back. */
    const clear = () => {
      if (timer !== null) { window.clearTimeout(timer); timer = null; }
      if (retryTimer !== null) { window.clearTimeout(retryTimer); retryTimer = null; }
    };

    const schedule = (state: StreamState) => {
      if (state.kind !== "reconnecting") return;
      if (retryTimer !== null) window.clearTimeout(retryTimer);
      retryTimer = window.setTimeout(() => { retryTimer = null; if (!stopped) open(); }, state.nextInMs);
    };

    const open = () => {
      source?.close();
      source = new EventSource(url());
      // Keep a live stream live: re-announcing "connecting" on every reconnect would flicker the
      // one indicator that is supposed to be quiet when everything is fine.
      setConn((c) => (c.kind === "live" ? c : { kind: "connecting" }));
      source.onopen = () => {
        if (stopped) return;
        attempt = 0;
        setConn(afterOpen());
      };
      source.onerror = () => {
        if (stopped) return;
        attempt += 1;
        /* The browser has already given up on a non-200 and will not retry it, so we must. First
           learn WHY, then let `domain/stream` decide: a 404 closes for good, a 503 retries. The probe
           is one request per failure, and it is the only way to tell the two apart — which is the
           whole defect (specs/012 02 §F2). */
        void probeStatus(url()).then((status) => {
          if (stopped) return;
          const next = afterFailure(status, attempt, navigator.onLine);
          setConn(next);
          if (next.kind === "reconnecting") schedule(next);
        });
      };
      source.onmessage = (m) => {
        let ev: AgentEvent;
        try { ev = JSON.parse(m.data); } catch { return; }
        if (typeof ev.seq === "number") {
          if (ev.seq <= seq.current) return;
          seq.current = ev.seq;
        }
        queued.push(ev);
        if (timer === null) timer = window.setTimeout(flush, BATCH_MS);
      };
    };
    open();

    const onVisible = () => {
      // A backgrounded tab's source may have been closed by the browser. Re-open only then, so
      // returning to a healthy tab does not reset the connection for nothing.
      if (document.visibilityState === "visible" && source?.readyState === EventSource.CLOSED) {
        attempt = 0;
        open();
      }
    };
    const onOnline = () => { if (!stopped) { attempt = 0; open(); } };
    // Offline is a retry, not a death: the backoff will carry it while the socket is gone, and the
    // `online` handler above resets the counter the moment there is a network again.
    const onOffline = () => {
      if (stopped) return;
      const next = afterFailure(null, Math.max(1, attempt), false);
      setConn(next);
      schedule(next);
    };
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      stopped = true;
      clear();
      queued = [];
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
      document.removeEventListener("visibilitychange", onVisible);
      source?.close();
    };
    /* `retryNonce` is in the dependency list on purpose: it is how `retry()` re-runs this effect
       without touching any state the effect reads, which is what keeps the reconnect-loop regression
       (see this file's header) from coming back. */
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, retryNonce]);

  const send = useCallback(async (text: string, attachments: Attachment[] = []) => {
    if (!sessionId) return;
    setError(null);
    // Show the user's message at once. Waiting for the server's echo made a slow start look like
    // nothing had been sent, and people sent the same request twice.
    const pending = `${PENDING}${Date.now()}`;
    setSession((s) => ({
      ...s, status: "streaming",
      turns: [...s.turns, { ...newTurn(pending, s.turns.length + 1, text, s.model), attachments, status: "running" }],
    }));
    try {
      await api.send(sessionId, text, `${sessionId}:${Date.now()}`, attachments);
    } catch (e) {
      setSession((s) => ({ ...s, status: "ready", turns: s.turns.filter((t) => t.id !== pending) }));
      setError(e instanceof ApiError ? e.message : "could not send");
      throw e;
    }
  }, [sessionId]);

  const stop = useCallback(async () => { if (sessionId) await api.cancel(sessionId); }, [sessionId]);

  const restore = useCallback(async () => {
    if (!sessionId) return;
    const result = await api.resume(sessionId);
    setSession((s) => ({ ...s, ...result }));
  }, [sessionId]);

  /** The user pressed Retry. Re-runs the stream effect from the current cursor with a fresh attempt
   *  counter, so a manual retry is not punished for the failures before it (specs/012 ST-3). */
  const retry = useCallback(() => {
    setConn(afterRetry());
    setRetryNonce((n) => n + 1);
  }, []);

  return { session, conn, error, send, stop, restore, retry, setSession };
}
