[Index](README.md) · prev: [09 Edge cases](09-edge-cases.md) · next: [11 E2E plan](11-e2e-plan.md)

# 10 · Roadblocks

What is in the way, grounded in code and in the platform's documentation, and the way past each. Every
roadblock names whether it can be **removed from here**, **worked around**, or only **reported** — the
distinction 013's `10` made and that a reviewer is entitled to.

An `[RB-*]` cited from a requirement is defined here and nowhere else.

| # | Roadblock | Removable? | What it costs if ignored |
|---|---|---|---|
| `[RB-1]` | `jobs` and `pipelines` are not grantable user-authorization scopes | **no** — the platform decides | every page 403s, and no sign-in can fix it |
| `[RB-2]` | A Job app resource binds **one job id**, which cannot exist before the agent creates the job | **partly** — a two-speed identity | the agent can create jobs it cannot read back |
| `[RB-3]` | The tool server is a subprocess with no durable state, and the pipeline fence needs state | **yes** — a file the app owns | a resumed session cannot stop what it made |
| `[RB-4]` | The tool budget is 25 and a test holds it | **yes** — a decision, made in `07 §6` | nine new tools advertised on every turn |
| `[RB-5]` | The graph validator exists in two runtimes (tool server and app) | **no** — separate processes | the two disagree, and a valid job renders as cyclic |
| `[RB-6]` | `runs/get-output` is only valid for a *terminal* run | **yes** — a guard | a `400` on every page load of a running run |
| `[RB-7]` | The rail cannot show a run state without `n` calls | **yes** — moved to the page | a 25-call rail on a cold workspace |
| `[RB-8]` | Serverless pipelines need a region, the terms accepted, and Unity Catalog | **no** — a workspace property | a create that fails with a sentence nobody predicted |

---

## `[RB-1]` · The forwarded user token cannot call Jobs or Pipelines

**The obstacle.** The Databricks Apps authorization documentation lists the **supported
`user_api_scopes`**: `ai-functions`, `ai-gateway`, `apps`, `files`, `genie`, `model-serving`, `postgres`,
`sql`, `vector-search`, `sql:restricted-query`, and the SDK scopes `catalog.*` and `workspace.workspace`.
**`jobs` and `pipelines` are not on that list.** The platform blocks access outside the approved scopes
even when the user has the permission in the workspace.

**Measured in this repository, before this spec.** `tools/databricks_notebook_mcp.py:1029-1036` catches
`PermissionError` from `jobs/runs/submit` and comments:

> *"A Databricks App's user authorization has no jobs scope, so the user's token cannot submit a run."*

So the measurement already exists in the codebase and nothing acted on it: the notebook-run path has a
fallback (run it as the app, for administrators) and the **job** path has none.

**What the platform provides instead.** A **Lakeflow Jobs app resource**. The documentation:

> "When you add a job resource, the app's service principal gains the specified permissions on the
> selected job" — `CAN_VIEW`, `CAN_MANAGE_RUN`, or `CAN_MANAGE`.

The resource is declared in the app's spec:

```json
{ "name": "job", "job": { "id": "812345678901", "permission": "CAN_MANAGE_RUN" } }
```

**Why that is not enough on its own.** `[RB-2]`.

**The mitigation, as far as it can go from here.**

1. **Reads go through the app's service principal**, unconditionally, exactly as 013 made Lakebase reads
   go through it. The app's SP is the owner of every job it creates, so it can read them.
2. **Every payload says which identity read it** (`identity: "service principal" | "your sign-in"`), and
   the page states it. This is 013's rule — *"the page says so instead of blaming the user's sign-in"* —
   applied to a second API.
3. **Writes stay on the tool server**, and the tool server falls back to the SP token on a `403` from a
   user token, reporting `ran_as` in its result. The pattern exists: `dbx_run_notebook` already does
   exactly this.
4. **The remedy is a sentence, not a retry.** When neither identity can act, the refusal is the
   platform's text plus *"attach a Job resource with CAN_MANAGE_RUN in the app's settings"* — an action a
   workspace admin can take. The page links to the app's settings URL.

**What is honestly not solved.** The app resource binds **one job id per resource entry**. A workspace
with 200 jobs would need 200 resource entries, which the app spec cannot express sanely. So for a user
whose jobs the SP does not own — a job created in the Databricks UI by a person — the page will show a
refusal until an admin attaches the resource. That is reported, not hidden: the `Data` tab says
*"2 jobs are not readable by this app"* rather than omitting them.

**Test.** `test_jobs_adapter.py::reads_use_the_service_principal_and_say_so`,
`test_infra_routes.py::a_payload_names_the_identity_that_read_it`.

---

## `[RB-2]` · A Job app resource binds an id that does not exist yet

**The obstacle.** The whole point of this spec is that the **agent creates** a job. A resource is
declared in `databricks.yml` and granted at deploy time. There is no way to declare a resource for a job
whose id is generated during a conversation.

**What this means, concretely.**
* a job the **agent** created: the app's SP is its creator, therefore its owner, therefore it can read
  and run it — no resource needed;
* a job a **person** created in the Databricks UI: the SP has no permission on it, and no resource entry
  can exist for it, so the page refuses.

That asymmetry is the actual capability boundary of this product, and it is the right one: this app
manages what it built, and links out for the rest. 013 reached the same conclusion for Lakebase (a
project the app created is readable; one it did not may not be) and stated it as a product decision
rather than a defect.

**The mitigation.** The `Data` tab's job group is labelled with its scope: *"Jobs this app created"*, and
a footer says *"jobs created elsewhere are opened in Databricks"*. A second group, if the SP can list
workspace jobs at all, is rendered read-only with the refusal inline.

**Test.** `test_infra_routes.py::an_unreadable_job_is_counted_not_omitted`.

---

## `[RB-3]` · The tool server is a subprocess, and the pipeline fence needs state

**The obstacle.** `api/adapters/mcp/registry.py` starts one tool-server process per session and kills it
on `stop()` (`:120-126`). A pipeline id is a UUID with no session prefix, so `[TOOL-6]` needs a list of
"what this session created" — and process memory does not survive a restart, which 010's whole durable
session model makes a routine event, not an error.

**The way past it.** A **ledger file**, one path per session, owned by the app and passed to the tool
server in the environment (`NBMCP_SESSION_LEDGER`). One JSON line per created object:

```json
{"kind":"pipeline","id":"f0e1c4a2-…-9a2b","name":"sales_medallion","created":"2026-11-10T05:58:41Z"}
```

**Why a file and not a table.** The ledger is append-only, per-session, and tiny. A table would be a
schema, a migration and a write path into the session store for a question that is *"did this
conversation make it?"* — a weaker question than authorization, as the database lens argued. A file is
the honest representation, and it is inspectable with `cat` when something goes wrong.

**Why not the app's database, given 010 ships one.** Because the ledger must be readable by the **tool
server**, which has no database credential and should not get one: its only credential is the Databricks
token. Handing it a Postgres connection to answer a permission question would widen what a compromised
tool server can reach from "one workspace API" to "the session store". The file is written by the process
that asks the question, in a directory the app chose.

**The cost, stated.** A redeploy that wipes the volume loses the ledger, and a Stop becomes a refusal. The
`/tmp` path used for blobs (`app.yaml`'s `APP_BLOB_DIR`) has the same property, and this spec puts the
ledger beside it rather than inventing a second durability story. `[E-16]` records the behaviour.

**Test.** `test_pipelines_tools.py::test_the_ledger_survives_a_tool_server_restart`.

---

## `[RB-4]` · The tool budget is 25, and a test holds it

**The obstacle.** `_CORE` has exactly 25 entries and
`tests/test_tools_fence.py:208-212` asserts `len(m._CORE) == 25`. Every MCP tool is advertised on every
request, so the count is a per-turn cost in tokens and in the model's attention. This spec needs five
pipeline tools and one model-only job tool.

**The way past it.** A stated decision, in [07 §6](07-architecture.md#6-the-tool-budget-spent-deliberately):
three Lakebase scaffold calls leave `core` (each named by a skill, so still discoverable), one tool is
added for jobs, five for pipelines, and the budget becomes **28** with three assertions replacing the
equality. A budget raised with a reason, a compensating removal and a test is a decision; a budget raised
by editing `25` to `28` is a drift.

**Test.** `test_tools_fence.py::test_the_core_profile_stays_within_its_budget` (three assertions) and
`::every_tool_that_left_core_is_named_by_a_skill`.

---

## `[RB-5]` · The graph validator exists twice, by necessity

**The obstacle.** The tool server is a separate process and cannot import `api.domain.jobs`
(`registry.py:73-83` spawns `python3 tools/databricks_notebook_mcp.py`). So the "is this task graph
valid" rule must exist on both sides: the tool server refuses before calling the platform, and the app
classifies a graph it renders.

This is the same duplication 013 recorded as `[RB-5]` for the write fence, with the same resolution.

**The way past it.** One module, `tools/job_graph.py`, with **no I/O** — it imports nothing but
`dataclasses` and `re`. The tool server imports it by path; the app imports it by path in tests. One
table of cases (`tests/test_job_graph.py::SHAPES`) is asserted against both, and the app's `taskLevels`
and the tool's `validate` are required to agree on every row.

**Why not a shared package.** Both processes are shipped in one directory tree and the app is deployed as
a single folder; a third top-level package would need to be in the deploy's include list, the
`pyproject.toml`'s package list, and the packaging test. A module in `tools/` that both sides reach by
path is the smaller change, and `_find_server()` (`registry.py:19-28`) already walks parents looking for
`tools/`, so the path logic exists.

**Test.** `test_job_graph.py::the_app_and_the_tool_agree_on_every_shape`.

---

## `[RB-6]` · `runs/get-output` is only valid for a terminal run

**The obstacle.** The Jobs API documents `get-output` as available for a run that has finished. Calling
it while `life_cycle_state` is `RUNNING` answers `400 INVALID_PARAMETER_VALUE`. The job page reads the
latest run's output whenever a task failed — and the latest run may be **running**, in which case there is
no output and there never was a failure.

**The way past it.** The adapter checks `is_terminal(life_cycle)` **before** it asks, and returns
`output: null` with no call. This is one `if` and it saves a `400` on every poll of a running job — which
is the case where the page is being read most often. `duration_seconds` has the same shape (`[E-12]`).

**Test.** `test_jobs_adapter.py::no_output_call_for_a_running_run` (asserts the fake recorded one GET of
the run and no call to `get-output`).

---

## `[RB-7]` · The rail's run state would cost `n` calls

**The obstacle.** The natural design — a rail row per job with its last run's state — needs
`runs/list?job_id=…` per job. The job object from `jobs/list` carries no run state (`F6`). At 25 rows on
a cold workspace that is 25 round trips before the rail paints; at 100 it is unusable.

**The way past it.** The state moves to the object that has one page: the job page. The rail row carries
the **schedule's** pause state, which `jobs/list` *does* return (inside `settings.schedule`), and no run
state. The palette's job entries carry the same. A user who wants the run state opens the job — one
click, one page, five calls.

This is the same trade 013's `[06 §6.1]` made: *"One call per kind, no fan-out: this lists on every page
load."*

**Test.** `test_infra_routes.py::the_jobs_list_is_one_call`.

---

## `[RB-8]` · A serverless pipeline needs three workspace properties

**The obstacle.** The documentation's requirements for a serverless pipeline:

* Unity Catalog enabled;
* `ADVANCED` product edition;
* the serverless terms of use accepted;
* a serverless-enabled region.

None of these can be created from a tool call, and any of them missing produces a failure whose sentence
does not obviously name the property to fix.

**The way past it, as far as it goes.** `[TOOL-7]` validates what it can locally (`catalog` non-empty,
`edition` legal, no `clusters` with `serverless`), so the common mistakes are refused before a round trip.
For the rest, the platform's sentence is returned **verbatim** plus the one line that names the three
properties and the link to the workspace's serverless settings. The page renders the same sentence in
the block that failed, with no retry.

**What cannot be done from here.** A workspace in a region with no serverless cannot run this workflow,
and the product must say so rather than appear broken. That is `[E-4]`.

**Test.** `test_pipelines_tools.py::test_a_serverless_refusal_names_the_classic_alternative`.

---

## The roadblocks 013 left, and how they interact with this one

Worth stating, because a reviewer of this spec will ask whether it reopened anything.

| 013's roadblock | Still true? | Effect here |
|---|---|---|
| `[RB-10]` `postgres` cannot run OBO | yes | this spec reuses 013's `sp_token.provider` for jobs and pipelines, so the identity plumbing is shared, not copied |
| `[RB-5]` the fence exists in two runtimes | yes | `[RB-5]` above is the identical shape for the graph, and takes the identical resolution |
| `[RB-12]` the API's field names are not the guessable ones | yes | `[E-10]`, `[E-12]` and `[PIPE-5]` are three more instances: `result_state` is absent while running, `life_cycle_state` is not a result, a pipeline's `state` is not its update's |

The pattern in that third row is the reason this spec spends a whole document on state words: **every
Databricks API has one field that is convenient and one that is honest, and they are never the same
field.** The mitigation is structural — a pure function per object, one table, two runtimes, one parity
test — because the next object type will have the same trap.

---

## What a reviewer should do with this document

1. Check the claim in `[RB-1]` against the platform's current supported-scope list. If `jobs` appears
   there one day, the two-identity design can collapse into one, and this document is where that change
   starts.
2. Check that every roadblock with a mitigation has a test named. Eight roadblocks, eight tests.
3. Check that no roadblock is described as "will be fine" — that phrase does not appear.
