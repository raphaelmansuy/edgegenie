[Index](README.md) · prev: [08 Implementation plan](08-implementation-plan.md) · next: [10 Roadblocks](10-roadblocks.md)

# 09 · Edge cases

Every failure I could name, the mitigation, and the test that holds it. An `[E-*]` cited from a
requirement is defined here and nowhere else.

Format: **Trigger** · **Behaviour** (what the user or the agent gets) · **Test** (the name that fails when
the mitigation is removed). Twenty-eight cases in six groups.

---

## A · The platform refuses

### `[E-1]` · `PERMISSION_DENIED` on a job read

**Trigger.** The app's service principal can list jobs but cannot read this one; or the user opened a
link to a job in another team's folder.
**Behaviour.** The block that failed renders the platform's sentence, verbatim, plus one line naming who
can grant it. **No retry**: a grant does not appear between two clicks (`isPermanent`, reused from 013).
The four other blocks keep their facts.
**Test.** `JobsPages.test.tsx::no retry for a permission wall`, and
`test_infra_routes.py::a_403_keeps_the_other_blocks`.

### `[E-2]` · A job whose name is outside the session prefix

**Trigger.** The agent passes `job_id` 9 of a job a colleague created, or a model reuses an id from an
earlier conversation.
**Behaviour.** The **action** tools refuse before acting: `dbx_run_job`, `dbx_create_job`,
`dbx_job_update` re-read the job and check the returned name against `NBMCP_WRITE_JOB_PREFIX`. The
refusal names the rule and the real name. A **read** is unaffected — inspecting a job you may not run is
not a write, which is the same distinction `dbx_lakebase_branch` already draws between listing and
creating.
**Test.** `test_jobs_tools.py::test_run_re_reads_the_job_and_refuses_a_foreign_name` and
`::test_reading_a_foreign_job_is_not_refused`. `[TOOL-4]`.

### `[E-3]` · The workspace rejects the create with `400 INVALID_PARAMETER_VALUE`

**Trigger.** A field the local validator does not check: an unsupported `node_type_id`, a `timeout_seconds`
above the ceiling, a cron the scheduler will not parse.
**Behaviour.** The tool returns `{"created": false, "http_status": 400, "platform_error": "<verbatim>",
"nothing_was_created": true}`. The `nothing_was_created` key is the mitigation: without it a model reads a
`400` and writes "the job failed", which asserts an object that does not exist.
**Test.** `test_jobs_tools.py::test_a_400_says_nothing_was_created`.

### `[E-4]` · The workspace has no serverless compute

**Trigger.** A pipeline created with `serverless: true` on a workspace in a region without serverless, or
without the terms accepted.
**Behaviour.** The platform's sentence is returned verbatim, and the tool adds one line:
*"this workspace cannot run a serverless pipeline; a classic pipeline needs `clusters`, which this tool
does not create — build it in Databricks and open it here."* That is honest about a limit rather than
retrying a call that cannot work.
**Test.** `test_pipelines_tools.py::test_a_serverless_refusal_names_the_classic_alternative`.

---

## B · Running and spending

### `[E-5]` · A double click starts two runs

**Trigger.** The user clicks Run now twice; the first request is slow; the browser sends both.
**Behaviour.** Two protections, in two layers. The tool sends an `idempotency_token` derived from
`(session, job, purpose)`, so identical calls produce **one** run and the second returns `reused: true`.
The page, independently, disables the control while its own request is in flight. If the tool reports
`reused`, the page opens the existing run and says so — never silently, because "a run was already
started" is a different fact from "your run started".
**Test.** `test_jobs_tools.py::test_two_identical_runs_send_one_token`,
`JobsPages.test.tsx::a double click sends one intent`. `[TOOL-5]`, `[RUN-4]`.

### `[E-6]` · A job is already running when Run now is clicked

**Trigger.** A schedule fired at 06:00 and the user clicks Run now at 06:01.
**Behaviour.** With queueing on (2.2's default, made explicit), the platform **queues** the run and
returns a new `run_id`. The page says *"queued behind run 812345678"* rather than presenting it as a
concurrent second run. With queueing off, the platform returns a `400`, and the tool's sentence names the
active run.
**Test.** `test_jobs_tools.py::test_a_queued_run_is_reported_as_queued`.

### `[E-7]` · Full refresh on a pipeline that someone else is updating

**Trigger.** Two people start an update on the same pipeline.
**Behaviour.** The platform refuses with *"there is already an active update"*. The tool returns that
sentence and the **active update's id and state**, read from `updates/list`. The page offers "open the
active update" instead of a retry.
**Test.** `test_pipelines_tools.py::test_a_busy_pipeline_names_the_active_update`.

### `[E-8]` · Cancel is accepted but the run keeps running

**Trigger.** Every cancel. The platform documents: *"The run is canceled asynchronously, so it may still
be running when this request completes."*
**Behaviour.** The page never renders `canceled` from the cancel response. It renders "cancelling…" and
keeps polling; the word changes only when the **run** reports `CANCELED`. A user who is told "cancelled"
while a cluster is still billing has been lied to about money.
**Test.** `JobsPages.test.tsx::cancel is absent on a finished run and states it is asynchronous` and
`domain/jobs.test.ts::accepted is not canceled`. `[RUN-2]`.

---

## C · Time and money

### `[E-9]` · A job with no runs, and a job we could not read

**Trigger.** A job created but never run; or a job for which `runs/list` was denied.
**Behaviour.** These are **different** facts and are never merged: `lastRun: null` means "never ran";
the job's id in `runsUnread` means "not read". The page renders "This job has not run yet" for the first
and "the last run could not be read" for the second.
**Test.** `test_jobs_adapter.py::a_never_run_job_is_not_a_run_we_could_not_read`,
`JobsPages.test.tsx::an unread run is not an empty history`. `[TOOL-9]`.

### `[E-10]` · A run in flight has no `result_state`

**Trigger.** Every running run. The platform documents `result_state` as *"only available for terminal
lifecycle states"*.
**Behaviour.** `run_word()` reads `life_cycle_state` when `result_state` is absent, so a running run reads
`running` and never `unknown`. A page that reads `result_state` alone shows nothing useful for the whole
duration of the run — which is the whole time the user is watching.
**Test.** `test_jobs_domain.py::a_running_run_has_no_result_state_and_still_reads_running`.

### `[E-11]` · The rail has 200 jobs and the workspace is slow

**Trigger.** A real workspace.
**Behaviour.** Three bounds. The rail reads **25 jobs, one page**, and shows no run state (that would be
25 more calls). It does not poll. A page's five calls are independent, so one slow call costs one block.
And the whole read path is behind a per-token cache with a TTL, so a second visit inside 30 s makes zero
calls.
**Test.** `test_infra_routes.py::the_jobs_list_is_one_call` (asserts one HTTP call, not 25) and
`test_jobs_adapter.py::the_cache_is_keyed_by_token`.

### `[E-12]` · A duration computed from a missing timestamp

**Trigger.** A queued task with no `start_time`, a task the platform skipped.
**Behaviour.** `duration_seconds()` returns `None`, and the page renders `—`. It never returns `0`: a zero
duration reads as "instant" and a skipped task was not instant. The run's own duration is used for the
header even when the sum of its tasks differs — and the difference is disclosed when it exceeds 20 %,
because that gap is a queue wait.
**Test.** `domain/jobs.test.ts::durationOf` (five cases) and `::a queue wait is disclosed`.

### `[E-13]` · A repair of a run that was already repaired

**Trigger.** The user clicks Repair twice, or repairs a run that a colleague repaired.
**Behaviour.** The platform requires `latest_repair_id` on the second repair and rejects the call without
it. The adapter reads `repair_history` from the run and passes the last `id`; when there is none it omits
the field. A model that does not know this would loop on a `400`.
**Test.** `test_jobs_adapter.py::repair_chains_the_latest_repair_id_when_one_exists`. `[RUN-3]`.

---

## D · Identity and the fence

### `[E-14]` · The user's token cannot call Jobs at all

**Trigger.** Always, in a deployed app: `jobs` is not a grantable `user_api_scopes` value.
**Behaviour.** Reads use the app's service principal, and every page payload carries
`identity: "the app's service principal"` so the page can state it. A tool call that needs user authority
falls back to the SP on a 403 and says so in its result (`ran_as`), which is the pattern `dbx_run_notebook`
already established for notebook runs.
**Test.** `test_jobs_adapter.py::reads_use_the_service_principal_and_say_so`. `[RB-1]`.

### `[E-15]` · No service principal is available (a laptop)

**Trigger.** Local development with a PAT and no `NBMCP_SP_TOKEN_FILE`.
**Behaviour.** The provider falls back to the configured token — the same fallback `_sp_token()` already
does (`tools/…:110-126`) — so nothing breaks outside a deployment, and nothing silently changes inside
one.
**Test.** `test_jobs_adapter.py::no_sp_falls_back_to_the_configured_token`.

### `[E-16]` · A pipeline created in an earlier conversation

**Trigger.** A session resumes (010) and the ledger file is still there, but the tool server is a new
process.
**Behaviour.** The ledger is a file the app owns, not process memory, so the id is still present and Stop
still works. If the file is gone (a redeploy that wiped `/tmp`), the tool refuses with
*"this pipeline is not in this conversation's ledger; open it in Databricks"* — which is true and
recoverable, unlike "permission denied".
**Test.** `test_pipelines_tools.py::test_the_ledger_survives_a_tool_server_restart`. `[TOOL-6]`.

### `[E-17]` · A pipeline id that is not a UUID

**Trigger.** A model passes `"sales_medallion"` — the pipeline's *name* — as its id.
**Behaviour.** The tool refuses locally, before any call, naming the difference: *"a pipeline is
identified by its id (a UUID); 'sales_medallion' is a name — call dbx_list_pipelines to find the id."*
This is the class of bug 013 recorded as [RB-12]'s display-name-as-id confusion, and it is cheaper to
refuse than to answer `404` and be read as a permission problem.
**Test.** `test_pipelines_tools.py::test_a_pipeline_name_is_refused_as_an_id_with_the_alternative`.

### `[E-18]` · A destructive update the fence cannot see

**Trigger.** `dbx_pipeline_edit` replaces the libraries wholesale — a file removed from the list stops
being part of the pipeline, and its tables stop being maintained.
**Behaviour.** The body sent is computed by diffing the new library list against the one read back, and
the **removed** paths are named in the tool's result. An edit that removes a library is not refused — the
user may have asked for it — but it is impossible to do silently.
**Test.** `test_pipelines_tools.py::an_edit_names_the_libraries_it_removes`.

---

## E · The surfaces

### `[E-19]` · A deep link to a job that no longer exists

**Trigger.** Someone bookmarked a job and a colleague deleted it.
**Behaviour.** The route parses (a number is a number), the read answers `404`, and the page renders a
single block: *"this job no longer exists"*, plus a link to the `Data` tab. It is not an error state with
a retry, because retrying cannot recreate it.
**Test.** `JobsPages.test.tsx::a deleted job says so and offers the Data tab`.

### `[E-20]` · A malformed id in a deep link

**Trigger.** `#/run/abc`, `#/job/`, `#/pipeline/../../etc`.
**Behaviour.** `parseRoute` returns the **empty route**, so the app opens its start screen. A stale link
must never produce a blank page or a request to a nonsense path — the rule `route.ts` already documents
for every other kind.
**Test.** `domain/route.test.ts::a malformed run id opens the app`. `[UI-7]`.

### `[E-21]` · A tool row arrives while the run page is open

**Trigger.** The agent repairs a run; the open run page's data is now stale.
**Behaviour.** `touched()` marks the object `mutates`, and the page re-reads on `rev` change — the same
mechanism `NotebookViewer` uses for a written notebook. No polling is added for this; one re-read on one
event.
**Test.** `domain/docs.test.ts::a repair marks the run stale`.

### `[E-22]` · The dock offers to explain a run

**Trigger.** Every new kind invites the 013 S2 defect: a suggestion that is plausible and wrong about its
subject.
**Behaviour.** Each new kind has its own three suggestions (`[UI-6]`), and a test asserts that no
`kind` falls through to the notebook branch. This is asserted **before** the screenshot can find it,
because 013 found it twice by looking.
**Test.** `domain/dock.test.ts::a job is never offered notebook actions`.

### `[E-23]` · Two rail groups fail for one cause

**Trigger.** The app's SP lacks both `jobs` and `pipelines` permission — one grant, two failures.
**Behaviour.** One box, not two, because `errorBoxes()` collapses identical messages and keeps different
ones. 013's `DataTree` already does this for two groups; the table-driven version must keep it for four,
and that is a test rather than an assumption.
**Test.** `DataTree.test.tsx::one cause shows one box and two causes show two`.

---

## F · The agent's own behaviour

### `[E-24]` · A model sends `tasks_json` as a string

**Trigger.** A model that formats its arguments as JSON text, which happens.
**Behaviour.** Accepted (the parameter exists for this) **and** parsed through the same validator, so a
string is not a way around `[TOOL-3]`. A malformed string returns one sentence naming the parse error and
the alternative (a native list).
**Test.** `test_jobs_tools.py::a_json_string_is_validated_like_a_list`.

### `[E-25]` · A model invents a `depends_on` key

**Trigger.** The model writes `{"task_key": "gold", "depends_on": ["Silver"]}` and the task is `silver`.
**Behaviour.** The refusal **names the case-insensitive match** when there is exactly one:
*"`depends_on` names 'Silver', which is not a task; did you mean 'silver'?"* A near-miss is the most
common graph error and a good sentence fixes it in one turn.
**Test.** `test_job_graph.py::a near-miss dependency is named`. `[TOOL-3]`.

### `[E-26]` · A model claims a run succeeded when it did not

**Trigger.** The tool returns `TERMINATED`/`FAILED` and the model's prose says "the job ran".
**Behaviour.** Not solvable in the tool; solved by the product. The run's state word is rendered from the
payload, the dock's answer and the page disagree visibly when a model lies, and the evidence supervisor
(`api/domain/supervisor.py`) already reports a claim with no supporting call. This spec adds the
**object** that makes the disagreement visible, which is the only honest mitigation.
**Test.** *manual* — the E2E scene S3 asserts a failing run renders `failed` while the answer is on
screen.

### `[E-27]` · The skill and the tools disagree

**Trigger.** `etl-pipelines.md` says "orchestrate with a job"; the tools can now build a pipeline.
**Behaviour.** The skill is rewritten as a decision table and a test asserts it names both objects, so a
future edit that removes one fails.
**Test.** `test_skills.py::test_the_pipeline_skill_names_both_objects_and_how_to_choose`. `[PIPE-1]`.

### `[E-28]` · A tool that leaves `core` is no longer discoverable

**Trigger.** `[TOOL-1]` removes three Lakebase tools from `core`.
**Behaviour.** Each is named by `lakebase-postgres.md`, and a test asserts every tool that left core is
named by some skill. Without that, a scaffold that used to work loses three calls and the agent has no
way to learn they exist.
**Test.** `test_tools_fence.py::every_tool_that_left_core_is_named_by_a_skill`.

---

## The cases that are deliberately *not* handled

| Not handled | Why |
|---|---|
| A job whose cron is in a timezone the platform rejects | the platform's sentence is returned verbatim; validating JVM timezone ids locally would be a second, worse list |
| A pipeline whose source file was deleted | the platform reports it in the update's events; the page shows the event, not a local guess |
| A run whose cluster was terminated by an admin | it appears as `INTERNAL_ERROR` with the platform's message; inventing a cause is worse than quoting one |
| Two users editing one job's schedule at once | the platform is last-write-wins and says so; this app has no schedule editor (`04` §What is deliberately absent) |
| A job with more than 100 tasks | the platform pages tasks; the page renders the first 100 and says "more tasks exist", rather than a graph that silently omits nodes |
