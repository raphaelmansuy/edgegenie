/** The Data rail tab: Lakebase projects and Databricks Apps, and nothing else.
 *
 * A fourth tab rather than a folder in Files or a section in Catalog, and the reason is a mental
 * model: a project is not a workspace path (Files would need a fake one) and not Unity Catalog
 * (Catalog is governed by a different API). The two object types share a lifecycle — build, run,
 * verify — which is what a tab is for (spec 013 [UI-2], [06 §2.3]).
 *
 * One call per kind, no fan-out: this lists on every page load ([06 §6.1]).
 */
import { useEffect, useState } from "react";
import { api, type LakebaseProject, type AppView } from "../api/client";
import { appStateWord, tone } from "../domain/app";
import { makeDoc, type Doc } from "../domain/docs";
import { PaneError } from "./PaneError";
import { Refresh } from "./Icons";

type Load<T> = { state: "loading" | "ready" | "error"; data: T; error?: string };

export function DataTree({ onOpen, selected }: {
  onOpen: (d: Doc) => void;
  /** The `docId` of the open document, so the row can mark itself. */
  selected: string | null;
}) {
  const [projects, setProjects] = useState<Load<LakebaseProject[]>>({ state: "loading", data: [] });
  const [apps, setApps] = useState<Load<AppView[]>>({ state: "loading", data: [] });
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let live = true;
    setProjects({ state: "loading", data: [] });
    setApps({ state: "loading", data: [] });
    api.lakebaseProjects()
      .then((r) => live && setProjects({ state: "ready", data: r.items }))
      .catch((e) => live && setProjects({ state: "error", data: [], error: e instanceof Error ? e.message : "cannot read Lakebase" }));
    api.apps()
      .then((r) => live && setApps({ state: "ready", data: r.items }))
      .catch((e) => live && setApps({ state: "error", data: [], error: e instanceof Error ? e.message : "cannot read Apps" }));
    return () => { live = false; };
  }, [tick]);

  const retry = () => setTick((n) => n + 1);
  const busy = projects.state === "loading" || apps.state === "loading";

  return (
    <div className="tree data-tree">
      <div className="tree-search">
        <div className="tree-hint">Lakebase databases and apps you can see</div>
        <button className="icon-btn tree-refresh" title="Refresh" aria-label="Refresh Lakebase and apps"
          disabled={busy} onClick={retry}>
          <Refresh size={15} className={busy ? "spin" : ""} />
        </button>
      </div>

      {/*
        ONE message for two failed calls. The screenshot of the deployed app showed this pane with
        the identical "Your sign-in needs refreshing" box twice — once for the projects call and once
        for the apps call — because both fail for the same reason (one missing scope). Two copies of
        one fact read as two problems, and a user cannot tell whether fixing one is enough
        (spec 013 [UI-6]: one statement per fact, which is the rule [012] applied to the dock).

        Identical messages collapse to one. DIFFERENT messages stay separate, because two distinct
        faults are genuinely two things to fix.
      */}
      {errorBoxes(projects, apps).map((e) => (
        <PaneError key={e} message={e} onRetry={retry} />
      ))}

      <div role="tree" aria-label="Lakebase and apps" className="tree-body">
        <div className="tree-group">Lakebase</div>
        {projects.state === "loading" && <Skeleton />}
        {projects.state === "ready" && projects.data.length === 0 && (
          <div className="tree-empty">No projects yet. Ask the agent to create one.</div>
        )}
        {projects.data.map((p) => {
          const doc = makeDoc("lakebase", p.ref, p.displayName || p.name);
          return (
            <button key={p.ref} role="treeitem" aria-selected={selected === doc.id}
              className={`tree-row data-row${selected === doc.id ? " is-selected" : ""}`}
              onClick={() => onOpen(doc)}
              title={`${p.ref}${p.owner ? `\nowner ${p.owner}` : ""}`}>
              <span className={`tree-icon kind-lakebase`} aria-hidden>▤</span>
              <span className="tree-name">{p.displayName || p.name}</span>
              {/*
                NO state pill, and that is the correction. A Lakebase PROJECT has no state field:
                measured, neither the get nor the list payload carries one, because readiness belongs
                to a branch and a compute. This used to render `p.ready ? "ready" : "busy"`, so every
                project showed a green "ready" whatever its real state was — a fabricated fact, which
                is worse than no fact (spec 013 [RB-12]).
                The Postgres version is real in the same payload, so it takes the space instead.
              */}
              {p.pgVersion ? <span className="infra-tag quiet">v{p.pgVersion}</span> : null}
            </button>
          );
        })}

        <div className="tree-group">Databricks Apps</div>
        {apps.state === "loading" && <Skeleton />}
        {apps.state === "ready" && apps.data.length === 0 && (
          <div className="tree-empty">No apps yet. Ask the agent to build one.</div>
        )}
        {apps.data.map((a) => {
          const doc = makeDoc("app", a.name);
          return (
            <button key={a.name} role="treeitem" aria-selected={selected === doc.id}
              className={`tree-row data-row${selected === doc.id ? " is-selected" : ""}`}
              onClick={() => onOpen(doc)}
              title={`${a.name}\n${a.state}`}>
              <span className="tree-icon kind-app" aria-hidden>▢</span>
              <span className="tree-name">{a.name}</span>
              <span className={`infra-pill tone-${tone(appStateWord(a.state))}`}>{appStateWord(a.state)}</span>
            </button>
          );
        })}
      </div>
      <p className="tree-note">Only databases and apps your account may see are listed.</p>
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
 *  Two calls, one cause, one box: projects and apps both ask the Postgres and Apps APIs, so a single
 *  missing scope fails both with the same sentence. Rendering it twice (which the deployed app did)
 *  reads as two problems. A message that DIFFERS is kept, because two faults are two things to fix.
 *
 *  Pure and exported so the collapsing is testable without a browser. */
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
