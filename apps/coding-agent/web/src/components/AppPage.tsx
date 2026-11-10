/** A Databricks App, as a read-only page.
 *
 * The user's question after "build me an app" is **is it working**, and the only honest answer is an
 * HTTP status. A deployment's `SUCCEEDED` means the process started — this repository's own `make
 * deploy` learned that the expensive way — so the health row is the headline here, and a cold start
 * is its own state, not a failure (spec 013 [UI-4], [AP-4], [E-14]).
 */
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import {
  fixPrompt, healthSentence, logsUrl, postgresResource, tone, type AppView,
} from "../domain/app";
import type { Doc } from "../domain/docs";
import type { Workspace } from "../domain/links";
import { ExtLink } from "./ExtLink";
import { Block, Fact, StatePill } from "./Infra";
import { Refresh, Sparkle } from "./Icons";

export function AppPage({ doc, workspace, onAsk }: {
  doc: Doc; workspace: Workspace | null;
  /** Ask the agent to fix it. The prompt carries the status code, so it does not rediscover it. */
  onAsk?: (prompt: string) => void;
}) {
  const [app, setApp] = useState<{ state: "loading" | "ready" | "error"; data?: AppView; error?: string }>({ state: "loading" });
  const [tick, setTick] = useState(0);
  const [checking, setChecking] = useState(false);

  const retry = useCallback(() => setTick((n) => n + 1), []);

  const load = useCallback(() => {
    setApp({ state: "loading" });
    api.app(doc.ref)
      .then((data) => setApp({ state: "ready", data }))
      .catch((e) => setApp({ state: "error", error: e instanceof Error ? e.message : "could not read this app" }));
  }, [doc.ref]);

  useEffect(() => { load(); }, [load, tick]);

  const recheck = async () => {
    setChecking(true);
    try {
      const health = await api.appHealth(doc.ref, true);
      setApp((cur) => (cur.data ? { ...cur, data: { ...cur.data, health } } : cur));
    } catch { /* the page keeps the last health it had; the button is not a promise */ }
    finally { setChecking(false); }
  };

  const a = app.data;
  const pg = postgresResource(a);
  const health = a?.health;
  const logs = a ? logsUrl(a.url) : null;
  const failing = health?.state === "failing" || a?.state === "failing";
  const host = workspace?.host ? workspace.host.replace(/\/+$/, "") : "";

  return (
    <section className="viewer infra-view" aria-label={`${doc.name} app`}>
      <header className="viewer-head">
        <div className="viewer-title">
          <span className="viewer-name">{a?.name || doc.name}</span>
          <StatePill state={a?.state ?? (app.state === "error" ? "unreadable" : "loading")}
            tone={app.state === "error" ? "bad" : tone(a?.state ?? "")} />
        </div>
        <button className="viewer-path" title={`Copy the app name ${doc.ref}`}
          aria-label={`Copy the app name ${doc.ref}`}
          onClick={() => void navigator.clipboard?.writeText(doc.ref)}>
          {a?.url ? a.url.replace(/^https?:\/\//, "") : doc.ref}
        </button>
        <div className="viewer-actions" role="toolbar" aria-label="Check or open this app">
          <button className="btn" onClick={() => void recheck()} disabled={checking || !a}
            title="Fetch the app's URL now and report the status code">
            <Refresh size={13} className={checking ? "spin" : ""} /> {checking ? "Checking…" : "Check health"}
          </button>
          {a?.url && (
            <ExtLink className="btn" label="Open this app in a new tab" target={{ kind: "app", ref: a.url }}>
              Open app ↗
            </ExtLink>
          )}
          {host && (
            <ExtLink className="btn" label="Open this app's page in Databricks" target={{ kind: "app", ref: doc.ref }}>
              Databricks ↗
            </ExtLink>
          )}
        </div>
      </header>

      <div className="viewer-body infra-body">
        <Block title="Health" state={app.state === "ready" ? "ready" : app.state} error={app.error}
          onRetry={retry} retryLabel="Try again"
          note={health?.checkedAt ? `checked ${health.checkedAt}` : undefined}>
          {a && (
            <div className={`infra-health tone-${health ? (health.state === "running" ? "good" : health.state === "failing" ? "bad" : "busy") : "quiet"}`}>
              <span className="infra-health-sentence">{healthSentence(health, a.state)}</span>
              {health?.status !== null && health?.status !== undefined && (
                <span className="infra-health-code">{health.status}</span>
              )}
            </div>
          )}
          {failing && onAsk && a && (
            <p className="infra-fix">
              <button className="btn sm" onClick={() => onAsk(fixPrompt(a))}>
                <Sparkle size={12} /> Ask the agent to fix it
              </button>
              <span className="infra-note">The prompt carries the status code and the logs URL.</span>
            </p>
          )}
        </Block>

        <Block title="App" state={app.state === "ready" ? "ready" : app.state} error={app.error} onRetry={retry}>
          {a && (
            <div className="infra-facts">
              <Fact label="url" value={a.url || "—"} />
              <Fact label="compute" value={a.computeSize || "—"} />
              <Fact label="deployment" value={a.deploymentState || "—"} />
              <Fact label="creator" value={a.creator || "—"} mono={false} />
              {logs && <Fact label="logs" value={<a className="infra-link" href={logs} target="_blank" rel="noopener noreferrer">/logz</a>} />}
            </div>
          )}
        </Block>

        <Block title="Resources"
          state={a ? (a.resources.length ? "ready" : "empty") : app.state === "error" ? "error" : "loading"}
          error={app.error}
          empty="No resources. Without a postgres resource the app cannot reach a Lakebase database."
          note={a && a.resources.length ? `${a.resources.length}` : undefined}>
          {a && a.resources.length > 0 && (
            <div className="infra-rows">
              {a.resources.map((r) => (
                <div key={`${r.kind}:${r.name}`} className="infra-row">
                  <span className="infra-row-name">{r.name}</span>
                  <span className="infra-row-meta">{r.kind}</span>
                  <span className="infra-row-range">{r.permission || "—"}</span>
                  <span className="infra-row-host" title={r.branch}>{r.branch ? r.branch.split("/branches/").pop() : "—"}</span>
                </div>
              ))}
            </div>
          )}
          {a && !pg && (
            <p className="infra-note">
              No postgres resource: the platform injects no <code>PGHOST</code>, so the app starts without a database.
            </p>
          )}
        </Block>

        {a?.lakebase && (
          <p className="infra-note">
            Reads <code>{a.lakebase}</code> · <button className="infra-link" onClick={() => {
              const event = new CustomEvent("opengenie:open-lakebase", { detail: a.lakebase });
              window.dispatchEvent(event);
            }}>open the project</button>
          </p>
        )}
      </div>
    </section>
  );
}
