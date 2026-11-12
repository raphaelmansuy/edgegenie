[Index](README.md) · prev: [02 Assessment](02-assessment.md) · next: [04 Wireframes](04-wireframes.md)

# 03 · Requirements

Testable statements, in four groups. An id is cited from the document that must satisfy it, and from
[09 Edge cases](09-edge-cases.md) when a failure could violate it. No requirement here is a
restatement of an old one: each is new work, or a claim that was false before this spec.

Format: **MUST** = the release is not done without it. **SHOULD** = a stated trade-off if omitted.

---

## Group 1 · Lakebase (`LB-*`)

The database half. "Project" means a Lakebase Autoscaling project: `projects/{project_id}` with a
`production` branch.

### `[LB-1]` · Tools speak the Postgres API

Every Lakebase tool MUST use `/api/2.0/postgres/`, and MUST name the object it operates on by its
resource path. No tool may read `read_write_dns`, `capacity` or `instance_names`.

Why: `[F2]`. The compatibility layer makes the old call *succeed*, so the failure is silent and the
output is wrong.

Test: `tests/test_lakebase_tools.py` asserts the URL of every call against a fake transport; a
regression to `/api/2.0/database/` fails the test suite.

### `[LB-2]` · The five objects a user can build with are reachable

The tool server MUST expose, at minimum:

| Object | Operation | Tool |
|---|---|---|
| Project | create, get, list | `dbx_lakebase_create`, `dbx_lakebase_status`, `dbx_lakebase_list` |
| Branch | create from a branch, get, list | `dbx_lakebase_branch` |
| Database | create, list | `dbx_lakebase_database` |
| Role | create for a service principal, list | `dbx_lakebase_role` |
| Credential + SQL | mint, run, describe | `dbx_lakebase_sql`, `dbx_lakebase_tables` |
| Endpoint (compute) | get, update the autoscaling range | `dbx_lakebase_compute` |

Why: `[F2]`. Without a branch tool the agent cannot isolate work; without a role tool the app it
creates cannot connect; without a database tool it cannot create one.

Test: the tool count in the `core` profile is asserted; each tool has one test against a fake
transport asserting the method, path and body it builds.

### `[LB-3]` · SQL runs on a named branch, on the installed client

`dbx_lakebase_sql` MUST:

1. accept a project and an optional branch (default `production`), and resolve the branch's
   **read-write endpoint**;
2. mint a credential with `POST /api/2.0/postgres/credentials {endpoint}`, per call, never cached;
3. connect with **`psycopg` (v3)**, the client already in `requirements.txt`, with
   `sslmode=require` and a bounded `connect_timeout`;
4. connect as the signed-in user (Databricks identity), because the tool acts as them;
5. return `{columns, rows, row_count}` for a read, and `{ok, rowcount}` for a write;
6. never include the token in the returned text, an exception message, or a log line.

Why: `[F1]` (the import), `[F2]` (the endpoint), and `[001 rule 1]` (a secret is a reference).

Test: one test asserts the SQL text of a refused `GRANT` is not echoed with the password; one asserts
the credential is minted once per call and not reused across two calls.

### `[LB-4]` · The capacity rule is checked before the call

Creating or updating a compute MUST reject `max − min > 16`, `max > 64`, `min < 0.5`, and
`max > 32` when scale-to-zero is requested — with a sentence naming the rule, not a 400 from the
platform.

Why: the numbers are in the vendor contract; a user who types `0.5 → 32` should learn why in the same
turn, not from a stack trace.

Test: four parametrised cases, each asserting the message contains the violated bound.

### `[LB-5]` · A project's identity is its resource path

`projectRef("pg_tickets")` and `projectRef("projects/pg_tickets")` MUST produce the same key. A branch
ref is `projects/{p}/branches/{b}`; an endpoint ref is
`projects/{p}/branches/{b}/endpoints/{e}`. Nothing in the app may parse one of these out of prose.

Why: `[P2]`. The notebook equivalent is `canonicalPath`, added because one object in two spellings made
two tabs and a refresh that never fired.

Test: `domain/lakebase.test.ts` — the two spellings, idempotence, and a rejection of a path with `..`.

---

## Group 2 · Databricks Apps (`AP-*`)

### `[AP-1]` · Creating an app includes what the app needs to run

`dbx_create_app` MUST accept, and send:

- `name` — validated locally against `^[a-z0-9][a-z0-9-]{1,28}[a-z0-9]$` **before** the call;
- `resources` — a list; a `postgres` resource carries `branch`, `database`,
  `permission: CAN_CONNECT_AND_CREATE`;
- `user_api_scopes` — at minimum `postgres` when a postgres resource is present;
- `source_code_path` — optional, and when present it MUST be inside the session's write folder;
- `git_repository` — optional; when the workspace refuses a workspace-path source, its refusal is
  returned verbatim.

Why: `[F6]`. An app without the resource starts and cannot connect; the card's own promise then fails
one step later, in a place the user cannot see.

Test: the built body is asserted field by field against a fake transport; a missing branch or database
in a `postgres` resource is a local `ValueError` with the reason.

### `[AP-2]` · The app-name fence reads the app prefix

The tool server MUST read `NBMCP_WRITE_APP_PREFIX`, the registry MUST pass it, and `dbx_create_app`
MUST check the name against it. The check MUST NOT share the instance prefix.

Why: `[F3]`. The two prefixes are equal today, which is why the defect is invisible.

Test: `tests/test_tools_fence.py` starts the server with two *different* prefixes and asserts an app
name matching the instance prefix is refused, and a Lakebase project name matching the app prefix is
refused. The test fails if the wiring is removed.

### `[AP-3]` · A deployment is verified, not claimed

`dbx_create_app` MUST, after a successful deployment, poll the app's status until it is `RUNNING` or a
bounded timeout (~90 s) expires, and MUST return the state it observed plus a `verified` boolean. It
MUST NOT return the string "deployed" for a deployment that has not been observed running.

Why: `[001 rule 3]`. The repository's own `make deploy` learned this the expensive way — `SUCCEEDED`
means "the process started", not "it is running your code".

Test: a fake transport that stays `DEPLOYING` produces `verified: false` with the state and the next
action; one that reaches `RUNNING` produces `verified: true`.

### `[AP-4]` · An app's health is one HTTP call

A tool MUST fetch `GET https://{app.url}/` with the app's own token semantics (the app is a Databricks
App: it accepts the forwarded identity, so a plain GET returns a status and, for a UI, HTML). It MUST
report the status code and the elapsed time, and MUST treat a cold-start timeout as `starting`, not
`broken`.

Why: `[P1]` — "proven" means observed. An app that scales to zero answers slowly once.

Test: 200, 500, a connection error and a 3 s timeout each produce a distinct state.

---

## Group 3 · The scaffold, as one workflow (`SCF-*`)

### `[SCF-1]` · Seven steps, each with its own proof

A "new app from a Lakebase table" workflow MUST be expressible as an ordered set of steps, each
carrying the fact that proves it:

| # | Step | Proof |
|---|---|---|
| 1 | project | a project resource name |
| 2 | branch | a branch resource name, different from `production` |
| 3 | database + table | a row count read back |
| 4 | role + grant | the role exists for the app's service principal |
| 5 | files | `dbx_write_file` returned a byte count for each of the three files |
| 6 | app | the app resource name, with its postgres resource |
| 7 | verify | an HTTP status and a row count from the app |

Why: `[P1]`. This is the shape the card implies and the product cannot express.

Test: a `scaffold` domain module builds the plan from a list of tool results and reports
`done | pending | blocked` per step; a step with no matching completed call is `pending`.

### `[SCF-2]` · A failure stops the chain

If step *n* is blocked, steps *n+1…* MUST NOT run, and the plan MUST say which step is blocked and
why. Creating an app whose database does not exist is not a partial success; it is a broken object.

Why: `[P1]`, `[AP-1]`. The current tools have no ordering at all — the model decides, and a model that
reasons "the create failed, continue anyway" leaves an app pointing at nothing.

Test: a scripted scenario where the table step fails asserts zero `/api/2.0/apps` calls.

### `[SCF-3]` · The plan is visible while the work runs

The dock MUST show the plan from the ACP `plan` update it already receives, with each step's proof, and
the centre MUST show the step list with its state. A step is never drawn `✓` without a proof.

Why: `[P1]`. The app already maps `plan` to a `plan.updated` event (`api/adapters/acp/mapper.py`,
`from_update`); the transcript renders tool rows but does not connect a plan entry to the call that
proved it.

Test: `domain/scaffold.test.ts` maps a plan plus tool calls to the seven-step view; a call with
`status: "completed"` and no matching entry leaves the step `pending`.

### `[SCF-4]` · Nothing is created outside the fence

Creating a Lakebase project, a branch, a database, an app or a credential MUST be classified by the
same policy that classifies a path, and the tool server MUST refuse a name outside the session's
prefix. A refusal MUST name the prefix.

Why: `[F3]`, `[F4]`. Three of five policy functions currently have no caller; this makes "the fence
covers what the agent creates" true.

Test: the fence test from `[AP-2]`, plus a case for a project and a branch.

---

## Group 4 · What the user sees (`UI-*`)

### `[UI-1]` · Two new document kinds

`DocKind` and `DocRouteKind` MUST become
`"notebook" | "file" | "table" | "lakebase" | "app"`, and:

- `#/lakebase/projects/pg_tickets` opens the project;
- `#/lakebase/projects/pg_tickets/branches/agent-4ff4405d` opens that branch;
- `#/app/tickets_app` opens the app;
- an unknown or malformed route MUST still open the app (never a blank page);
- `parse(format(r)) === r` for every kind.

Why: `[F5]`, `[P4]`. The deep-link property is already asserted for three kinds and is what makes a
link pasteable into a ticket.

Test: `domain/route.test.ts` extended; the existing three-kind cases must keep passing unchanged.

### `[UI-2]` · A rail tab for the two new objects

The navigator MUST gain a fourth tab, **Data**, listing Lakebase projects and Databricks Apps with
state; `⌘4` selects it. The existing three tabs and their shortcuts MUST NOT change meaning.

Why: `[F5]`. Two new objects with no place to find them are reachable only by remembering a URL.

Test: `⌘4` selects Data; `⌘1..3` are unchanged; the tab order in the DOM matches the visual order.

### `[UI-3]` · A project page says what it is

Opening a project MUST show: resource name, Postgres version, branch count, the default branch, the
compute (endpoint type, autoscaling range with the ≤ 16 rule evaluated, idle policy), the databases
with table and row counts, and the apps using it. Each value MUST be a fact from a call, and a value
that could not be read MUST say so rather than render as `0`.

Why: `[P1]`, `[F5]`. The failure this replaces is a transcript that says "created" and a screen that
says nothing.

Test: a component test with a fixed payload asserts every label; a payload with a missing field renders
`—` and a note, never `0` or a blank.

### `[UI-4]` · An app page says whether it works

Opening an app MUST show: state, deployment state, URL (a real link), compute size, resources (with the
Lakebase branch and permission), the last health check with its status and time, and a link to `/logz`.
A cold-start timeout MUST read `starting`, not `down`.

Why: `[AP-3]`, `[AP-4]`. The user's next question after "create me an app" is "is it working", and it
must be answerable by looking.

Test: component test for `RUNNING`, `STOPPED`, `DEPLOYING`, and `starting`; the `/logz` link is
`https://{url}/logz`.

### `[UI-5]` · Both objects can be reached from where they appear

A tool row that created or read one of these objects MUST offer *Open* — the same affordance
`ToolCard` already gives a notebook (`touched()`) — and the palette and the `@` picker MUST find them by
name.

Why: `[F5]`. The transcript is where the user learns the object exists; it must be the door.

Test: `domain/toolview` or `domain/docs` maps `dbx_lakebase_create` / `dbx_create_app` arguments to a
`Doc`; a call whose arguments name nothing openable returns `null` (never a guess).

### `[UI-6]` · A refusal is shown with its remedy

A refusal from the platform (a missing `CAN MANAGE`, a git-only workspace, a name that does not match
the platform's pattern) MUST be rendered as: the platform's sentence, one line saying who can fix it,
and at most one action. It MUST NOT be rendered as a red block with a retry button that cannot work.

Why: `[P3]`. `[012]` established this for connection states; the same rule for permissions.

Test: three refusal payloads, each asserting the sentence is present verbatim and no retry is offered
when `[E-9]` says retrying cannot help.

---

## Non-goals

Stated so a reviewer does not look for them.

| Not doing | Why |
|---|---|
| A Lakebase **query editor** with results grid, history and saved queries | a different product; the `@table` preview and the notebook's SQL cell already cover ad-hoc reads |
| Managing every Lakebase setting (PG parameters, HA, read replicas, instant restore) | the pages show what a scaffold needs; the link to Databricks covers the rest |
| Creating an app from a **git** source on the user's behalf | `[RB-3]`: the app cannot grant its own service principal access to a repository; the refusal is reported and the git path is documented |
| Provisioning the workspace-level prerequisites (a secret scope, `CAN MANAGE` on a project) | `[RB-1]`, `[RB-2]`: identity and ownership are the boundary |
| Scheduled/parallel Genie-Code-style threads | [011] covers the mission model; this spec is about two object types |
| Replacing the agent with a deterministic scaffolder | the agent chooses; the *steps* are constrained, not the reasoning |

## Traceability

Every finding in [02](02-assessment.md) is closed by at least one requirement, and every requirement is
implemented in a named file in [08](08-implementation-plan.md).

| Finding | Requirements |
|---|---|
| F1 | `[LB-3]`, and the guard widened in phase 1 |
| F2 | `[LB-1]`, `[LB-2]`, `[LB-4]`, `[LB-5]` |
| F3 | `[AP-2]`, `[SCF-4]` |
| F4 | `[SCF-4]` |
| F5 | `[UI-1]`…`[UI-5]` |
| F6 | `[AP-1]`, `[AP-3]` |
| F7 | the `lakebase-postgres` skill, rewritten in phase 2 |
| F8 | phase 1: one copy, one test |
| F9 | phase 1: one copy, one test |
