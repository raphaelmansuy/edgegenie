[Index](README.md) · prev: [07 Architecture](07-architecture.md) · next: [09 Edge cases](09-edge-cases.md)

# 08 · Implementation plan

Four phases. Each phase ends with a gate that can fail, and each phase is independently shippable: phase
1 makes the product's existing claims true, phase 2 speaks the current API, phase 3 gives the user a
screen, phase 4 hardens.

The ordering is not arbitrary. **A screen over a broken call shows a broken fact more prominently**, so
the fixes come before the surface.

---

## Phase 1 · Make the claims true

Nothing user-visible changes. Four defects become non-defects, and two guards become real.

### 1.1 · One Postgres client in the tool server

**Files:** `tools/databricks_notebook_mcp.py`

Replace the `psycopg2` path in `dbx_lakebase_sql` with `psycopg` (v3), which `requirements.txt` already
ships. Introduce one helper so there is one place that opens a connection:

```python
def _pg_connect(endpoint_host: str, database: str, user: str) -> "psycopg.Connection":
    """One connection, one caller, always closed by the caller's `finally`."""
    import psycopg
    token = _lakebase_token(...)                  # per call, never cached
    return psycopg.connect(host=..., port=5432, dbname=database, user=user,
                           password=token, sslmode="require", connect_timeout=20)
```

**Gate:** `NBMCP_ALLOW_WRITES=1 .venv/bin/python -c 'import …; m.dbx_lakebase_sql(...)'` no longer raises
`ModuleNotFoundError`; the new test asserts the module resolves and that two calls mint two credentials.

**Why first:** it is the only change that turns a traceback into a call. Everything in phase 2 depends on
a working connection.

### 1.2 · The dependency guard covers the process the app starts

**Files:** `tests/test_packaging.py`

```python
for py in [p for root in ("api", "tools")
             for p in (APP / root).rglob("*.py")
             if ".venv" not in p.parts]:
```

**Gate:** the test fails on the **current** tree before 1.1 lands (proven: it reports `{'psycopg2'}`), and
passes after. That before/after is the test of the test — it must fail on the bug it exists to catch.

**Risk this closes:** a future import of `boto3`, `pandas` or `requests` in the tool server ships a crash
that no local test can see, because the tool server is started by the app at request time.

### 1.3 · One copy of each artefact

**Files:** delete `mcp/databricks_notebook_mcp.py` and `mcp/skills/*.md`; `api/adapters/mcp/registry.py`
keeps a single resolution order.

**Decision, and why this direction.** The app copy ships and has three behaviours the repository copy
lacks (`_token`, `_refuse`, the run bridge). Keeping the repository copy and deleting the app copy would
delete those three, so the app copy wins. `mcp/` keeps a `README.md` that says where the server moved and
why — a deletion with a signpost, because somebody has a bookmark.

**Gate:** `_find_server()` returns the same path in local dev and in a deployment; a test asserts exactly
one `databricks_notebook_mcp.py` exists in the repository, and one copy of each of the four skills.

### 1.4 · The app prefix is wired

**Files:** `api/adapters/mcp/registry.py` (+1 line), `tools/databricks_notebook_mcp.py`.

```python
APP_PREFIX = os.environ.get("NBMCP_WRITE_APP_PREFIX", "")
...
_check_prefix("app", name, APP_PREFIX)
```

**Files:** `tests/test_tools_fence.py` — **new**, and the test is the point:

```python
def test_an_app_name_is_checked_against_the_APP_prefix_not_the_instance_prefix(monkeypatch):
    # five different prefixes, so a mix-up cannot pass by coincidence
    monkeypatch.setenv("NBMCP_WRITE_INSTANCE_PREFIX", "agent-inst-")
    monkeypatch.setenv("NBMCP_WRITE_APP_PREFIX", "app-prefix-")
    mod = load_tool_server()
    with pytest.raises(PermissionError, match="app-prefix-"):
        mod.dbx_create_app("agent-inst-app")      # matches the INSTANCE prefix
    mod._check_prefix("app", "app-prefix-ok", mod.APP_PREFIX)   # and the right one passes
```

**Gate:** the test fails against today's code (`agent-inst-app` is accepted) and passes after. This is the
only way to prove a fix for a defect that worked by coincidence.

### Phase 1 acceptance

| Check | Command | Pass |
|---|---|---|
| The missing client is gone | the F1 probe in [02](02-assessment.md#probes) | no `ModuleNotFoundError` |
| The guard sees the tool server | `pytest tests/test_packaging.py -q` | passes; before 1.1 it fails naming `psycopg2` |
| One copy of the server | `pytest tests/test_packaging.py -q` | one path |
| The prefix is separate | `pytest tests/test_tools_fence.py -q` | both cases |
| Nothing else broke | `make check` | 548 + tests still pass |

---

## Phase 2 · Speak the current API

The agent's Lakebase and Apps tools become correct against the platform as it is in November 2026.

### 2.1 · The Lakebase adapter

**File:** `api/adapters/databricks/lakebase.py` — **new** (~180 lines)

One class, `LakebaseAdmin`, over `DbxHttp`. Eleven methods, each a single call, no aggregation:

| Method | Path |
|---|---|
| `projects` | `GET /api/2.0/postgres/projects` |
| `project` | `GET /api/2.0/postgres/projects/{p}` |
| `branches` | `GET /api/2.0/postgres/projects/{p}/branches` |
| `databases` | `GET …/branches/{b}/databases` |
| `endpoints` | `GET …/branches/{b}/endpoints` |
| `credential` | `POST /api/2.0/postgres/credentials` |

**File:** `api/domain/lakebase.py` — **new** (~90 lines), pure:

- `project_ref(name)` — `pg_tickets` and `projects/pg_tickets` → `projects/pg_tickets` (`[LB-5]`)
- `branch_ref(project, branch)` — `production` → the full path
- `capacity_problem(min_cu, max_cu, scale_to_zero)` — `None` or a sentence naming the bound (`[LB-4]`)
- `credential_request(endpoint)` — the body, in one place

**Gate:** `tests/test_lakebase_adapter.py` asserts every URL and no field named `read_write_dns`,
`capacity` or `instance_names` appears anywhere in the adapter. That last assertion is the one that keeps
the Provisioned dialect from creeping back.

### 2.2 · The tools, on the new surface

**File:** `tools/databricks_notebook_mcp.py`

| Tool | Change |
|---|---|
| `dbx_lakebase_create` | `POST /postgres/projects`; the body is `{"project_id": …, "spec": {"display_name": …, "default_endpoint_settings": {...}}}`; poll for `READY`; return `project` and `branch` |
| `dbx_lakebase_status` | `GET /postgres/projects/{p}`; return the project and its `production` branch |
| `dbx_lakebase_list` | **new**; `GET /postgres/projects` |
| `dbx_lakebase_branch` | **new**; `POST …/branches`; returns the branch and its endpoints |
| `dbx_lakebase_database` | **new**; `POST …/databases`; returns the database path |
| `dbx_lakebase_role` | **new**; `GET …/roles`, and a create for a *named* identity — documented as "the platform creates the app's role when the resource is attached" |
| `dbx_lakebase_compute` | **new**; `GET`/`PATCH …/endpoints/{e}` with the capacity guard |
| `dbx_lakebase_sql` | branch parameter; `psycopg`; credential per call |
| `dbx_lakebase_tables` | **new**; a count per table, `LIMIT 50`, `truncated` |

Every mutating tool's answer ends with a `next` line naming the following call and its argument
([06 §7.1](06-lenses.md#7-ai-engineer)).

**Gate:** `tests/test_lakebase_tools.py` — **new** — one test per tool against a fake transport. Each
asserts the **method, path and the fields of the body**, and each asserts the `next` hint names a tool
that exists (a test that reads `_CORE` and checks the closure, so a renamed tool cannot leave a stale
hint).

### 2.3 · The Apps tools

**File:** `api/adapters/databricks/apps.py` — **new** (~120 lines)

`apps()`, `app(name)`, `health(url)` — and `health` is the interesting one:

| Condition | State returned |
|---|---|
| 2xx within 3 s | `running` with the code and ms |
| 2xx within 15 s | `starting` (a cold start: the app scaled to zero) |
| timeout > 15 s | `unresponsive` |
| 5xx | `failing` with the code |
| connection error | `unreachable` |

**File:** `tools/databricks_notebook_mcp.py`

`dbx_create_app` gains: local name validation, `resources`, `user_api_scopes`, a bounded wait for
`RUNNING`, and a `verified` boolean. `dbx_app_health` is new.

**Gate:** `tests/test_apps_adapter.py` — **new** — five health states, and the create body asserted field
by field. The scenario that matters: a body **without** a `postgres` resource and with
`resources` requested is a local `ValueError` naming the missing `branch`, not a 400 from the platform.

### 2.4 · The two skills, rewritten

**Files:** `tools/skills/lakebase-postgres.md`, `tools/skills/databricks-apps.md`

Both are rewritten around the contract that actually exists. The Lakebase skill's connection snippet
becomes the **app-resource** form:

```python
# In a Databricks App, the platform injects PGHOST/PGPORT/PGDATABASE/PGUSER/PGSSLMODE
# for the first postgres resource, and LAKEBASE_ENDPOINT via `valueFrom: postgres`.
import os
import psycopg
with psycopg.connect(host=os.environ["PGHOST"], dbname=os.environ["PGDATABASE"],
                     user=os.environ["PGUSER"], sslmode=os.environ.get("PGSSLMODE", "require")) as conn:
    ...
```

**Gate:** a test reads both skills and asserts that the Lakebase skill contains `PGHOST` and
`LAKEBASE_ENDPOINT` and does **not** contain `psycopg2` or `instance_names`; and that the Apps skill
contains `resources`, `CAN_CONNECT_AND_CREATE` and `git_repository`. Docs tested like code, because these
two files *are* the agent's code path.

### Phase 2 acceptance

| Check | Command | Pass |
|---|---|---|
| Every URL is the new API | `pytest tests/test_lakebase_adapter.py -q` | 0 occurrences of the old dialect |
| Every tool builds the right call | `pytest tests/test_lakebase_tools.py tests/test_apps_adapter.py -q` | one test per tool |
| The next-hint closure holds | same | every `next` names a real tool |
| The skills teach the real contract | `pytest tests/test_skills_contract.py -q` | forbidden strings absent |
| Nothing else broke | `make check` | |

---

## Phase 3 · Give the user a screen

Two document kinds, one rail tab, two pages, five ways in.

### 3.1 · The union, and the route grammar

**Files:** `web/src/domain/docs.ts`, `route.ts`, `layout.ts`, `keys.ts`, `api/client.ts`

```ts
export type DocKind = "notebook" | "file" | "table" | "lakebase" | "app";
```

`route.ts` gains two `format` cases and two `parse` cases. The parser's existing contract holds: an
unrecognised hash returns `EMPTY_ROUTE`, never throws.

**Gate:** `domain/route.test.ts` — extend, do not replace. The three existing kinds' cases must pass with
no edit; the two new kinds get `parse(format(r)) === r`, a percent-encoded project id, a branch segment,
and a malformed case (`#/app/` → empty route).

**Why the order matters here:** the union first, because TypeScript will then point at every place that
must handle the new members — the tab icon, the `ACTIONS_FOR` map, the palette group, the `@` hint. That
compiler output *is* the task list for the rest of phase 3.

### 3.2 · The domain modules

**Files:** `web/src/domain/lakebase.ts`, `app.ts`, `scaffold.ts` — **new**

`scaffold.ts` is the one with a performance requirement. One pass:

```ts
export function stepsFrom(entries: PlanEntry[], calls: ToolCall[]): Step[] {
  const byTool = groupBy(calls, c => c.name);          // O(c)
  return STEPS.map(s => ({ ...s, ...prove(s, byTool) }));  // O(s), constant lookups
}
```

**Gate:** `domain/scaffold.test.ts` — the seven-step table from a full call list; a call list with a gap
leaves later steps `pending`; 2 000 calls complete in < 5 ms (asserted, because this runs per render
tick).

### 3.3 · The two pages and the tree

**Files:** `components/LakebasePage.tsx`, `AppPage.tsx`, `DataTree.tsx` — **new**;
`components/DocTabs.tsx`, `Icons.tsx` (a `Branch` glyph), `App.tsx`, `styles.css` — edited

Each page is four (or three) `Block`s, and a `Block` owns its own loading, error and empty states:

```tsx
<Block title="Branches" load={() => api.branches(ref)}>
  {(rows) => rows.map(b => <BranchRow key={b.ref} branch={b} />)}
</Block>
```

That is the whole isolation story from [06 §5](06-lenses.md#5-system-design-expert) in one component: a
failed `Block` renders `PaneError` in place and cannot affect its siblings.

**Gate:** `components/LakebasePage.test.tsx`, `AppPage.test.tsx` — **new** — for each: the full payload,
one field missing (`—`, not `0`), one block failing (others still render), the health states, and the
`/logz` URL. `DataTree` gets a test for lazy expansion.

### 3.4 · The five ways in

| Way in | Where | Test |
|---|---|---|
| the rail's `Data` tab | `App.tsx` | `⌘4` selects it; the three old shortcuts unchanged |
| a tool row's **Open** | `domain/docs.ts::touched` | two new cases; `null` for a call that names nothing |
| the palette | `App.tsx::paletteActions` | a project and an app are found by name |
| the `@` picker | `Composer.tsx` via `client.ts` | a project can be attached as context |
| a URL | `route.ts` | `parse(format(r)) === r` |

Attachment is the fifth and least obvious: a project attached as context means the agent receives its
ref in the fenced block, so "add an index to the tickets table" has an unambiguous subject.

### Phase 3 acceptance

| Check | Command | Pass |
|---|---|---|
| Types are exhaustive | `npx tsc -b --noEmit` | no error; the union forces every case |
| Routes round-trip | `vitest run domain/route.test.ts` | five kinds |
| The step table is right and fast | `vitest run domain/scaffold.test.ts` | 2 000 calls < 5 ms |
| Pages are honest about missing fields | `vitest run components/LakebasePage.test.tsx components/AppPage.test.tsx` | |
| a11y and layout | `make audits` | no new violations, no overflow at 900 / 1180 / 1480 |

---

## Phase 4 · Harden, then prove it with pictures

### 4.1 · The E2E scenes

**File:** `web/scripts/lakebase-e2e.mjs` — **new**

Eight scenes, each asserting its own pass criteria before taking a picture ([11](11-e2e-plan.md)). The
scenes run against a **fake** app server for the tool side and a **fixture** API for the two pages, so
they are deterministic and need no workspace.

### 4.2 · The screenshots

**Destination:** `specs/013-improve-coding/e2e/screenshots/`

Each is inspected, and the README records what the inspection changed. That column is the point: [012]
found five defects by looking at pictures that every assertion had passed.

### 4.3 · Edge cases with tests

**File:** `specs/013-improve-coding/09-edge-cases.md` defines them; each has a test named after its id.

### Phase 4 acceptance

| Check | Command | Pass |
|---|---|---|
| Scenes pass and save | `node scripts/lakebase-e2e.mjs` | 8/8, files present |
| Every screenshot inspected | the README's table | one row per file, with what it changed |
| The whole gate | `make check && make audits` | green |
| Spec integrity | `verify-spec-links` + `verify-spec-ascii` + `verify-spec-mermaid` | 0 problems |

---

## Order, dependencies, and what can go wrong

```text
1.1 psycopg ──► 2.1 adapter ──► 2.2 tools ──► 3.2 scaffold.ts ──► 3.3 pages ──► 4.1 scenes
1.2 guard  ─┘                                                                      │
1.3 one copy ──► 1.4 app prefix ──► 2.3 apps tools ──► 3.1 union ──► 3.4 five doors ─┘
```

| Risk | Detected by | Mitigation |
|---|---|---|
| The Postgres API differs from the reference (a field renamed) | the first adapter test against the real workspace | the adapter asserts fields it reads; a missing one raises with the path |
| `psycopg` v3's `sslmode` handling differs from v2 | the connection test | explicit `sslmode="require"`, asserted |
| Adding a `DocKind` breaks a switch somewhere unexpected | `tsc -b` | the union is exhaustive; the compiler is the test |
| The fourth rail tab breaks the layout arithmetic | `make audits` at three widths | `RAIL_TABS` is data; the grid does not know how many tabs there are |
| A page's four calls make the shell feel slow | the CLS/overflow audits and the scene timings | blocks render skeletons first; the shell does not wait |
| The skills drift from the tools again | `test_skills_contract.py` | forbidden strings; a new tool name must appear in a skill |

## What each phase proves, in one line

| Phase | Proves |
|---|---|
| 1 | the product's existing claims are true, for the first time |
| 2 | the agent speaks the API as it is, not as it was |
| 3 | the user can see, open, link and judge both objects |
| 4 | it looks right, and it fails gracefully |
