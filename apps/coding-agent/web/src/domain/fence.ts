/** The client's view of the write fence. A **preview** of a decision the server makes.
 *
 * Spec 003 WR-2 is explicit about what this is for: the fence has to explain itself *before* the
 * user types, because "this path is outside your working folder, saving will ask" is useful at the
 * moment of typing and useless as a 403 after a pause. It is not authority. If this ever disagrees
 * with the server, the server wins and that disagreement is a defect.
 *
 * To keep that honest, this file mirrors `api/domain/scope.py::check_path` — a short function — and
 * `fence.test.ts` runs a corpus of paths through both this and the server's rules, so a drift fails
 * a test rather than surprising a user.
 */

export type Verdict = "allow" | "ask" | "deny";

export interface FenceDecision {
  verdict: Verdict;
  /** The path the decision is about, normalised. */
  target: string;
  /** A sentence for the UI: why, in the user's terms. Empty when allowed. */
  reason: string;
}

/** Normalise the way the server does: forward slashes, collapsed, quotes trimmed. */
export function normalise(path: string): string {
  let p = path.replace(/\\/g, "/").replace(/^[`"']+|[`"']+$/g, "").trim();
  while (p.includes("//")) p = p.replace(/\/\//g, "/");
  return p;
}

/** Is `path` inside `folder`? Traversal is refused outright, as on the server. */
export function isInside(path: string, folder: string): boolean {
  const p = normalise(path);
  if (p.split("/").includes("..")) return false;
  const f = normalise(folder);
  return p.startsWith(f) && p.length > f.length - 1;
}

/** Mirrors `check_path`. Folders end with a slash on both sides, because a prefix test without one
 *  would treat `/agent_scratch_evil` as inside `/agent_scratch`. */
export function checkPath(folder: string, path: string): FenceDecision {
  const target = normalise(path);
  if (target.split("/").includes("..")) {
    return { verdict: "deny", target, reason: "a path cannot contain .." };
  }
  if (!folder) {
    return { verdict: "ask", target, reason: "open a session to have a writable folder" };
  }
  if (isInside(target, folder)) return { verdict: "allow", target, reason: "" };
  return { verdict: "ask", target, reason: `outside ${folder}` };
}

/** One line for the editor bar. Text, not colour alone (UX-5). */
export function describeFence(d: FenceDecision, readOnly: boolean): { label: string; tone: "ok" | "warn" | "off" } {
  if (readOnly) return { label: "read-only", tone: "off" };
  if (d.verdict === "allow") return { label: "in your folder", tone: "ok" };
  if (d.verdict === "deny") return { label: "cannot write here", tone: "off" };
  /* With no session there IS no folder, so "outside your folder" would name something that does not
     exist. The chip has to describe the actual situation, because it is the first and often only
     thing a user reads before typing. */
  if (!d.reason || /no session|open a session/i.test(d.reason)) return { label: "Review on save", tone: "off" };
  return { label: "outside your folder — will ask", tone: "warn" };
}
