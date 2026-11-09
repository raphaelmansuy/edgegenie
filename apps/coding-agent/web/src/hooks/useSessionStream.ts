/** useSessionStream: SSE with replay. The reducer owns all state changes.
 *
 * Two things here are load-bearing and were each a real bug:
 *  - switching session must reset the view (a new session used to show the old transcript);
 *  - the stream effect must NOT depend on anything that changes when state changes, or it
 *    reconnects in a loop and the transcript never renders.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import { emptySession, newTurn, PENDING, reduce, type AgentEvent, type Attachment, type SessionView, type Turn } from "../domain/events";

/** How long streamed events are collected before one state update. One long answer arrives as
 *  hundreds of deltas; rendering each one re-parses the whole markdown tree and froze the tab. */
const BATCH_MS = 40;

export type Conn = "idle" | "connecting" | "live" | "reconnecting" | "lost";

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
    execution: d?.execution,
    // Hydration is what a reload reads. Without the turns it is a session with no history, and every chip
    // the user sent is gone from the screen while the server still has it.
    turns: Array.isArray(d?.turns) ? (d.turns as unknown as Record<string, unknown>[]).map(adoptTurn) : [],
  };
}

export function useSessionStream(sessionId: string | null) {
  const [session, setSession] = useState<SessionView>(() => emptySession());
  const [conn, setConn] = useState<Conn>("idle");
  const [error, setError] = useState<string | null>(null);
  const seq = useRef(0);

  // 1) reset + hydrate when the session changes
  useEffect(() => {
    if (!sessionId) {
      setSession(emptySession());
      setConn("idle");
      return;
    }
    setSession(hydrate(sessionId, undefined));
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

    const flush = () => {
      timer = null;
      if (queued.length === 0) return;
      const batch = queued;
      queued = [];
      setSession((s) => batch.reduce(reduce, s));
    };

    const open = () => {
      source?.close();
      source = new EventSource(`/api/sessions/${sessionId}/stream?after=${seq.current}`);
      setConn((c) => (c === "live" ? c : "connecting"));
      source.onopen = () => { if (!stopped) setConn("live"); };
      source.onerror = () => { if (!stopped) setConn(navigator.onLine ? "reconnecting" : "lost"); };
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
      if (document.visibilityState === "visible" && source?.readyState === EventSource.CLOSED) open();
    };
    const onOnline = () => { if (!stopped) open(); };
    const onOffline = () => setConn("lost");
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      stopped = true;
      if (timer !== null) window.clearTimeout(timer);
      queued = [];
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
      document.removeEventListener("visibilitychange", onVisible);
      source?.close();
    };
  }, [sessionId]);

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

  return { session, conn, error, send, stop, restore, setSession };
}
