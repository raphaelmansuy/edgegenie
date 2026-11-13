[Index](README.md) · prev: [04 Wireframes](04-wireframes.md) · next: [06 Lenses](06-lenses.md)

# 05 · Diagrams (Mermaid)

Behaviour over time, and the data the behaviour touches. Wireframes (`04`) show one state; these show
how a state is reached and what makes it change.

Every block below is parsed by the real Mermaid parser before this document is accepted:

```bash
cd /tmp && mkdir -p mmd && cd mmd && npm i mermaid jsdom
NODE_PATH=/tmp/mmd/node_modules node \
  apps/coding-agent/web/scripts/verify-spec-mermaid.mjs specs/013-improve-coding
```

---

## 1 · The scaffold, end to end

The sequence the card promises. Two properties are load-bearing and they are why this is a sequence
and not a list: **each step consumes the previous step's identity** (`[LB-5]`), and **a refusal stops
the chain** (`[SCF-2]`).

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant UI as React (dock + centre)
    participant API as FastAPI
    participant A as opencode (ACP)
    participant T as Tool server
    participant P as Lakebase (Postgres API)
    participant AP as Databricks Apps API

    U->>UI: "Create a Lakebase database with one table and a small app"
    UI->>API: POST /sessions/{id}/messages
    API->>A: prompt (+ fence: folder, schema, prefixes)
    A->>T: dbx_lakebase_create(name)
    T->>P: POST /api/2.0/postgres/projects
    P-->>T: projects/pg-tickets (+ production branch)
    T-->>A: {project, branch: production, state: READY}
    Note over A,T: step 1 proved: a resource name came back

    A->>T: dbx_lakebase_branch(project, from=production)
    T->>P: POST /projects/{p}/branches
    P-->>T: projects/{p}/branches/agent-4ff4405d
    T-->>A: {branch, endpoints: [primary]}

    A->>T: dbx_lakebase_database(project, branch, name)
    T->>P: POST .../branches/{b}/databases
    P-->>T: .../databases/db-tickets

    A->>T: dbx_lakebase_sql(project, branch, DDL + seed)
    T->>P: POST /api/2.0/postgres/credentials {endpoint}
    P-->>T: token (<= 60 min)
    T->>P: psycopg connect + execute (sslmode=require)
    T-->>A: {ok: true, rowcount: 12}
    A->>T: dbx_lakebase_sql(project, branch, SELECT count(*))
    T-->>A: {rows: [["12"]], row_count: 1}
    Note over A,T: step 3 proved: a row count was read back

    A->>T: dbx_write_file(app.yaml, main.py, requirements.txt)
    T-->>A: {path, bytes} x3

    A->>T: dbx_create_app(name, resources=[postgres], scopes=[postgres])
    alt name outside the app prefix
        T-->>A: PermissionError "name must start with agent-XXXX-"
        Note over A: stop. nothing was created [SCF-4]
    else allowed
        T->>AP: POST /api/2.0/apps (name + resources + scopes)
        AP-->>T: app + service principal
        T->>AP: POST /apps/{name}/deployments {source_code_path}
        AP-->>T: deployment id, state DEPLOYING
        loop until RUNNING or 90 s
            T->>AP: GET /apps/{name}
            AP-->>T: app_status.state
        end
        T-->>A: {app, url, verified: true|false}
    end

    A->>T: dbx_app_health(url)
    T->>AP: GET https://{url}/
    AP-->>T: 200 in 412 ms
    T-->>A: {status: 200, ms: 412}

    A-->>API: final message + plan (7 steps, each proved)
    API-->>UI: SSE events
    UI-->>U: two tool rows with "Open", and a plan with 7 ticks
```

**What this replaces.** Today the same request produces: a create against
`/api/2.0/database/instances`, a `ModuleNotFoundError` on the first SQL, and `POST /apps {name}` with no
resource. `[F1] [F2] [F6]`

---

## 2 · The scaffold's step machine

One state per step, and one rule: a step can only be `done` with a proof. This is the model S6 draws
and the one `domain/scaffold.ts` computes — from tool calls the app actually received, not from the
agent's prose.

```mermaid
stateDiagram-v2
    direction LR
    [*] --> pending
    pending --> running: a tool call started for this step
    running --> done: completed AND returned the proof
    running --> blocked: error, refusal, or a timeout
    running --> pending: cancelled (the turn was stopped)
    blocked --> pending: the user retries the turn
    done --> [*]

    note right of done
        proof is required:
        project→resource name
        branch→branch name
        table→row count
        role→role id
        files→byte counts
        app→app name+resource
        verify→HTTP status
    end note
```

```mermaid
stateDiagram-v2
    direction TB
    [*] --> Idle
    Idle --> Scaffolding: a plan with >= 2 steps arrives
    Scaffolding --> Scaffolding: a step proved
    Scaffolding --> Blocked: a step blocks
    Scaffolding --> Complete: every step proved
    Blocked --> Scaffolding: the user retries (new turn)
    Blocked --> Abandoned: the user starts something else
    Complete --> [*]
    Abandoned --> [*]

    note right of Blocked
        the chain stops here [SCF-2]:
        no later step runs
    end note
```

**The precedence that matters:** `Blocked` outranks `Scaffolding`. A plan whose step 3 failed is not
"still running" — and drawing it that way is how the previous UX hid a dead end ([012] found the same
class of bug in the dock's connection pill).

---

## 3 · The app's life, as the app can now observe it

The user's question is "is it working". The answer is an HTTP status, not a deployment state — a
distinction this repository learned when `SUCCEEDED` was mistaken for "serving this code".

```mermaid
stateDiagram-v2
    [*] --> NotFound
    NotFound --> Creating: dbx_create_app
    Creating --> Deploying: deployment accepted
    Creating --> Refused: 4xx (name, quota, git-only)
    Deploying --> Running: app_status RUNNING
    Deploying --> Failed: deployment FAILED
    Running --> Starting: a request after scale-to-zero
    Starting --> Running: first response under the timeout
    Starting --> Unresponsive: timeout exceeded
    Running --> Stopped: compute stopped
    Stopped --> Running: started again
    Running --> Failed: a 5xx health check
    Refused --> [*]
    Failed --> [*]

    note right of Unresponsive
        shown as "starting", never
        as "down": an app that
        scales to zero is slow once
        [E-14]
    end note
```

---

## 4 · One read of a project page

What happens when the user opens `#/lakebase/projects/pg_tickets`. Four calls in parallel, because the
page is a summary and a slow field must not hold up the others; each failure is local to its own block
(`[UI-3]`).

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant UI as Project page
    participant API as FastAPI
    participant P as Lakebase (Postgres API)

    U->>UI: open #/lakebase/projects/pg_tickets
    par four independent reads
        UI->>API: GET /api/lakebase/projects/pg_tickets
        API->>P: GET /projects/pg_tickets
        P-->>API: spec + status
        API-->>UI: {pgVersion, defaultBranch, endpoints, ...}
    and
        UI->>API: GET /api/lakebase/projects/pg_tickets/branches
        API->>P: GET /projects/{p}/branches
        P-->>API: [production, agent-4ff4405d]
        API-->>UI: branches
    and
        UI->>API: GET /api/lakebase/projects/pg_tickets/databases
        API->>P: GET .../branches/{b}/databases
        P-->>API: [databricks_postgres]
        API-->>UI: databases
    and
        UI->>API: GET /api/apps?lakebase=pg_tickets
        API->>P: GET /api/2.0/apps
        API-->>UI: apps whose postgres resource names this project
    end
    UI-->>U: four blocks, each with its own loading/error state
    Note over UI: a block that fails says so in place.<br/>It never shows 0 rows for "could not read" [E-11]
```

---

## 5 · The write fence, now that it has two new concepts

The fence is one function per kind of target, and the tool server is a **separate process**, so the
policy reaches it as environment plus the same pure rules. `[SCF-4]` makes the four previously-uncalled
functions real; `[RB-5]` explains why the sharing is by value and not by import.

```mermaid
flowchart TB
    subgraph session["one session"]
        S["Scope.for_session()<br/>folder · schema · job prefix<br/>app prefix · instance prefix"]
    end
    subgraph proc["app process (FastAPI)"]
        R["routers: save, materialise"]
        POL["domain/scope.py<br/>check_path check_sql<br/>check_job check_app check_instance"]
        R --> POL
    end
    subgraph child["tool server process (per session)"]
        ENV["NBMCP_WRITE_PATHS · _SCHEMAS<br/>_JOB_PREFIX · _APP_PREFIX · _INSTANCE_PREFIX"]
        CHK["_check_path_scope<br/>_check_sql_scope<br/>_check_prefix(kind, name, prefix)"]
        ENV --> CHK
    end
    S -->|"same five values"| ENV
    S -->|"used directly"| POL
    T1["dbx_write_notebook"] --> CHK
    T2["dbx_run_sql"] --> CHK
    T3["dbx_create_job"] --> CHK
    T4["dbx_create_app"] --> CHK
    T5["dbx_lakebase_create"] --> CHK
    CHK -->|"refusal names the prefix"| AGENT["the agent reads a sentence"]
    POL -->|"Verdict.ASK"| APPROVAL["approval panel"]
```

**The invariant** (asserted by `tests/test_tools_fence.py`): for each of the five kinds, a name inside
the prefix is allowed and a name outside it is refused, when the prefixes are **all different**. The
second half is the part today's code would fail: `dbx_create_app` compares against the instance prefix,
so an app named with the instance's prefix passes.

---

## 6 · The data model: what is stored, and what is only read

Nothing new is persisted for the two object kinds except a **cache with a TTL** and the session's
prefixes, which already exist. A project's and an app's truth lives in the workspace; the app is a
viewer. This is the `[E-R]` for the two new pages and their one durable addition.

```mermaid
erDiagram
    SESSION ||--o{ TURN : "has"
    TURN ||--o{ TOOL_CALL : "made"
    TOOL_CALL }o--|| OBJECT_REF : "names"
    OBJECT_REF ||--o| LAKEBASE_CACHE : "may be cached"
    OBJECT_REF ||--o| APP_CACHE : "may be cached"
    SESSION ||--|| SCOPE : "is fenced by"

    SESSION {
        string id PK
        string user_id
        string folder
        string schema
    }
    SCOPE {
        string folder
        string schema
        string job_prefix
        string app_prefix
        string instance_prefix
    }
    TURN {
        string id PK
        string session_id FK
        string status
        int step_index
    }
    TOOL_CALL {
        string call_id PK
        string turn_id FK
        string name
        string status
        string args_summary
        string result_summary
    }
    OBJECT_REF {
        string kind "lakebase|app"
        string ref "projects/p|appname"
        string display
    }
    LAKEBASE_CACHE {
        string ref PK
        string payload_json
        int fetched_at
        int ttl_seconds
    }
    APP_CACHE {
        string ref PK
        string payload_json
        int health_status
        int health_ms
        int fetched_at
    }
```

**Why a cache at all, and why it must be disposable.** A project page makes four calls. The rail lists
projects and apps on every load. Re-reading both on every keystroke would be slow and would spend the
user's API quota; a 60-second TTL makes the page feel instant and the staleness bounded. Nothing is
lost when the cache is dropped, which is why the test for it asserts the page still works with an empty
cache.

---

## 7 · Where a refusal goes

The path a non-2xx takes, in the four places it can arise. `[UI-6]` is satisfied only when **one** of
the terminal boxes is reached — never two, and never a retry on the right-hand branch.

```mermaid
flowchart LR
    A["a tool asks the workspace"] --> B{"status"}
    B -->|"2xx"| OK["a fact returns<br/>→ a step is proved"]
    B -->|"401 / 403"| P{"scope or ACL?"}
    B -->|"400 name / range"| V["our own validation<br/>(before the call)"]
    B -->|"404"| N["the object is gone<br/>→ offer a refresh"]
    B -->|"429 / 5xx"| T["transient<br/>→ one bounded retry"]
    P -->|"token lacks a scope"| S1["'this app is missing a permission'<br/>owner: the app's owner"]
    P -->|"the user's ACL"| S2["'you do not have CAN MANAGE'<br/>owner: the project's owner"]
    S1 --> STOP["shown once, with one action.<br/>No retry button."]
    S2 --> STOP
    V --> STOP
    N --> BACK["Refresh"]
    T --> AGAIN["retried once, then shown"]
    AGAIN --> STOP
    OK --> DONE["plan step ✓"]
```

The distinction in the `P` branch is not cosmetic: `ScopeMissing` in
`api/adapters/databricks/http.py` exists because telling a user "you do not have access" when the *app*
was never granted a scope sends them to the wrong person to ask.
