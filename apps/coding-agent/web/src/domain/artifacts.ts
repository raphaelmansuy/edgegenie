/** What a conversation has made or opened, in the order it happened. Pure.
 *
 * The centre of the app is the work. While the agent works in the dock and nothing is open, the centre
 * used to show the first-run screen ("What should we build today?"), as if nothing had started. This is
 * the list that lets it say what exists so far: each notebook or file the agent wrote (or read), once,
 * with whether it wrote it.
 */
import { touched, type Doc } from "./docs";

export interface Artifact { doc: Doc; wrote: boolean }

export function artifactsOf(turns: { tools: { name: string; args?: string; summary?: string; status: string }[] }[]): Artifact[] {
  const byRef = new Map<string, Artifact>();
  for (const turn of turns) for (const call of turn.tools) {
    if (call.status !== "completed") continue;
    const hit = touched(call.name, call.args, call.summary);
    if (!hit) continue;
    const seen = byRef.get(hit.doc.ref);
    if (seen) seen.wrote ||= hit.mutates;
    else byRef.set(hit.doc.ref, { doc: hit.doc, wrote: hit.mutates });
  }
  // What it wrote first: the point of looking is the thing that was made, not what it read on the way.
  return [...byRef.values()].sort((a, b) => Number(b.wrote) - Number(a.wrote));
}

/**
 * Did the agent write something OTHER than the document on screen?
 *
 * The observed failure: a notebook at `/Repos/.../demo/x` was open, the user said "add a new KPI",
 * and the agent — correctly, because that path is outside the session's write folder — wrote
 * `agent_scratch/x_with_kpi` instead. The write succeeded and the dock said so, but the centre was
 * unchanged and silent, which reads exactly like "the agent did nothing". Silence is the bug: the
 * screen must say where the work went and offer to show it.
 *
 * Returns the documents written by the most recent turn that wrote anything, when none of them is
 * the open one. Empty when the open document was written (the editor adopts that itself), or when
 * nothing was written.
 */
export function wroteElsewhere(
  turns: { id?: string; tools: { name: string; args?: string; summary?: string; status: string }[] }[],
  openId: string | null,
): { docs: Doc[]; at: string } | null {
  for (let i = turns.length - 1; i >= 0; i--) {
    const written = new Map<string, Doc>();
    for (const call of turns[i].tools) {
      if (call.status !== "completed") continue;
      const hit = touched(call.name, call.args, call.summary);
      if (hit?.mutates) written.set(hit.doc.id, hit.doc);
    }
    if (written.size === 0) continue;                 // nothing written this turn: keep looking back
    if (openId && written.has(openId)) return null;   // the open document was written: not "elsewhere"
    // `at` identifies the turn, so dismissing the banner dismisses THIS write and a later one is
    // news again — rather than a file name that stays silent for the rest of the session.
    return { docs: [...written.values()], at: `${turns[i].id ?? i}` };
  }
  return null;
}
