/** A Lakebase project, as a read-only page.
 *
 * The page answers three questions a user asks after "create me a database": what is it, is it
 * running, and what is in it. Every value is a fact from a call — a value that could not be read
 * renders `—` and a note, never `0` (spec 013 [UI-3], [P1]).
 *
 * Four blocks, four independent calls. A block that fails renders its own refusal in place and
 * cannot blank its siblings ([06 §5], [E-11]). No editor, no save, no dirty state: the component has
 * no prop for one, which is how read-only is taught structurally rather than by a comment.
 */
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { Doc } from "../domain/docs";
import {
  isError, lakebaseUrl, orDash, projectId, type LakebasePageData,
} from "../domain/lakebase";
import type { Workspace } from "../domain/links";
import { ExtLink } from "./ExtLink";
import { Block, Fact, StatePill } from "./Infra";
import { Refresh } from "./Icons";

type Load<T> = { state: "loading" | "ready" | "empty" | "error"; data?: T; error?: string };

function settled<T>(v: T | { error: string } | undefined, isEmpty: (v: T) => boolean): Load<T> {
  if (v === undefined) return { state: "loading" };
  if (isError(v)) return { state: "error", error: v.error };
  return { state: isEmpty(v) ? "empty" : "ready", data: v };
}

export function LakebasePage({ doc, workspace }: { doc: Doc; workspace: Workspace | null }) {
  const [page, setPage] = useState<Load<LakebasePageData>>({ state: "loading" });
  const [tick, setTick] = useState(0);
  const [tables, setTables] = useState<Load<{ tables: string[]; truncated: boolean }>>({ state: "loading" });

  const load = useCallback(() => {
    setPage({ state: "loading" });
    setTables({ state: "loading" });
    api.lakebaseProject(doc.ref)
      .then((p) => setPage({ state: "ready", data: p }))
      .catch((e) => setPage({ state: "error", error: e instanceof Error ? e.message : "could not read this project" }));
  }, [doc.ref]);

  useEffect(() => { load(); }, [load, tick]);

  const branch = page.data?.branches && !isError(page.data.branches)
    ? page.data.branches.find((b) => b.isDefault)?.name ?? page.data.branches[0]?.name ?? "production"
    : "production";

  // The table list needs a database connection, so it loads after the branches are known. A failure
  // here is local: the rest of the page is already on screen.
  useEffect(() => {
    if (tick < 0) return;
    let live = true;
    setTables({ state: "loading" });
    api.lakebaseTables(doc.ref, branch, "databricks_postgres", "public")
      .then((r) => live && setTables({ state: r.tables.length ? "ready" : "empty", data: r }))
      .catch((e) => live && setTables({ state: "error", error: e instanceof Error ? e.message : "could not read the tables" }));
    return () => { live = false; };
  }, [doc.ref, branch, tick]);

  const p = page.data;
  const project = p?.project && !isError(p.project) ? p.project : undefined;
  const branches = p?.branches;
  const databases = p?.databases;
  const compute = p?.compute;
  const host = lakebaseUrl(workspace?.host, doc.ref);

  const refresh = () => {
    void api.refreshLakebase(doc.ref).catch(() => undefined);
    setTick((n) => n + 1);
  };

  return (
    <section className="viewer infra-view" aria-label={`${doc.name} project`}>
      <header className="viewer-head">
        <div className="viewer-title">
          <span className="viewer-name">{project?.displayName || doc.name}</span>
          <StatePill state={project?.state ? project.state : page.state === "error" ? "unreadable" : "loading"}
            tone={project?.ready ? "good" : page.state === "error" ? "bad" : "busy"} />
        </div>
        <button className="viewer-path" title={`Copy the resource name ${doc.ref}`}
          aria-label={`Copy the resource name ${doc.ref}`}
          onClick={() => void navigator.clipboard?.writeText(doc.ref)}>{doc.ref}</button>
        <div className="viewer-actions" role="toolbar" aria-label="Refresh or open this project">
          <button className="btn" onClick={refresh} title="Re-read every block from the workspace">
            <Refresh size={13} /> Refresh
          </button>
          {host && (
            <ExtLink className="btn" label="Open this project in Databricks" target={{ kind: "lakebase", ref: doc.ref }}>
              Open in Databricks ↗
            </ExtLink>
          )}
        </div>
      </header>

      <div className="viewer-body infra-body">
        <Block title="Project"
          state={page.state === "error" ? "error" : isError(p?.project) ? "error" : page.state === "ready" ? "ready" : page.state}
          error={page.error ?? (isError(p?.project) ? p?.project.error : undefined)}
          onRetry={load} retryLabel="Try again">
          <div className="infra-facts">
            <Fact label="id" value={projectId(doc.ref)} />
            <Fact label="postgres" value={orDash(project?.pgVersion)} />
            <Fact label="default branch" value={orDash(project?.defaultBranch)} />
            <Fact label="state" value={orDash(project?.state)} mono={false} />
          </div>
        </Block>

        <Block title="Compute" state={settled(compute, (c) => c.length === 0).state}
          error={settled(compute, () => false).error}
          empty="No compute yet: the platform creates one with the branch."
          note={compute && !isError(compute) && compute.length ? `${compute.length} endpoint${compute.length === 1 ? "" : "s"}` : undefined}>
          {compute && !isError(compute) && (
            <div className="infra-rows">
              {compute.map((c) => (
                <div key={c.ref} className="infra-row">
                  <span className="infra-row-name">{c.name}</span>
                  <span className="infra-row-meta">{c.type.replace("ENDPOINT_TYPE_", "").toLowerCase()}</span>
                  <span className={`infra-row-range${c.rangeValid ? "" : " is-bad"}`}>{c.range}</span>
                  <StatePill state={c.suspended ? "asleep" : c.state} tone={c.suspended ? "quiet" : "good"} />
                  <span className="infra-row-host" title={c.host}>{c.host || "—"}</span>
                </div>
              ))}
            </div>
          )}
        </Block>

        <Block title="Branches" state={settled(branches, (b) => b.length === 0).state}
          error={settled(branches, () => false).error}
          empty="No branches reported."
          note={branches && !isError(branches) && branches.length ? `${branches.length}` : undefined}>
          {branches && !isError(branches) && (
            <ul className="infra-list">
              {branches.map((b) => (
                <li key={b.ref} className="infra-list-row">
                  <span className="infra-mono">{b.name}</span>
                  {b.isDefault && <span className="infra-tag">default</span>}
                  {!b.isDefault && <span className="infra-tag quiet">from production</span>}
                </li>
              ))}
            </ul>
          )}
        </Block>

        <Block title="Databases" state={settled(databases, (d) => d.length === 0).state}
          error={settled(databases, () => false).error}
          empty="No database reported: a branch arrives with databricks_postgres."
          note={databases && !isError(databases) && databases.length ? `${databases.length}` : undefined}>
          {databases && !isError(databases) && (
            <ul className="infra-list">
              {databases.map((d) => (
                <li key={d.ref} className="infra-list-row">
                  <span className="infra-mono">{d.name}</span>
                  <span className="infra-tag quiet">{branch}</span>
                </li>
              ))}
            </ul>
          )}
        </Block>

        <Block title="Tables in public" state={tables.state} error={tables.error}
          onRetry={() => setTick((n) => n + 1)} retryLabel="Try again"
          empty="This database has no tables in the public schema yet."
          note={tables.data ? `${tables.data.tables.length}${tables.data.truncated ? "+" : ""}` : undefined}>
          {tables.data && (
            <>
              <ul className="infra-list cols">
                {tables.data.tables.map((t) => <li key={t} className="infra-list-row"><span className="infra-mono">{t}</span></li>)}
              </ul>
              {tables.data.truncated && (
                <p className="infra-note">50 of more: open the project in Databricks for the rest.</p>
              )}
            </>
          )}
        </Block>
      </div>
    </section>
  );
}
