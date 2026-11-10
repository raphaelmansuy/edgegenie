---
name: databricks-apps
description: Build and deploy a Databricks App — app.yaml, requirements, the Lakebase resource that lets it connect, deployment, and the health check that proves it works. Use when asked to build, scaffold or deploy an app.
---

# Databricks Apps: the files, the resource, the deploy, the proof

An app is a small web process inside the workspace. It gets an HTTPS URL, the signed-in user's
identity, and whatever resources you attach to it. Attaching the resource is not optional if the app
needs a database: without it the platform injects no `PGHOST` and the app cannot connect.

## The shape that works

```text
<folder>/app.yaml            the runtime contract
<folder>/requirements.txt    pip packages
<folder>/main.py             the app
```

`app.yaml` — `command` is a top-level **list**, never a shell string, and only
`$DATABRICKS_APP_PORT` is substituted:

```yaml
command: ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
env:
  - name: LAKEBASE_ENDPOINT
    valueFrom: postgres        # the resource key, from databricks.yml / the app's resources
```

`requirements.txt`:

```text
fastapi
uvicorn[standard]
psycopg[binary]>=3.2
databricks-sdk
```

`main.py` — read the connection from the environment, never from a file:

```python
import os
import psycopg
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    with psycopg.connect(host=os.environ["PGHOST"], dbname=os.environ["PGDATABASE"],
                         user=os.environ["PGUSER"],
                         sslmode=os.environ.get("PGSSLMODE", "require")) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM app.tickets")
            return {"tickets": cur.fetchone()[0]}
```

## The create call carries the resource

`dbx_create_app` takes the database with it. This is the difference between an app that works and an
app that starts and cannot connect:

```text
dbx_create_app(
    name="agent-<session>-tickets",
    project="<project id>",
    branch="agent-<session>",           # never "production"
    database="databricks_postgres",
    source_code_path="/Users/me/agent_scratch/tickets_app")
```

That sends, in one call:

```json
{"name": "...",
 "resources": [{"name": "postgres",
                "postgres": {"branch": "projects/p/branches/b",
                             "database": "projects/p/branches/b/databases/databricks_postgres",
                             "permission": "CAN_CONNECT_AND_CREATE"}}],
 "user_api_scopes": ["postgres"]}
```

When the resource is attached the **platform creates the Postgres role** for the app's service
principal and grants it `CONNECT` and `CREATE`. Do not create a role yourself; read it back with
`dbx_lakebase_role` to prove it exists.

## Rules that decide whether it works

- **Listen on `0.0.0.0`** at `DATABRICKS_APP_PORT`. Bound to `127.0.0.1` the app is unreachable and the
  deployment still reports `SUCCEEDED`.
- **Never put a token or password in any file.** Read it from the environment, or mint it.
- **State on local disk is lost** when the app stops. Keep state in Lakebase or a volume.
- **`SUCCEEDED` means the process started**, not that it serves your code. Prove it with
  `dbx_app_health(app=...)`, and report the status code.
- **A first request after the app was idle is slow** (it scaled to zero). `state: "starting"` is
  healthy; `unreachable` is not.
- **Some workspaces require a Git repository** to create an app at all. On those, pass
  `git_repository: {"url": "...", "provider": "gitHub"}` — or, if the platform refuses a
  workspace-path source, the refusal is in `platform_error`: quote it exactly, say the app was NOT
  deployed, and tell the user to deploy from git. **Never retry the same call.**
- Logs are at `https://<app-url>/logz` and are lost when compute stops. Quote the first error line, not
  the whole log.

## Report, in this order

1. The app name and its URL.
2. Whether it is `RUNNING`, and the deployment state you observed.
3. The health check: status code and elapsed time. If you did not run it, say so.
4. The resource: which project, branch and database, and the role you read back.
5. Anything the platform refused, verbatim.
