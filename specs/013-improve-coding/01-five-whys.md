[Index](README.md) · next: [02 Measured assessment](02-assessment.md)

# 01 · Five whys and first principles

The card in the product is one sentence long. The failure is eight files deep. This document walks
down to the irreducible part, then walks back up with the smallest set of rules that fixes it.

---

## The report

> *"Lakebase and an app — Create a Lakebase database with one table and a small app that reads it. Show
> me the connection details."*
>
> On the deployed app: the turn ends with a prose summary and two tool rows. Nothing opens. Re-running
> it fails differently. Asking "is the app running?" gets a fresh guess instead of a fact.

## Why 1 — why does the turn end without a usable object?

Because three of the five tools it needs do not work, and the two that do have no output the app can
show.

```text
dbx_lakebase_create   → /api/2.0/database/instances   returns the Provisioned shape
dbx_lakebase_sql      → import psycopg2               ModuleNotFoundError: no psycopg2
dbx_create_app        → POST /api/2.0/apps {name}     no resources, no scopes, no source
dbx_write_file        → works (a plain workspace file)
dbx_skill             → works (reads the markdown)
```

`dbx_lakebase_sql` is the load-bearing one: it is the only way to create a schema, a table, a seed row
or a verification query on the new database. Without it the agent can create an instance and no data,
which is exactly the half-finished state the card was written to avoid.

## Why 2 — why is `psycopg2` missing?

Because the tool server is not part of the app's dependency surface. It is a **separate process** that
the app spawns (`SubprocessToolRegistry.start`), it runs with `sys.executable`, and its imports are
inside `tools/`, which no build step inspects:

```python
# tools/databricks_notebook_mcp.py:1026-1033
import uuid
import psycopg2                     # not in requirements.txt, not in pyproject.toml
```

The repository has a test whose whole purpose is "every runtime import is declared"
(`test_packaging.py::test_every_runtime_import_is_declared`) — and it walks `api/` only:

```python
for py in (APP / "api").rglob("*.py"):
```

The `app` root is `api/`, `tools/` is a sibling of `api/`, and the walk never descends into it. The
guard was written for a deployment that crashed on `pydantic_settings`; it protects the app and not the
process the app starts. A dependency hole opened the day the tool server gained a Postgres client, and
the test that exists to catch exactly that cannot see it.

Meanwhile the app **does** ship a Postgres client: `psycopg[binary]>=3.2` in `requirements.txt`, used
by the model registry. So the fix is not "add a dependency" but "use the one already installed, and
make the check cover the process that needs it". Two clients for one protocol is the drift this spec
keeps finding.

## Why 3 — why does the Lakebase tool describe objects the platform no longer has?

Because the tool was written against Lakebase **Provisioned**, and Lakebase became **Autoscaling**
underneath it:

| | Provisioned (what the tool assumes) | Autoscaling (what exists now) |
|---|---|---|
| Object | one instance | project → branch → endpoint → database → role |
| Create | `POST /api/2.0/database/instances {name, capacity}` | `POST /api/2.0/postgres/projects` (a `production` branch is created with it) |
| Address a compute | `read_write_dns` on the instance | `status.hosts.host` on an endpoint, `projects/{p}/branches/{b}/endpoints/{e}` |
| Credential | `POST /api/2.0/database/credentials {instance_names}` | `POST /api/2.0/postgres/credentials {endpoint}` |
| Size | `capacity: CU_1` | `autoscaling_limit_min_cu` / `_max_cu`, `max − min ≤ 16` |
| Idle | always on | scale to zero, 24 h default |

Since 2026-03-12 the *old* endpoint creates an Autoscaling project, so the tool's create call still
"succeeds" — and every field it reads back afterwards belongs to an API result the platform is
maintaining for compatibility, not to the object the user now has. That is worse than a hard failure:
it produces a plausible host, a plausible capacity, and no branch, no database and no role to connect
with. The deployment scripts in this repository already use the new API
(`databricks postgres get-project`, `create-role`, `generate-database-credential`), so the repository
contains both dialects and the agent is on the wrong one.

## Why 4 — why did nobody notice?

Because the two objects have **no representation in the product**. There is no `DocKind` for a project
and none for an app:

```ts
// web/src/domain/docs.ts:4
export type DocKind = "notebook" | "file" | "table";
```

```ts
// web/src/domain/route.ts:17
export type DocRouteKind = "notebook" | "file" | "table";
```

So a turn that creates a project cannot open it, and a project cannot have a URL. The only trace of the
work is the transcript row — `created a database ✓` — which is the tool's label, not the object's
state. A product that cannot *show* an object gives an engineer no surface on which to notice that the
object is wrong.

## Why 5 — why was the object never added?

Because the fence, the route grammar and the tool prefix were all designed for **workspace paths**, and
the two new types are not paths:

- a notebook has a path, and `check_path` compares a prefix;
- a table has a three-part name, and `check_sql` parses the statement;
- a Lakebase project has an **id the platform chose** (or the user's name, which becomes the id);
- an app has a **name the platform restricts** to `[a-z0-9-]{2,30}` and a service principal.

`Scope` did grow `app_prefix` and `instance_prefix`, and `check_app` / `check_instance` were written and
tested. Then the wiring stopped: the tool server is started with `NBMCP_WRITE_INSTANCE_PREFIX` and
**not** `NBMCP_WRITE_APP_PREFIX`, so `dbx_create_app` compares the app's name to the *instance* prefix,
and `check_app` has no caller outside its test.

That is the irreducible finding: **the fence grew two new concepts and the wiring only carried one of
them.** Everything else in this document follows from finishing that wiring and giving both concepts a
screen.

---

## First principles

Four statements that do not depend on any API version. Each is a test in
[08](08-implementation-plan.md).

### P1 · A scaffold is a sequence of proven facts

An infrastructure turn is not a paragraph with a list in it. It is a chain:

```text
project exists → branch exists → a role may connect → a table exists with N rows
              → an app exists → the app has the database as a resource → the app answers HTTP 200
```

Every link is a call that returned something checkable. If a link is missing, the chain stops **there**
and the next link is not attempted. This is [001 rule 3] ("done means proven") with infrastructure as
the subject, and it is why the plan in S6 draws `·` for steps that have no proof.

*Test:* a scaffold that fails at the table step must never create an app. `[SCF-4]`

### P2 · The identity of the object is the one the platform assigned

A project's resource name is `projects/{project_id}`, an endpoint's is
`projects/{p}/branches/{b}/endpoints/{e}`, an app's is its name. The app must never parse one out of a
prose summary, and never invent one from a display name. This is the same rule that made
`canonicalPath` necessary for notebooks: one object, one key, or two tabs for one thing.

*Test:* `projectRef("pg_tickets")` and `projectRef("projects/pg_tickets")` produce the same `Doc.id`.

### P3 · A permission denial is a first-class outcome, not an error to retry

`CAN MANAGE` on a project, `apps` scope on the token, a git-only workspace, a workspace that refuses
Apps without a Git repository: each produces one sentence, one owner to ask, and **no retry loop**. The
tool server already does this for a 401/403 (`_refuse` raises `PermissionError("… Do not retry …")`);
the same discipline has to reach the Lakebase and Apps tools, and the UI has to render the refusal with
its remedy. [012]'s principle, applied to a different kind of failure.

*Test:* a 403 from `POST /projects` returns a message containing "CAN MANAGE" and the tests assert the
tool was called once.

### P4 · An object that exists in the workspace must be openable in the app

Four kinds of object, one navigation model: `notebook | file | table | lakebase | app`. The route
grammar, the tab strip, the recent list, the palette and the `@` picker all read one union; adding a
kind is a case in one switch and a branch in one renderer, not a new subsystem.

*Test:* `parseRoute(formatRoute(r)) === r` for every kind, including a project id with a branch, and a
malformed one still opens the app rather than a blank page — the property `route.test.ts` already
holds for three kinds and must hold for five.

---

## What the platform says, and what it costs us

Each row is a constraint this design must live inside. Sources are the current vendor docs; the ones
that bite are in [10 Roadblocks](10-roadblocks.md).

| Fact | Consequence |
|---|---|
| New Lakebase work goes through `POST /api/2.0/postgres/projects`; the Database Instance API still works and creates a project | the tool must speak the Postgres API and may keep a legacy read for old instances |
| A project's root branch is always `production` | no need to invent a branch name on create |
| `max − min ≤ 16 CU`; autoscaling ≤ 64 CU; scale-to-zero only when max ≤ 32 | the create/update tool validates the range locally and says the rule in the error |
| `POST /postgres/credentials {endpoint}` returns a token valid ≤ 60 min | the SQL tool mints per call; never store it (the app already does this in `llm/store/lakebase.py`) |
| An app resource of type `postgres` needs `branch`, `database`, `permission: CAN_CONNECT_AND_CREATE` | `dbx_create_app` must accept resources, not only a name |
| `app.name` is `[a-z0-9-]{2,30}`, unique | validate before the call, so the refusal is ours and instant |
| `POST /api/2.0/apps/{name}/deployments` needs a `source_code_path` in the workspace, or a git source | the tool must require a path it also wrote, and report the platform's refusal verbatim when the workspace is git-only |
| Apps scale to zero when idle; state on local disk is lost | the scaffold's verify step must tolerate a cold start (retry the GET, do not call a slow app broken) |
| App logs are at `/logz`, and are lost when compute shuts down | "logs" is a link and a snapshot, never a promise |
| Genie Code now ships a full-page command centre with parallel threads, skills and MCP customisation | the parity bar has moved; this spec closes the *object* gap, and 011 covers the mission/thread model |

## The four rules, restated as requirements

These become `[SCF-*]`, `[LB-*]`, `[AP-*]` and `[UI-*]` in [03](03-requirements.md).

1. **`[SCF]`** A scaffold step is done when a call proved it, and the plan shows which steps have proof.
2. **`[LB]`** Every Lakebase tool speaks the Postgres API (projects, branches, endpoints, credentials)
   and uses the Postgres client the app already ships.
3. **`[AP]`** Creating an app includes the resource that lets it reach its database, and the refusal is
   the platform's own sentence.
4. **`[UI]`** A project and an app are documents: a route, a tab, a rail node, a detail page, a link out.
