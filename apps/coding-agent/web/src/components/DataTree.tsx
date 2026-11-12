/** The Data rail tab: every object the agent can build and the user can operate — Lakebase, jobs,
 *  pipelines, apps — and nothing else.
 *
 *  A tab rather than a folder in Files or a section in Catalog, and the reason is a mental model: a
 *  database project is not a workspace path (Files would need a fake one) and not Unity Catalog (Catalog
 *  is governed by a different API). These object types share a lifecycle — build, run, verify — which is
 *  what a tab is for (spec 013 [UI-2]).
 *
 *  **Four groups, one primitive.** 013 wrote this component with two `useState` + two `useEffect` + two
 *  renderers, which was fine at two. At four that is four places to get the error-collapsing rule wrong,
 *  so the groups are a TABLE and each row is loaded by `useResource` (spec 014 [UI-2]).
 *
 *  One message for one cause. Two calls that fail because one scope is missing must read as one problem:
 *  013's `errorBoxes` collapses identical sentences and keeps different ones, and that rule is applied
 *  here to four groups instead of two ([E-23]).
 */
import { api, type JobRow, type PipelineRow, type AppView, type LakebaseProject } from "../api/client";
import { appStateWord, tone } from "../domain/app";
import { makeDoc, type Doc } from "../domain/docs";
import { useResource, type Resource } from "../hooks/useResource";
import { PaneError } from "./PaneError";
import { Refresh } from "./Icons";

interface Row {
  doc: Doc;
  icon: string;
  kind: string;
  pill: { word: string; tone: string } | null;
  note: string | null;
}

interface Group {
  key: string;
  label: string;
  items: Resource<unknown[]>;
  empty: string;
  row: (item: never) => Row;
}

export function DataTree({ onOpen, selected }: {
  onOpen: (d: Doc) => void;
  /** The `docId` of the open document, so the row can mark itself. */
  selected: string | null;
}) {
  // Four hooks, four fixed call sites: a hook cannot be called in a loop, so the LOADING is explicit and
  // the RENDERING is table-driven. The honest split, stated because a reviewer will ask why not `map`.
  const projects = useResource<LakebaseProject[]>("lakebase",
    () => api.lakebaseProjects().then((r) => r.items), { initial: [] });
  const jobs = useResource<JobRow[]>("jobs", () => api.jobs().then((r) => r.items), { initial: [] });
  const pipelines = useResource<PipelineRow[]>("pipelines",
    () => api.pipelines().then((r) => r.items), { initial: [] });
  const apps = useResource<AppView[]>("apps", () => api.apps().then((r) => r.items), { initial: [] });

  const groups: Group[] = [
    {
      key: "lakebase", label: "Lakebase", items: projects as Resource<unknown[]>,
      empty: "No projects yet. Ask the agent to create one.",
      row: (item: never) => {
        const p = item as LakebaseProject;
        return {
          doc: makeDoc("lakebase", p.ref, p.displayName || p.name),
          icon: "▤", kind: "lakebase",
          // NO state pill: a Lakebase PROJECT has no state field, and 013's [RB-12] recorded what happened
          // when this row read one anyway — every project showed a green "ready" whatever it was doing.
          pill: null,
          // The Postgres version IS in the payload, so it takes the space instead of a fabricated state.
          note: p.pgVersion ? `v${p.pgVersion}` : null,
        };
      },
    },
    {
      key: "jobs", label: "Jobs", items: jobs as Resource<unknown[]>,
      empty: "No jobs yet. Ask the agent to build one, or open Databricks.",
      // The row shows the SCHEDULE's pause state, which `jobs/list` does carry. It does not show a run
      // state: that needs one call per job, and a rail that fans out is a rail that takes 40 s on a slow
      // workspace ([RB-7], the systems lens's argument).
      row: (item: never) => {
        const j = item as JobRow;
        return {
          doc: makeDoc("job", String(j.job_id ?? ""), j.name || undefined),
          icon: "▶", kind: "job",
          pill: j.paused ? { word: "paused", tone: "quiet" }
            : (j.schedule ? { word: "scheduled", tone: "good" } : null),
          note: j.schedule?.cron ?? null,
        };
      },
    },
    {
      key: "pipelines", label: "Pipelines", items: pipelines as Resource<unknown[]>,
      empty: "No pipelines yet. A pipeline needs a catalog and a schema to publish into.",
      // The word comes from the LAST UPDATE (`word`), the field that answers "is it working?". A
      // pipeline's own `state` is `IDLE` for both "never run" and "the last run failed" ([PIPE-5]).
      row: (item: never) => {
        const p = item as PipelineRow;
        return {
          doc: makeDoc("pipeline", p.pipeline_id, p.name || undefined),
          icon: "▦", kind: "pipeline",
          pill: { word: p.word, tone: p.tone },
          note: null,
        };
      },
    },
    {
      key: "apps", label: "Databricks Apps", items: apps as Resource<unknown[]>,
      empty: "No apps yet. Ask the agent to build one.",
      row: (item: never) => {
        const a = item as AppView;
        const word = appStateWord(a.state);
        return {
          doc: makeDoc("app", a.name),
          icon: "▢", kind: "app",
          pill: { word, tone: tone(word) },
          note: null,
        };
      },
    },
  ];

  const busy = groups.some((g) => g.items.state === "loading" || g.items.refreshing);
  const retry = () => groups.forEach((g) => g.items.reload());

  return (
    <div className="tree data-tree">
      <div className="tree-search">
        <div className="tree-hint">Databases, jobs, pipelines and apps you can see</div>
        <button className="icon-btn tree-refresh" title="Refresh" aria-label="Refresh every group"
          disabled={busy} onClick={retry}>
          <Refresh size={15} className={busy ? "spin" : ""} />
        </button>
      </div>

      {/* ONE message for one cause, across all four groups. Four calls behind two APIs fail together when
          a permission is missing, and four identical boxes read as four problems ([E-23], 013's [UI-6]). */}
      {errorBoxes(...groups.map((g) => ({ state: g.items.state, error: g.items.error }))).map((e) => (
        <PaneError key={e} message={e} onRetry={retry} />
      ))}

      <div role="tree" aria-label="Databases, jobs, pipelines and apps" className="tree-body">
        {groups.map((group) => {
          const rows = (group.items.data ?? []) as unknown[];
          return (
            <div key={group.key} className="tree-group-block">
              <div className="tree-group">
                {group.label}
                {rows.length > 0 && <span className="tree-group-count">{rows.length}</span>}
              </div>
              {group.items.state === "loading" && group.items.data === undefined && <Skeleton />}
              {group.items.state === "ready" && rows.length === 0 && (
                <div className="tree-empty">{group.empty}</div>
              )}
              {group.items.state === "error" && rows.length === 0 && (
                <div className="tree-empty">Could not read {group.label.toLowerCase()}.</div>
              )}
              {rows.map((item) => {
                const row = group.row(item as never);
                return (
                  <button key={row.doc.id} role="treeitem" aria-selected={selected === row.doc.id}
                    className={`tree-row data-row${selected === row.doc.id ? " is-selected" : ""}`}
                    onClick={() => onOpen(row.doc)}
                    title={`${row.doc.ref}${row.note ? `\n${row.note}` : ""}`}>
                    <span className={`tree-icon kind-${row.kind}`} aria-hidden>{row.icon}</span>
                    <span className="tree-name">{row.doc.name}</span>
                    {row.note && !row.pill && <span className="infra-tag quiet">{row.note}</span>}
                    {row.pill && (
                      <span className={`infra-pill tone-${row.pill.tone}`}>{row.pill.word}</span>
                    )}
                  </button>
                );
              })}
            </div>
          );
        })}
      </div>
      <p className="tree-note">Only objects your account may see are listed.</p>
    </div>
  );
}

function Skeleton() {
  return (
    <div className="sk-list" role="status" aria-label="Loading">
      {[0, 1].map((i) => (
        <div className="sk-row" key={i}><span className="sk a" /><span className="sk b" /></div>
      ))}
    </div>
  );
}

/** The distinct failures to show, as a short list.
 *
 *  Calls that fail for one cause get one box: two groups asking APIs the app is not authorized for fail
 *  with the same sentence, and rendering it twice (which the deployed app did in 013) reads as two
 *  problems. A message that DIFFERS is kept, because two faults are two things to fix.
 *
 *  Pure and exported so the collapsing is testable without a browser.
 */
export function errorBoxes(
  ...loads: { state: string; error?: string }[]
): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const load of loads) {
    if (load.state !== "error" || !load.error) continue;
    if (seen.has(load.error)) continue;
    seen.add(load.error);
    out.push(load.error);
  }
  return out;
}
