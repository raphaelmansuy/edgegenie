/** Keep an open document in step with the workspace.
 *
 * The agent's writes reach the screen through two layers, because either alone can miss one:
 *
 *   1. instant — a completed `write_*` tool event names the path (App.tsx bumps the document's `rev`);
 *   2. this — a cheap version check (`get-status`, no content) that runs
 *        · every POLL_MS while the agent is working,
 *        · once more shortly after a turn ends (the last write may have landed after the last event),
 *        · whenever the window regains focus (an edit made elsewhere: another tab, the Databricks UI).
 *
 * A changed version calls `stale()`, which reloads the document; the editor then adopts the change
 * and says which cells moved (EditorSurface). Failures are ignored on purpose: an overwrite is a
 * delete followed by an import, so the path is briefly absent, and the next tick sees it again.
 */
import { useCallback, useEffect, useRef } from "react";
import { api } from "../api/client";

export const POLL_MS = 2500;
export const SETTLE_MS = 700;

export function useFresh({ ref, known, live, stale }: {
  ref: string;
  /** The version this view was loaded at; null while it is still loading. */
  known: string | null;
  /** The agent is working: poll. */
  live: boolean;
  stale: () => void;
}): void {
  const knownRef = useRef(known);
  knownRef.current = known;
  const asked = useRef<string | null>(null);
  const flying = useRef(false);
  // A new version loaded: whatever was being asked about is now history.
  useEffect(() => { asked.current = null; }, [known]);

  const check = useCallback(async () => {
    if (flying.current || !knownRef.current) return;
    flying.current = true;
    try {
      const { version } = await api.version(ref);
      if (version && knownRef.current && version !== knownRef.current && version !== asked.current) {
        asked.current = version;     // one reload per new version, however many ticks see it
        stale();
      }
    } catch {
      /* see above */
    } finally {
      flying.current = false;
    }
  }, [ref, stale]);

  useEffect(() => {
    if (!live) return;
    const id = window.setInterval(() => void check(), POLL_MS);
    return () => window.clearInterval(id);
  }, [live, check]);

  const wasLive = useRef(live);
  useEffect(() => {
    const ended = wasLive.current && !live;
    wasLive.current = live;
    if (!ended) return;
    const id = window.setTimeout(() => void check(), SETTLE_MS);
    return () => window.clearTimeout(id);
  }, [live, check]);

  useEffect(() => {
    const on = () => { if (document.visibilityState === "visible") void check(); };
    window.addEventListener("focus", on);
    document.addEventListener("visibilitychange", on);
    return () => { window.removeEventListener("focus", on); document.removeEventListener("visibilitychange", on); };
  }, [check]);
}
