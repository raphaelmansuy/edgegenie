/** What to offer after an answer. Pure.
 *
 * Genie Code ends a turn with the next sensible step so the user is never staring at a blinking
 * cursor. The rule here is that a follow-up must be **true of this turn**: "Run it" is offered only if
 * the notebook was written and not run; "Explain these numbers" only if a query returned some. A fixed
 * menu of generic prompts is marketing copy; derived ones are help.
 *
 * Nothing is offered after a turn that did not finish: a blocked or failed turn has its own actions
 * (Retry, Change model), and a chip beside them would be a third place to look.
 */
import type { Turn } from "./events";

export interface FollowUp { label: string; prompt: string }

const WROTE = /write_(notebook|file)/;
const RAN_NOTEBOOK = /run_notebook/;
const SQL = /(run_sql|sql|query)/;

const ok = (t: Turn, re: RegExp) => t.tools.some((c) => re.test(c.name) && c.status === "completed");
const failed = (t: Turn) => t.tools.some((c) => c.status === "error");

export function followUps(turn: Turn | undefined | null, max = 3): FollowUp[] {
  if (!turn || turn.status !== "completed" || !turn.answer.trim()) return [];
  const out: FollowUp[] = [];
  const add = (label: string, prompt: string) => { if (!out.some((o) => o.label === label)) out.push({ label, prompt }); };

  const wrote = ok(turn, WROTE);
  const ran = ok(turn, RAN_NOTEBOOK);
  const hasRows = turn.tools.some((c) => c.table && c.table.rows.length > 0);

  if (failed(turn)) {
    add("Find the cause and fix it", "Something failed in your last turn. Find the cause, fix it, and show the evidence that it works now.");
  }
  if (wrote && !ran) add("Run it and show the result", "Run the notebook you just wrote and show me the result.");
  if (wrote) {
    add("Explain what it does", "Explain the notebook you just wrote, cell by cell, in plain English. Do not change anything.");
    add("Review it for bugs", "Review the notebook you just wrote for bugs. Check each table and column name against the real schema.");
  }
  if (hasRows) {
    add("Chart these results", "Chart the result you just showed me, with one sentence saying what the chart shows.");
    if (!wrote) add("Turn this into a notebook", "Turn the query you just ran into a notebook with a short markdown summary.");
    add("Explain these numbers", "Explain what the numbers you just showed mean, and point out anything surprising.");
  } else if (turn.tools.some((c) => SQL.test(c.name)) && !wrote) {
    add("Show me the SQL", "Show me the exact SQL you ran, and what each clause is for.");
  }
  if (wrote) add("Add a chart", "Add a cell that charts the result, with a markdown cell explaining it.");
  if (out.length === 0) {
    add("Summarise what you did", "Summarise what you did in this conversation in five lines or fewer.");
    add("What should I check next?", "What should I double-check next, and why?");
  }
  return out.slice(0, max);
}
