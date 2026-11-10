[Index](README.md) · prev: [01 Five whys](01-five-whys.md) · next: [03 Requirements](03-requirements.md)

# 02 · Measured assessment

Eleven findings. Each names a file and a line in **this checkout**, the behaviour that line produces,
and — where the platform is the authority — the sentence the platform actually documents. Nothing here
is remembered; every claim was checked on 10 November 2026 against the repository and against
`docs.databricks.com`.

The findings are the evidence for the requirements in [03](03-requirements.md). They are cited as `F1`
… `F11` without brackets so they cannot be confused with the defined ids `[JOB-1]`, `[E-1]`, `[RB-1]`.

---

## A · The job tools answer a slightly different question than the one asked

### `F1` · The tool speaks Jobs API 2.1; 2.2 changed a default

```1088:1097:apps/coding-agent/tools/databricks_notebook_mcp.py
    body: dict = {"name": name, "tasks": tasks}
    if cron:
        body["schedule"] = {"quartz_cron_expression": cron, "timezone_id": timezone, "pause_status": "PAUSED"}
    data = _post("/api/2.1/jobs/create", body)
```

`/api/2.1/jobs/create` still works: 2.0 and 2.1 remain callable. The problem is the documented
difference in behaviour, quoted from the platform's *Updating from Jobs API 2.1 to 2.2*:

> "For jobs created with the Jobs API 2.2, queueing is enabled by default. You can turn off queueing by
> setting the `queue` field to `false` in request bodies when you create or update a job."

So a job this tool creates and the identical job created in the Databricks UI today are **different
objects**: one skips a run when resources are unavailable, the other queues it. Neither the transcript
nor any screen says which. That is a silent behavioural difference in a product whose entire value
proposition is that its claims are checkable. [F1]

Moving to 2.2 also brings the fields this spec needs and 2.1 makes awkward: `idempotency_token` on
`submit`, `queue`, and `environments` for serverless Python.

### `F2` · Running a job is not idempotent

```1101:1110:apps/coding-agent/tools/databricks_notebook_mcp.py
@tool()
def dbx_run_job(job_id: int, wait_seconds: int = 45) -> str:
    """Trigger a job run. With wait_seconds > 0 wait for it and return per-task
    results (exit values, errors). Requires NBMCP_ALLOW_WRITES=1."""
    _need_writes()
    job = _get("/api/2.1/jobs/get", {"job_id": job_id})
    _check_prefix("job", (job.get("settings") or {}).get("name", ""), JOB_PREFIX)
    run_id = _post("/api/2.1/jobs/run-now", {"job_id": job_id})["run_id"]
```

`run-now` accepts `idempotency_token`: *"An optional token to guarantee the idempotency of job run
requests. If a run with the provided token already exists, the request does not create a new run but
returns the run ID of the existing run."* The tool sends none.

The consequence is not theoretical. The server's `_retry` (`:276-296`) deliberately does not retry a
POST except on 429/503 — a decision made precisely so "a retried runs/submit can never double-launch".
But that protection lives in the *retry helper*, not in the *operation*: an agent that is unsure
whether its call landed, or a UI that offers "Run now" twice while the first request is in flight,
starts two runs of a job that bills per cluster-minute. The pipeline equivalent (`start`) has the same
shape. [F2] → `[JOB-6]`, `[RUN-4]`, `[E-5]`.

### `F3` · A malformed task graph reaches the platform

```1078:1090:apps/coding-agent/tools/databricks_notebook_mcp.py
    built = []
    for t in tasks:
        _check_path_scope(t["notebook_path"])
        item: dict = {"task_key": t["task_key"], "notebook_task": {"notebook_path": t["notebook_path"]}}
        if t.get("depends_on"):
            item["depends_on"] = [{"task_key": k} for k in t["depends_on"]]
```

Four inputs are accepted here and refused later by the platform with `400
INVALID_PARAMETER_VALUE`:

| Input | What the platform says | What the agent concludes |
|---|---|---|
| two tasks with the same `task_key` | `Duplicated task keys` | "the job is broken" |
| `depends_on` naming a task that is not in the list | `Task <k> depends on unknown task` | "the dependency failed" |
| a cycle (`a → b → a`) | `Dependency cycle detected` | "the job is stuck" |
| a task with neither `notebook_path` nor `pipeline_id` nor `job_id` | `Task <k> must have exactly one task type` | "the tool is broken" |

The important part is **when** the failure happens: the create call is rejected, so **nothing was
created**, yet the agent's answer is built from a traceback and reads like a job exists. A refusal that
happens before any HTTP call can say *"task keys must be unique; you sent `silver` twice"* — a sentence
the model can act on in the same turn. [F3] → `[JOB-3]`, `[E-1]`.

### `F6` · `dbx_list_jobs` does not return what its docstring promises

```861:873:apps/coding-agent/tools/databricks_notebook_mcp.py
def dbx_list_jobs(limit: int = 25) -> str:
    """List jobs with their latest run state."""
    data = _get("/api/2.1/jobs/list", {"limit": limit, "expand_tasks": "false"})
    return _trim(
        [
            {
                "job_id": j.get("job_id"),
                "name": (j.get("settings") or {}).get("name"),
                "schedule": ((j.get("settings") or {}).get("schedule") or {}).get("quartz_cron_expression"),
            }
```

There is no run state in the payload. `jobs/list` does not carry one: the job object has `settings`,
`created_time`, `creator_user_name` and (with `expand_tasks`) `tasks`. The latest run needs
`jobs/runs/list?job_id=…&limit=1`, one call per job.

Two consequences. The rail cannot show a state beside a job without N calls, which is `O(n)` round
trips for a list that renders on every page load — the exact cost 013's [06 §6.2] refused for apps. And
an agent asked "is my job healthy?" receives a payload that looks like it answered and did not.

**A third, found while checking the first two.** The tool is not in `_CORE`. Every session is started
with `NBMCP_PROFILE=core` (`api/adapters/mcp/registry.py:55`), and the set at
`tools/databricks_notebook_mcp.py:75-87` contains `dbx_create_job`, `dbx_run_job` and
`dbx_job_run_status` but **not** `dbx_list_jobs`. So a deployed agent can create a job, run it, and poll
a run id it already holds — and cannot answer *"which jobs do I have?"* at all. The asymmetry is not a
design decision anyone made; it is the shape of a set that grew by demand. Measured, not inferred:
`_CORE` has exactly 25 entries and `dbx_list_jobs` is not one of them.

## B · Pipelines are a read-only afterthought

### `F4` · There is exactly one pipeline tool, and it cannot create anything

The whole of the pipeline surface is:

```1121:1129:apps/coding-agent/tools/databricks_notebook_mcp.py
@tool()
def dbx_list_pipelines(limit: int = 25) -> str:
    """List Lakeflow Spark Declarative Pipelines."""
    data = _get("/api/2.0/pipelines", {"max_results": limit})
    return _trim(
        [{"pipeline_id": p.get("pipeline_id"), "name": p.get("name"),
          "state": p.get("state"), "catalog": p.get("catalog")}
         for p in data.get("statuses", data.get("pipelines", []))]
    )
```

The Pipelines API offers `create`, `get`, `update`, `delete`, `start`, `stop`, `list-updates`,
`get-update`, `list-events`, `clone`, and edit. This tool uses one of them.

Meanwhile `tools/skills/etl-pipelines.md` — the skill an agent reads before building a medallion
architecture — says:

```1:7:apps/coding-agent/tools/skills/etl-pipelines.md
# ETL pipelines as Databricks Jobs (bronze -> silver -> gold)

## Shape
- One notebook per stage under the allowed workspace folder, created with `dbx_write_notebook`.
- Orchestrate with `dbx_create_job(name, tasks=[...])`, then `dbx_run_job(job_id, wait_seconds=300)`.
```

So "build me a pipeline" produces **a job of three notebooks**. That is a legitimate architecture and it
is the wrong object: the user asked for Lakeflow, gets no lineage graph, no expectations, no
`STREAMING TABLE`, no incremental refresh — and the skill never mentions that the product cannot build
what was asked for. This is the most expensive finding in the set, because it is a *capability gap
papered over by a skill*, which is precisely the failure 013 recorded as [F6]. [F4] → `[PIPE-1]`…`[PIPE-6]`.

### `F5` · The pipeline state is not an update's result

`p.get("state")` returns the **pipeline's** state. The documented values are `DEPLOYING`, `STARTING`,
`RUNNING`, `STOPPING`, `DELETED`, `RECOVERING`, `FAILED`, `RESETTING`, `IDLE`. A pipeline that has never
run is `IDLE`, and a pipeline whose last update failed is *also* `IDLE` — the failure lives on
`latest_updates[].state`, whose documented values are `QUEUED`, `WAITING_FOR_RESOURCES`, `INITIALIZING`,
`RESETTING`, `CREATING_FLOW`, `RUNNING`, `IDLE`, `COMPLETED`, `FAILED`, `CANCELED`.

Reading `state` therefore reports "idle" for both "never run" and "last run failed". This is [F5], and
it is the same class of defect as 013's [RB-12]: the convenient field is not the honest one.
→ `[PIPE-5]`, `[UI-8]`.

## C · The product cannot show either object

### `F7` · Five document kinds, none of them a job

```8:8:apps/coding-agent/web/src/domain/docs.ts
export type DocKind = "notebook" | "file" | "table" | "lakebase" | "app";
```

The union is enumerated in six places, each of which must grow:

| File | Line | What enumerates it |
|---|---|---|
| `web/src/domain/docs.ts` | 8 | the kind itself |
| `web/src/domain/route.ts` | 20 | `DocRouteKind`, the URL grammar |
| `web/src/domain/recent.ts` | 14, 34, 67 | the "recently opened" list and its name rule |
| `web/src/domain/dock.ts` | 104-121 | three suggestions per kind |
| `web/src/App.tsx` | 77-79, 1009-1013 | the palette group and the page switch |
| `web/src/domain/docs.ts` | 154-163 | `ACTIONS_FOR`, the quick actions |

Growing it is mechanical but *not* optional: `Record<DocKind, …>` means the compiler names every site,
which is the mechanism 013 relied on and which worked. [F7] → `[UI-1]`.

### `F8` · `touched()` knows five kinds and reads two new ones

```93:112:apps/coding-agent/web/src/domain/docs.ts
export function touched(name: string, args?: string, result?: string): { doc: Doc; mutates: boolean } | null {
  if (LAKEBASE_TOOLS.test(name)) {
    const found = projectFrom(result) ?? projectFrom(args);
    if (!found) return null;
    return { doc: makeDoc("lakebase", found), mutates: /create|branch|database/.test(name) };
  }
  if (APP_TOOLS.test(name)) { /* … */ }
  const m = (args && PATH_ARG.exec(args)) || (result && PATH_ARG.exec(result)) || null;
  if (!m) return null;
  const mutates = MUTATING.test(name);
  if (NOTEBOOK_TOOLS.test(name)) return { doc: makeDoc("notebook", m[1]), mutates };
  if (FILE_TOOLS.test(name)) return { doc: makeDoc("file", m[1]), mutates };
  return null;
}
```

Two hand-written branches for infrastructure, then a path regex. `dbx_create_job` returns
`{"job_id": …}` — an integer — and this function returns `null`. Nothing opens. Nothing is marked stale.
Nothing is clickable. That is why the card's job turn produces text, and it is the *same* mechanism 013
built for Lakebase, applied to one more object type and reaching its limit. [F8] → `[JOB-9]`.

The DRY correction is not another `if`: it is a table, `TOUCHED`, of `(name pattern, kind, extract)`
where `extract` returns `{ref, name}` or `null`. Adding a kind becomes a row, and a test asserts the
table covers every kind (a `Record<DocKind, …>` makes the compiler insist).

### `F9` · The `Data` tab has two hard-coded groups

```24:49:apps/coding-agent/web/src/components/DataTree.tsx
  const [projects, setProjects] = useState<Load<LakebaseProject[]>>({ state: "loading", data: [] });
  const [apps, setApps] = useState<Load<AppView[]>>({ state: "loading", data: [] });
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let live = true;
    setProjects({ state: "loading", data: [] });
    setApps({ state: "loading", data: [] });
    api.lakebaseProjects()/* … */
    api.apps()/* … */
    return () => { live = false; };
  }, [tick]);
```

Two states, two calls, two group headings (`Lakebase`, `Databricks Apps` at `:69` and `:97`), and a
hand-written row renderer per group. Four groups (Lakebase, Jobs, Pipelines, Apps) with four
independent `Load` states written the same way is 4 × the boilerplate and three more places to get the
error-collapsing rule wrong — the rule `errorBoxes()` (`:136-148`) exists for, because two calls that
fail for one cause must show one box ([013 UI-6]).

The DRY correction is a `useResource` hook + a declarative group table, so the four groups differ only
in data. [F9] → `[UI-2]`.

## D · The two roadblocks

### `F10` · Jobs and pipelines are not grantable user scopes

This decides the architecture, so it is stated in the platform's words. The Databricks Apps
authorization documentation lists the **supported `user_api_scopes`**:

> `ai-functions`, `ai-functions`, `ai-gateway`, `apps`, `files`, `genie`, `model-serving`, `postgres`,
> `sql`, `vector-search`, `sql:restricted-query`; and the SDK scopes `catalog.catalogs`,
> `catalog.connections`, `catalog.schemas`, `catalog.tables`, `workspace.workspace`.

`jobs` and `pipelines` are **not on that list**. The platform's documented remedy for a workload is a
**Lakeflow Jobs app resource**:

> "When you add a job resource, the app's service principal gains the specified permissions on the
> selected job" — with `CAN_VIEW`, `CAN_MANAGE_RUN` or `CAN_MANAGE`.

The tool server already contains a measurement of this, from the notebook-run path:

```1029:1036:apps/coding-agent/tools/databricks_notebook_mcp.py
    try:
        run_id = _post("/api/2.1/jobs/runs/submit", {"run_name": "nbmcp-run", "tasks": [task]})["run_id"]
    except PermissionError:
        # A Databricks App's user authorization has no jobs scope, so the user's token cannot submit a
        # run. When the host app offers to run it itself (as the app, for administrators), ask it to.
```

So the same reasoning that made 013 put Lakebase *reads* on the service principal ([RB-10] there)
applies here, and with a sharper edge: a **Job app resource binds one job id**, which cannot be known
before the agent creates the job. The roadblock is real and the mitigation is architectural — a
two-identity design where the tool server writes as the user when it can and the *page reads* go
through the app's service principal, with the app resource attached on demand. It is worked through in
[10 Roadblocks](10-roadblocks.md) as `[RB-1]`, `[RB-2]`, `[RB-3]`.

### `F11` · The tool budget is 25, and it is enforced

```75:87:apps/coding-agent/tools/databricks_notebook_mcp.py
_CORE = {
    "dbx_whoami", "dbx_list_tables", "dbx_describe_table", "dbx_search_tables", "dbx_run_sql",
    "dbx_list_notebooks", "dbx_read_notebook", "dbx_grep_notebook", "dbx_write_notebook",
    "dbx_write_file", "dbx_run_notebook", "dbx_run_notebook_status", "dbx_create_job", "dbx_run_job", "dbx_job_run_status",
    "dbx_lakebase_create", "dbx_lakebase_status", "dbx_lakebase_sql", "dbx_lakebase_branch",
    "dbx_lakebase_database", "dbx_lakebase_role", "dbx_lakebase_tables",
    "dbx_create_app", "dbx_app_health", "dbx_skill",
}
```

```208:212:apps/coding-agent/tests/test_tools_fence.py
def test_the_core_profile_is_a_deliberate_size(monkeypatch):
    """[RB-8] Every MCP tool is advertised on every request. The count is asserted so growth is a
    decision rather than a drift."""
    m = load(monkeypatch)
    assert len(m._CORE) == 25, sorted(m._CORE)
```

Every MCP tool is advertised on every request, so the count is a cost paid on every turn of every
session. The budget is currently exactly 25 and a test holds it there. This spec adds job read/edit
tools and a full pipeline surface; it must therefore **spend** some of the existing slots — the three
`dbx_lakebase_database`/`role`/`tables` calls that only a scaffold uses are candidates — and it must
change that test from "exactly 25" to "at most 25, and every member has a page or a documented flow",
which is a better assertion. [F11] → `[TOOL-1]`, `[E-20]`.

---

## What the platform says, in the places this spec depends on it

Collected so a reviewer does not have to fetch four pages. All quoted from `docs.databricks.com` on
2026-11-10.

| Fact | Source |
|---|---|
| `POST /api/2.2/jobs/create`; a task is `{task_key, <one task type>, depends_on[], timeout_seconds, max_retries, run_if}` | Jobs API 2.2, *Create a new job* |
| `notebook_task.notebook_path` required; `pipeline_task.pipeline_id` required; `run_job_task.job_id` required; `sql_task`, `spark_python_task`, `condition_task`, `for_each_task` also exist | same |
| Queueing defaults **on** for 2.2, **off** for 2.0/2.1 | Jobs API 2.2 update notes |
| `life_cycle_state` ∈ `{PENDING, RUNNING, TERMINATING, TERMINATED, SKIPPED, INTERNAL_ERROR, BLOCKED, WAITING_FOR_RETRY, QUEUED}` | Jobs API, Run object |
| `result_state` ∈ `{SUCCESS, FAILED, TIMEDOUT, CANCELED, MAXIMUM_CONCURRENT_RUNS_REACHED, UPSTREAM_CANCELED, UPSTREAM_FAILED, EXCLUDED, SUCCESS_WITH_FAILURES, DISABLED}`, **only in a terminal state** | same |
| `runs/list` limit is `1..25`, default 20; `start_time_from`/`start_time_to` are epoch ms; `run_type` ∈ `{JOB_RUN, WORKFLOW_RUN, SUBMIT_RUN}` | Jobs API, *List job runs* |
| `runs/cancel` is asynchronous — the run may still be running when the call returns | Jobs API, *Cancel a run* |
| `runs/repair` returns `repair_id`, and a second repair must pass `latest_repair_id` | Jobs API, *Repair a job run* |
| `runs/delete` refuses an active run | Jobs API, *Delete a job run* |
| `jobs/update` merges arrays by `task_key`; `fields_to_remove` handles top-level fields and `tasks/<key>` | Jobs API, *Update job settings partially* |
| `POST /api/2.0/pipelines` create; `serverless: true` requires `edition: ADVANCED` and Unity Catalog, and `clusters` must be omitted | Pipelines API; *Configure a serverless pipeline* |
| Pipeline states: `DEPLOYING, STARTING, RUNNING, STOPPING, DELETED, RECOVERING, FAILED, RESETTING, IDLE` | Pipelines API, *List pipelines* |
| Update states: `QUEUED, WAITING_FOR_RESOURCES, INITIALIZING, RESETTING, CREATING_FLOW, RUNNING, IDLE, COMPLETED, FAILED, CANCELED` | Pipelines API, *List pipeline updates* |
| `start` accepts `full_refresh`, `refresh_selection`, `full_refresh_selection`, `reset_checkpoint_selection`, `validate_only`, `development` | Pipelines API, *Start a pipeline* |
| `libraries[]` is `{notebook: {path}}`, `{file: {path}}` or `{glob: {include}}` | Pipelines API, `PipelineSpec` |
| An app's `job` resource supports `CAN_VIEW`, `CAN_MANAGE_RUN`, `CAN_MANAGE` | App resource reference; *Add a Lakeflow Jobs resource* |

Everything in [07 Architecture](07-architecture.md) is a consequence of that table, and every URL in
the adapters is one of the rows above.
