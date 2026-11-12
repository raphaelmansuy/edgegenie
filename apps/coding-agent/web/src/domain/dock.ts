/** The assistant dock's state and the words it uses. Pure: one function, four states.
 *
 * Four states, not five. Every other condition is a detail of one of them — a fifth state is how a
 * dock acquires an unreachable screen (spec 006 AD-7, 04 §the state machine).
 *
 * The precedence is load-bearing and asserted: **an approval outranks streaming.** A run waiting for
 * a human is not making progress, and showing "streaming" would hide the one thing the user must do.
 */
import type { DocKind } from "./docs";
import type { Focus } from "./focus";
import { ACTIONS, type Action } from "./docs";

export type DockState = "empty" | "streaming" | "asking" | "failed";

export interface DockInput {
  /** Is a session loaded at all? `false` shows the start-from-nothing state. */
  hasSession: boolean;
  /** The session's status string, as the server reports it. */
  status: string;
  /** The last turn, when there is one. */
  last?: { status: string } | null;
  /** Approvals with no outcome yet. */
  pendingApprovals: number;
}

export function dockState(input: DockInput): DockState {
  if (!input.hasSession) return "empty";
  // An approval is a decision *about* a turn, so it is checked before the turn's own status: a turn
  // blocked on a human is not "running" from the user's point of view.
  if (input.pendingApprovals > 0) return "asking";
  const last = input.last?.status;
  if (last === "failed" || input.status === "failed") return "failed";
  if (input.status === "streaming" || last === "running" || last === "queued" || last === "auditing") {
    return "streaming";
  }
  return "empty";
}

/** The header line. A state names what it is, in the user's language.
 *
 * `hasTurns` matters: a dock that says "new conversation" while a finished turn is on screen is
 * simply wrong, and the header is the one place a user checks to see what this panel is doing.
 */
export function dockTitle(state: DockState, hasSession: boolean, hasTurns = false): string {
  switch (state) {
    case "asking": return "needs your decision";
    case "failed": return "that turn failed";
    case "streaming": return "working";
    default: return hasSession && hasTurns ? "conversation" : "new conversation";
  }
}

/** The word next to the state glyph. Short on purpose: the header's width belongs to the binding. */
export function dockStateWord(state: DockState, hasSession: boolean, hasTurns = false, lastStatus?: string): string {
  switch (state) {
    case "asking": return "decide";
    case "failed": return "failed";
    case "streaming": return "working";
    default:
      // Four states stay four; the last turn's outcome only changes the word. "ready" after a blocked
      // turn told the user the one thing that was not true.
      if (lastStatus === "blocked") return "blocked";
      if (lastStatus === "interrupted") return "interrupted";
      if (lastStatus === "cancelled") return "stopped";
      return hasSession && hasTurns ? "ready" : "new";
  }
}

export interface Suggestion { label: string; prompt: string; action?: Action }

/** Three things to do, derived from what is open. Never marketing copy (spec 006 04 §starting). */
export function suggestionsFor(focus: Focus): Suggestion[] {
  const doc: { kind: DocKind; name: string } | null = focus.doc;
  if (!doc) {
    return [
      { label: "What can you do here?", prompt: "What can you do in this workspace? Be concrete and brief." },
      { label: "Open something from Files", prompt: "Summarise what I have in my home folder." },
      { label: "Start a scratch notebook", prompt: "Create a notebook in my working folder that I can experiment in." },
    ];
  }
  if (doc.kind === "query" || doc.kind === "query-draft") return [
    { label: "Explain this query", prompt: "Explain the attached SQL query, its grain, joins, parameters and assumptions. Do not execute or change it." },
    { label: "Review the SQL", prompt: "Review the attached SQL for correctness. Describe real table schemas before making claims about columns or joins. Propose changes only; do not save or execute." },
    { label: "Suggest an optimization", prompt: "Suggest a SQL optimization, state its assumptions and return a SQL code block for review. Do not execute or save it." },
  ];
  const n = focus.cell;
  if (doc.kind === "table") {
    return [
      { label: "Profile this table", prompt: ACTIONS.profile.prompt, action: "profile" },
      { label: "Suggest three queries", prompt: ACTIONS.query.prompt, action: "query" },
      { label: "Document the columns", prompt: `Document the columns of the attached table based on the real values you observe.`, action: "profile" },
    ];
  }
  if (n) {
    return [
      { label: `Explain cell ${n}`, prompt: `Explain what cell ${n} of the attached notebook does, in plain English. Do not change anything.`, action: "explain" },
      { label: `Fix cell ${n}`, prompt: `Find the bug in cell ${n} of the attached notebook. Check every table and column name with describe_table first. Write a corrected copy in your working folder and show the evidence it runs.`, action: "fix" },
      { label: `Add a null guard to cell ${n}`, prompt: `Add a null guard to cell ${n} of the attached notebook. Write the change in your working folder, never to the original.` },
    ];
  }
  if (doc.kind === "file") {
    return [
      { label: "Explain this file", prompt: ACTIONS.explain.prompt, action: "explain" },
      { label: "Find a bug in this file", prompt: `Review the attached file for bugs. Check every name it uses, then write a corrected copy in your working folder and run it.`, action: "fix" },
      { label: "Rewrite it in my folder", prompt: `Rewrite the attached file in my working folder with the same behaviour and clearer structure. Leave the original alone.` },
    ];
  }
  /* A project and an app are infrastructure, so the suggestions are about their state rather than
   * about reading code. Showing "Explain this notebook" over a Lakebase project is the defect the S2
   * screenshot found: a plausible button that is wrong about the subject (spec 013 [UI-3], [UI-4]).
   *
   * Spec 014 adds three more kinds, and every one of them was a chance to repeat that defect — which is
   * why `[UI-6]` asserts it in a test rather than trusting the next author to notice. */
  if (doc.kind === "lakebase") {
    return [
      { label: `What is in ${doc.name}?`, prompt: `List the tables in the Lakebase project ${doc.name} with their row counts, and name the branch you read. Quote the numbers.` },
      { label: "Is it healthy?", prompt: `Check the Lakebase project ${doc.name}: are its compute and branches ready, is anything suspended, and is the autoscaling range legal? Report what you observe, not what you assume.` },
      { label: "Add a table", prompt: `Create a new table in the Lakebase project ${doc.name} on a branch for this session (never on production), insert a few seed rows, and show me the count you read back.` },
    ];
  }
  if (doc.kind === "app") {
    return [
      { label: `Is ${doc.name} working?`, prompt: `Run a health check on the Databricks App ${doc.name}: report the status code and the time it took. If it is failing, read its logs and tell me the first error.` },
      { label: "What does it read?", prompt: `Describe the Databricks App ${doc.name}: its resources, which Lakebase branch it connects to, and which tables it reads.` },
      { label: "Fix it", prompt: `The Databricks App ${doc.name} is not working. Read its logs at its /logz URL, find the cause, fix the source in my working folder, redeploy, and prove it answers.` },
    ];
  }
  if (doc.kind === "job") {
    return [
      { label: "Why did the last run fail?", prompt: `Read the last run of the job ${doc.name}. Name the task that failed, quote its error, and check the tables that task reads against their real columns with describe_table. Then tell me whether the code or the data is wrong. Do not change anything until you have said which.` },
      { label: "What does this job write?", prompt: `Describe the job ${doc.name}: its tasks in order, the notebook or pipeline each one runs, and the tables each task writes. Check every table name with describe_table before you name it.` },
      { label: "Add a task and re-run it", prompt: `Add a task to the job ${doc.name} that checks the output row count of its last task and fails if it is zero. Re-read the job first so you keep its existing tasks and dependencies, then run it and show me the new task's result.` },
    ];
  }
  if (doc.kind === "run") {
    return [
      { label: "What failed here?", prompt: `Read run ${doc.name}. Name the task that failed, quote its error and the tail of its trace, and say which table or column the error is about.` },
      { label: "Which task is slow?", prompt: `Read run ${doc.name} and compare each task's duration. Name the slowest, and read its notebook to say what it does that could be slow. Quote the durations.` },
      { label: "Make this job more reliable", prompt: `Run ${doc.name} failed or was slow. Read the job's tasks, then write a corrected copy of the failing notebook in my working folder with a retry-safe write and a row-count check, and tell me what you changed.` },
    ];
  }
  if (doc.kind === "pipeline") {
    return [
      { label: "Did the last update work?", prompt: `Read the pipeline ${doc.name}: its last update's state, how many flows it has, and any failed expectation. Quote the update id and the counts.` },
      { label: "What does it build?", prompt: `Describe the pipeline ${doc.name}: each library file, the tables it materialises, and the expectations it declares. Read the files; do not guess from the name.` },
      { label: "The last update failed", prompt: `The pipeline ${doc.name}: read its recent ERROR events, find the cause in the library files, fix the source in my working folder, validate with validate_only, then start an update and show me its result.` },
    ];
  }
  return [
    { label: "Explain this notebook", prompt: ACTIONS.explain.prompt, action: "explain" },
    { label: "Find the bug in this notebook", prompt: `Review the attached notebook for bugs. Check every table and column name with describe_table before judging it. Write a corrected copy in your working folder, run it, and show the evidence.`, action: "fix" },
    { label: "Document it in my folder", prompt: ACTIONS.document.prompt, action: "document" },
  ];
}

/** Announcing a streamed answer: once, when a turn ends. Never per token. */
export function announce(previous: { turns: number; running: boolean }, next: { turns: number; running: boolean }): string {
  if (previous.running && !next.running && next.turns >= previous.turns) return "the answer is ready";
  if (!previous.running && next.running) return "the agent is working";
  return "";
}

/** The dock's width bounds live in layout.ts; this is only the label for its handle. */
export const DOCK_LABEL = "Resize the assistant";
