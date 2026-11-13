/** One run, as its own document.
 *
 *  A run is a document because a user pastes it into a ticket: `#/run/812345679` is that artifact, and a
 *  tab inside the job page cannot be pasted (spec 014 [UI-7], the UI lens's argument). Its layout reuses
 *  the job page's block rhythm rather than inventing one — the similarity is deliberate.
 *
 *  Two rules make it honest:
 *   * a task that has not started reads `not started`, never `running` — a queued task is not doing work;
 *   * Cancel is offered only while active, and after the click the page says the cancellation is
 *     asynchronous, because the platform documents exactly that and a user told "cancelled" while a
 *     cluster still bills has been lied to about money ([RUN-2], [E-8]).
 */
import { useEffect, useState } from "react";
import { api, type RunPageData, type TaskRun } from "../api/client";
import type { Doc } from "../domain/docs";
import { useResource } from "../hooks/useResource";
import { ExtLink } from "./ExtLink";
import { Block, Fact, StatePill } from "./Infra";
import { when } from "./JobsPage";
import { Play, Refresh, Sparkle, Stop } from "./Icons";

/** Every task's own outcome, as rows. Pure, so the assertion "a queued task is not running" is a unit
 *  test rather than a screenshot ([RUN-1]). */
export function TaskTable({ tasks }: { tasks: TaskRun[] }) {
  if (!tasks.length) {
    return <p className="infra-block-empty">This run reports no tasks yet.</p>;
  }
  return (
    <div className="infra-rows run-tasks">
      {tasks.map((t) => (
        <div key={`${t.taskKey}:${t.taskRunId}`} className="infra-row">
          <span className="infra-row-name">{t.taskKey}</span>
          <StatePill state={t.word} tone={t.tone} />
          <span className="infra-row-range">{t.duration}</span>
          <span className="infra-row-host" title={t.message || undefined}>
            {t.message || (t.lifeCycle ? `${t.lifeCycle.toLowerCase()}` : "—")}
          </span>
        </div>
      ))}
    </div>
  );
}

export function RunsPage({ doc, onAsk }: {
  doc: Doc;
  onAsk?: (prompt: string) => void;
}) {
  const [tick, setTick] = useState(0);
  const [notice, setNotice] = useState("");
  const page = useResource<RunPageData>(`${doc.ref}#${tick}`, () => api.run(doc.ref));
  const run = page.data;

  // Poll while the run is active, and only while the tab is visible: a background tab that keeps polling
  // buys nothing and nobody is looking ([05 diagram 8]).
  useEffect(() => {
    if (!run?.active) return;
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") setTick((n) => n + 1);
    }, 3000);
    return () => window.clearInterval(id);
  }, [run?.active]);

  const refresh = () => setTick((n) => n + 1);
  const headerWord = page.state === "error" ? "unreadable" : (run?.word ?? "loading");

  return (
    <section className="viewer infra-view" aria-label={`run ${doc.ref}`}>
      <header className="viewer-head">
        <div className="viewer-title">
          {/* The run's id AND the job's name: a pasted `#/run/…` link must tell the reader which job it
              belongs to, or it is a bare number in a ticket ([RUN-1]). */}
          <span className="viewer-name">{run?.jobName ? `${run.jobName} · run ${doc.ref}` : `run ${doc.ref}`}</span>
          <StatePill state={headerWord} tone={page.state === "error" ? "bad" : (run?.tone ?? "quiet")} />
        </div>
        {run?.job_id ? (
          <button className="viewer-path" title={`Open job ${run.job_id}`}
            aria-label={`Open job ${run.job_id}`}
            onClick={() => {
              const event = new CustomEvent("opengenie:open-job", { detail: String(run.job_id) });
              window.dispatchEvent(event);
            }}>
            job {run.job_id} ↗
          </button>
        ) : <span className="viewer-path">—</span>}
        <div className="viewer-actions" role="toolbar" aria-label="Refresh, cancel or open this run">
          {run?.cancel && (
            <button className="btn" onClick={() => {
              setNotice("Asking the agent to cancel. Cancellation is asynchronous: the run may keep "
                + "running for a moment, and this page will say so until the platform reports it stopped.");
              onAsk?.(`Cancel run ${doc.ref}. Then keep reading it until the platform reports a terminal ` +
                "state, and tell me what it says — do not report it cancelled before the platform does.");
            }}>
              <Stop size={13} /> Cancel
            </button>
          )}
          <button className="btn" onClick={refresh} disabled={page.refreshing}>
            <Refresh size={13} className={page.refreshing ? "spin" : ""} /> Refresh
          </button>
          <ExtLink className="btn" label="Open this run in Databricks" target={{ kind: "run", ref: doc.ref }}>
            Databricks ↗
          </ExtLink>
        </div>
      </header>

      <div className="viewer-body infra-body">
        <Block title="Run" state={page.state} error={page.error} onRetry={refresh} retryLabel="Try again">
          {run && (
            <div className="infra-facts">
              <Fact label="result" value={run.word} mono={false} />
              <Fact label="duration" value={run.duration} />
              <Fact label="started" value={run.startTime ? when(run.startTime) : "—"} mono={false} />
              <Fact label="trigger" value={run.trigger || "manual"} mono={false} />
              <Fact label="life cycle" value={run.lifeCycle || "—"} mono={false} />
            </div>
          )}
          {run?.active && (
            <p className="infra-note" role="status">
              Still {run.word}. This page re-reads it every 3 s while the tab is visible, and stops when
              the run is terminal.
            </p>
          )}
          {notice && <p className="infra-note" role="status">{notice}</p>}
        </Block>

        <Block title="Tasks"
          state={page.state === "loading" ? "loading" : page.state === "error" ? "error" : (run?.tasks?.length ? "ready" : "empty")}
          error={page.error} onRetry={refresh}
          note={run?.tasks?.length ? `${run.tasks.length}` : undefined}
          empty="No tasks reported yet.">
          {run?.tasks && <TaskTable tasks={run.tasks} />}
        </Block>

        {run?.output && (
          <Block title="Error" state="ready" note={run.output.taskKey}>
            <pre className="infra-error-text">{run.output.error}</pre>
            {run.output.traceTail && (
              <details className="infra-details">
                <summary>Stack trace (tail)</summary>
                <pre className="infra-error-text">{run.output.traceTail}</pre>
              </details>
            )}
            <p className="infra-fix">
              <button className="btn sm" onClick={() => onAsk?.(
                `Run ${doc.ref} failed on task ${run.output?.taskKey ?? "unknown"}. Here is the error:\n\n` +
                `${run.output?.error ?? ""}\n\nFind the cause, check the tables it reads against their ` +
                "real columns, fix the source in my working folder, and prove the fix with a new run.")}>
                <Sparkle size={12} /> Ask the agent to fix it
              </button>
              <span className="infra-note">The prompt carries the task and the error text.</span>
            </p>
          </Block>
        )}

        {run?.repair && (
          <Block title="Repair" state="ready" note="only the failed tasks">
            <p className="infra-fix">
              <button className="btn sm" onClick={() => onAsk?.(
                `Repair run ${doc.ref} of the job it belongs to: re-run only the tasks that failed, then ` +
                "tell me each task's result. Re-read the run first so you know which tasks failed.")}>
                <Play size={12} /> Repair the failed tasks
              </button>
              <span className="infra-note">
                A repair chains onto this run&rsquo;s repair history; it does not start a new run.
              </span>
            </p>
          </Block>
        )}
      </div>
    </section>
  );
}
