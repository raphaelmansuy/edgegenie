/** How a tool call reads in one line. Pure, no React.
 *
 * The raw arguments are JSON, and a row of `{"full_name": "samples.nyctaxi.trips"}` is noise in a
 * transcript. This picks out the one thing the call is about; the full arguments stay one click away.
 */

const ORDER = ["path", "full_name", "fullName", "name", "table", "sql", "statement", "job_id",
  "run_id", "instance", "pattern", "query", "needle", "todos", "cells"];

/** The subject of a call, or "" when the arguments say nothing useful. */
export function subject(args?: string, limit = 90): string {
  if (!args) return "";
  let parsed: unknown;
  try { parsed = JSON.parse(args); } catch { return squash(args, limit); }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return squash(args, limit);
  const obj = parsed as Record<string, unknown>;
  for (const key of ORDER) {
    const v = obj[key];
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) return `${v.length} item${v.length === 1 ? "" : "s"}`;
    if (typeof v === "object") continue;
    const text = String(v);
    if (text === "{}" || text === "[]") continue;
    return squash(text, limit);
  }
  // Nothing recognisable and every value empty: the arguments say nothing worth a line.
  const useful = Object.values(obj).some((v) => v !== undefined && v !== null && v !== "" && v !== "{}" && v !== "[]");
  return useful ? squash(JSON.stringify(obj), limit) : "";
}

const squash = (s: string, limit: number) => {
  const one = s.replace(/\s+/g, " ").trim();
  return one.length > limit ? `${one.slice(0, limit - 1)}…` : one;
};

/** The EVIDENCE table the agent is asked to append is shown as the Evidence panel, not twice. */
export function stripEvidence(answer: string): string {
  if (!answer) return answer;
  const at = answer.search(/^\s*#{0,4}\s*\**\s*EVIDENCE\s*\**\s*$/im);
  return at === -1 ? answer : answer.slice(0, at).trimEnd();
}
