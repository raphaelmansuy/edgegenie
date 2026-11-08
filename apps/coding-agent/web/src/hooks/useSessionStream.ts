/** useSessionStream: SSE with replay. The reducer owns all state changes.
 *
 * Two things here are load-bearing and were each a real bug:
 *  - switching session must reset the view (a new session used to show the old transcript);
 *  - the stream effect must NOT depend on anything that changes when state changes, or it
 *    reconnects in a loop and the transcript never renders.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import { emptySession, newTurn, PENDING, reduce, type AgentEvent, type Attachment, type SessionView } from "../domain/events";

/** How long streamed events are collected before one state update. One long answer arrives as
 *  hundreds of deltas; rendering each one re-parses the whole markdown tree and froze the tab. */
const BATCH_MS = 40;

export type Conn = "idle" | "connecting" | "live" | "reconnecting" | "lost";

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
    scope: d?.scope,
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
      .then((d) => { if (live) setSession((prev) => hydrate(sessionId, { ...prev, ...(d as Partial<SessionView>) })); })
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
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      stopped = true;
      if (timer !== null) window.clearTimeout(timer);
      queued = [];
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

  return { session, conn, error, send, stop, setSession };
}
