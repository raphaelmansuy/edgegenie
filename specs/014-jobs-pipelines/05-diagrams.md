[Index](README.md) · prev: [04 Wireframes](04-wireframes.md) · next: [06 Lenses](06-lenses.md)

# 05 · Diagrams

Five sequence diagrams, three state machines, one E/R model. Every one is checked to *parse* by
`node scripts/verify-spec-mermaid.mjs`, because a diagram that renders as a red error box is worse than
none at all.

The states and the fields are the platform's, quoted in [02](02-assessment.md#what-the-platform-says-in-the-places-this-spec-depends-on-it).
Where this spec adds a state of its own it says so, and the state is in `api/domain/jobs.py` — not in a
component.

---

## 1 · Sequence: "create a daily job and prove the first run"

The turn the product's own card promises. The point of the diagram is the **number of round trips**
and **where the fence is re-checked**.

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant S as App (FastAPI)
    participant A as Agent (ACP)
    participant T as Tool server
    participant W as Workspace API
    participant P as Platform (Jobs 2.2)

    U->>S: "Create a job that recomputes revenue at 06:00, run it once, prove it"
    S->>A: session/prompt
    A->>T: dbx_write_notebook(silver), dbx_write_notebook(gold)
    T->>W: POST /api/2.0/workspace/import
    W-->>T: object_id
    A->>T: dbx_create_job(name, tasks, cron)
    T->>T: fence: name starts with job_prefix
    T->>T: validate graph: unique keys, known deps, acyclic, one type each
    Note over T: a violation returns ONE sentence and<br/>makes ZERO HTTP calls
    T->>P: POST /api/2.2/jobs/create (queue on, schedule PAUSED)
    P-->>T: job_id 812345678901
    T-->>A: {job_id, name, schedule: "created PAUSED", next: "dbx_run_job"}
    A->>T: dbx_run_job(job_id, purpose="first-run")
    T->>P: GET /api/2.2/jobs/get (re-read, re-check the name)
    T->>P: POST /api/2.2/jobs/run-now (idempotency_token)
    P-->>T: run_id 812345679
    T->>P: GET /api/2.2/jobs/runs/get (poll, bounded)
    P-->>T: TERMINATED + FAILED, per-task error
    T-->>A: {run_id, tasks:[{gold: FAILED, error}]}
    A-->>S: answer: job created (paused), first run FAILED on gold, error quoted
    S-->>U: two clickable objects: the job and the run
```

**What the diagram asserts.** Six platform calls for a job that gets created, run and read back. No
call is made to validate the graph. The fence is checked **twice** on the write path and **once more**
on the run path, from the object the platform returned.

---

## 2 · Sequence: "read a job page"

Five independent reads, because one slow or denied call must not blank the other four — 013's
`page_blocks` decision, applied to a job.

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant B as Browser
    participant S as App
    participant W as Workspace API
    participant P as Platform

    U->>B: open #/job/812345678901
    B->>S: GET /api/jobs/812345678901
    par five reads, any of which may fail alone
        S->>P: GET /api/2.2/jobs/get
    and
        S->>P: GET /api/2.2/jobs/runs/list?job_id=…&limit=5
    and
        S->>P: GET /api/2.2/jobs/runs/get?run_id=<latest>
    and
        S->>P: GET /api/2.2/jobs/runs/get-output?run_id=<latest failed task>
    and
        S->>P: GET /api/2.1/unity-catalog/tables/<from the last run's SQL hint>
    end
    P-->>S: five answers, in whatever order they arrive
    S-->>B: {job, runs, latestRun, output, tables} — any key may be {error}
    B->>B: each Block renders its own state
    B-->>U: F2, with a per-block refusal where one call was denied
```

**What the diagram asserts.** The response is a **record of outcomes**, not a success or a throw. The
browser never sees one error replace four facts.

---

## 3 · Sequence: "run in flight, cancelled by the user"

Cancellation is asynchronous in the platform's own words: *"The run is canceled asynchronously, so it
may still be running when this request completes."* The diagram is the reason the page keeps polling.

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant B as Browser
    participant S as App
    participant P as Platform

    U->>B: Run now
    B->>S: POST /api/jobs/812345678901/runs {purpose:"ui-<n>"}
    S->>P: POST /api/2.2/jobs/run-now (idempotency_token from purpose)
    P-->>S: run_id, reused=false
    S-->>B: {run_id}
    B->>B: open #/run/812345679 immediately (not "wait for the answer")
    loop every 3 s while the tab is visible
        B->>S: GET /api/runs/812345679
        S->>P: GET /api/2.2/jobs/runs/get
        P-->>S: RUNNING
        S-->>B: running, elapsed 12 s
    end
    U->>B: Cancel (confirm dialog names run id + elapsed)
    B->>S: POST /api/runs/812345679/cancel
    S->>P: POST /api/2.2/jobs/runs/cancel
    P-->>S: {} (accepted, not completed)
    S-->>B: {accepted:true, note:"cancellation is asynchronous"}
    loop until terminal or the tab is hidden
        B->>S: GET /api/runs/812345679
        S-->>B: TERMINATING, then TERMINATED + CANCELED
    end
    B-->>U: the run's own word: canceled
```

**What the diagram asserts.** The UI opens the run **before** it is finished — a run page that only
exists after completion is not a way to watch a run. And `accepted: true` is never rendered as
`canceled`.

---

## 4 · Sequence: "build a pipeline and start an update"

The object this product could not create at all before this spec.

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant A as Agent
    participant T as Tool server
    participant W as Workspace API
    participant P as Platform (Pipelines 2.0)

    U->>A: "build a medallion pipeline: bronze, silver, gold, with a data-quality check"
    A->>T: dbx_write_notebook(bronze_orders), (silver_orders), (gold_revenue)
    T->>W: POST /api/2.0/workspace/import  (x3)
    A->>T: dbx_create_pipeline(name, libraries, catalog, schema)
    T->>T: refuse if catalog empty (serverless always uses UC)
    T->>P: POST /api/2.0/pipelines (serverless, edition ADVANCED, no clusters)
    P-->>T: pipeline_id f0e1c4a2-…
    T->>T: record pipeline_id in THIS session's ledger
    T-->>A: {pipeline_id, state:"IDLE", next:"dbx_start_pipeline(validate_only=true)"}
    A->>T: dbx_start_pipeline(pipeline_id, validate_only=true)
    T->>T: fence: pipeline_id is in the ledger
    T->>P: POST /api/2.0/pipelines/f0e1…/updates {validate_only:true}
    P-->>T: update_id
    T->>P: GET /api/2.0/pipelines/f0e1…/updates/<id>
    P-->>T: COMPLETED (validated, nothing materialised)
    A->>T: dbx_start_pipeline(pipeline_id)  (a real run)
    T->>P: POST …/updates {}
    P-->>T: update_id 8a0b6d02
    T->>P: GET …/updates/8a0b6d02 (poll)
    P-->>T: COMPLETED
    A-->>U: pipeline f0e1… created and updated — 6 flows, 0 expectations failed
```

**What the diagram asserts.** `validate_only` first. It is free, it answers the question an edit
creates, and it turns a five-minute debugging loop into a twenty-second one. And the fence for a
pipeline is the **session ledger**, because a UUID has no prefix.

---

## 5 · Sequence: "the app reads a job the user may not"

The roadblock, drawn. `[RB-1]` and `[RB-2]` are defined in [10](10-roadblocks.md).

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant B as Browser
    participant S as App
    participant SP as Service principal
    participant P as Platform

    U->>B: open #/job/812345678901
    B->>S: GET /api/jobs/812345678901
    S->>S: which identity may read a JOB?
    Note over S: jobs is NOT a grantable user scope,<br/>so the forwarded user token cannot call it
    alt a job app resource is attached for this workspace
        S->>SP: GET /api/2.2/jobs/get (SP token)
        P-->>SP: the job
        SP-->>S: the job
        S-->>B: the page, with identity:"the app's service principal"
    else no resource is attached
        S-->>B: 403 with the platform's sentence AND the remedy:<br/>"attach a Job resource with CAN_VIEW in the app's settings"
        B-->>U: F6, with one action: "how to grant this"
    end
```

**What the diagram asserts.** The page never claims to be showing what the *user* can see when it is
showing what the *app* can see. The identity is on the page, in words — the rule 013's `infra.py`
header established for Lakebase, extended to jobs.

---

## 6 · State: a job run

The platform's two fields, drawn as one machine. `life_cycle_state` is the position;
`result_state` is the colour of the terminal node.

```mermaid
stateDiagram-v2
    [*] --> QUEUED: run-now accepted
    QUEUED --> PENDING: compute requested
    QUEUED --> BLOCKED: a dependency cannot run
    PENDING --> RUNNING: cluster up
    RUNNING --> TERMINATING: work finished
    RUNNING --> WAITING_FOR_RETRY: task failed, retries left
    WAITING_FOR_RETRY --> RUNNING: retry begins
    RUNNING --> INTERNAL_ERROR: platform fault
    TERMINATING --> TERMINATED
    TERMINATED --> [*]: result_state decides the word
    INTERNAL_ERROR --> [*]
    BLOCKED --> [*]
    SKIPPED --> [*]

    state TERMINATED {
        [*] --> SUCCESS
        [*] --> FAILED
        [*] --> TIMEDOUT
        [*] --> CANCELED
        [*] --> UPSTREAM_FAILED
        [*] --> SUCCESS_WITH_FAILURES
    }
```

Three consequences for the code, each a test:

1. **`TERMINATED` is not success.** `lifeCycle === "TERMINATED" && result === "SUCCESS"` is the only
   success. This is the defect class 013's [RB-12] recorded.
2. **Active means six words, not one.** `PENDING`, `QUEUED`, `RUNNING`, `TERMINATING`, `BLOCKED`,
   `WAITING_FOR_RETRY`. "Cancel" must appear for all six, and "Repair" only after a terminal
   `FAILED`/`TIMEDOUT`.
3. **`result_state` is absent while running.** A page that reads it during a run gets `undefined`, so
   the state word must be derived from `life_cycle_state` in that case — and `undefined` must render
   as `running`, not as `unknown`.

---

## 7 · State: a pipeline update

```mermaid
stateDiagram-v2
    [*] --> QUEUED: start accepted
    QUEUED --> WAITING_FOR_RESOURCES
    QUEUED --> INITIALIZING
    WAITING_FOR_RESOURCES --> INITIALIZING
    INITIALIZING --> CREATING_FLOW
    CREATING_FLOW --> RUNNING
    RUNNING --> COMPLETED
    RUNNING --> FAILED
    RUNNING --> CANCELED: stop
    RESETTING --> RUNNING: full refresh
    QUEUED --> CANCELED: stop before start
    COMPLETED --> [*]
    FAILED --> [*]
    CANCELED --> [*]
```

The pipeline's **own** state (`IDLE`, `RUNNING`, `FAILED`, …) is a different axis and is shown beside
the update, never instead of it. A pipeline is `IDLE` both when it has never run and when its last
update failed; `pipelineWord()` reads the update. That is `[PIPE-5]`.

---

## 8 · State: what the pages do while a run is in flight

The client-side machine, which is not the platform's. Its point is that polling has an end.

```mermaid
stateDiagram-v2
    [*] --> loading: the page opens
    loading --> ready: the first read answered
    loading --> error: the first read failed
    ready --> polling: the run is active
    polling --> polling: every 3 s, tab visible
    polling --> ready: the run is terminal
    polling --> paused: the tab is hidden
    paused --> polling: the tab is visible again
    ready --> canceling: the user confirms Cancel
    canceling --> polling: accepted, still active
    error --> loading: retry (transient only)
    ready --> [*]: the user leaves
    polling --> [*]: the user leaves
```

`paused` exists because a background tab that keeps polling a job costs the platform money in API
calls and buys nothing — nobody is looking. `document.visibilityState` is the signal, and one test
asserts that no interval survives the tab being hidden.

---

## 9 · E/R: what the product stores, and what it only reads

The point of this diagram is the **left half vs the right half**. Everything inside the app's database
is durable; everything outside it is a cache of a platform fact and must never be the only copy.

```mermaid
erDiagram
    SESSION ||--o{ TOOL_CALL : "observes"
    SESSION ||--o{ SESSION_PIPELINE : "created"
    SESSION ||--|| SCOPE : "is fenced by"
    TOOL_CALL }o--|| OBJECT_REF : "names"
    OBJECT_REF ||--o| JOB_CACHE : "may be cached as"
    OBJECT_REF ||--o| RUN_CACHE : "may be cached as"
    OBJECT_REF ||--o| PIPELINE_CACHE : "may be cached as"

    SESSION {
        text id PK
        text folder
        text schema_name
        text user_id
    }
    SCOPE {
        text session_id PK
        text folder_prefix
        text job_prefix
        text app_prefix
        text instance_prefix
    }
    TOOL_CALL {
        text id PK
        text session_id FK
        text name
        text status
        text result_json
        int started_at
    }
    OBJECT_REF {
        text kind "job|run|pipeline"
        text ref "the platform's id, as text"
        text session_id FK
    }
    SESSION_PIPELINE {
        text session_id PK
        text pipeline_id PK
        int created_at
    }
    JOB_CACHE {
        text job_id PK
        text settings_json
        int fetched_at
    }
    RUN_CACHE {
        text run_id PK
        text life_cycle_state
        text result_state
        int start_time
        int end_time
    }
    PIPELINE_CACHE {
        text pipeline_id PK
        text last_update_id
        text last_update_state
        int fetched_at
    }
```

| Table | Written by | Read by | Loss means |
|---|---|---|---|
| `SESSION`, `TOOL_CALL` | the orchestrator, every event | the transcript, the mission, the evidence check | the conversation is gone (it is durable, 010) |
| `SCOPE` | derived, never stored as state | the fence, both runtimes | nothing: it is a function of the session id |
| `OBJECT_REF` | the transcript reducer | `touched()`'s server twin, the "recent" list | a tool row's object stops being clickable |
| `SESSION_PIPELINE` | `dbx_create_pipeline` | the pipeline fence `[TOOL-6]` | a restart forgets which pipelines this session may stop |
| `JOB_CACHE`, `RUN_CACHE`, `PIPELINE_CACHE` | the adapters, with a TTL | the pages, to avoid a re-read | a slower page, never a wrong one |

**Why the caches are separate tables and not columns on `OBJECT_REF`.** A job and a run have different
lifetimes and different cache keys: a run is immutable once terminal and can be cached forever, a job's
`settings` change. Putting both in one row means one TTL for two facts, which is how a page ends up
showing a stale schedule beside a fresh run.

**Why `SESSION_PIPELINE` is durable and not in process memory.** `[TOOL-6]` says the fence for a
pipeline is the ledger of what this session created. If the ledger lives in the tool-server process, a
session that resumes after an app restart (010's whole point) can no longer stop the pipeline it made an
hour ago — and the refusal would read as a permission problem. So the ledger is a table, and the tool
server asks the app for it.

---

## 10 · Sequence: the fence, end to end

The one diagram a security reviewer wants: every rule applied to the action it governs.

```mermaid
sequenceDiagram
    autonumber
    participant A as Agent
    participant T as Tool server
    participant S as App
    participant P as Platform

    A->>T: create_job(name, tasks)
    T->>T: 1. name starts with NBMCP_WRITE_JOB_PREFIX
    T->>T: 2. every notebook_path is inside NBMCP_WRITE_PATHS
    T->>T: 3. the graph is valid (unique, known deps, acyclic)
    T->>P: create
    Note over T,P: nothing reaches the platform until 1, 2 and 3 pass

    A->>T: run_job(job_id)
    T->>P: GET job
    T->>T: 4. the RETURNED name satisfies rule 1
    T->>P: run-now with an idempotency token

    A->>T: start_pipeline(pipeline_id)
    T->>S: 5. is this id in this session's ledger?
    S-->>T: yes / no
    T->>P: start (only on yes)

    A->>T: stop_pipeline(pipeline_id)
    T->>S: 5. same ledger question
    S-->>T: yes / no

    A->>T: update_job(job_id, settings)
    T->>P: GET job
    T->>T: 4. the returned name satisfies rule 1
    T->>P: update
```

Rules 1–4 are the prefix-and-path fence the repository already had; rule 5 is new and is the reason
`SESSION_PIPELINE` exists. **A rule with no call site is a comment**, which was 013's [F4]; so
`test_fence_parity.py` gains a row per rule and each row fails if the call is removed.
