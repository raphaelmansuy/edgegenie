/** The state vocabulary of a job run, a pipeline and its updates. Pure: no React, no fetch.
 *
 *  Mirrored from `api/domain/jobs.py`, and held to `jobs-table.json` by this side's test and by
 *  `tests/test_jobs_domain.py` on the other. A word changed on one side alone fails one test that names
 *  the row (spec 014 [UI-8], [PIPE-5]).
 *
 *  The rule this module exists to enforce, from 013's [RB-12]: **the field that is convenient is never the
 *  field that is honest.** A run carries `life_cycle_state` always and `result_state` only when terminal;
 *  a pipeline is `IDLE` both when it has never run and when its last update failed. So the word comes from
 *  a function over the whole payload, never from a property access at a call site.
 */

export type Tone = "good" | "busy" | "bad" | "quiet";

/** Life cycle states in which a run is doing something. `BLOCKED` and `WAITING_FOR_RETRY` are included
 *  deliberately: a run waiting on a dependency still holds a slot the user may want back. */
export const ACTIVE = new Set([
  "PENDING", "QUEUED", "RUNNING", "TERMINATING", "BLOCKED", "WAITING_FOR_RETRY",
]);

/** States after which nothing changes: a Repair becomes possible and a poll can stop. */
export const TERMINAL = new Set(["TERMINATED", "SKIPPED", "INTERNAL_ERROR"]);

/** Results that mean the work did not happen. `SUCCESS_WITH_FAILURES` is here on purpose: a job whose
 *  child runs failed is not a success for someone reading a dashboard. */
export const FAILED_RESULTS = new Set([
  "FAILED", "TIMEDOUT", "CANCELED", "MAXIMUM_CONCURRENT_RUNS_REACHED",
  "UPSTREAM_CANCELED", "UPSTREAM_FAILED", "EXCLUDED", "DISABLED", "SUCCESS_WITH_FAILURES",
]);

/** An update in progress, for which Stop belongs on screen. */
export const ACTIVE_UPDATE = new Set([
  "QUEUED", "WAITING_FOR_RESOURCES", "INITIALIZING", "RESETTING", "CREATING_FLOW", "RUNNING",
]);

export const RUN_WORDS: Record<string, string> = {
  SUCCESS: "succeeded",
  FAILED: "failed",
  TIMEDOUT: "timed out",
  CANCELED: "canceled",
  UPSTREAM_FAILED: "upstream failed",
  UPSTREAM_CANCELED: "upstream canceled",
  MAXIMUM_CONCURRENT_RUNS_REACHED: "busy",
  SUCCESS_WITH_FAILURES: "succeeded with failures",
  EXCLUDED: "excluded",
  DISABLED: "disabled",
  PENDING: "pending",
  QUEUED: "queued",
  RUNNING: "running",
  TERMINATING: "finishing",
  BLOCKED: "blocked",
  WAITING_FOR_RETRY: "waiting to retry",
  SKIPPED: "skipped",
  INTERNAL_ERROR: "platform error",
  TERMINATED: "finished",
};

export const UPDATE_WORDS: Record<string, string> = {
  QUEUED: "queued",
  WAITING_FOR_RESOURCES: "waiting for compute",
  INITIALIZING: "starting",
  RESETTING: "resetting",
  CREATING_FLOW: "creating flows",
  RUNNING: "running",
  IDLE: "idle",
  COMPLETED: "succeeded",
  FAILED: "failed",
  CANCELED: "canceled",
};

export const PIPELINE_WORDS: Record<string, string> = {
  DEPLOYING: "deploying",
  STARTING: "starting",
  RUNNING: "running",
  STOPPING: "stopping",
  DELETED: "deleted",
  RECOVERING: "recovering",
  FAILED: "failed",
  RESETTING: "resetting",
  IDLE: "idle",
};

export const RUN_TONES: Record<string, Tone> = {
  succeeded: "good",
  running: "busy",
  pending: "busy",
  queued: "busy",
  finishing: "busy",
  "waiting to retry": "busy",
  blocked: "busy",
  starting: "busy",
  failed: "bad",
  "timed out": "bad",
  "upstream failed": "bad",
  "platform error": "bad",
  "succeeded with failures": "bad",
  canceled: "quiet",
  "upstream canceled": "quiet",
  skipped: "quiet",
  excluded: "quiet",
  disabled: "quiet",
  finished: "quiet",
  busy: "busy",
};

/** The one word a page shows for a run.
 *
 *  `result` decides when it exists, because only it separates a success from a failure inside
 *  `TERMINATED`. It is absent while a run is active, and reading it alone shows nothing for the whole
 *  duration of a long run (spec 014 [E-10]). An unknown value comes back verbatim, lowercased: a
 *  paraphrase of a state nobody has seen is a guess. */
export function runWord(lifeCycle?: string | null, result?: string | null): string {
  if (result) return RUN_WORDS[result.toUpperCase()] ?? String(result).toLowerCase();
  if (lifeCycle) return RUN_WORDS[lifeCycle.toUpperCase()] ?? String(lifeCycle).toLowerCase();
  return "unknown";
}

export const updateWord = (state?: string | null): string =>
  state ? (UPDATE_WORDS[state.toUpperCase()] ?? String(state).toLowerCase()) : "unknown";

/** The one word a pipeline page shows — THE reason this module exists.
 *
 *  A pipeline's own `state` is `IDLE` both when it has never run and when its last update **failed**, so
 *  the last update decides and the pipeline's state is only the fallback when there is no update. */
export function pipelineWord(state?: string | null, lastUpdate?: string | null): string {
  if (lastUpdate) return updateWord(lastUpdate);
  if (state) return PIPELINE_WORDS[state.toUpperCase()] ?? String(state).toLowerCase();
  return "unknown";
}

export const tone = (word: string): Tone => RUN_TONES[word] ?? "quiet";

export const isActive = (lifeCycle?: string | null): boolean =>
  ACTIVE.has((lifeCycle ?? "").toUpperCase());

export const isTerminal = (lifeCycle?: string | null): boolean =>
  TERMINAL.has((lifeCycle ?? "").toUpperCase());

export const isFailed = (result?: string | null): boolean =>
  FAILED_RESULTS.has((result ?? "").toUpperCase());

export const updateIsActive = (state?: string | null): boolean =>
  ACTIVE_UPDATE.has((state ?? "").toUpperCase());

/** Whether a Cancel control belongs on screen. The platform's cancellation is asynchronous, so this
 *  answers "is there something to cancel", not "will it stop now" ([RUN-2], [E-8]). */
export const canCancel = (lifeCycle?: string | null): boolean => isActive(lifeCycle);

/** Repair re-runs failed tasks of a FINISHED run; `rerun_tasks` on a live run is a `400`. */
export const canRepair = (result?: string | null, lifeCycle?: string | null): boolean =>
  isTerminal(lifeCycle) && ["FAILED", "TIMEDOUT"].includes((result ?? "").toUpperCase());

/** A duration in seconds, or null when it cannot be known. The platform reports epoch milliseconds.
 *
 *  Three cases, and the third is the one that matters: an active run's duration is `now - start`, and a
 *  run with no start is **not** zero seconds ([E-12]). */
export function durationSeconds(
  startMs?: number | null, endMs?: number | null, nowMs?: number | null,
): number | null {
  if (endMs && startMs) return Math.max(0, Math.floor((endMs - startMs) / 1000));
  if (startMs && nowMs && nowMs >= startMs) return Math.max(0, Math.floor((nowMs - startMs) / 1000));
  return null;
}

/** `1 m 42 s`, `38 s`, `—`. Never `0 s` for an unknown value. */
export function describeDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds < 60) return `${seconds} s`;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  if (minutes < 60) return `${minutes} m ${String(rest).padStart(2, "0")} s`;
  const hours = Math.floor(minutes / 60);
  return `${hours} h ${String(minutes % 60).padStart(2, "0")} m`;
}

/** A job or run id as a number, or null.
 *
 *  A URL carries a string and a tool result carries a number; both are one object (`[JOB-1]`). Returns
 *  null rather than throwing because a caller is usually a route parser, whose contract is "an
 *  unrecognised id parses to the empty route". */
export function asId(value: unknown): number | null {
  if (typeof value === "number" && Number.isInteger(value) && value > 0) return value;
  if (typeof value === "string" && /^\d+$/.test(value.trim())) {
    const n = Number(value.trim());
    return n > 0 ? n : null;
  }
  return null;
}

/** A pipeline id as the platform spells it. A UUID has 36 characters and four hyphens; a name does not,
 *  and a name answered with a `404` reads as a permission problem ([E-17]). */
export const isPipelineId = (value: string): boolean =>
  value.length === 36 && value.split("-").length === 5 &&
  /^[0-9a-f-]+$/i.test(value);

/** The graph, by dependency depth. `[]` for a cyclic graph: a partial picture reads as a small job.
 *
 *  Kahn's algorithm, `O(v + e)`, and the same algorithm the tool server validates with
 *  (`tools/job_graph.py`) — one rule, two runtimes, held to one table ([RB-5], [JOB-3]). A task's display
 *  order within a level is the input's, so a graph does not reshuffle between renders. */
export function taskLevels(tasks: { task_key?: string; depends_on?: string[] }[]): string[][] {
  const keys = tasks.map((t, i) => t.task_key ?? `<task ${i + 1}>`);
  const known = new Set(keys);
  const deps = new Map<string, string[]>(
    keys.map((k, i) => [k, (tasks[i].depends_on ?? []).filter((d) => known.has(d))]),
  );
  const done = new Set<string>();
  const out: string[][] = [];
  while (done.size < keys.length) {
    const ready = keys.filter((k) => !done.has(k) && deps.get(k)!.every((d) => done.has(d)));
    if (!ready.length) return [];
    out.push(ready);
    ready.forEach((k) => done.add(k));
  }
  return out;
}

/** `3 tasks in 2 levels`, for a block's note. Reads as a person would say it. */
export function describeTasks(tasks: { task_key?: string; depends_on?: string[] }[]): string {
  if (!tasks.length) return "no tasks";
  const levels = taskLevels(tasks);
  const noun = tasks.length === 1 ? "task" : "tasks";
  if (!levels.length) return `${tasks.length} ${noun}, with a cycle`;
  if (levels.length === 1) return `${tasks.length} ${noun}, all independent`;
  return `${tasks.length} ${noun} in ${levels.length} levels`;
}

/** Which of the three controls a run page offers, in one matrix.
 *
 *  A table rather than three `if`s in three components: a control that exists in the wrong state is the
 *  inert-control defect 011 [N5] removed, and the matrix is the spec ([RUN-2], [RUN-3], [PIPE-4]). */
export interface RunActions { cancel: boolean; repair: boolean; runAgain: boolean }

export function runActions(lifeCycle?: string | null, result?: string | null): RunActions {
  return {
    cancel: canCancel(lifeCycle),
    repair: canRepair(result, lifeCycle),
    runAgain: isTerminal(lifeCycle),
  };
}

/** Where a job, a run and a pipeline live in the Databricks UI. One function each, because a link built
 *  two ways is a link that 404s in one of them (013's `lakebaseUrl`, extended). */
export function jobUrl(host: string | null | undefined, jobId: string | number): string | null {
  if (!host) return null;
  return `${host.replace(/\/+$/, "")}/jobs/${encodeURIComponent(String(jobId))}`;
}

export function runUrl(host: string | null | undefined, jobId: string | number | null,
                       runId: string | number): string | null {
  if (!host) return null;
  const base = `${host.replace(/\/+$/, "")}/jobs`;
  const id = jobId ? `${encodeURIComponent(String(jobId))}/` : "";
  return `${base}/${id}runs/${encodeURIComponent(String(runId))}`;
}

export function pipelineUrl(host: string | null | undefined, pipelineId: string): string | null {
  if (!host) return null;
  return `${host.replace(/\/+$/, "")}/pipelines/${encodeURIComponent(pipelineId)}`;
}
