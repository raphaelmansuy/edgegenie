[Index](README.md) · prev: [02 Measured assessment](02-assessment.md) · next: [04 Wireframes](04-wireframes.md)

# 03 · Requirements

Every requirement is a sentence that can be false. `[JOB-*]` `[PIPE-*]` `[RUN-*]` are defined here and
nowhere else; `[TOOL-*]` and `[UI-*]` likewise. A requirement cites the finding it answers (`F1`…`F11`,
defined in [02](02-assessment.md)) and the test that will hold it.

The grammar, used consistently below:

* **Shall** — the implementation must do this; a test fails without it.
* **Shall not** — the implementation must not; a test fails if it does.
* The **proof** column names the test that would fail if the requirement is removed. A requirement
  with no test is marked *manual* and appears in the E2E plan instead.

---

## A · The tool the agent calls

### `[TOOL-1]` · The advertised tool set stays inside its budget

Every MCP tool is advertised on every request, so the count is a cost on every turn of every session.
The `core` profile **shall** contain **at most 28** tools (raised from 25 by the arithmetic in
[07 §6](07-architecture.md#6-the-tool-budget-spent-deliberately)), and:

* every member **shall** be reachable from a documented flow: a page that reads what it writes, or a
  skill that requires it;
* every tool that **left** `core` **shall** be named by a skill, so the agent can still discover it.

The three Lakebase calls that exist only for a scaffold (`dbx_lakebase_database`, `dbx_lakebase_role`,
`dbx_lakebase_tables`) leave `core` and stay registered in the `full` profile.

**Proof.** `test_tools_fence.py::test_the_core_profile_stays_within_its_budget` — three assertions:
`<= 28`, reachable, and the departed tools named by a skill — plus
`::test_every_core_tool_is_reachable_from_a_flow`. `F11`.

### `[TOOL-2]` · Jobs are spoken in API 2.2

Every job call in the tool server **shall** use `/api/2.2/`. A job created through the tool **shall**
therefore have queueing on by default, matching a job created in the Databricks UI today, and the
create body **shall** make that explicit (`queue: {enabled: true}`) so the behaviour does not depend on
a version default.

**Proof.** `test_jobs_tools.py::test_every_job_call_uses_api_2_2` (asserts the path prefix of every
recorded call) and `::test_create_body_states_the_queue_setting`. `F1`.

### `[TOOL-3]` · A malformed task graph is refused before the platform is called

`dbx_create_job` **shall** validate, with **zero HTTP calls**, that:

1. at least one task is given;
2. every `task_key` is non-empty, matches `^[A-Za-z0-9_-]{1,100}$`, and is **unique**;
3. every `depends_on` entry names a task in the same list;
4. the dependency graph is acyclic;
5. every task names exactly one task type: `notebook_path`, `python_file`, `sql_file`, `pipeline_id`
   or `job_id`;
6. every workspace path (`notebook_path`, `python_file`, `sql_file`) is inside the session's write
   fence.

A violation **shall** return one sentence naming the offending key and the transformation that fixes
it — never a bare `400`, and never a partial create.

**Proof.** `test_job_graph.py` (six parametrised cases, each asserting `0` HTTP calls) and
`test_job_graph.py::test_a_cycle_names_the_cycle`. `F3`.

### `[TOOL-4]` · The name fence is re-checked from the object the platform returned

Any tool that **acts on an existing job** (`run`, `cancel`, `repair`, `update`, `reset`, `delete`) or
**on an existing pipeline** (`start`, `stop`, `update`, `delete`) **shall** first read the object and
check its name against the session's rule, rather than trusting the id in its own arguments. A refusal
**shall** name the rule and the object's real name.

**Proof.** `test_jobs_tools.py::test_run_re_reads_the_job_and_refuses_a_foreign_name`,
`test_pipelines_tools.py::test_start_refuses_a_pipeline_outside_the_session_ledger`. `F10`, `[E-2]`.

### `[TOOL-5]` · Running a job is idempotent

`dbx_run_job` **shall** send an `idempotency_token`. The token **shall** be derived from the session id,
the job id and an explicit `purpose` argument, so that:

* two identical calls in one turn produce **one** run;
* two calls with different purposes (a first run and a re-run after a fix) produce two.

The tool **shall** report whether it returned an existing run or created one (`reused: true|false`).

**Proof.** `test_jobs_tools.py::test_two_identical_runs_send_one_token`,
`::test_a_different_purpose_sends_a_different_token`. `F2`, `[E-5]`.

### `[TOOL-6]` · A pipeline is fenced by what this session created

A pipeline id is a platform UUID with no session prefix, so a prefix rule cannot exist. A tool that
acts on a pipeline **shall** accept it only when the id is in the **session ledger** — the list of
pipeline ids this session's `dbx_create_pipeline` returned — and **shall** refuse with a sentence that
says so, naming the ledger's size and how to see it (`dbx_list_pipelines`).

The ledger lives in the tool server process for that session. It is **not** a security boundary against
a determined caller (the process is per-session and the token is the real boundary); it is the
guarantee that an agent cannot be talked into stopping a pipeline a data team depends on.

**Proof.** `test_pipelines_tools.py::test_a_pipeline_not_in_the_ledger_is_refused` and
`::test_a_pipeline_in_the_ledger_is_accepted`. `[E-17]`.

### `[TOOL-7]` · A pipeline can be created, started, read, stopped and edited

The tool server **shall** expose, at minimum:

| Tool | Purpose |
|---|---|
| `dbx_create_pipeline` | create a serverless pipeline from notebook/file libraries, with `catalog`, `schema`, `edition` |
| `dbx_pipeline_status` | the pipeline, its libraries, and its last three updates |
| `dbx_start_pipeline` | start an update, `full_refresh` explicit, `validate_only` available |
| `dbx_stop_pipeline` | stop the active update |
| `dbx_pipeline_events` | the last *n* events, filtered to `ERROR`/`WARN` by default |

`dbx_create_pipeline` **shall** default to `serverless: true` and `edition: "ADVANCED"` (the documented
requirement for serverless), **shall** omit `clusters` (the platform rejects both), and **shall**
refuse locally when `catalog` is empty, because a serverless pipeline always uses Unity Catalog.

**Proof.** `test_pipelines_tools.py` (one test per tool, asserting method, path and body) and
`::test_serverless_requires_a_catalog_and_omits_clusters`. `F4`.

### `[TOOL-8]` · `dbx_list_pipelines` answers the question it is asked

The list **shall** carry, per pipeline, its `state`, its **last update's** `state` and `update_id`, and
whether an update is currently active. A pipeline that has never been updated **shall** report
`lastUpdate: null`, not a synthesised state.

**Proof.** `test_pipelines_tools.py::test_list_carries_the_last_update_state_and_null_when_absent`. `F5`.

### `[TOOL-9]` · `dbx_list_jobs` returns what its docstring promises

The list **shall** carry, per job, `job_id`, `name`, the schedule (cron, timezone, pause status), and
the **latest run's** `run_id`, `life_cycle_state`, `result_state` and `start_time`. It **shall** do this
in `O(1 + n/100)` calls: one `jobs/list` page plus one `runs/list` per 25 jobs whose latest run is not
already known, batched by `job_id` in the same request where the API allows it — never one call per job.

Where the batch cannot answer, the field **shall** be `null` and a `runsUnread` list **shall** name the
jobs whose state could not be read, so the agent knows the difference between "no runs" and "not read".

**Proof.** `test_jobs_tools.py::test_list_includes_the_latest_run_state`,
`::test_list_costs_one_call_per_page_not_one_per_job`. `F6`, `[E-9]`.

---

## B · The object the user opens

### `[JOB-1]` · A job is identified by its id, and one job is one tab

`job_id` is the identity. `812345678901` and `"812345678901"` are one object; a job referenced from a
tool result and from a URL opens the **same** tab. No job is ever identified by its name, because a
name is not unique in a workspace.

**Proof.** `domain/jobs.test.ts::one job is one document however it is spelled`, `jobs.test.tsx`.

### `[JOB-2]` · A job page answers "is it working?" before "what is it?"

The page **shall** render, in this order: a header carrying the job's name and its **last run's state
word**; a **Last run** block (outcome, duration, when, the one failing task if any); a **Tasks** block
(the graph); a **Schedule** block (cron, timezone, pause state, next fire time or why it will not
fire); a **Settings** block (owner, timeout, retries, queueing, tags). Every value comes from a call.
A value that could not be read renders `—`, never `0`, never a guess.

**Proof.** `JobsPages.test.tsx::renders the five blocks the wireframe names`,
`::a job that never ran says so instead of showing success`. `[UI-3]`.

### `[JOB-3]` · The task graph is drawn, not listed

The Tasks block **shall** render the dependency graph as an ordered list of **levels**, each task with
its task type, its target (notebook path, pipeline id, job id, SQL file), its `depends_on`, its timeout
and its retry count. A task that depends on two others **shall** appear below both. The rendering is
derived from `depends_on` by a **pure function** (`taskLevels()`), so the same function is testable
without a browser and cannot disagree with the validation in `[TOOL-3]`.

**Proof.** `domain/jobs.test.ts::taskLevels` (five shapes: chain, fan-out, fan-in, diamond, cycle
refused), `JobsPages.test.tsx::the graph shows fan-in below both parents`.

### `[JOB-4]` · A schedule the agent created is paused, and the page says so

Every job created by the agent with a cron **shall** be created `PAUSED`, and the page **shall** state
this in the Schedule block in one sentence, plus the sentence that resumes it. The transcript's answer
**shall** say it too. A user who believes a job is firing when it is paused has a silent data outage;
a user who believes it is paused when it is firing has an invoice.

**Proof.** `test_jobs_tools.py::test_a_scheduled_job_is_created_paused`,
`JobsPages.test.tsx::a paused schedule is stated, not implied`. `[JOB-5]`.

### `[JOB-5]` · Pausing and resuming are one control, and resuming names its consequence

The Schedule block **shall** offer exactly one toggle. Resuming **shall** be a two-step action whose
confirmation names what will happen ("this job will run at 06:00 UTC every day until you pause it"),
because it is the only control in this spec that creates an unbounded future cost. Pausing asks
nothing: it removes cost.

A resume that the platform refuses (a cron the scheduler rejects, a `CAN_MANAGE` gap) **shall** show the
platform's sentence verbatim and leave the previous state on screen.

**Proof.** `JobsPages.test.tsx::resume asks before it schedules`,
`::a refused resume keeps the paused state and shows the sentence`. `[E-6]`.

### `[JOB-6]` · "Run now" says what it starts

The Run-now control **shall** carry the consequence in its own label or its adjacent note: the compute
it starts and the last run's duration as the expectation ("starts a serverless job; last run 1 m 42 s").
It **shall** be disabled while a run is active for that job, with the reason given ("a run is already
active"), rather than replaced by a spinner that explains nothing.

**Proof.** `JobsPages.test.tsx::run now is disabled while a run is active and says why`. `[E-5]`.

### `[PIPE-1]` · A pipeline is created as a Lakeflow pipeline, not as a job of notebooks

`dbx_create_pipeline` **shall** create a pipeline object with `serverless: true`, an explicit
`edition`, a `catalog`, a `schema` and `libraries`. The `etl-pipelines` skill **shall** be rewritten to
choose between the two objects on the user's words: *pipeline*, *declarative*, *streaming table*,
*expectation*, *medallion* → a pipeline; *sequence of notebooks*, *orchestrate*, *dependency*, *retry* →
a job. The skill **shall** say which one it chose and why.

**Proof.** `test_pipelines_tools.py::test_create_sends_the_serverless_body`,
`test_skills.py::test_the_pipeline_skill_names_both_objects_and_how_to_choose`. `F4`.

### `[PIPE-2]` · A pipeline page answers "did the last update work?"

The page **shall** render: a header with the pipeline's name and a state word derived from its **last
update**; an **Last update** block (update id, state, when it started, how long, whether it was a full
refresh, and the first error event if it failed); a **Libraries** block (each file/notebook, with the
path); a **Configuration** block (catalog, schema, edition, serverless, channel, continuous); an
**Events** block (the last 20 events, errors and warnings first).

**Proof.** `JobsPages.test.tsx::a pipeline's header follows its last update, not its state`,
`::a never-updated pipeline says so`. `[PIPE-5]`, `[UI-8]`.

### `[PIPE-3]` · Starting an update names what it will re-read

Starting an update **shall** offer two variants with different costs, each labelled: **Start** (incremental,
re-reads only new data) and **Full refresh** (re-reads every source; a confirmation names the tables in
the pipeline). A third, `validate_only`, **shall** be offered as "Check the code without running it",
because it is free and answers the most common question after an edit.

**Proof.** `JobsPages.test.tsx::start offers incremental, full refresh and validate-only, each labelled`.
`[E-7]`.

### `[PIPE-4]` · Stopping an update asks first

Stopping the active update **shall** be confirmed with the update id and its elapsed time, because a stop
abandons work in flight. The control **shall** be absent — not disabled — when no update is active, since
a button that cannot act is the inert control 011 [N5] removed.

**Proof.** `JobsPages.test.tsx::stop is absent with no active update and asks when there is one`.

### `[PIPE-5]` · A state word comes from the terminal field

`pipelineWord()` and `updateWord()` **shall** be pure functions over the whole payload, and:

* a pipeline whose last update `COMPLETED` reads `succeeded`;
* a pipeline whose last update `FAILED` reads `failed` — **even though** its own `state` is `IDLE`;
* a pipeline that has never updated reads `never run`;
* an unknown word is returned verbatim, lowercased, never mapped to a synonym;
* a missing word is `unknown`, not `ready`.

**Proof.** `domain/jobs.test.ts::pipelineWord` (a table of eight payloads, including the `IDLE`+`FAILED`
case), `api` twin in `test_jobs_domain.py`. `F5`, `[UI-8]`.

### `[PIPE-6]` · The events are readable, and an error is at the top

The Events block **shall** show level, timestamp, message and, when present, the error's `stack_trace`
trimmed to its last 40 lines behind a disclosure. Errors and warnings **shall** sort before info. A
pipeline that failed with no `ERROR` event **shall** say so ("the platform reported a failure with no
error event"), because that is the honest state and inventing a cause is worse.

**Proof.** `JobsPages.test.tsx::events put errors first and disclose a stack trace`.

---

## C · The run, which is the proof

### `[RUN-1]` · A run page shows every task's outcome

The page **shall** render the run's state word, its duration, its trigger (manual, scheduled, repair,
`submit`), and a row per task with: task key, `life_cycle_state`, `result_state`, duration, and — when
the task is terminal — its exit value or its error. A task that has not started **shall** read "not
started", not "running".

**Proof.** `JobsPages.test.tsx::a run lists every task with its own outcome`,
`::a task that has not started is not called running`.

### `[RUN-2]` · Cancelling is offered only while a run is active, and says it is asynchronous

The Cancel control **shall** appear only for a run whose `life_cycle_state` is active
(`PENDING`, `QUEUED`, `RUNNING`, `TERMINATING`, `BLOCKED`, `WAITING_FOR_RETRY`), and the click **shall**
confirm. After the click the page **shall** say that cancellation is asynchronous — the platform
documents that the run may still be running — and **shall** keep polling until the run reaches a
terminal state or the user leaves.

**Proof.** `JobsPages.test.tsx::cancel is absent on a finished run and states it is asynchronous`.
`[E-8]`.

### `[RUN-3]` · Repair re-runs the failed tasks and is available only on a finished run

Repair **shall** appear only on a run whose `result_state` is `FAILED` or `TIMEDOUT`, and **shall** send
`rerun_all_failed_tasks: true`. The page **shall** state which tasks will be re-run, read from the run's
own task list. A second repair of the same run **shall** pass the `latest_repair_id` the platform
returned the first time — omitting it is a documented error.

**Proof.** `test_jobs_tools.py::test_repair_sends_all_failed_and_chains_the_repair_id`,
`JobsPages.test.tsx::repair names the failed tasks`.

### `[RUN-4]` · Run now is idempotent from the UI too

The Run-now control **shall** send one `purpose` per user intent and re-use it while the request is in
flight, so a double click cannot create two runs. If the tool reports `reused: true`, the page **shall**
open the existing run and say so ("an identical run was already started").

**Proof.** `JobsPages.test.tsx::a double click sends one intent` (asserts `fetch` was called once).
`[TOOL-5]`.

### `[RUN-5]` · Durations are computed from timestamps, and a missing one is not zero

A duration **shall** be computed as `end_time - start_time` when both exist, as `now - start_time` when
the run is active, and **shall** render `—` when `start_time` is absent. A run with 4 tasks **shall**
report the run's own duration, not the sum of the tasks', and the page **shall** disclose the task total
beside it when they differ by more than 20 % (the signature of a queue wait).

**Proof.** `domain/jobs.test.ts::durationOf` (five cases including absent start), `JobsPages.test.tsx`.

---

## D · The surfaces around them

### `[UI-1]` · Three new document kinds, and the compiler names every site

`DocKind` **shall** gain `"job"`, `"pipeline"` and `"run"`. Every `Record<DocKind, …>` **shall** be
extended, and the three new kinds **shall** have: a tab icon, a palette group, a route, a recent-list
entry rule, a `touched()` extractor, a dock suggestion set, and a page. A kind with no `ACTIONS_FOR`
entry **shall** be an empty list, not a fallthrough to the notebook actions.

**Proof.** `tsc --noEmit` (exhaustiveness), `domain/docs.test.ts::every kind has a group, a route and an
action set`, `domain/route.test.ts::round-trips all eight kinds`. `F7`.

### `[UI-2]` · The `Data` tab lists four groups through one loading primitive

The tab **shall** list Lakebase, Jobs, Pipelines and Apps, each independently loaded, each with its own
error. Two calls that fail with one message **shall** render one box ([013 UI-6]); two different
messages **shall** stay two. Adding a group **shall** be a table row, not a fourth `useState` +
`useEffect` + renderer.

**Proof.** `DataTree.test.tsx::four groups render independently`,
`::one cause shows one box and two causes show two`, `::the group table is exhaustive`. `F9`.

### `[UI-3]` · A value that could not be read says so

Every fact rendered by the three pages uses the same rule as 013's pages: `—` for a missing value, a
`Block` in `error` state carrying the platform's sentence for a failed call, and no block ever blanking
a sibling.

**Proof.** `JobsPages.test.tsx::a denied block leaves the other blocks standing`. `[E-1]`.

### `[UI-4]` · A permanent refusal offers no retry

A `PERMISSION_DENIED`, a missing `CAN_MANAGE_RUN`, a "required scopes" sentence or a name the platform
excludes **shall** render without a retry button, because a second click cannot change a grant. A
transient failure (502, timeout) **shall** offer one. This reuses `isPermanent()` from 013 rather than
restating the regex.

**Proof.** `JobsPages.test.tsx::no retry for a permission wall`, and 013's `Infra.tsx` test stays green.

### `[UI-5]` · A tool call that names an object opens it

`touched()` **shall** resolve a job from `{"job_id": …}`, a pipeline from `{"pipeline_id": …}`, and a
run from `{"run_id": …}`, in arguments **or** in the result (a create call's result is where the id
first exists). It **shall** be driven by a **table** so that a seventh kind is a row, and it **shall**
never guess: an id of the wrong shape returns `null`.

**Proof.** `domain/docs.test.ts::touched resolves every kind from its own table`,
`::an id of the wrong shape is not guessed`. `F8`.

### `[UI-6]` · The dock's suggestions are about the object on screen

A job, a pipeline and a run **shall** each have three suggestions that are about that object — never
"Explain this notebook". A job's are: *Why did the last run fail?*, *What does this job write?*, *Add a
task and re-run it*. A pipeline's are about its flows and its failed expectations; a run's are about its
failure and its tasks.

**Proof.** `domain/dock.test.ts::a job is never offered notebook actions`. This is the S2/S3 defect 013
found twice, asserted before it can recur.

### `[UI-7]` · Every one of the three objects has a deep link

The route grammar **shall** accept `#/job/812345678901`, `#/pipeline/<uuid>` and `#/run/812345679`,
**shall** round-trip (`parse(format(r)) === r`), and an unparseable id **shall** parse to the empty
route rather than throwing, so a stale link opens the app rather than a blank page.

**Proof.** `domain/route.test.ts::round-trips all eight kinds`,
`::a malformed run id opens the app`.

### `[UI-8]` · One state vocabulary, in both runtimes

The state words, the tone of each, and the "is this active" / "is this terminal" predicates **shall** be
defined once per runtime (`api/domain/jobs.py`, `web/src/domain/jobs.ts`) and held to **one table** of
cases by a parity test. A word added to one side and not the other fails that test.

**Proof.** `test_jobs_domain.py::the_word_table_is_the_same_in_both_runtimes` reading
`web/src/domain/jobs-table.json`. `[PIPE-5]`, `[RUN-1]`.

---

## E · What is explicitly *not* a requirement

Named so a reviewer does not look for them.

| Not required | Why |
|---|---|
| A visual DAG editor | A graph you can drag is a product of its own; the link to Databricks is the escape hatch |
| Creating a job cluster, or sizing one | Serverless is the default and the product's cost story; classic compute is a Databricks-UI task |
| Reading a run's Spark logs | They live behind the cluster and can be gigabytes; `/logz`-equivalent links are given instead of a log viewer |
| Scheduling *this app* | Out of scope (017/021) |
| Editing a pipeline's source file | The file is a workspace document this app already edits (010); the pipeline page links to it |
| A job's permissions matrix | `CAN_MANAGE` grants are a workspace-admin action; the page names the refusal and where to grant it |
