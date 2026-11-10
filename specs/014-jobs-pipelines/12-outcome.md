[Index](README.md) · prev: [11 E2E plan](11-e2e-plan.md) · next: [Coherence check](13-coherence.md)

# 12 · Outcome

Written last, from the running app. What shipped, what the tests hold, and — the useful part — what
looking at the screenshots found that every assertion had passed.

Counts are read from the last run on this machine, not remembered:

| Suite | Result |
|---|---|
| Python | **1 056 passed, 7 skipped** (was 797 before this spec: +259) |
| Front end | **951 passed in 68 files** (was 749 in 64: +202) |
| E2E | **9/9 scenes**, every screenshot inspected |
| Spec ASCII | 9 blocks, 13 boxes, **0 problems** |
| Spec Mermaid | **10 diagrams, 0 failing to parse** |
| Spec links | 14 documents, 90 internal links, **0 problems** |
| **Deployed** | **18/18 checks against the live dev app**, 0 skipped |

## Deployed and verified

The dev workspace (`dbc-cb61f1e1-bd8e`) builds from **git**, so the deployment is the commit, not the
working tree: `4c50ede` on `main`, resolved by the platform and read back from the deployment record.

The first deploy was verified by a check that ran nothing — `verify-deployed.sh` skipped every HTTP probe,
because a personal access token cannot pass the app's OAuth proxy, and the platform API cannot read the
app's logs with a PAT either. "Deployment SUCCEEDED" is precisely the answer that was true three times
while the app served none of the work.

So the check was made real rather than accepted. An OAuth token for the workspace was minted through the
account's SSO, and `verify-deployed.sh` gained spec 014's fingerprints:

| Check | Result |
|---|---|
| `/api/jobs` and `/api/pipelines` are served | `{"items":[],"identity":"the app's service principal"}` |
| the state vocabulary is live, not just the routing | a `RUNNING` run reads `running`, `cancel: true`, `repair: false` |
| …and the other half of the matrix | a `TERMINATED`+`FAILED` run reads `failed`, `repair: true`, `cancel: false` |
| the browser has no write path | `POST /api/jobs/1` → **405**, `POST /api/pipelines/abc` → **405** |
| the served front end is this commit | the bundle is **byte-identical** to a local build from `4c50ede` |
| a real session starts | the default model works |

**18 passed, 0 failed, 0 skipped.** The third and fourth rows are the ones worth having: they are computed
server-side by `api.domain.jobs`, so they cannot be true of a tree that predates this spec — which is what
makes them proof rather than a health check.

One defect was found *by doing this*. The workspace probe's first version accepted any non-404 as
"served", so four routes reported `PASS` with `HTTP 401` from the proxy while no handler had run — a loose
assertion proving a looser thing. A `401`/`403` is now a **skip that says so**, never a pass. Deploying is
the only way to find that class of mistake: locally every one of those routes answers 200.

Not deployed, and said so: the app's own **logs** need an OAuth login that a PAT cannot provide, so no log
line was read from this session. The verification above does not depend on one.

---

## What is true now that was not

### The tool the agent calls

* **Jobs are spoken in API 2.2.** Queueing is on by default there and off in 2.1, so before this the same
  job created by the agent and by the UI were different objects. The create body now also states
  `queue: {enabled: true}` so the behaviour does not rest on a version default that can change again.
* **A malformed task graph is refused with zero HTTP calls**, naming every problem in one sentence: a
  duplicate key, a dependency on a task that does not exist (with the near-miss named: *"did you mean
  'silver'?"*), two task types on one task, or a cycle named as a path. Before, each of those reached the
  platform and came back as a `400` the model paraphrased as "the job failed" — while nothing had been
  created.
* **Running a job is idempotent.** `run-now` carries an `idempotency_token` derived from (session, job,
  purpose), and the tool reports `reused: true|false` by comparing the newest run before and after. Two
  identical calls make one run; a deliberate re-run with `purpose="retry-after-fix"` makes a second.
* **Pipelines can be built.** Five tools: create (serverless, Unity Catalog, `ADVANCED`), status (with the
  last three updates **and** events in one object), start (incremental, full refresh, or `validate_only`),
  stop, and edit. `dbx_list_pipelines` now carries each pipeline's **last update's** state, because
  `IDLE` means both "never run" and "the last run failed".
* **`dbx_job_failure_context`** assembles the failing task, its error, the tables its notebook reads with
  their **real** columns, and the last good duration — one answer where a model would otherwise make three
  calls and has three chances to conclude "the job is broken" when the truth is "the column was renamed".
* **The tool budget is 28, with a reason.** Three Lakebase scaffold calls left `core` (each named by a
  skill, so still discoverable); one tool was added for jobs, five for pipelines. The test that held `==
  25` now asserts `<= 28`, that every member is reachable from a page or a skill, and that every departing
  tool is named by a skill — which is the only thing that makes a removal safe.

### The surfaces

* **Three new document kinds** — `job`, `pipeline`, `run` — so the compiler named every place that had to
  handle them. Eight kinds, each with a route, a palette group, a recent entry, an action set, a dock
  suggestion set, and a page.
* **A job page whose header carries the last run's outcome**, in five blocks ordered by the question a user
  asks first. The task graph is drawn in **levels** by the same function the tool validates with, so a
  graph the validator accepted cannot render as cyclic — and a cyclic one renders as a refusal, never as a
  partial picture.
* **A run page** with every task's own word, the platform's exception quoted, and a Repair that appears only
  after a failure. A task that has not started reads `not started`, never `running`.
* **A pipeline page whose header follows the last update**, three start modes each labelled with its cost,
  and Stop **absent** (not disabled) when nothing is active.
* **The `Data` tab lists four groups** through one hook and one table, so the fifth group is a row rather
  than a fourth copy of the same `useState`/`useEffect`/renderer.
* **No write route.** Every action — run, resume, cancel, repair, start, stop — goes through the agent, so
  the write fence has one home. `test_infra_routes.py` asserts the route table has no `POST` under
  `/api/jobs` or `/api/pipelines`, which is the version of that decision that survives a contributor with a
  good reason.

---

## What looking at the pictures found

Six defects, each with the screenshot that showed it. Three of them coexisted with **passing** assertions,
which is the argument for this step existing.

| # | Defect | Found by | The fix |
|---|---|---|---|
| 1 | A refusal was stated **five times**, once per block, on a page whose read had failed | S6's first picture | one page-level statement + a block's own sentence only when it differs |
| 2 | After (1), one call site was **missed**, so `Settings` repeated the sentence under the banner | S6's second picture | `Block` gained a fifth state, `unread`; the guard is now a count of error boxes, not a per-block check |
| 3 | With the repetition gone, every block fell back to its **empty** sentence — "This job has not run yet", "No runs in this job's history" — two **claims** a failed read cannot support | S6's third picture | each block says what it could not read; `unread` exists so `empty` can never be reused for it |
| 4 | The palette could only find **open** documents: a job you had just looked at and closed was unreachable by name | S9 | the palette lists recently-opened infrastructure objects as well as open tabs |
| 5 | A job rendered as a **file** in the mission's outputs (`notebook ? <Notebook/> : <FileIcon/>`, a two-way branch from when there were three kinds) | S7 | `artifactIcon()` maps every kind |
| 6 | The run page named **no job**, so a pasted `#/run/<id>` was a bare number | S3 | the adapter resolves the job's name through the job cache, which costs nothing when the run is opened from its job |

Two more were found by tests before any picture:

* **A page could not state a page-level refusal at all.** `Block` renders `error` only when its state says
  so, and the job page's state expression fell through to `empty` on a page-level failure — the sentence was
  passed as `error` and never shown. The `blockState()` helper now takes the page's state, the block's own
  error, and whether it is empty, so the four outcomes cannot disagree between blocks.
* **Two cross-page controls dispatched events nobody listened to** — `opengenie:open-lakebase` from 013's app
  page and `opengenie:open-job` from this spec's run page. A dead dispatch renders an ordinary button, so
  only a test finds it. `docFromOpenEvent` is now one mapping with a test that names both events, and the
  listener in `App.tsx` calls it through a ref so it always uses the live `openDoc`.

Defect 1 is the one worth dwelling on: **every assertion passed.** "The platform's sentence is verbatim" ✓,
"no retry is offered" ✓, "the refusal is in the block that failed" ✓. The screen still read as five
problems. That is 013's [UI-6] rule — one statement per fact — and it took a person looking at the image to
see it. Defect 3 is the same class from the other direction: the page was saying things it did not know.

---

## What is not done, and why

| Not done | Why |
|---|---|
| The fixtures are **not** a recording of a live workspace | They are the documentation's field lists plus 013's measured shapes for adjacent APIs. [11](11-e2e-plan.md) records the required manual check — one run against a real workspace, compared field by field — and it is a **required** check, not a nice-to-have. A fixture that drifts from the platform is a test that passes forever |
| No visual DAG editor, cron builder, or log viewer | Each is a product of its own; `04` §What is deliberately absent says so and the Databricks link is the escape hatch |
| A job a **person** created in the UI may not be readable | `[RB-2]`: a Job app resource binds one job id, which cannot exist before the agent creates the job. Jobs the app created are readable because the service principal owns them; others show a refusal that names the remedy |
| `dbx_pipeline_edit` is in `full`, not `core` | An edit is a step a skill describes, not a call a model must make unprompted — the same reasoning that let three Lakebase calls leave `core`. `etl-pipelines` names it |
| The classic-compute pipeline is refused | `[TOOL-7]` creates serverless only, and says so with the alternative. `clusters` alongside `serverless` is a platform `400` whose text does not say which one this product wants |

---

## The four sentences this ends with

1. **A run is the proof.** Every page leads with what happened, not with what was configured. A job that
   has never run says so; it never shows a green tick on a schedule that has never fired.
2. **The honest field, not the convenient one.** `run_word(life_cycle, result)` and
   `pipeline_word(state, last_update)` are pure functions over the whole payload, held to one fixture by
   both runtimes. `TERMINATED`+`FAILED` is a failure; `IDLE`+`FAILED` is a failed pipeline.
3. **Every control that spends money says so.** Run now names the compute and the last duration. Full
   refresh names what it re-reads. Resuming a schedule is the only control that creates an unbounded future
   cost, so it is the only one with a confirmation.
4. **A page that could not read something says that, and nothing else.** Not "no runs": *"the run history
   could not be read"*. The distinction is the whole spec in one sentence, and it is the defect that
   looking at the screenshots found last.

## Where to start reading, if this is your first visit

[02](02-assessment.md) for the eleven findings with line numbers · [10](10-roadblocks.md) for why the app
cannot call Jobs as the user, which decides the architecture · [13](13-coherence.md) for the six places the
spec was wrong before implementation · [e2e/screenshots](e2e/screenshots/README.md) for what it looks like
and what the pictures found.
