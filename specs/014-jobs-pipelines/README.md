# 014 · Jobs and pipelines as first-class surfaces

**Status:** specification, implementation plan, and implementation · 10 November 2026
**Built and running.** Two pure modules, two adapters, one router, five new tool tools plus one rewritten,
three front-end pages, four new components, two skills touched. **1 055 Python tests, 951 front-end tests,
9/9 E2E scenes**, and every screenshot inspected — the [outcome](12-outcome.md) records the six defects the
pictures found, three of which passed their assertions first.
**Scope:** the two Databricks object types a data engineer schedules and operates — **Lakeflow Jobs** and
**Lakeflow Spark Declarative Pipelines** — from the tool the agent calls, through the API, to the screens
the user reads. Not the agent runtime (001), not the notebook model (010), not Lakebase or Apps (013), not
the deployment of this app itself (017/021). Cited, not restated.

> **The report this starts from.** OpenGenie already has a card that says *"Create a job that
> recomputes daily revenue at 06:00 after a dependency task, run it once, and prove the run
> succeeded."* The agent can call `dbx_create_job` and `dbx_run_job`, so half the promise is real. The
> other half is not: there is no screen that names a job, no way to open a run, no way to see the task
> graph the agent built, and no way to cancel a run that is burning cluster time. The turn ends with a
> JSON blob in the transcript, and the run id in it is a dead end — nothing in the product can be
> clicked to reach it.

---

## What this folder is

| # | Document | Answers |
|---|---|---|
| 01 | [Five whys and first principles](01-five-whys.md) | Why is "make me a job" a turn that ends in prose rather than a working, openable workflow? |
| 02 | [Measured assessment](02-assessment.md) | What is actually wrong: file, line, and what the platform actually says |
| 03 | [Requirements](03-requirements.md) | What must be true when it is done (`JOB-*`, `PIPE-*`, `RUN-*`, `UI-*`, `TOOL-*`) |
| 04 | [Wireframes (ASCII)](04-wireframes.md) | Every screen, every state, every recovery path |
| 05 | [Diagrams (Mermaid)](05-diagrams.md) | Sequence, state and E/R: the workflows drawn out |
| 06 | [Lenses](06-lenses.md) | The same work seen by seven owners |
| 07 | [Architecture](07-architecture.md) | Where each rule lives, and why there |
| 08 | [Implementation plan](08-implementation-plan.md) | Phases, files, tests, order |
| 09 | [Edge cases](09-edge-cases.md) | Every failure I could name, its mitigation, its test |
| 10 | [Roadblocks](10-roadblocks.md) | What is in the way, grounded in code, and the way past each |
| 11 | [E2E plan](11-e2e-plan.md) | Scenes, screenshots, pass criteria |
| 12 | [Outcome](12-outcome.md) | What shipped, and what the screenshots found |
| — | [Coherence check](13-coherence.md) | The spec against the code, line by line, before implementation |
| — | [E2E screenshots](e2e/screenshots/README.md) | What it actually looks like, each one inspected |

Cross-references: a requirement is `[JOB-3]`, an edge case `[E-12]`, a scene `[S4]`, a roadblock
`[RB-5]`. Each id is defined once — in `03`, `09` or `10` — and cited everywhere else. A citation that
is not defined in one of those three is a bug in this document set. Findings `F1`–`F11` are the
exception: they are the *evidence*, defined in [02](02-assessment.md), and cited without brackets so
they cannot be confused with a defined id.

Builds on:
[001](../001-databricks-coding-agents/README.md) the app, its ports and its fence ·
[006](../006-databricks/README.md) Genie Code parity ·
[010](../010-long-running/README.md) durable sessions ·
[011](../011-ux-coding-mission/README.md) the mission view ·
[013](../013-improve-coding/README.md) the `Data` rail tab, the two infrastructure pages, and the
`Block` component this spec reuses instead of re-inventing.
It replaces none of them. It finishes a workflow the product already advertises and then stops.

---

## The one sentence

> A turn that creates a job or a pipeline must end with an object the user **can open, read the
> schedule of, run, watch, cancel, and compare across runs** — or say in one sentence what blocked it
> and what they can do about it.

Today it ends with text. `dbx_create_job` returns `{"job_id": 8123…}` and the product has no surface
that can render a job id.

## The finding, in one table

Every row was measured against the code in this checkout and against the platform documentation
fetched on 10 November 2026, not remembered.

| # | Finding | Evidence | Kind |
|---|---|---|---|
| **F1** | `dbx_create_job` speaks **Jobs API 2.1**. The current API is **2.2**, and 2.2 changes a default that matters: **queueing is on by default** for jobs created through 2.2, off for 2.1. A job created by this tool is therefore a *different object* from the same job created today in the Databricks UI. | `tools/databricks_notebook_mcp.py:1094`; Jobs API 2.2 update reference | **defect** |
| **F2** | `dbx_run_job` calls `/api/2.1/jobs/run-now`. It sends `{"job_id": …}` only: no `idempotency_token`, so a retried call starts a **second** run of a job that costs money per run. The server's `_retry` helper does not retry a POST, which hides the risk in this call site and leaves it in the next one. | `tools/databricks_notebook_mcp.py:1107`; `_retry` at `:276-296` | **defect** |
| **F3** | `dbx_create_job` builds tasks from `t["task_key"]` with no validation. A duplicate key, a `depends_on` naming a task that does not exist, or a cycle makes the platform answer `400 INVALID_PARAMETER_VALUE` — a sentence the agent then paraphrases as "the job failed", which is wrong: **nothing was created**. | `tools/databricks_notebook_mcp.py:1082-1090` | **defect** |
| **F4** | There is **one** pipeline tool, `dbx_list_pipelines`, and it is a read. Nothing can create a pipeline, edit one, start an update, read an update's state, or stop one. The `etl-pipelines` skill tells the agent to orchestrate with a *job of notebooks* instead — so "make me a pipeline" produces a job, and the user's Lakeflow lineage never exists. | `tools/databricks_notebook_mcp.py:1122-1129`; `tools/skills/etl-pipelines.md` | **gap** |
| **F5** | `dbx_list_pipelines` reads `data["statuses"]` and `p.get("state")`. The list payload's `state` is the **pipeline's** state (`IDLE`, `RUNNING`, `FAILED`, …), which is not a *run's* result. So the tool cannot answer "did the last update succeed?", which is the only question a user has. | `tools/databricks_notebook_mcp.py:1126-1128`; Pipelines API `statuses[].state` | **defect** |
| **F6** | `dbx_list_jobs` returns `job_id`, `name` and a cron expression. It does **not** return the latest run's state, though its own docstring says *"jobs with their latest run state"* — a comment that lies about the payload. And the tool is **not in `core`**: `registry.start` runs every session at `NBMCP_PROFILE=core`, so an agent can *create* a job and cannot *enumerate* one. | `tools/databricks_notebook_mcp.py:861-873` vs `:862`; `_CORE` at `:75-87`; `api/adapters/mcp/registry.py:55` | **defect** |
| **F7** | `DocKind` is `"notebook" \| "file" \| "table" \| "lakebase" \| "app"`. There is no kind for a job, a pipeline or a run. The route grammar, the recent list, the palette groups, the dock suggestions, the `touched()` reducer and the `ACTIONS_FOR` table all enumerate that union, so a job cannot be opened even if a page existed. | `web/src/domain/docs.ts:8`; `route.ts:20`; `recent.ts:14`; `dock.ts:104-121`; `App.tsx:77-79` | **gap** |
| **F8** | `touched()` reads an object out of a tool call's arguments for notebooks, files, tables, Lakebase projects and apps. The job tools return `{"job_id": …}` and the pipeline tools would return `{"pipeline_id": …}`, and **nothing** reads either. The consequence: after the agent creates a job, the transcript has no clickable object and no open tab — the same defect 013 found for Lakebase ([F5] there), one object type later. | `web/src/domain/docs.ts:83-112` | **gap** |
| **F9** | The `Data` rail tab lists Lakebase projects and Databricks Apps, in two hard-coded groups. Jobs and pipelines belong in the same tab — same lifecycle (build → run → verify), same cost model — but the component's two `useEffect` calls are wired to two endpoints and its `role="tree"` has two group headings. | `web/src/components/DataTree.tsx:24-49` | **gap** |
| **F10** | **`jobs` and `pipelines` are not grantable user-authorization scopes.** The supported list is `ai-functions`, `ai-gateway`, `apps`, `files`, `genie`, `model-serving`, `postgres`, `sql`, `vector-search`, `sql:restricted-query` plus five SDK scopes. The platform's own remedy is a **Job app resource** (`CAN_VIEW` / `CAN_MANAGE_RUN` / `CAN_MANAGE`), bound to the app's service principal. The tool server already knows this: the comment at `:1031` says *"A Databricks App's user authorization has no jobs scope"* — and nothing acts on it. | `tools/databricks_notebook_mcp.py:1029-1036`; Databricks Apps auth docs "Supported scopes"; Lakeflow-Jobs app resource docs | **roadblock** |
| **F11** | The job tools are **absent from the `core` profile**: `_CORE` lists `dbx_create_job`, `dbx_run_job` and `dbx_job_run_status`, but the registry starts every session with `NBMCP_PROFILE=core`, and the set is capped at 25 by a test. Adding six job tools and six pipeline tools without removing anything makes 37 and fails that test — so the tool budget is a real constraint on this design, not a style note. | `tools/databricks_notebook_mcp.py:75-87`; `api/adapters/mcp/registry.py:55`; `tests/test_tools_fence.py:208-212` | **roadblock** |

F1, F2, F3, F5 and F6 are defects: the tools exist and answer something subtly untrue. F4, F7, F8 and
F9 are the gap: the product can *change* a schedule it cannot *show*. F10 and F11 are the roadblocks
that decide the architecture, and they are why this spec reads differently from 013.

## What is *not* wrong

Worth stating, because the fix must not disturb it.

| Works today | Where |
|---|---|
| The write fence's server-side prefix for job names: `NBMCP_WRITE_JOB_PREFIX`, enforced in `dbx_create_job` and `dbx_run_job` | `tools/databricks_notebook_mcp.py:1073`, `:1106` |
| The `Scope` the app computes per session (`job_prefix`, `app_prefix`, `instance_prefix`), passed to the tool server by `registry.start` | `api/domain/scope.py:44-59`; `api/adapters/mcp/registry.py:60-67` |
| Run polling that returns per-task exit values and error text, and stops at a terminal state | `tools/databricks_notebook_mcp.py:876-923` |
| The app's error contract: `PermissionError → 403`, `LookupError → 404`, `ValueError → 422`, `RuntimeError → 502` | `api/routers/api.py:498-512`; `api/adapters/databricks/http.py` |
| `Block`, `Fact`, `StatePill` and `isPermanent(error)` — one component, four states, no retry on a permanent refusal | `web/src/components/Infra.tsx` |
| The scaffold scorecard: a step is `done` only when a completed call returned its proof field | `web/src/domain/scaffold.ts`; `api/domain/scaffold.py`; `web/src/domain/scaffold-steps.json` |
| The `Data` tab as the home for infrastructure objects, and `⌘4` | `web/src/components/DataTree.tsx`; `web/src/domain/keys.ts:127` |

The asymmetry is the point of the whole spec: this app is excellent at **running a notebook** and at
**proving a claim**, and it treats a scheduled job as a notebook that happened to be triggered.

## The five principles this rests on

1. **A run is the proof, not the job.** "I created a job" is a configuration change. "It ran at 06:00
   and task `gold` returned 1 234 rows" is the fact the user asked for. So the unit the product shows
   is a *run*, and the job page's headline is its last run's outcome — never a green tick on a
   schedule that has never fired.
2. **A state word is derived from the terminal field, not from the field that is available.** Jobs
   report `life_cycle_state` **and** `result_state`, and only the second one distinguishes `SUCCESS`
   from `FAILED` — a run that failed is `TERMINATED` + `FAILED`. Pipelines report a pipeline state
   (`IDLE`) *and* a list of updates with their own states (`COMPLETED`, `FAILED`). Reading the
   convenient field is exactly the defect 013's [RB-12] recorded for Lakebase.
3. **Every control that spends money says what it spends it on.** "Run now" starts compute. "Full
   refresh" re-reads every source. A button that can cost a cluster-hour is labelled with its
   consequence, and a destructive one (stop an update, delete a run) asks first — the rule
   `[012]` made for scroll and `[013]` made for retry, applied to spend.
4. **The platform's refusal is the message, and it usually names a person.** `PERMISSION_DENIED`,
   `CAN_MANAGE_RUN`, a pipeline that needs `ADVANCED` edition, a workspace that has not accepted the
   serverless terms: each is a sentence the platform wrote, and repeating it verbatim with one action
   beside it beats any paraphrase we invent.
5. **A tool with no surface is half a tool.** `dbx_create_job` has existed since the first release and
   the product has never shown a job. Either an object is openable, or creating it is not offered.

Everything below is an argument about those five sentences.

---

## Reading order for a reviewer short on time

1. [02 Measured assessment](02-assessment.md) — the eleven findings with line numbers. Ten minutes.
2. [10 Roadblocks](10-roadblocks.md) — why the app cannot call Jobs "as the user", and what the
   platform provides instead. This decides the architecture; read it before 07.
3. [13 Coherence check](13-coherence.md) — the spec against the code, before a line was written.
4. [08 Implementation plan](08-implementation-plan.md) — the order, and what each phase proves.
5. [12 Outcome](12-outcome.md) — written last, from the running app, with the screenshots.

## The implementation, in one table

| Phase | What it made true | Gate |
|---|---|---|
| 1 | the tool server speaks Jobs **2.2**, is **idempotent** on run, and refuses a malformed task graph **before** it calls the platform | `test_job_graph.py`, `test_jobs_tools.py` |
| 2 | pipelines are a real tool surface: create, start, read an update, stop, edit, and read events | `test_pipelines_tools.py`, `test_pipeline_adapter.py` |
| 3 | the app can **read** both objects as the identity that may see them, and the fence is true | `test_jobs_adapter.py`, `test_infra_routes.py` |
| 4 | the user can **see and open** them: three new document kinds, a `Data` tab with four groups, three pages | `route.test.ts`, `JobsPages.test.tsx`, `tsc` |
| 5 | it **looks right and fails gracefully**: nine E2E scenes, every screenshot inspected | `jobs-e2e.mjs` 9/9 |
