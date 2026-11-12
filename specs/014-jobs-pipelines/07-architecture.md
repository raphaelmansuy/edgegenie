[Index](README.md) · prev: [06 Lenses](06-lenses.md) · next: [08 Implementation plan](08-implementation-plan.md)

# 07 · Architecture

Where each rule lives, and why there rather than somewhere else. The test of a placement is: **if this
rule is removed, how many files fail?** One is right. Zero is a comment. Five is a missing abstraction.

Every path and line below was read in this checkout. The shape follows 013's `07` deliberately — same
ports, same error contract, same `Block` — because a second architecture in one app is a second app.

---

## 1 · The layers, and what each one is allowed to know

```text
  ┌──────────────────────────────────────────────────────────────────────────────────────────┐
  │ web/src/components/JobsPage · RunsPage · PipelinePage · DataTree                         │
  │   renders facts, never computes a policy         ·  Block, Fact, StatePill (013)         │
  ├──────────────────────────────────────────────────────────────────────────────────────────┤
  │ web/src/domain/jobs.ts                                                                   │
  │   PURE: words, tones, active/terminal, durationOf, taskLevels, pipelineWord              │
  │   no fetch, no React, no Date.now() except through an argument                           │
  ├──────────────────────────────────────────────────────────────────────────────────────────┤
  │ web/src/api/client.ts                                                                    │
  │   one place that knows the HTTP surface                                                  │
  ├──────────────────────────────────────────────────────────────────────────────────────────┤
  │ api/routers/jobs.py · api/routers/infra.py                                               │
  │   HTTP shapes, status mapping (_dbx_errors), no policy                                   │
  ├──────────────────────────────────────────────────────────────────────────────────────────┤
  │ api/domain/jobs.py                                                                       │
  │   PURE: state tables, runWord, updateWord, taskLevels, run graph validation              │
  ├──────────────────────────────────────────────────────────────────────────────────────────┤
  │ api/adapters/databricks/jobs.py · pipelines.py                                           │
  │   the only place that knows /api/2.2/jobs and /api/2.0/pipelines                         │
  ├──────────────────────────────────────────────────────────────────────────────────────────┤
  │ api/adapters/databricks/http.py  (DbxHttp — exists)                                      │
  │   the only place that maps 401/403/404 to PermissionError/LookupError                    │
  └──────────────────────────────────────────────────────────────────────────────────────────┘

  ┌──────────────────────────────────────────────────────────────────────────────────────────┐
  │ tools/databricks_notebook_mcp.py                                                         │
  │   the agent's surface: fence, validation, idempotency, and a sentence for every refusal  │
  └──────────────────────────────────────────────────────────────────────────────────────────┘
```

Two consequences a reviewer should check against the code:

* `api/domain/jobs.py` mirrors `web/src/domain/jobs.ts`, and the mirror is held by a **fixture**
  (`web/src/domain/jobs-table.json`), exactly as `event-parity.json` holds the event vocabulary
  (`tests/test_event_parity.py`). A word added on one side alone fails a test that names the file.
* the tool server is a **separate process** (`api/adapters/mcp/registry.py:73-83`), so it cannot import
  `api.domain.jobs`. Its copy of the graph validation is guarded by a parity test with one table of
  cases — the pattern 013's [RB-5] established for the fence, reused for the graph.

---

## 2 · The read path, and the three caches

A page makes **five fixed, independent** reads. This is 013's `page_blocks` decision, and the reason it
is repeated here rather than generalised into a framework is that the five differ per object: a job has
runs, a pipeline has updates and events, a run has task outputs. A generic fan-out helper would need a
per-object list anyway, so the list lives beside the object.

```text
GET /api/jobs/{job_id}
  ├── GET /api/2.2/jobs/get                    → {job}
  ├── GET /api/2.2/jobs/runs/list?limit=5      → {runs}
  ├── GET /api/2.2/jobs/runs/get?run_id=…      → {latestRun}      (tasks, states)
  ├── GET /api/2.2/jobs/runs/get-output        → {output}         (only when a task failed)
  └── GET /api/2.1/unity-catalog/tables/{t}    → {tables}         (only the tables the error names)
```

| Cache | Key | TTL | Why that lifetime |
|---|---|---|---|
| `RunCache` | `(token-hash, run_id)` | **infinite once terminal** | a terminal run's timestamps are frozen; the platform never rewrites them |
| `JobCache` | `(token-hash, job_id)` | 30 s, bypassed by the page's Refresh | `settings` change; a schedule shown 31 seconds stale is still true |
| `PipelineSpecCache` | `(token-hash, pipeline_id)` | 60 s, bypassed by Refresh | libraries and configuration change when someone edits the pipeline |
| *not cached* | — | — | a pipeline's **last update**: it is the one fact the page exists to report |

The token is part of every key. 013's `_Cache` (`api/adapters/databricks/lakebase.py:25-48`) already
does this and states why; this spec reuses the class instead of writing a second cache with the same
leak.

**Nothing on this path writes.** A page cannot change a job; the controls POST to a different route, and
that route is the only one with the fence on it.

---

## 3 · The six abstractions, and the count that justifies each

| Abstraction | Where | Replaces | The rule it owns |
|---|---|---|---|
| `Block` | `components/Infra.tsx` (exists) | a hand-written 4-state section | one refusal cannot blank a sibling; no retry on a permanent refusal |
| `useResource` | `web/src/hooks/useResource.ts` (new) | `useState` + `useEffect` + `.catch` per call | `loading → ready → error` is spelled once, and the error text extraction is one function |
| `TOUCHED` | `domain/docs.ts` (new table) | 5 `if` branches in `touched()` | how a tool call names an object; a kind is a row |
| `GROUPS` | `components/DataTree.tsx` (new table) | 2 × (`useState`+`useEffect`+renderer) | a rail group is data, not code |
| `RUN_ACTIONS` | `domain/jobs.ts` (new table) | `if (active) … else if (failed) …` in 3 components | which control is available in which state, from one matrix |
| state tables | `api/domain/jobs.py` + `web/src/domain/jobs.ts` | a `dict`/`Map` per component | one vocabulary, two runtimes, one fixture |

`useResource` is the only new hook, and it earns its place at nine call sites. Its contract is small
enough to state in one line: *given a key and a fetcher, return `{state, data, error, reload}` and cancel
an out-of-date response*. The cancel is not optional — a run page that navigates between run 1 and run 2
while run 1's request is in flight will otherwise paint run 1's tasks over run 2's header, which is the
race `LakebasePage` avoids by keying its component (`key={viewDoc.id}` in `App.tsx:1009-1013`). This spec
uses the same `key` trick **and** the hook's cancel, because the `key` remounts on a different document
but not on a re-poll of the same one.

---

## 4 · Where each policy lives

| Policy | Lives in | Enforced by | A test that fails if it moves |
|---|---|---|---|
| a job name starts with the session prefix | `tools/…_mcp.py::_check_prefix` + `api/domain/scope.py::check_job` | the tool server, at the call | `test_fence_parity.py::test_name_prefix_fence_is_per_kind` |
| the prefix is re-checked from the **returned** object | `tools/…_mcp.py::dbx_run_job` (and every new action tool) | the tool server | `test_jobs_tools.py::test_run_re_reads_the_job_and_refuses_a_foreign_name` |
| a task graph is valid | `tools/…_mcp.py::_validate_graph` + `api/domain/jobs.py::task_graph_problem` | the tool server before any HTTP; the app for its own copy | `test_job_graph.py`, `test_jobs_domain.py` (one table, both runtimes) |
| a pipeline belongs to this session | `SESSION_PIPELINE` table + `dbx_*_pipeline` | the tool server, asking the app | `test_pipelines_tools.py::test_a_pipeline_not_in_the_ledger_is_refused` |
| a schedule the agent creates is paused | `tools/…_mcp.py::dbx_create_job` | the tool server | `test_jobs_tools.py::test_a_scheduled_job_is_created_paused` |
| a run's state word | `api/domain/jobs.py::run_word` + `web/src/domain/jobs.ts::runWord` | both, held by a fixture | `test_jobs_domain.py::the_word_table_is_the_same_in_both_runtimes` |
| a page cannot be blanked by one denial | `Block` + the router's per-key exception capture | the component | `JobsPages.test.tsx::a denied block leaves the other blocks standing` |
| 25 tools at most | `tools/…_mcp.py::_CORE` | the tool server | `test_tools_fence.py::test_the_core_profile_stays_within_its_budget` |

The one rule with **two** implementations is the graph validation, and that is deliberate: the tool
server must refuse before it calls the platform (a refusal costs nothing; a 400 costs a round trip and
produces a worse sentence), and the app must classify a graph it is *shown* without calling the tool
server. Both read one table of cases, as the fence does.

---

## 5 · The identity question, resolved

`[RB-1]` (defined in [10](10-roadblocks.md)) is the roadblock: **a Databricks App's forwarded user token
cannot call the Jobs or Pipelines API**, because neither is a grantable `user_api_scopes` value. So the
architecture has two identities, and the rule for which is used is a property of the **API**, not of the
call site — the lesson 013's tool server already wrote down for Postgres
(`tools/…_mcp.py:133-145`: *"The three helpers below exist so that 'which identity' is a property of the
PATH'S API rather than of the call site — a call site is what got it wrong."*).

| Surface | Identity | Why |
|---|---|---|
| the agent's job tools (create, run, cancel, repair) | **the user**, then **the app's service principal** on a 403 | the platform grants a user token Jobs access only if a Job app resource is attached; where none is, the app's SP can still run jobs it has been given |
| the agent's pipeline tools | **the user**, then the SP | same shape |
| the pages' reads (job, run, pipeline) | **the app's service principal** | a page must render for a user who cannot call Jobs directly; the alternative is an empty page with no explanation |
| the page's **write** controls (Run now, Resume, Cancel, Stop) | **the user, via the tool server** — never a direct HTTP write from the browser | one fence, in one process. A page that could POST a run directly would be a second, un-fenced write path |

That last row is the important one, and it is a design constraint rather than an implementation detail:
**the browser has no write route for a job.** "Run now" asks the agent to call `dbx_run_job`, through the
same approval machinery every other write uses. That is slower than a direct POST by about a second, and
it means the product has exactly one place where a job can be started.

**The consequence, stated so it is not a surprise.** The pages show what the **app** may read, not what
the viewer may read, and 013's `infra.py` already prints that sentence for Lakebase. This spec keeps the
same sentence and adds the identity to the payload (`identity: "service principal" | "your sign-in"`), so
the page can say which it is instead of implying the stronger claim.

---

## 6 · The tool budget, spent deliberately

`[TOOL-1]` caps `core` at **28**. That is a raise from 25, so here is the arithmetic and the reason,
because a budget raised by editing an `==` to a bigger `==` is a drift, and a budget raised with a
reason, a compensating removal and a test is a decision.

| Action | Δ | Count | Note |
|---|---|---|---|
| before | — | 25 | measured: `_CORE` has 25, and it contains `dbx_create_job`, `dbx_run_job`, `dbx_job_run_status` — but **not** `dbx_list_jobs` and **not** `dbx_list_pipelines` |
| leave `core`, stay registered | −3 | 22 | `dbx_lakebase_database`, `dbx_lakebase_role`, `dbx_lakebase_tables` — a scaffold calls each once, and `lakebase-postgres` names all three |
| + `dbx_list_jobs` | +1 | 23 | **the oddest omission today**: the agent can create a job and never enumerate one, so "why did my job fail?" has no first step. It stays in `full` for nobody's benefit. |
| + `dbx_job_failure_context` | +1 | 24 | model-only: the failing task, its error, the real columns, the last good duration — assembled server-side so a model cannot conclude "the job is broken" when the truth is "the column was renamed" |
| + `dbx_create_pipeline` | +1 | 25 | |
| + `dbx_start_pipeline`, `dbx_stop_pipeline` | +2 | 27 | |
| + `dbx_pipeline_status` | +1 | 28 | carries the last update **and** the recent events: one call, one object |
| = | | **28** | |

**`dbx_pipeline_edit` does not enter `core`.** It stays registered in `full` and is named by the
rewritten `etl-pipelines` skill, on the same reasoning that lets the three Lakebase calls leave: an edit
is a step a skill describes, not a call a model must be able to make unprompted. It is the difference
between the four pipeline calls a conversation *starts* with and the one it reaches for after reading a
skill.

This also settles a question the first draft of the budget raised: **listing stays out of `core` for
pipelines**, because a pipeline the agent creates is returned with its id and read by
`dbx_pipeline_status`, and discovering pipelines that already exist is the rail's job — the same division
the product makes for Lakebase.

Two merges I considered and **rejected**, recorded so the next reader does not re-litigate them:

* **`dbx_start_pipeline` + `dbx_stop_pipeline` → `dbx_pipeline_control(action)`.** Saves one slot. It
  costs the model a decision it should not have to make (`action` is a string, and a typo is a 422 the
  model has to recover from), and it costs the fence one code path that must branch on the verb before it
  can check anything. Two tools with identical argument shapes are cheap; one tool with a verb argument
  is a union the model has to parse.
* **`dbx_list_jobs` + `dbx_list_pipelines` → `dbx_infra_list(kind)`.** Saves one slot. The two list
  payloads share no field: a job carries a schedule and a latest run, a pipeline carries an edition and a
  last update. A merged tool returns a union, and a model reading a union of two shapes guesses.

So the budget goes to 28, and `[TOOL-1]`'s test becomes three assertions rather than one equality:

```python
def test_the_core_profile_stays_within_its_budget(monkeypatch):
    m = load(monkeypatch)
    assert len(m._CORE) <= 28, sorted(m._CORE)
    # every member is reachable from a documented flow
    # every member that LEFT core is named by a skill
```

The third assertion is the one that makes the removal safe: `lakebase-postgres.md` must name
`dbx_lakebase_tables`, `dbx_lakebase_role` and `dbx_lakebase_database`, or a scaffold that used to work
silently loses three calls it needs. A tool that left `core` but is named by no skill is a tool the agent
can no longer discover — which is the removal's only real risk.

---

## 7 · What is reused, and what must not be re-invented

| Need | Reuse | Do not write |
|---|---|---|
| a 4-state section | `Block` (`components/Infra.tsx`) | a second loader component |
| a permission sentence | `api/adapters/databricks/http.py::denial` / `ScopeMissing` | a regex over error text in a router |
| HTTP status mapping | `_dbx_errors` (`routers/api.py:498`) | a `try/except` per route |
| "is this value a failure" | `isPermanent` (`components/Infra.tsx:37`) | a second regex |
| a deep link | `domain/route.ts::formatRoute/parseRoute` | a `window.location` builder |
| the tab, palette and recent wiring | `DocKind` exhaustiveness (`[UI-1]`) | a special case in `App.tsx` |
| the agent's evidence | `api/domain/supervisor.py` + `domain/scaffold.ts` | a job-specific checker |
| a refusal the model can act on | the `PermissionError` sentences in the tool server | a bare `{"error": "denied"}` |

The scaffold's step table (`web/src/domain/scaffold-steps.json`) gains **no** steps: a job is not a
seven-step scaffold. `[JOB-*]` is a page requirement, not a plan. The one thing the scaffold does get is
a proof field for the job it already creates — `job_id` — so that a `create a job` flow reports `1 of 1`
rather than nothing.

---

## 8 · The failure surface, in one table

Every failure the new code can produce, which layer produces it, and what the user reads.

| Failure | Layer | Status | The user reads |
|---|---|---|---|
| the token cannot call Jobs | adapter, via `DbxHttp.denial` | 403 | `ScopeMissing`'s sentence when a scope is named; else "you do not have access to job …" |
| the job does not exist | adapter, `LookupError` | 404 | "not found: /api/2.2/jobs/get" — and the page offers the Data tab |
| the task graph is invalid | tool server, before any call | — (tool result) | one sentence naming the key, in the transcript |
| the platform rejects the create | platform → tool server | tool result | the platform's `400` text, verbatim, plus "nothing was created" |
| the run is already active | tool server / adapter | 409 | "a run is already active for this job: run 812345678 (cancel it first)" |
| the pipeline is not in this session's ledger | tool server | — (tool result) | "this pipeline was not created in this conversation; open it in Databricks to change it" |
| the pipeline needs `ADVANCED` edition | platform | 200 + `platform_error` | the platform's sentence, verbatim |
| the workspace has no serverless | platform | 200 + `platform_error` | the platform's sentence, and the classic-compute alternative |
| a read was denied | adapter | 403 | the platform's sentence, in that block, with no retry |
| a read timed out | adapter | 502 | "the workspace did not answer in 20 s", with a retry |
| the run id is malformed | router, `ValueError` | 422 | "a run id is a number; got 'abc'" |

Two of these are worth their own sentence. **"a run is already active"** is a *success* from the
platform's point of view — `run-now` with an idempotency token returns the existing run — so the tool
must distinguish `reused: true` (fine, say so) from a second *deliberate* run. And **"nothing was
created"**
is the sentence that turns a `400` into information: without it, a model reads an exception and writes
"the job failed", which is the finding `F3` recorded.
