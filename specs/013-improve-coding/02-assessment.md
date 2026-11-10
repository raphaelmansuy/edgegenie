[Index](README.md) · prev: [01 Five whys](01-five-whys.md) · next: [03 Requirements](03-requirements.md)

# 02 · Measured assessment

Nine findings. Each has a probe you can re-run, and the probe output is quoted. Nothing here is
remembered: where a claim could be executed, it was.

Probes ran in this checkout on 2026-11-10 with the app's own virtualenv
(`apps/coding-agent/.venv`, Python 3.12). The commands are in [§Probes](#probes).

---

## F1 · The tool that creates data in Lakebase cannot import its Postgres client

**Proven.**

```text
psycopg2 installed? NO
psycopg (v3) installed? yes 3.3.8
PROVEN F1 -> ModuleNotFoundError: No module named 'psycopg2'
```

`dbx_lakebase_sql` is the only tool that can run DDL or DML on a Lakebase database — create a schema,
create a table, insert a seed row, or verify a count. Its third line imports `psycopg2`:

```1026:1034:apps/coding-agent/tools/databricks_notebook_mcp.py
    _need_writes()
    _check_prefix("instance", instance, INSTANCE_PREFIX)
    import uuid
    import psycopg2
    d = _get(f"/api/2.0/database/instances/{instance}")
    cred = _post("/api/2.0/database/credentials", {"request_id": str(uuid.uuid4()), "instance_names": [instance]})
    me = _get("/api/2.0/preview/scim/v2/Me").get("userName")
    conn = psycopg2.connect(host=d["read_write_dns"], port=5432, dbname=database, user=me,
                            password=cred["token"], sslmode="require", connect_timeout=20)
```

`psycopg2` appears in **no** dependency file:

| File | Contains |
|---|---|
| `requirements.txt` | `psycopg[binary]>=3.2`, `psycopg-pool>=3.2` — the **v3** driver |
| `pyproject.toml` | `psycopg[binary]>=3.2` — the same |

So the app ships a Postgres client the tool server does not use, and the tool server imports a client
the app does not ship. The card's first data step fails with a Python traceback the model then
paraphrases.

**Why no test caught it.** `test_packaging.py` exists precisely to catch "imported but not declared".

```26:50:apps/coding-agent/tests/test_packaging.py
def test_every_runtime_import_is_declared():
    """Walk the imports and fail if something is used but not declared."""
    import sys
    stdlib = set(sys.stdlib_module_names)
    declared = (APP / "requirements.txt").read_text().lower()
    alias = {"pydantic_settings": "pydantic-settings", "psycopg_pool": "psycopg-pool"}
    missing: set[str] = set()
    for py in (APP / "api").rglob("*.py"):
```

Measured with the same algorithm, over two roots:

```text
what the CURRENT test checks (api/ only): nothing missing
what it MISSES (tools/ too)            : {'psycopg2'}
```

The tool server is a **separate process** the app spawns (`SubprocessToolRegistry.start`, with
`python=sys.executable`). Its dependencies are the app's runtime dependencies. The guard looks at the
app and not at the child — a real, general, one-line hole.

---

## F2 · The Lakebase tools speak the API of an object model that was migrated away

**Proven from the vendor reference and from the code.**

The three Lakebase tools call `/api/2.0/database/instances` and read `read_write_dns` and `capacity`.
Those are the fields of **Database Instance** (Lakebase Provisioned). Since **2026-03-12**, a create on
that endpoint produces an **Autoscaling project**, and every Lakebase Provisioned instance was upgraded
to Autoscaling in July 2026. The current management API is `/api/2.0/postgres/`:

| Need | Current endpoint | What the tool calls |
|---|---|---|
| Create a database | `POST /api/2.0/postgres/projects` | `POST /api/2.0/database/instances` |
| Read one | `GET /api/2.0/postgres/projects/{p}` | `GET /api/2.0/database/instances/{name}` |
| A compute's host | `endpoint.status.hosts.host` | `instance.read_write_dns` |
| A credential | `POST /api/2.0/postgres/credentials {endpoint}` | `POST /api/2.0/database/credentials {instance_names}` |
| Size | `autoscaling_limit_min_cu` / `_max_cu` | `capacity: "CU_1"` |
| Branches, databases, roles | **five objects** | **no tool at all** |

The consequence is not a clean error. The create call succeeds — the compatibility layer makes it
create a project — and every field read afterwards describes a shape the object no longer has, so the
agent reports a host, a "capacity" and a database name that do not form a working connection string.
There is no tool for a branch, so it cannot put the user's data on a branch; none for a role, so it
cannot grant the app's service principal `CONNECT`; none for a database, so it cannot create one.

**The repository already knows better.** `scripts/provision-lakebase.sh` uses the new surface
throughout:

```bash
databricks postgres get-project "$PROJECT" -o json
databricks postgres create-role "projects/${P}/branches/${B}" --role-id "${APP_NAME}-sp" ...
databricks postgres generate-database-credential "$DEPLOY_LAKEBASE_ENDPOINT" -o json
```

So two dialects live in one repository: the shell scripts speak Autoscaling, the agent's tools speak
Provisioned. The agent is the one that talks to users.

---

## F3 · The app-name fence reads the instance prefix

**Proven.**

```text
INSTANCE_PREFIX  = 'agent-abc12345-'
has APP prefix var? False
create_app checks : ['_check_prefix("app", name, INSTANCE_PREFIX)']
```

```1050:1057:apps/coding-agent/tools/databricks_notebook_mcp.py
def dbx_create_app(name: str, source_code_path: str = "") -> str:
    """Try to create (and deploy) a Databricks App. Returns the platform's answer
    verbatim, including refusals (some workspaces require a Git repository for
    Apps). Report that text to the user exactly; never claim a deploy that failed."""
    _need_writes()
    _check_prefix("app", name, INSTANCE_PREFIX)
```

The two prefixes happen to be the same string today, so the check *works by coincidence*:

```text
scope.app_prefix     = agent-abcdef12-
scope.instance_prefix= agent-abcdef12-
identical: True
```

That coincidence is the whole safety story for app creation, and it is invisible to a reader. The
moment either prefix changes — a different separator, a per-type salt — apps are fenced by the wrong
rule and nothing fails loudly.

**And the fence's own app policy is unreachable.** `api/domain/scope.py` defines `app_prefix` and
`check_app`, and `check_app` is called only from `tests/test_domain.py`:

```text
$ rg 'check_app|check_job|check_instance' api/
(no call sites)
```

The tool server is a **separate process**; it cannot import `api.domain.scope`. Its fence is
environment variables, and `registry.start` passes four of the five:

```58:62:apps/coding-agent/api/adapters/mcp/registry.py
            "NBMCP_WRITE_SCHEMAS": schema or "",
            "NBMCP_WRITE_PATHS": folder.rstrip("/") + "/",
            "NBMCP_WRITE_JOB_PREFIX": f"agent_{session_id[:8]}_",
            "NBMCP_WRITE_INSTANCE_PREFIX": f"agent-{session_id[:8]}-",
```

No `NBMCP_WRITE_APP_PREFIX`. So the module that documents itself as *"the write fence: what a session
may touch. Pure and total"* is, for apps, documentation.

---

## F4 · Four of the five policy functions have no production caller

**Proven.**

```text
$ rg 'check_sql\(|check_job\(|check_app\(|check_instance\(' api/ --glob '!tests/*'
api/routers/api.py:754:    decision = scope_mod.check_path(scope, path)
api/routers/api.py:782:    decision = scope_mod.check_path(scope, path)
api/routers/api.py:1196:   decision = scope_mod.check_path(scope, target)
```

| Function | Documented meaning | Production callers |
|---|---|---|
| `check_path` | may this be written? | **3** — the save routes |
| `check_sql` | may this statement run? | 0 |
| `check_job` | may this job be created? | 0 |
| `check_app` | may this app be created? | 0 |
| `check_instance` | may this database be created? | 0 |

`check_sql` is arguably covered elsewhere: `_check_sql_scope` in the tool server does the same work
inside the process that actually runs the SQL. `check_job`, `check_app` and `check_instance` are not
covered by anything, so the module's opening sentence — *"the boundary is that the tool server only
receives requests that passed here"* — is false for three of five.

This is a finding about **claims**, not only code. A spec that says the fence covers apps, and a
`check_app` with tests and no users, is worse than no fence: a reviewer reads the test, sees
`Verdict.ALLOW` and `Verdict.ASK`, and stops asking.

---

## F5 · Neither object can be opened in the app

**Proven.**

```text
$ rg 'export type DocKind' web/src/domain/docs.ts
4:export type DocKind = "notebook" | "file" | "table";

$ rg 'DocRouteKind' web/src/domain/route.ts
17:export type DocRouteKind = "notebook" | "file" | "table";
```

The route grammar, the tab strip, the rail, the recent list, the palette and the `@` picker all key on
this union. Three kinds, so:

| Question a user asks after the card | Answer in the product |
|---|---|
| Where is the project? | a transcript row saying `created a database` |
| Is it running? | ask the agent again (a new model call, a new guess) |
| Which branch does the app use? | nothing on screen |
| What is its URL? | maybe in the prose, not clickable |
| Did the app actually answer? | not shown |

The only durable trace of the turn is the tool row, which is labelled by `toolLabel` — `created a
database`, `created an app` — a fixed phrase, not the object's state. The user's next question cannot
be answered by looking.

---

## F6 · `dbx_create_app` sends one field of the four an app needs

**Proven from the code and the current API reference.**

```1058:1068:apps/coding-agent/tools/databricks_notebook_mcp.py
    with _client() as c:
        r = c.post("/api/2.0/apps", json={"name": name})
        if not r.is_success:
            return _trim({"created": False, "http_status": r.status_code, "platform_error": r.text[:800]})
        app = r.json()
        if source_code_path:
            dep = c.post(f"/api/2.0/apps/{name}/deployments", json={"source_code_path": source_code_path})
```

The body is `{"name": …}`. An app that can reach a Lakebase database needs a **resource**:

```json
{"name": "tickets_app",
 "resources": [{"name": "postgres",
                "postgres": {"branch": "projects/pg-tickets/branches/production",
                             "database": "projects/pg-tickets/branches/production/databases/db-1",
                             "permission": "CAN_CONNECT_AND_CREATE"}}],
 "user_api_scopes": ["postgres"]}
```

Without `resources`, the platform sets **no** `PGHOST`/`PGDATABASE`/`PGUSER`/`PGSSLMODE` and the app
starts with no database to talk to. Without `user_api_scopes`, the app's own identity cannot mint a
credential. So the skill's own recipe (`dbx_write_file` for `app.yaml`, then `dbx_create_app`) produces
an app that cannot do the one thing the card asked for.

**And the skill is what the agent reads.** `tools/skills/databricks-apps.md` is 33 lines and never
mentions `resources`, `user_api_scopes`, `LAKEBASE_ENDPOINT`, or `git_repository`. It says:

> `dbx_create_app` returns the platform's answer verbatim, including refusals. If it refuses, quote the
> exact `platform_error`.

That is a good instinct applied to a call that is already missing three quarters of its input.

---

## F7 · The Lakebase skill teaches a connection the platform does not use

**Proven against the current app-resource contract.**

```20:27:apps/coding-agent/tools/skills/lakebase-postgres.md
```python
import uuid
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()
token = w.database.generate_database_credential(
    request_id=str(uuid.uuid4()), instance_names=["<instance>"]).token
conn = psycopg2.connect(host=host, port=5432, dbname="databricks_postgres",
                        user=w.current_user.me().user_name, password=token, sslmode="require")
```
```

Four problems in eight lines:

| Line | Problem |
|---|---|
| `generate_database_credential(instance_names=[...])` | the Provisioned call; the current one takes an **endpoint** path |
| `psycopg2` | not installed, and not what the app ships |
| `host=host` | a Databricks App does not receive a host this way: it gets `PGHOST` injected by the platform, plus `LAKEBASE_ENDPOINT` from `valueFrom: postgres` |
| `user=…me().user_name` | a deployed app connects as its **service principal** (`PGUSER`), not as the human |

A developer who follows the skill writes an app that starts, cannot connect, and logs a timeout. The
skill is the product's teaching surface for this workflow, so this is a product defect and not a doc
typo.

---

## F8 · Two tool servers have diverged

**Proven.**

```text
$ diff -q mcp/databricks_notebook_mcp.py apps/coding-agent/tools/databricks_notebook_mcp.py
Files ... differ
$ wc -l
  987 mcp/databricks_notebook_mcp.py
 1104 apps/coding-agent/tools/databricks_notebook_mcp.py
```

The app's copy carries three things the repository copy does not:

| In the app copy only | Why it matters |
|---|---|
| `_token()` reading `NBMCP_TOKEN_FILE` | the user's token is rewritten per turn; without it the server uses a stale token |
| the `_refuse` hook mapping 401/403 to `PermissionError("Do not retry")` | the model's behaviour on a denied call |
| the run bridge (`NBMCP_RUN_URL`) | `dbx_run_notebook` falls back to the app's own serverless run |

`api/adapters/mcp/registry.py::_find_server` looks in **this order**: `tools/databricks_notebook_mcp.py`
first, then `mcp/databricks_notebook_mcp.py`. So a deployment ships the app copy, and the repository copy
is dead code that the README's tool table still describes. A fix applied to `mcp/` reaches nobody; a fix
applied to `tools/` makes the two diverge further.

---

## F9 · The four skills are duplicated byte for byte

**Proven.**

```text
databricks-apps.md:     058c7fb3… == 058c7fb3…
etl-pipelines.md:       01bdcbab… == 01bdcbab…
lakebase-postgres.md:   60d3acde… == 60d3acde…
notebook-authoring.md:  c134e65f… == c134e65f…
```

Identical today. The deployed app reads `tools/skills/` (`NBMCP_SKILLS_DIR` is set from
`self._server.parent / "skills"`). So `mcp/skills/` is a copy that will drift on the first edit, and the
one edit that matters — F7 — must be made twice or made in the copy nobody ships.

---

## What is healthy, measured

The fix must not disturb these. Each is exercised by a test that passes today.

| Behaviour | Proof |
|---|---|
| Lakebase as this app's own store, with a minted token per connection | `tests/test_llm_lakebase.py` (token refresh, pool lifetime) |
| The Provisioned→Autoscaling **credential** call, correctly used by the app itself | `lakebase.TokenSource.get` → `client.postgres.generate_database_credential(endpoint=…)` — already the *new* API |
| Path and SQL fences enforced inside the tool server process | `NBMCP_WRITE_PATHS`/`_SCHEMAS` at `tools/…:191-248`, and `tests/test_pyrun.py` |
| A 403 becomes "Do not retry" for the model | `tests/test_genie_features.py::test_a_403_becomes_a_final_instruction_not_a_retry_invitation` |
| The app's own deployment: two workspaces, two transports, verified live | `databricks.yml`, `scripts/env.sh`, `make verify` |
| 548 Python tests, 655 front-end tests | `make check` |

The sharpest line in that table is the second: **the app already calls the correct credential API for
itself.** `api/adapters/llm/store/lakebase.py` uses
`client.postgres.generate_database_credential(endpoint=…)`. The tool server, written later, uses the
old one. The repository teaches both, and the agent learned the wrong one.

---

## Probes

Re-run any of these. `apps/coding-agent/.venv` is the app's own environment.

```bash
cd apps/coding-agent

# F1 — the missing client, and the guard's blind spot
NBMCP_ALLOW_WRITES=1 DATABRICKS_HOST=h DATABRICKS_TOKEN=t .venv/bin/python -c '
import importlib.util as u
s = u.spec_from_file_location("n", "tools/databricks_notebook_mcp.py"); m = u.module_from_spec(s)
s.loader.exec_module(m)
try: m.dbx_lakebase_sql("agent-x-db", "select 1")
except ModuleNotFoundError as e: print("F1:", e)'

# F1/F8/F9 — declarations, divergence, duplication
.venv/bin/python -m pytest tests/test_packaging.py -q
diff <(git show HEAD:mcp/databricks_notebook_mcp.py) tools/databricks_notebook_mcp.py | head
md5 ../../mcp/skills/*.md tools/skills/*.md

# F3 — the prefix the app name is checked against
NBMCP_ALLOW_WRITES=1 NBMCP_WRITE_INSTANCE_PREFIX=agent-abc12345- \
  DATABRICKS_HOST=h DATABRICKS_TOKEN=t .venv/bin/python -c '
import importlib.util as u, inspect
s = u.spec_from_file_location("n", "tools/databricks_notebook_mcp.py"); m = u.module_from_spec(s)
s.loader.exec_module(m)
print([l.strip() for l in inspect.getsource(m.dbx_create_app).splitlines() if "_check_prefix" in l])'

# F4 — the policy functions with no caller
rg 'check_(sql|job|app|instance)\(' api/ | grep -v tests/ || echo "F4: no production callers"

# F5 — the document kinds
rg 'export type (Doc|DocRoute)Kind' ../../web/src/domain/*.ts
```

## What the assessment changes about the plan

| Finding | The fix | Phase |
|---|---|---|
| F1 | one Postgres client (the installed one), and the packaging guard walks `tools/` too | 1 |
| F2 | Lakebase tools on `/api/2.0/postgres`: project, branch, database, role, credential, SQL | 2 |
| F3, F4 | one policy module the tool server reads from the environment, and every prefix wired | 1 |
| F5 | `lakebase` and `app` as document kinds: route, tab, rail, detail, link | 3 |
| F6, F7 | the tools accept resources; the two skills teach the real contract | 2 |
| F8, F9 | one copy of each artefact, and a test that fails when they differ | 1 |

Phase 1 is "make the claims true". Phase 2 is "speak the current API". Phase 3 is "let the user see
it". That order is deliberate: a screen over a broken call shows a broken fact more prominently.
