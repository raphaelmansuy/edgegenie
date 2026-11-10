[Index](README.md) · prev: [07 Architecture](07-architecture.md) · next: [09 Edge cases](09-edge-cases.md)

# 08 · Implementation plan

Five phases. Each one ends with a **gate** that fails on the previous tree, which is the only thing that
makes a phase a phase rather than a folder of edits. The order is forced: a page cannot be written
before there is a route to read, and a route cannot be tested before the tool that creates the object.

Nothing here is a rewrite. Every phase extends a seam that exists.

---

## The phases at a glance

| Phase | What it makes true | Gate (fails on the old tree) | Files |
|---|---|---|---|
| **1** | the job tools speak 2.2, are idempotent, and refuse a bad graph before the platform sees it | `test_job_graph.py`, `test_jobs_tools.py` | 2 new, 1 edited, 1 skill |
| **2** | a pipeline can be created, started, read, stopped and edited | `test_pipelines_tools.py`, `test_pipeline_body.py` | 2 new, 2 edited |
| **3** | the app can **read** both objects, and the fence is true of both | `test_jobs_adapter.py`, `test_infra_routes.py`, `test_fence_parity.py` | 6 new, 3 edited |
| **4** | the user can **open** them: three kinds, four rail groups, three pages | `route.test.ts`, `docs.test.ts`, `JobsPages.test.tsx`, `tsc` | 8 new, 9 edited |
| **5** | it **looks right** and fails gracefully under nine scenes | `jobs-e2e.mjs` 9/9, every screenshot inspected | 2 new, 1 fixture |
Totals: **26 new files, 16 edited, 2 skills rewritten.** No file is rewritten wholesale except the two
skills, which exist to be rewritten.

---

## Phase 1 · The job tools, corrected

**Why first.** Phases 3–5 read what these tools write. A page built on 2.1 semantics would show a
schedule whose queueing behaves differently from the one the user sees in the Databricks UI, and that
difference would be attributed to the page.

### 1.1 · `_validate_graph` — the graph rule, pure and testable

**New:** `tools/job_graph.py` — a module with no I/O, imported by the tool server. It is a separate
module, not three functions inside an 1 815-line file, because the app needs the same rule for its own
classification and a 1 815-line file cannot be imported by a test without importing MCP.

```python
# tools/job_graph.py  (sketch, not final)
TASK_TYPES = ("notebook_path", "python_file", "sql_file", "pipeline_id", "job_id")

def validate(tasks: list[dict]) -> str | None:
    """The first problem with a task list, as one sentence, or None.

    Checks, in this order, because the first failure is the one worth reporting:
      1. at least one task
      2. every task_key is present, well-formed and unique
      3. every depends_on names a task in this list
      4. exactly one task type per task
      5. no cycle (Kahn, O(v + e))
    """
```

**Test:** `tests/test_job_graph.py` — a table per rule, each asserting the sentence contains the
offending key. Plus one property test that a cycle of length 2 and one of length 5 both name the whole
cycle.

**Why a separate file and not inline.** `[TOOL-3]`'s rule is also `[JOB-3]`'s renderer input: the page
shows the graph the tool validated. If the page used a different `taskLevels`, a job that the validator
accepted could render as cyclic — or worse, a cyclic job could render cleanly. One algorithm, one module,
two importers, and `test_job_graph.py` asserts the two agree on a table of shapes.

### 1.2 · `dbx_create_job` — 2.2, validated, queued explicitly

**Edit** `tools/databricks_notebook_mcp.py`:

* `/api/2.1/jobs/create` → `/api/2.2/jobs/create`;
* call `validate()` **before** the first `_check_path_scope`, and return the sentence on failure;
* add `queue: {"enabled": True}` and `performance_target: "STANDARD"` to the body — the first because
  2.2's default is silent, the second because serverless cost is a product decision and not a platform
  default;
* keep `pause_status: "PAUSED"` (already correct) and say so in the return payload as
  `"schedule": {"cron": …, "timezone": …, "pauseStatus": "PAUSED"}`, not the string `"created PAUSED"`
  the page cannot parse.

**Test:** `tests/test_jobs_tools.py` — the call path, the body, the paused schedule, and a recorded HTTP
fake that asserts **zero** calls for each invalid graph.

### 1.3 · `dbx_run_job` — 2.2, idempotent, and a real 409

**Edit** the same file:

* `run-now` → `/api/2.2/jobs/run-now`;
* add a `purpose: str = "run"` argument and send
  `idempotency_token = sha256(f"{session}:{job_id}:{purpose}")[:40]`. The session id is already in the
  environment (`NBMCP_RUN_SESSION`); the tool falls back to a per-process constant when it is absent, so
  a laptop keeps working;
* return `reused` — the platform does not say whether the token matched, so the tool reads
  `runs/list` with `limit=1` **before** the call, and after it compares the returned `run_id` to the
  pre-read newest. That is one extra GET on a write path; it is the price of telling the truth about
  whether a second run was created, and it is worth it;
* on a `400` whose text names a queue or concurrency limit, return the platform's sentence plus
  *"a run is already active: run <id>"* when the pre-read found one.

**Test:** `::test_two_identical_runs_send_one_token`, `::test_reused_is_true_when_the_id_matches`,
`::test_a_busy_job_names_the_active_run`.

### 1.4 · `dbx_job_failure_context` — the new, model-only tool

**New tool** in the same file: reads the job's latest failed run, the failing task, its output's `error`
and `error_trace` tail, the tables that task's notebook reads (the repository already extracts these in
`dbx_run_notebook`, `tools/…:1042-1058` — this reuses the same regex and the same `describe_table` call),
and the last successful run's duration. Returns one object.

**Why it exists.** It is the only tool in this spec that exists purely for a model (lens 7). Without it,
"why did my job fail?" costs three calls and three chances to conclude the wrong thing.

**Test:** `::test_failure_context_carries_the_error_and_the_real_columns`, with a recorded payload pair.

### 1.5 · The core set, re-budgeted

**Edit** `_CORE`: remove the three Lakebase scaffold tools, add `dbx_job_failure_context`.
**Edit** `tests/test_tools_fence.py`: the `== 25` assertion becomes the three assertions `[TOOL-1]`
names. **Edit** `tools/skills/lakebase-postgres.md` to name the three departed tools, which is what makes
their removal safe.

### Phase 1 gate

```
.venv/bin/python -m pytest tests/test_job_graph.py tests/test_jobs_tools.py tests/test_tools_fence.py -q
```
All three fail on the pre-phase tree: `test_job_graph.py` because the module does not exist,
`test_jobs_tools.py` because the paths say 2.1, and `test_tools_fence.py` because `_CORE` has 25 and no
`dbx_job_failure_context`.

---

## Phase 2 · The pipeline surface

**Why second.** Independent of the job tools, and it is the object the product cannot create at all
(`F4`). Doing it second means the page work in phase 4 has both objects to render.

### 2.1 · `tools/pipeline_body.py` — the body, pure

**New:** a module that turns arguments into a Pipelines API body, and refuses locally:

* `catalog` empty → refuse ("a serverless pipeline always publishes to Unity Catalog; pass catalog='main'");
* `serverless` true → `edition` defaults `ADVANCED`, `clusters` **must** be absent (the platform rejects
  both together);
* `libraries` empty → refuse;
* a `libraries` path is inside the session's write fence (the same `_check_path_scope`, passed in as a
  callable so this module stays pure).

**Test:** `tests/test_pipeline_body.py` — a table of arguments to (body | refusal), asserting the refusal
names the argument.

### 2.2 · Five tools

**Edit** `tools/databricks_notebook_mcp.py`, adding:

| Tool | Call | The part that matters |
|---|---|---|
| `dbx_create_pipeline` | `POST /api/2.0/pipelines` | records the id in the ledger; returns `{pipeline_id, state, next}` |
| `dbx_pipeline_status` | `GET /api/2.0/pipelines/{id}`, `GET …/updates?max_results=3`, `GET …/events?max_results=20` | returns `lastUpdate` and events in one object |
| `dbx_start_pipeline` | `POST …/updates` | `full_refresh` explicit (never defaulted); `validate_only` passed through |
| `dbx_stop_pipeline` | `POST …/updates/{update_id}/cancel` (falls back to `…/stop` when the API version needs it) | refuses when no update is active, with the reason |
| `dbx_pipeline_edit` | `PUT /api/2.0/pipelines/{id}` | `allow_duplicate_names` off; re-reads the pipeline before editing (fence rule 5) |

`dbx_list_pipelines` is edited to carry `lastUpdate` (`[TOOL-8]`).

### 2.3 · The ledger

**The problem.** `[TOOL-6]` needs the set of pipeline ids this session created, and the tool server is a
subprocess that dies with the session (`registry.py:120-126`).

**The decision.** The tool server writes the id to a **ledger file** in a directory the app gives it
(`NBMCP_SESSION_LEDGER`), one JSON line per created object. The app reads that file when it needs the
ledger for its own classification, and the file survives a tool-server restart because the app owns the
path. That is smaller than a database table and it is enough: the ledger is per-session, append-only, and
tiny.

**This changes [05 §9](05-diagrams.md#9-er-what-the-product-stores-and-what-it-only-reads).** The E/R
diagram's `SESSION_PIPELINE` row is read as `SESSION_LEDGER` — a file, not a table — and the diagram's
caption is corrected in phase 2 rather than left to disagree with the code. A file is the honest
representation of "what one process created for one session", and a table would imply a durability
guarantee the app does not need.

**Test:** `::test_the_ledger_survives_a_tool_server_restart` — write, stop, start, read.

### Phase 2 gate

```
.venv/bin/python -m pytest tests/test_pipelines_tools.py tests/test_pipeline_body.py -q
```

---

## Phase 3 · The read path

**Why third.** The pages cannot be written against a route that does not exist, and the route's shape is
the decision that took the longest to get right (`[RB-1]`).

### 3.1 · `api/domain/jobs.py` — the vocabulary, pure

**New:** state tables and three functions, all total:

```python
RUN_LIFE_CYCLE = ("PENDING", "QUEUED", "RUNNING", "TERMINATING", "TERMINATED",
                  "SKIPPED", "INTERNAL_ERROR", "BLOCKED", "WAITING_FOR_RETRY")
RUN_RESULT = ("SUCCESS", "FAILED", "TIMEDOUT", "CANCELED", "MAXIMUM_CONCURRENT_RUNS_REACHED",
              "UPSTREAM_CANCELED", "UPSTREAM_FAILED", "EXCLUDED", "SUCCESS_WITH_FAILURES", "DISABLED")
PIPELINE_STATE = ("DEPLOYING", "STARTING", "RUNNING", "STOPPING", "DELETED", "RECOVERING",
                  "FAILED", "RESETTING", "IDLE")
UPDATE_STATE = ("QUEUED", "WAITING_FOR_RESOURCES", "INITIALIZING", "RESETTING", "CREATING_FLOW",
                "RUNNING", "IDLE", "COMPLETED", "FAILED", "CANCELED")

def run_word(life_cycle: str, result: str | None) -> str: ...
def is_active(life_cycle: str) -> bool: ...          # the six active words
def is_terminal(life_cycle: str) -> bool: ...
def pipeline_word(state: str, last_update: str | None) -> str: ...
def update_word(state: str) -> str: ...
def task_levels(tasks: list[dict]) -> tuple[list[list[str]], list[str]]: ...  # (levels, cycle)
def duration_seconds(start: int | None, end: int | None, now: int | None) -> int | None: ...
```

**Test:** `tests/test_jobs_domain.py` — a table per function, including the case that matters
(`IDLE` + `FAILED` update → `failed`) and the case that catches a lazy implementation
(`TERMINATED` + `FAILED` → `failed`, never `done`).

### 3.2 · `web/src/domain/jobs-table.json` — the one table, two runtimes

**New:** the fixture both runtimes are tested against, exactly as `event-parity.json` holds the event
vocabulary. Each row is `{life_cycle, result, word, tone, active, terminal}` and
`{pipeline_state, last_update, word}`.

**Test:** `test_jobs_domain.py::the_word_table_is_the_same_in_both_runtimes` reads the JSON and asserts
Python's output equals it; `domain/jobs.test.ts` asserts TypeScript's does too. A word changed on one side
alone fails one of them, and the failure names the row.

### 3.3 · `api/adapters/databricks/jobs.py` and `pipelines.py`

**New:** two classes, one call per method, everything through `DbxHttp` so the error contract is
inherited rather than restated (013's `LakebaseBrowser` is the model). Each method takes a token; each
returns a dict shaped for the page, not for the platform.

**The identity decision, implemented once.** Both classes take a `token_provider` that yields the
**app's service principal** for reads (013's `sp_token.provider`), because `[RB-1]` established that the
forwarded user token cannot call these APIs. `api/main.py` gains two lines beside the existing
`app.state.lakebase` / `app.state.apps`:

```python
app.state.jobs = JobsBrowser(host, provider(sp))
app.state.pipelines = PipelinesBrowser(host, provider(sp))
```

**Test:** `tests/test_jobs_adapter.py` — method, path and query per call, through a fake `DbxHttp`, and a
`403` that becomes `ScopeMissing` with the scope named.

### 3.4 · `api/routers/jobs.py`

**New:** seven routes, each one read or one write, each with `_dbx_errors`:

| Route | Returns |
|---|---|
| `GET /api/jobs` | the first page of jobs, 25, `{items, runsUnread}` |
| `GET /api/jobs/{job_id}` | five independent blocks, any of which may be `{error}` |
| `GET /api/runs/{run_id}` | the run, its tasks, its output |
| `GET /api/pipelines` | the first page, with each `lastUpdate` |
| `GET /api/pipelines/{pipeline_id}` | five independent blocks |
| `GET /api/pipelines/{pipeline_id}/events` | the events, filtered |
| `GET /api/infra/ledger` | the session ledger, for the page to know what it may control |

**There is no write route.** `[07 §5]` decided that: Run now, Resume, Cancel, Stop and Start go through
the agent, so the fence has one home. A test asserts the route table contains no `POST` under `/api/jobs`
or `/api/pipelines`, which is the structural version of that decision.

**Test:** `tests/test_infra_routes.py` — each route's shape, each error mapping, and the absence of a
write route.

### Phase 3 gate

```
.venv/bin/python -m pytest tests/test_jobs_domain.py tests/test_jobs_adapter.py tests/test_infra_routes.py -q
```

---

## Phase 4 · The surfaces

**Why fourth.** Everything below it now exists and answers. This phase is where a wrong assumption
becomes visible, which is why it is one phase and not spread through the others.

### 4.1 · Three kinds

**Edit** `web/src/domain/docs.ts`:

* `DocKind` gains `"job" | "pipeline" | "run"`;
* `keyOf` gains the three (a job and a run are their numeric id; a pipeline is its UUID);
* `touched()` is **rewritten** around a `TOUCHED` table (the DRY change `[UI-5]` requires);
* `ACTIONS_FOR` gains three empty lists, and `asAttachment` returns `null` for all three (a job is not
  content the server can attach, exactly as 013 decided for a project and an app).

**The compiler is the checklist.** `Record<DocKind, …>` in `App.tsx:77` and `docs.ts:154` will refuse to
compile until each new kind is handled. That is the mechanism, and it is why this change is safe.

### 4.2 · Three routes

**Edit** `web/src/domain/route.ts`: `#/job/<number>`, `#/pipeline/<uuid>`, `#/run/<number>`; each parses
to `null` (the empty route) on a malformed id; `parse(format(r)) === r` for all eight kinds.

### 4.3 · `useResource`

**New** `web/src/hooks/useResource.ts`: `{state, data, error, reload}`, with an `AbortController` and a
generation counter so a late response cannot overwrite a newer one. Nine call sites.

### 4.4 · The four rail groups

**Edit** `components/DataTree.tsx`: a `GROUPS` table of `{key, label, empty, fetcher, row}`, four rows,
one `useResource` per row via a fixed-length hook call (a hook cannot be called in a loop, so the four are
explicit and the *rendering* is table-driven — the honest split, stated because a reviewer will ask).

**Edit** `domain/keys.ts`: `⌘4`'s label becomes "Data panel (databases, jobs, pipelines, apps)".

### 4.5 · Three pages

**New:** `components/JobsPage.tsx`, `components/RunsPage.tsx`, `components/PipelinePage.tsx`. Each is a
`viewer-head` (copied structurally from `LakebasePage`, not abstracted, because the header of a
read-only page is 30 lines and a shared component would need four props to express three differences) and
a `viewer-body` of `Block`s.

**New:** `components/JobGraph.tsx` — the level renderer, driven by `taskLevels()`. It is a component and
not inline because the run page reuses it for a run's tasks grouped by their task's level.

### 4.6 · The dock and the palette

**Edit** `domain/dock.ts`: three suggestion sets (`[UI-6]`).
**Edit** `App.tsx`: `KIND_GROUP` gains three; the page switch gains three arms.

### Phase 4 gate

```
cd web && npx tsc -b && npx vitest run
```
`tsc` fails on the new kinds until every site is handled — which is the gate working.

---

## Phase 5 · The pictures

**Why last, and why it is not decoration.** Phase 4's tests assert what the code returns. They cannot see
that a header says `loading` over a healthy job (the defect 013's S2 found by looking), that a dock offers
"Explain this notebook" over a run, or that the task list is clipped at 900 px. Nine scenes, each with
its own assertions, each photographed and **looked at**.

**New:** `web/scripts/jobs-e2e.mjs`, `web/scripts/fixtures/jobs.json` (recorded payloads).
**New:** `specs/014-jobs-pipelines/e2e/build_wireframes.py` (already written; regenerates `04`).

### Phase 5 gate

```
node scripts/jobs-e2e.mjs http://127.0.0.1:8062     # 9/9 scenes
```

Then the screenshot review in [11](11-e2e-plan.md), which is a human step: every file inspected against
five criteria, and the inspection recorded in `e2e/screenshots/README.md` — including the defects it
found, because a screenshot that found nothing is a screenshot nobody looked at.

---

## What each phase proves, in one line

| Phase | The sentence it makes true |
|---|---|
| 1 | an agent cannot create a job it cannot run, and cannot run one twice by accident |
| 2 | "build me a pipeline" produces a pipeline |
| 3 | a page can read a job without pretending the user's token could |
| 4 | the object the agent named is an object the user can open |
| 5 | opening it tells the truth at every width, and a refusal is a sentence not a blank |

## Files, exhaustively

**New (24)**

```
tools/job_graph.py
tools/pipeline_body.py
tests/test_job_graph.py
tests/test_jobs_tools.py
tests/test_pipeline_body.py
tests/test_pipelines_tools.py
api/domain/jobs.py
api/adapters/databricks/jobs.py
api/adapters/databricks/pipelines.py
api/routers/jobs.py
tests/test_jobs_domain.py
tests/test_jobs_adapter.py
tests/test_pipeline_adapter.py
tests/test_infra_routes.py
web/src/domain/jobs.ts
web/src/domain/jobs-table.json
web/src/domain/jobs.test.ts
web/src/hooks/useResource.ts
web/src/components/JobsPage.tsx
web/src/components/RunsPage.tsx
web/src/components/PipelinePage.tsx
web/src/components/JobGraph.tsx
web/src/components/JobsPages.test.tsx
web/scripts/jobs-e2e.mjs
```
Plus `web/scripts/fixtures/jobs.json` and `e2e/screenshots/README.md`: **26 new paths**.

**Edited (15)**

```
tools/databricks_notebook_mcp.py         2.2, validate, idempotency, ledger, five pipeline tools
tools/skills/etl-pipelines.md            rewritten: which object, and why
tools/skills/lakebase-postgres.md        names the three tools that left core
api/main.py                              two adapters on app.state
api/routers/infra.py                     shares `_token` and `_dbx_errors` with the new router
web/src/domain/docs.ts                   kinds, TOUCHED table, ACTIONS_FOR
web/src/domain/route.ts                  three routes
web/src/domain/recent.ts                 three kinds
web/src/domain/dock.ts                   three suggestion sets
web/src/domain/keys.ts                   ⌘4 label
web/src/api/client.ts                    seven calls
web/src/components/DataTree.tsx          four groups
web/src/App.tsx                          KIND_GROUP, page switch
web/src/styles.css                       the job/pipeline page rules
tests/test_tools_fence.py                the budget, three assertions
tests/test_fence_parity.py               one row per fence rule
```

That is 16; the table at the top of this document says 14 and is corrected here rather than left to
disagree with the list. The count is not the point — the list is, because a reviewer checks a list.

## The order inside a phase, and why it is not negotiable

For every phase: **pure module → its test → the I/O that calls it → the I/O's test → the surface.**

The pure module first because it is the only part that can be made obviously correct. Its test second
because a pure module without a test is a draft. The I/O third because it is the part that can only be
verified against a fake, and the fake should be written against a rule that is already true. The surface
last because it is the only part that needs a running app.

Doing it the other way — page first, then the API it wishes existed — produced 013's [F5]: a page for an
object type that had no reader, discovered when the screenshot showed a blank block.
