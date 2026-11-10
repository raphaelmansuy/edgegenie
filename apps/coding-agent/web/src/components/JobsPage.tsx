/** A Lakeflow job, as a read-only page.
 *
 *  The block order is the argument this page makes: **Last run** outranks **Tasks**, which outranks
 *  **Schedule** and **Settings**, because "is it working?" is the question that brought the user here and
 *  reading order is the only hierarchy that survives a narrow window (spec 014 [JOB-2]).
 *
 *  Every value is a fact from a call. A value that could not be read renders `—`; a block whose call was
 *  denied renders the platform's sentence in place and cannot blank its siblings (013's [UI-3], [E-1]).
 *
 *  No editor, no save, no dirty state: the component has no prop for one. The controls it does have are
 *  the four ACTIONS, and none of them is a `POST` from this page — they ask the agent, because the write
 *  fence has one home ([07 §5]).
 */
import { useEffect, useState } from "react";
import { api, type JobFacts, type JobPageData, type RunRow } from "../api/client";
import type { Doc } from "../domain/docs";
import { describeDuration, durationSeconds } from "../domain/jobs";
import { useResource } from "../hooks/useResource";
import { ExtLink } from "./ExtLink";
import { Block, Fact, StatePill, isPermanent } from "./Infra";
import { JobGraph } from "./JobGraph";
import { Alert, Play, Refresh, Sparkle } from "./Icons";

/** The sentence a schedule block says, and the reason it is a sentence rather than a field.
 *
 *  A user who believes a paused job is firing has a silent data outage; one who believes a running job is
 *  paused has an invoice. So the pause state is stated in words, with what it means (spec 014 [JOB-4]). */
export function scheduleSentence(schedule: JobFacts["schedule"]): string {
  if (!schedule?.cron) return "No schedule: this job runs only when someone runs it.";
  const when = `every ${schedule.cron} (${schedule.timezone || "no timezone"})`;
  return schedule.paused
    ? `${when}, but PAUSED — nothing will run until you resume it.`
    : `${when}. It is running on that schedule now.`;
}

/** What "Run now" will cost, in the words of the last run. Never a spinner with no sentence. */
export function runCostSentence(latest: (RunRow & { tasks?: unknown[] }) | null | undefined): string {
  if (!latest) return "Starts a serverless job. It has never run, so there is no previous duration.";
  return `Starts a serverless job. The last run took ${latest.duration}.`;
}

/** A block's state, from the page's state, its own error, and whether it has anything to show.
 *
 *  When the whole page failed, the blocks are `error` but their SENTENCE is lifted to one page-level
 *  statement — see `pageRefusal` below. A Block that shows the same refusal five times reads as five
 *  problems, which is the rule 013's [UI-6] recorded: one statement per fact.
 */
export function blockState(
  pageState: string, blockError?: string, empty?: boolean, pageStated = false,
): "loading" | "ready" | "empty" | "error" | "unread" {
  if (pageState === "loading") return "loading";
  // The page has already stated why nothing could be read. A block that repeated it (or offered its own
  // retry) would turn one refusal into five, which is what S6's first version looked like: every assertion
  // passed and the screen read as five separate problems ([UI-6]). So `pageStated` is checked BEFORE the
  // block's own error: when every block failed for one cause, the cause is the page's to state.
  if (pageStated) return "unread";
  if (blockError) return "error";
  if (pageState === "error") return "error";
  return empty ? "empty" : "ready";
}

/** The ONE statement a page makes when its blocks share a refusal, or "" when they differ.
 *
 *  Found by looking at S6, after every assertion passed. Two shapes reach it:
 *   * the whole read failed (`pageError`), so every block is empty and the cause is the page's;
 *   * the read SUCCEEDED with `200` and each block carries the same `{"error": …}` — which is what the job
 *     adapter does, deliberately, so one denial cannot blank the others.
 *
 *  In both, rendering the sentence once per block turns one problem into five. The rule 013's [UI-6]
 *  established for the rail is the same rule here: identical sentences collapse; DIFFERENT ones are two
 *  faults and both show, because then they really are two things to fix.
 */
export function pageRefusal(pageError: string | undefined, blockErrors: (string | undefined)[]): string {
  const distinct = new Set(blockErrors.filter((e): e is string => Boolean(e)));
  if (pageError) {
    // The read itself failed, so EVERY block is empty and the cause is the page's, stated once. A block
    // that happened to carry a different sentence is still a consequence of the same failure, and showing
    // it beside a page-level statement reads as a second fault.
    const shared = [...distinct];
    return shared.length === 1 ? shared[0] : pageError;
  }
  if (distinct.size === 1 && blockErrors.filter(Boolean).length >= 2) {
    // Two or more blocks sharing one sentence is one cause. A SINGLE block with an error is that block's
    // own problem and stays where it is, beside the facts that did load.
    return [...distinct][0];
  }
  return "";
}

export function JobsPage({ doc, onAsk }: {
  doc: Doc;
  /** Ask the agent to act. Resume, Run now, Repair and "fix it" all go through here, so there is one
   *  write path and one fence ([07 §5]). */
  onAsk?: (prompt: string) => void;
}) {
  const [tick, setTick] = useState(0);
  const page = useResource<JobPageData>(
    `${doc.ref}#${tick}`,
    () => api.job(doc.ref),
  );

  // A run page and a job page both poll while a run is active, so the page a user is watching moves. The
  // interval stops at the first terminal state, and it does not run in a hidden tab: nobody is looking,
  // and a background tab polling a job costs calls for nothing ([05 diagram 8]).
  const latest = page.data?.latestRun && !("error" in page.data.latestRun)
    ? page.data.latestRun : null;
  const active = Boolean(latest?.active);
  useEffect(() => {
    if (!active) return;
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") setTick((n) => n + 1);
    }, 3000);
    return () => window.clearInterval(id);
  }, [active]);

  const job = page.data?.job && !("error" in page.data.job) ? page.data.job : null;
  const runs = page.data?.runs && !("error" in page.data.runs) ? page.data.runs : null;
  const jobError = page.data?.job && "error" in page.data.job ? page.data.job.error : undefined;
  const runsError = page.data?.runs && "error" in page.data.runs ? page.data.runs.error : undefined;

  const refresh = () => setTick((n) => n + 1);
  const headerWord = page.state === "error" ? "unreadable" : (latest?.word ?? "no runs");
  const headerTone = page.state === "error" ? "bad"
    : latest ? latest.tone : "quiet";

  const refusal = pageRefusal(page.error, [jobError, runsError]);
  const name = job?.name || doc.name;
  const runNow = () => onAsk?.(
    `Run the job ${name} (id ${doc.ref}) once now, and tell me every task's result. ` +
    "If a run is already active, say which one instead of starting another.");
  const repair = () => onAsk?.(
    `Repair the last failed run of ${name} (id ${doc.ref}): re-run only the tasks that failed, then ` +
    "tell me each task's result. If nothing failed, say so and change nothing.");

  return (
    <section className="viewer infra-view" aria-label={`${name} job`}>
      <header className="viewer-head">
        <div className="viewer-title">
          <span className="viewer-name">{name}</span>
          <StatePill state={headerWord} tone={headerTone} />
        </div>
        <button className="viewer-path" title={`Copy the job id ${doc.ref}`}
          aria-label={`Copy the job id ${doc.ref}`}
          onClick={() => void navigator.clipboard?.writeText(doc.ref)}>
          job {doc.ref}
        </button>
        <div className="viewer-actions" role="toolbar" aria-label="Run, refresh or open this job">
          <button className="btn" onClick={runNow} disabled={active || !onAsk}
            title={active ? "a run is already active; open it below" : runCostSentence(latest)}>
            <Play size={13} /> Run now
          </button>
          <button className="btn" onClick={refresh} disabled={page.refreshing}
            title="Re-read every block from the workspace">
            <Refresh size={13} className={page.refreshing ? "spin" : ""} /> Refresh
          </button>
          <ExtLink className="btn" label="Open this job in Databricks" target={{ kind: "job", ref: doc.ref }}>
            Databricks ↗
          </ExtLink>
        </div>
      </header>

      <div className="viewer-body infra-body">
        {/* ONE statement when the whole page failed for one cause. Five identical boxes read as five
            problems — the rule 013's [UI-6] made, found here by LOOKING at S6 after every assertion
            passed. A block whose state is `error` but has no sentence of its own renders "could not be
            read", which is a consequence, not a second cause. */}
        {refusal && (
          <div className="infra-page-refusal" role="alert">
            <Alert size={15} />
            <div>
              <strong>This page could not be read.</strong>
              <span>{refusal}</span>
              {isPermanent(refusal) ? (
                <span className="infra-note">
                  A retry cannot grant this. Ask the job&rsquo;s owner for access, or open it in Databricks.
                </span>
              ) : (
                <button className="btn sm ghost" onClick={refresh}>Try again</button>
              )}
            </div>
          </div>
        )}
        <Block title="Last run"
          state={blockState(page.state, runsError, !latest, Boolean(refusal))}
          error={runsError}
          onRetry={refresh} retryLabel="Try again"
          note={latest ? `run ${latest.run_id}` : undefined}
          empty="This job has not run yet. Run now starts the first run; it has never spent compute."
          unread="The last run could not be read, so this page cannot say whether the job has run.">
          {latest && (
            <>
              <div className="infra-facts">
                <Fact label="result" value={latest.word} mono={false} />
                <Fact label="duration" value={latest.duration} />
                <Fact label="started" value={latest.startTime ? when(latest.startTime) : "—"} mono={false} />
                <Fact label="trigger" value={latest.trigger || "manual"} mono={false} />
              </div>
              {latest.active && (
                <p className="infra-note" role="status">
                  Still {latest.word} — this page re-reads it every 3 s while the tab is visible.
                </p>
              )}
              {latest.output?.error && (
                <pre className="infra-error-text">{latest.output.error}</pre>
              )}
              <p className="infra-fix">
                <button className="btn sm" onClick={() => onAsk?.(
                  `Read the last run of ${name} (job ${doc.ref}) and tell me exactly which task failed and why. ` +
                  "Quote the error. Check the tables it reads against their real columns before you conclude anything.")}>
                  <Sparkle size={12} /> Ask why it failed
                </button>
                {latest.repair && (
                  <button className="btn sm" onClick={repair}>
                    Repair the failed tasks
                  </button>
                )}
                {latest.run_id !== null && (
                  <button className="btn sm ghost" onClick={() => onAsk?.(
                    `Open run ${latest.run_id} of ${name} and walk me through its tasks.`)}>
                    Open the run
                  </button>
                )}
                <span className="infra-note">The prompt carries the job id and the run id.</span>
              </p>
            </>
          )}
        </Block>

        <Block title="Schedule"
          state={blockState(page.state, jobError, !job, Boolean(refusal))}
          error={jobError} onRetry={refresh}
          empty="—"
          unread="The schedule could not be read, so this page cannot say when this job runs.">
          {job && (
            <>
              <p className={`infra-schedule${job.schedule?.paused ? " is-paused" : ""}`}>
                {scheduleSentence(job.schedule)}
              </p>
              {job.schedule && (
                <div className="infra-facts">
                  <Fact label="cron" value={job.schedule.cron} />
                  <Fact label="timezone" value={job.schedule.timezone || "—"} />
                  <Fact label="state" value={job.schedule.paused ? "paused" : "unpaused"} mono={false} />
                </div>
              )}
              <p className="infra-fix">
                {job.schedule?.paused ? (
                  <button className="btn sm" onClick={() => onAsk?.(
                    `Resume the schedule of the job ${name} (id ${doc.ref}) so it runs on its cron again. ` +
                    `Tell me exactly when it will next fire, and what compute it will start.`)}>
                    Resume schedule
                  </button>
                ) : job.schedule && (
                  <button className="btn sm" onClick={() => onAsk?.(
                    `Pause the schedule of the job ${name} (id ${doc.ref}) so it stops firing. ` +
                    "Confirm it is paused by reading the job back.")}>
                    Pause schedule
                  </button>
                )}
                <span className="infra-note">
                  {job.schedule?.paused
                    ? "Resuming creates a recurring cost: read the sentence above before you do."
                    : "Pausing removes a recurring cost."}
                </span>
              </p>
            </>
          )}
        </Block>

        <Block title="Tasks"
          state={blockState(page.state, jobError, !job, Boolean(refusal))}
          error={jobError} onRetry={refresh}
          note={page.data?.summary}
          empty="This job has no tasks."
          unread="The tasks could not be read, so this page cannot draw the graph.">
          {job && (
            <JobGraph tasks={job.tasks} levels={page.data?.levels}
              problem={page.data?.graphProblem ?? null} />
          )}
        </Block>

        <Block title="Runs" state={blockState(page.state, runsError, !runs?.length, Boolean(refusal))}
          error={runsError} onRetry={refresh}
          note={runs?.length ? `${runs.length} shown` : undefined}
          empty="No runs in this job's history."
          unread="The run history could not be read, so this page cannot list any runs.">
          {runs && runs.length > 0 && (
            <div className="infra-rows">
              {runs.map((r) => (
                <div key={r.run_id ?? r.startTime} className="infra-row">
                  <span className="infra-row-name">run {r.run_id}</span>
                  <span className="infra-row-meta">{r.startTime ? when(r.startTime) : "—"}</span>
                  <span className="infra-row-range">{r.duration}</span>
                  <StatePill state={r.word} tone={r.tone} />
                </div>
              ))}
            </div>
          )}
        </Block>

        <Block title="Settings"
          state={blockState(page.state, jobError, !job, Boolean(refusal))}
          error={jobError} onRetry={refresh} empty="—"
          unread="The settings could not be read, so this page cannot show this job's configuration.">
          {job && (
            <div className="infra-facts">
              <Fact label="owner" value={job.owner || "—"} mono={false} />
              <Fact label="queueing" value={job.queueing ? "on" : "off"} mono={false} />
              <Fact label="timeout" value={job.timeoutSeconds ? `${job.timeoutSeconds} s` : "none"} />
              <Fact label="retries" value={String(job.maxRetries)} />
              <Fact label="compute" value={job.performanceTarget || "serverless"} mono={false} />
              <Fact label="created" value={job.created ? when(job.created) : "—"} mono={false} />
            </div>
          )}
          {page.data && (
            <p className="infra-identity">
              read as {page.data.identity} — this page shows what the app may read, not what you may read.
            </p>
          )}
        </Block>

      </div>
    </section>
  );
}

/** What a timestamp reads as. A run page is not an audit log; the Databricks link is where an exact UTC
 *  instant belongs. Moved here so the run, job and pipeline pages cannot format one instant two ways. */
export function when(ms: number | null | undefined): string {
  if (!ms) return "—";
  const d = new Date(ms);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

/** A run's own duration, for the callers that need the number rather than the sentence. Exported so the
 *  run page and this page cannot disagree about it. */
export { durationSeconds, describeDuration };
