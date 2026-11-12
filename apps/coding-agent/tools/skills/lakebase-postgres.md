---
name: lakebase-postgres
description: Create and use a Lakebase Postgres database — projects, branches, databases, credentials, SQL — and wire a Databricks App to it. Use before creating a database or writing an app that reads one.
---

# Lakebase (managed Postgres): project, branch, data, app

Lakebase is organised as **projects → branches → endpoints (computes) → databases → roles**. A new
project arrives with a `production` branch and a `primary` read-write compute; you create nothing else
before you can run SQL.

## The flow, in order — each step returns the next call's argument

1. `dbx_lakebase_create(name)` → `{project, branch, endpoint, ready}`.
   The name must start with this session's prefix, be lowercase with hyphens, and becomes the
   project id. Pass `min_cu`/`max_cu` for an autoscaling range: `max − min ≤ 16`, `max ≤ 64`.
2. `dbx_lakebase_branch(project, branch="agent-<something>")` → `{branch}`.
   **Use a branch, not `production`,** for anything you build. It is copy-on-write and isolated, so a
   mistake costs nothing the user cares about.
3. `dbx_lakebase_sql(project, branch=branch, sql="CREATE SCHEMA IF NOT EXISTS app; CREATE TABLE ...")`.
   This runs on **that branch's** compute with a credential minted for the call.
4. Verify with a read, and quote the number: `dbx_lakebase_sql(..., sql="SELECT count(*) FROM app.tickets")`.
5. `dbx_lakebase_tables(project, branch=branch, schema="app")` → table names and row counts, for a
   report that a person can check.
6. To connect an app: create the app with the database as a **resource** —
   `dbx_create_app(name, project=..., branch=..., database="databricks_postgres")`.
7. Prove the role exists: `dbx_lakebase_role(project, branch=branch)`. The **platform** creates the
   app's role (named after its service principal) when the resource is attached; do not create one
   yourself.

## Facts that decide correctness

- Default database: `databricks_postgres`. Port 5432, TLS required.
- A credential is minted per call with `POST /api/2.0/postgres/credentials {endpoint}` and lives ≤ 60
  minutes. Never store one, never print one.
- The Postgres user is the **signed-in Databricks identity**.
- Create objects explicitly: `CREATE SCHEMA IF NOT EXISTS app;` then
  `CREATE TABLE IF NOT EXISTS app.tasks (...)`. `SERIAL` and `TIMESTAMPTZ DEFAULT now()` work.
- A suspended compute wakes on the first connection and takes a few seconds. That is not an error.
- `max − min ≤ 16 CU`; autoscaling tops out at 64 CU; scale-to-zero needs a maximum of 32 CU or less.
  `dbx_lakebase_compute` checks these before it calls the platform.
- Writes to `production` are refused unless you name it explicitly. Do not name it.
- **A second database is rarely the answer.** Every branch arrives with `databricks_postgres`, and a
  schema inside it is cheaper and more portable than a new database. When one IS wanted,
  `dbx_lakebase_database(project, branch, database="<name>")` creates it and
  `dbx_lakebase_database(project, branch)` with no name lists the branch's databases. These three
  (`dbx_lakebase_database`, `dbx_lakebase_role`, `dbx_lakebase_tables`) are not in the always-advertised
  `core` tool set, precisely because a scaffold needs each of them once: they are reachable, and this
  paragraph is how you know they exist.

## Connecting from a Databricks App (the only form that works when deployed)

A deployed app does **not** mint a token with the SDK and **does not** connect as the human. The
platform injects the connection for the first `postgres` resource:

```python
# app.yaml:  env: [{name: LAKEBASE_ENDPOINT, valueFrom: postgres}]
# The platform also injects PGHOST, PGPORT, PGDATABASE, PGUSER, PGSSLMODE.
import os
import psycopg                     # psycopg 3, the client this app ships

with psycopg.connect(
    host=os.environ["PGHOST"],
    dbname=os.environ["PGDATABASE"],
    user=os.environ["PGUSER"],
    sslmode=os.environ.get("PGSSLMODE", "require"),
) as conn, conn.cursor() as cur:
    cur.execute("SELECT count(*) FROM app.tickets")
    print(cur.fetchone())
```

Inside an app, use parameterised queries only: `cur.execute("INSERT ... VALUES (%s)", (value,))`.
Never build SQL with f-strings from request data.

## From a laptop, for a quick check

```python
import uuid
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()
token = w.database.generate_database_credential(
    request_id=str(uuid.uuid4()),
    endpoint="projects/<project>/branches/<branch>/endpoints/primary").token
```

Note the argument: an **endpoint path**, not a list of instance names. The Provisioned spelling no longer names a project.

## Reporting

Quote the numbers you read: the project path, the branch, the table names, the row count, and the
result of the verification query. "Created a database" is not a report; a row count is.
