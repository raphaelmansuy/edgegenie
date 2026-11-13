/** A Lakeflow pipeline, as a read-only page.
 *
 *  The header follows the **last update**, not the pipeline's `state`. A pipeline whose last update failed
 *  still reports `IDLE`, and a page that reads `state` shows "idle" over a broken pipeline — the finding
 *  `F5` recorded and `[PIPE-5]` forbids. `pipelineWord()` is the one function that decides it.
 *
 *  Three start modes with different costs, each labelled, because "Start" and "Full refresh" are the
 *  difference between seconds and an hour of compute ([PIPE-3]). Stop is ABSENT, not disabled, when no
 *  update is active: a button that cannot act is the inert control 011 [N5] removed ([PIPE-4]).
 */
import { useEffect, useState } from "react";
import { api, type PipelineEvent, type PipelineFacts, type PipelinePageData } from "../api/client";
import type { Doc } from "../domain/docs";
import { useResource } from "../hooks/useResource";
import { ExtLink } from "./ExtLink";
import { Block, Fact, StatePill, isPermanent } from "./Infra";
import { when } from "./JobsPage";
import { Play, Refresh, Sparkle, Stop } from "./Icons";

/** A block's state, from the page's state and the block's own error.
 *
 *  A page-level refusal (a 403 on the pipeline itself) used to fall through to `empty`, so the sentence
 *  was passed as `error` and never rendered — a Block shows `error` only when its state says so. A page
 *  that fails must say why, not that there is nothing to show. */
export function pipelineBlockState(
  pageState: string, blockError?: string, empty?: boolean,
): "loading" | "ready" | "empty" | "error" {
  if (blockError) return "error";
  if (pageState === "loading") return "loading";
  if (pageState === "error") return "error";
  return empty ? "empty" : "ready";
}

/** The events, errors and warnings first. Pure, so the ordering is a unit test ([PIPE-6]). */
export function orderedEvents(events: PipelineEvent[]): PipelineEvent[] {
  const rank: Record<string, number> = { ERROR: 0, WARN: 1, INFO: 2 };
  return [...events].sort((a, b) => (rank[a.level] ?? 9) - (rank[b.level] ?? 9));
}

/** What the page says about why an update failed, including the case where the platform said nothing.
 *  Inventing a cause is worse than reporting that none was given. */
export function failureSentence(events: PipelineEvent[]): string | null {
  const first = orderedEvents(events).find((e) => e.level === "ERROR");
  return first ? first.message : null;
}

export function PipelinePage({ doc, onAsk }: {
  doc: Doc;
  onAsk?: (prompt: string) => void;
}) {
  const [tick, setTick] = useState(0);
  const page = useResource<PipelinePageData>(`${doc.ref}#${tick}`, () => api.pipeline(doc.ref));
  const data = page.data;
  const pipeline = data?.pipeline && !("error" in data.pipeline) ? data.pipeline : null;
  const pipelineError = data?.pipeline && "error" in data.pipeline ? data.pipeline.error : undefined;
  const events = data?.events && !("error" in data.events) ? orderedEvents(data.events) : null;
  const lastUpdate = data?.lastUpdate && !("error" in data.lastUpdate) ? data.lastUpdate : null;
  const active = Boolean(data?.activeUpdate);

  // Poll while an update is active, and only while the tab is visible.
  useEffect(() => {
    if (!active) return;
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") setTick((n) => n + 1);
    }, 4000);
    return () => window.clearInterval(id);
  }, [active]);

  const refresh = () => setTick((n) => n + 1);
  const name = pipeline?.name || doc.name;
  const headerWord = page.state === "error" ? "unreadable"
    : data ? data.word : "loading";
  const headerTone = page.state === "error" ? "bad" : (data?.tone ?? "quiet");
  const failure = events && lastUpdate?.state === "FAILED" ? failureSentence(events) : null;

  const start = (mode: "incremental" | "full" | "validate") => {
    const verb = mode === "validate"
      ? "Check the code of"
      : mode === "full"
        ? "Start a FULL REFRESH of"
        : "Start an incremental update of";
    const tail = mode === "validate"
      ? "Use validate_only so nothing is materialised, then tell me what it found."
      : mode === "full"
        ? "It re-reads every source, so say which tables that touches before you start it."
        : "It re-reads only new data. Tell me each flow's result.";
    onAsk?.(`${verb} the pipeline ${name} (id ${doc.ref}). ${tail}`);
  };

  return (
    <section className="viewer infra-view" aria-label={`${name} pipeline`}>
      <header className="viewer-head">
        <div className="viewer-title">
          <span className="viewer-name">{name}</span>
          <StatePill state={headerWord} tone={headerTone} />
        </div>
        <button className="viewer-path" title={`Copy the pipeline id ${doc.ref}`}
          aria-label={`Copy the pipeline id ${doc.ref}`}
          onClick={() => void navigator.clipboard?.writeText(doc.ref)}>
          {doc.ref.slice(0, 8)}…
        </button>
        <div className="viewer-actions" role="toolbar" aria-label="Start, check or open this pipeline">
          <button className="btn" onClick={() => start("incremental")} disabled={active || !onAsk}
            title="Re-reads only new data">
            <Play size={13} /> Start
          </button>
          <button className="btn" onClick={() => start("full")} disabled={active || !onAsk}
            title="Resets every table and re-reads every source">
            Full refresh
          </button>
          <button className="btn ghost" onClick={() => start("validate")} disabled={!onAsk}
            title="Checks the code without materialising anything, and costs no compute">
            Check the code
          </button>
          {/* ABSENT when nothing is active, not disabled: a control that cannot act is a lie. */}
          {active && (
            <button className="btn" onClick={() => onAsk?.(
              `Stop the active update of the pipeline ${name} (id ${doc.ref}). Cancellation is ` +
              "asynchronous, so read the pipeline back and tell me what the platform reports.")}>
              <Stop size={13} /> Stop
            </button>
          )}
          <button className="btn" onClick={refresh} disabled={page.refreshing}>
            <Refresh size={13} className={page.refreshing ? "spin" : ""} /> Refresh
          </button>
          <ExtLink className="btn" label="Open this pipeline in Databricks"
            target={{ kind: "pipeline", ref: doc.ref }}>
            Databricks ↗
          </ExtLink>
        </div>
      </header>

      <div className="viewer-body infra-body">
        <Block title="Last update"
          state={pipelineBlockState(page.state, data?.lastUpdate && "error" in data.lastUpdate ? data.lastUpdate.error : undefined, !lastUpdate)}
          error={page.error ?? (data?.lastUpdate && "error" in data.lastUpdate ? data.lastUpdate.error : undefined)}
          onRetry={refresh} retryLabel="Try again"
          note={lastUpdate ? `update ${lastUpdate.updateId.slice(0, 8)}` : undefined}
          empty="Never run. Check the code validates every flow without materialising anything.">
          {lastUpdate && (
            <>
              <div className="infra-facts">
                <Fact label="result" value={lastUpdate.word} mono={false} />
                <Fact label="started" value={lastUpdate.creationTime ? when(lastUpdate.creationTime) : "—"} mono={false} />
                <Fact label="mode" value={lastUpdate.fullRefresh ? "full refresh" : "incremental"} mono={false} />
                <Fact label="cause" value={lastUpdate.cause || "—"} mono={false} />
              </div>
              {failure && <pre className="infra-error-text">{failure}</pre>}
              {lastUpdate.state === "FAILED" && !failure && (
                <p className="infra-note">
                  The platform reported a failed update with no ERROR event. That is the honest state:
                  open the update in Databricks for its full log.
                </p>
              )}
              {active && (
                <p className="infra-note" role="status">
                  An update is in progress. This page re-reads it every 4 s while the tab is visible.
                </p>
              )}
            </>
          )}
        </Block>

        <Block title="Libraries"
          state={pipelineBlockState(page.state, pipelineError, !pipeline?.libraries.length)}
          error={page.error ?? pipelineError} onRetry={refresh}
          note={pipeline?.libraries.length ? `${pipeline.libraries.length}` : undefined}
          empty="This pipeline has no libraries, so it materialises nothing.">
          {pipeline && pipeline.libraries.length > 0 && (
            <div className="infra-rows">
              {pipeline.libraries.map((lib) => (
                <div key={`${lib.kind}:${lib.path}`} className="infra-row">
                  <span className="infra-row-name">{lib.path.split("/").filter(Boolean).pop()}</span>
                  <span className="infra-row-meta">{lib.kind}</span>
                  <span className="infra-row-host" title={lib.path}>{lib.path}</span>
                </div>
              ))}
            </div>
          )}
        </Block>

        <Block title="Configuration"
          state={pipelineBlockState(page.state, pipelineError, !pipeline)}
          error={page.error ?? pipelineError} onRetry={refresh} empty="—">
          {pipeline && (
            <div className="infra-facts">
              <Fact label="catalog" value={pipeline.catalog || "—"} />
              <Fact label="schema" value={pipeline.schema || "—"} />
              <Fact label="edition" value={pipeline.edition || "—"} mono={false} />
              <Fact label="compute" value={pipeline.serverless ? "serverless" : "classic"} mono={false} />
              <Fact label="channel" value={pipeline.channel || "—"} mono={false} />
              <Fact label="continuous" value={pipeline.continuous ? "yes" : "no"} mono={false} />
            </div>
          )}
        </Block>

        <Block title="Events"
          state={pipelineBlockState(page.state, undefined, !events?.length)}
          error={page.error} onRetry={refresh}
          note={events?.length ? `${events.length}` : undefined}
          empty="No errors or warnings reported. Informational events are in Databricks.">
          {events && events.length > 0 && (
            <div className="infra-rows pipeline-events">
              {events.map((e, i) => (
                <div key={`${e.timestamp}-${i}`} className={`infra-row level-${e.level.toLowerCase()}`}>
                  <span className="infra-row-name">{e.level}</span>
                  <span className="infra-row-meta">{e.timestamp ? when(e.timestamp) : "—"}</span>
                  <span className="infra-row-host">{e.message}</span>
                </div>
              ))}
            </div>
          )}
          {events?.some((e) => e.stackTrace) && (
            <details className="infra-details">
              <summary>Stack trace</summary>
              <pre className="infra-error-text">
                {events.find((e) => e.stackTrace)?.stackTrace}
              </pre>
            </details>
          )}
        </Block>

        <Block title="Ask" state="ready">
          <p className="infra-fix">
            <button className="btn sm" onClick={() => onAsk?.(
              `The pipeline ${name} (id ${doc.ref}) — read its last update and its error events, find ` +
              "the cause in the library files, fix it in my working folder, validate with validate_only, " +
              "then start an update and show me the result.")}>
              <Sparkle size={12} /> Ask the agent to fix it
            </button>
            <span className="infra-note">The prompt carries the pipeline id, so the agent does not search.</span>
          </p>
          {page.data && (
            <p className="infra-identity">
              read as {page.data.identity} — this page shows what the app may read, not what you may read.
            </p>
          )}
          {page.state === "error" && page.error && isPermanent(page.error) && (
            <p className="infra-note">This refusal cannot be retried. Open the pipeline in Databricks.</p>
          )}
        </Block>
      </div>
    </section>
  );
}

export type { PipelineFacts };
