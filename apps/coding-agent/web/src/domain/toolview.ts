/** How a tool call reads in one line. Pure, no React.
 *
 * The raw arguments are JSON, and a row of `{"full_name": "samples.nyctaxi.trips"}` is noise in a
 * transcript. This picks out the one thing the call is about; the full arguments stay one click away.
 */

const ORDER = ["path", "full_name", "fullName", "id", "name", "table", "sql", "statement", "job_id",
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
  let start = 0;
  while (start <= answer.length) {
    let end = answer.indexOf("\n", start);
    if (end === -1) end = answer.length;
    if (isEvidenceHeading(answer, start, end)) return answer.slice(0, start).trimEnd();
    start = end + 1;
  }
  return answer;
}

const WORD = "evidence";
const isSpace = (c: string) => c === " " || c === "\t" || c === "\r" || c === "\f" || c === "\v" || c === "\u00a0";

/** One line is the heading when it is `#{0,4} **? EVIDENCE **?` and nothing else. Scanned by hand,
 *  one pass, no backtracking. The regex this replaces (`^\s*#{0,4}\s*\**\s*EVIDENCE\s*\**\s*$`) had
 *  adjacent `\s*` groups that match the same blanks, so a run of N blank lines cost O(N³): 500 blank
 *  lines took 65 seconds, and a streaming answer ran it on every render. That was the "Page
 *  Unresponsive" freeze. A model that pads its answer with blank lines is an ordinary failure. */
export function isEvidenceHeading(text: string, from: number, to: number): boolean {
  let i = from;
  const skipSpace = () => { while (i < to && isSpace(text[i])) i += 1; };
  const skipStars = () => { while (i < to && text[i] === "*") i += 1; };
  skipSpace();
  for (let hashes = 0; hashes < 4 && i < to && text[i] === "#"; hashes += 1) i += 1;
  skipSpace(); skipStars(); skipSpace();
  if (to - i < WORD.length || text.slice(i, i + WORD.length).toLowerCase() !== WORD) return false;
  i += WORD.length;
  skipSpace(); skipStars(); skipSpace();
  if (text[i] === ":") { i += 1; skipSpace(); }
  return i === to;
}

const FRIENDLY: Record<string, string> = {
  describe_table: "looked at the table", list_tables: "listed tables", run_sql: "ran SQL",
  write_notebook: "wrote a notebook", run_notebook: "ran a notebook", read_notebook: "read a notebook",
  grep_notebook: "searched a notebook", create_job: "created a job", run_job: "ran a job",
  write_file: "wrote a file", lakebase_create: "created a database", skill: "read a skill",
};

/** A tool's name as a past-tense phrase: "dbxnb_dbx_write_notebook" → "wrote a notebook". */
export function toolLabel(name: string): string {
  const plain = name.replace(/^dbxnb_/, "").replace(/^dbx_/, "").replace(/^dbx/, "").replace(/^db_dbx_/, "");
  return FRIENDLY[plain] ?? plain.replace(/_/g, " ");
}
