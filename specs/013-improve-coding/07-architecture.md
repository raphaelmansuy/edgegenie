[Index](README.md) · prev: [06 Lenses](06-lenses.md) · next: [08 Implementation plan](08-implementation-plan.md)

# 07 · Architecture

Where each rule lives, and why there. The test this document is written against: **a reader should be
able to predict which file changes** when a requirement changes. Where that prediction is hard, the
boundary is wrong.

The architecture is the one [001 §02](../001-databricks-coding-agents/02-architecture.md) established —
domain is pure, ports are contracts, adapters do I/O — extended to two object types. Nothing here is a
second stack.

---

## 1 · The layers, and what each one may know

```text
  browser            ┌─────────────────────────────────────────────────────────┐
                     │  domain/           pure, no React, no fetch             │
                     │  lakebase.ts  app.ts  scaffold.ts  (new)                │
                     │  docs.ts  route.ts  toolview.ts  (extended)             │
                     └────────────────────┬────────────────────────────────────┘
                                          │  imports
                     ┌────────────────────▼────────────────────────────────────┐
                     │  components/       React, props, no rules               │
                     │  LakebasePage  AppPage  DataTree  (new)                 │
                     └────────────────────┬────────────────────────────────────┘
                                          │  calls
                     ┌────────────────────▼────────────────────────────────────┐
                     │  api/client.ts     the one place that knows the HTTP API│
                     └────────────────────┬────────────────────────────────────┘
──────────────────────────────────────────┼─────────────────────────────────────
                                          │  HTTP
                     ┌────────────────────▼────────────────────────────────────┐
                     │  routers/          statuses, tokens, error mapping      │
                     │  lakebase.py  infra.py  (new)                           │
                     └────────────────────┬────────────────────────────────────┘
                                          │
                     ┌────────────────────▼────────────────────────────────────┐
                     │  domain/           pure Python, total functions         │
                     │  lakebase.py  scaffold.py  (new)                        │
                     │  scope.py  (wired, not new)                             │
                     └────────────────────┬────────────────────────────────────┘
                                          │
                     ┌────────────────────▼────────────────────────────────────┐
                     │  adapters/databricks/                                   │
                     │  lakebase.py  apps.py  (new, use DbxHttp)               │
                     └────────────────────┬────────────────────────────────────┘
                                          │  REST
                     ┌────────────────────▼────────────────────────────────────┐
                     │  the workspace: /api/2.0/postgres, /api/2.0/apps        │
                     └────────────────────┬────────────────────────────────────┘
```

**The one rule that keeps this honest:** a domain module imports nothing from `adapters` or `routers`,
and a component imports nothing from `api/` except `client.ts`. Both directions already hold in the
existing code; the new files inherit it because they are placed inside the same directories and tested
the same way (no fixtures, no network).

---

## 2 · The five rules, and where each one lives

| Rule | Lives in | Why there | Tested by |
|---|---|---|---|
| A step is done only with a proof | `api/domain/scaffold.py` (compute) and `web/src/domain/scaffold.ts` (render) | it is a function of two lists; no I/O, so it is tested with literals | `tests/test_scaffold.py`, `domain/scaffold.test.ts`, and a **parity table** both read |
| A name must match its prefix | `tools/databricks_notebook_mcp.py::_check_prefix` | the tool server is a separate process; it cannot import the app | `tests/test_tools_fence.py` with five *different* prefixes |
| A Lakebase call speaks the Postgres API | `api/adapters/databricks/lakebase.py` and the tool's own helpers | the URL is an adapter concern; a domain module never builds a path | `tests/test_lakebase_adapter.py` asserts every URL |
| A credential is minted per call | `api/domain/lakebase.py::credential_request`, `tools/…::_lakebase_connect` | it is a value object plus one call site | `tests/test_lakebase_tools.py` asserts two calls → two mints |
| An object is openable | `web/src/domain/route.ts`, `docs.ts` | the route grammar is the single definition of "what can be named" | `domain/route.test.ts` (`parse∘format = id` for five kinds) |

### 2.1 · Why the scaffold rule is in *both* runtimes

The app computes the step table from the calls it observed (so a model cannot promote a step). The UI
recomputes it from the same events to render **live**, without a round trip per token. Two
implementations of one rule is a drift risk, so both are generated from one table:

```text
web/src/domain/scaffold.ts          api/domain/scaffold.py
        │                                   │
        └────────── scaffold-steps.json ────┘
         { "steps": [ {"key": "project", "tools": ["dbx_lakebase_create"], "proof": "project"},
                      … ] }
```

`scaffold-steps.json` is the single definition: the step keys, the tool names that can prove each step,
and the name of the field that *is* the proof. A test in each language parses the same file and asserts
its own table matches. Adding a step is a JSON edit and two type errors, which is the mechanism that
makes "one rule, two runtimes" enforceable instead of aspirational.

**Why not one runtime?** The UI cannot call Python synchronously during a stream, and the server cannot
render. The alternatives — a websocket round trip per step, or trusting the model's plan status — are
each worse: the first adds latency to the one thing that must feel instant, the second is exactly the
bug [001 rule 3] exists to prevent.

---

## 3 · The ports, and the two new adapters

The port layer (`api/ports/__init__.py`) gains two protocols, in the shape the existing ones use.

```python
class LakebaseAdmin(Protocol):
    """A Lakebase project and its children, as the signed-in user sees them."""
    async def projects(self, token: str | None) -> list[dict]: ...
    async def project(self, project: str, token: str | None) -> dict: ...
    async def branches(self, project: str, token: str | None) -> list[dict]: ...
    async def databases(self, project: str, branch: str, token: str | None) -> list[dict]: ...
    async def credential(self, endpoint: str, token: str | None) -> str: ...

class AppAdmin(Protocol):
    """Databricks Apps, their resources and their reachability."""
    async def apps(self, token: str | None) -> list[dict]: ...
    async def app(self, name: str, token: str | None) -> dict: ...
    async def health(self, url: str, token: str | None) -> dict: ...
```

Each has exactly one production adapter (`adapters/databricks/lakebase.py`,
`adapters/databricks/apps.py`) and one in-memory fake for tests, which is the same pattern
`CatalogBrowser` / `ServingBrowser` already follow. **The adapter is where `DbxHttp` is used**, so the
error mapping (`PermissionError`, `LookupError`, `ScopeMissing`) is inherited rather than re-invented —
that inheritance is what makes `[UI-6]` work without new code in the page.

### 3.1 · The tool server's half

The tool server cannot use these adapters (separate process, no `api` import), so it has its own thin
helpers over `httpx`. That duplication is deliberate and bounded: the **URLs** are duplicated (two
places build `/api/2.0/postgres/…`), the **rules** are not (the SQL scope check exists once in the tool;
the path fence exists once in the tool; the app-side `check_path` is a second implementation held to the
same table by `tests/test_fence_parity.py`).

| Duplicated | Count | Held together by |
|---|---|---|
| Lakebase URLs | 2 (`adapter`, `tools/`) | a test in each that reads `tests/fixtures/lakebase_urls.json` |
| The path fence rule | 2 (`scope.check_path`, `_check_path_scope`) | `tests/test_fence_parity.py`, a table of 20 cases |
| The step definition | 2 + 1 JSON | `scaffold-steps.json` |

Nothing else is duplicated. In particular the **credential request body** is built in one function per
runtime from one shape, and the shape is in the JSON fixture too, so a change to
`{"endpoint": …}` fails three tests rather than silently breaking one.

---

## 4 · The API surface

Four new route groups. Every route takes the user's token, and every route maps errors through the
existing helper, so the responses are consistent with `/workspace/*` and `/catalog/*`.

| Route | Returns | Notes |
|---|---|---|
| `GET /api/lakebase/projects` | `{items: [{ref, displayName, state, branchCount}]}` | one call to the platform |
| `GET /api/lakebase/projects/{p}` | `{ref, pgVersion, defaultBranch, endpoints, databases}` | the project's own fields |
| `GET /api/lakebase/projects/{p}/branches` | `{items: [{ref, name, isDefault}]}` | lazy: called on expand |
| `GET /api/lakebase/projects/{p}/databases?branch=` | `{items: [{ref, name}]}` | |
| `GET /api/lakebase/projects/{p}/tables?branch=&schema=` | `{items: [{name, rows}], truncated}` | `LIMIT 50`, `truncated` is honest |
| `GET /api/apps` | `{items: [{name, state, url, lakebaseRef}]}` | `lakebaseRef` read from the **list** payload |
| `GET /api/apps/{name}` | `{…, resources, deployments, health}` | one health call, 15 s cache |

**Why `?branch=` is a query parameter, not a path segment, on the databases route.** A branch ref
contains slashes (`projects/p/branches/b`), and a path segment with slashes needs double encoding, which
is the class of bug `route.ts` already fought for notebook paths. A query parameter is unambiguous, and
the route grammar for the *UI* still uses slashes (it percent-encodes per segment, which `route.ts`
already does correctly).

**Why no aggregate `GET /api/lakebase/projects/{p}/overview`.** [06 §5](06-lenses.md#5-system-design-expert) settles
it: an aggregate endpoint makes one slow field hide four fast ones, and makes a partial failure
indistinguishable from an empty result. The page fans out; each block owns its own state.

---

## 5 · The front-end structure

Three new components, two extended, and one new union member used everywhere.

```text
domain/
  lakebase.ts     ref normalisation, capacity rules, "is this a branch of that project"
  app.ts          app state words, the health verdict (200 / starting / down), the /logz URL
  scaffold.ts     the seven-step table, computed from plan + calls, O(c + s)
  docs.ts         DocKind gains "lakebase" | "app"; makeDoc; ACTIONS_FOR for two kinds
  route.ts        two new kinds in format/parse; percent-encoding per segment as today
  toolview.ts     dbx_lakebase_* and dbx_create_app → a Doc, or null (never a guess)

components/
  LakebasePage.tsx   four independent blocks, each with loading/error/empty
  AppPage.tsx        state, resources, health, logs link
  DataTree.tsx       the fourth rail tab: projects then apps, lazy children
```

### 5.1 · Why three components and not one "InfraDocument"

A project and an app share nothing but being read-only. Their fields differ, their states differ, their
actions differ (a project has branches; an app has a health check and logs). One component would be a
union with a `kind` branch in every field, which is how a renderer becomes unreadable. Three components
with two shared primitives (`Field`, `Block`) is the DRY version: the *primitives* are shared, the
*content* is not.

### 5.2 · The read-only surface, stated once

`LakebasePage` and `AppPage` render `viewer-head` (the same header the table viewer uses) and **no**
`EditorSurface`. There is no save, no dirty state, and no `⌘S` handler, because the components have no
prop for one. That is the structural version of "read-only is taught by absence": a component that
cannot be passed a save callback cannot accidentally gain a save button.

### 5.3 · How a tool row opens the object

`touched()` in `domain/docs.ts` reads a path out of a tool's arguments or result. Two new cases, and the
rule stays "never guess":

```ts
// the arguments name the object, or the result does
dbx_lakebase_create  {name} → the result's `project` field is the identity
dbx_create_app       {name} → the app's name is the identity
```

For a Lakebase project the **result** is authoritative, not the argument: the create tool's `name` is the
id it asked for, and the platform may report the canonical path. Reading the result is what makes the
"one object, one key" rule (`[LB-5]`) hold even when the two spellings differ.

---

## 6 · Persistence

**What is stored: nothing new that is durable.** The session's five prefixes already exist in `Scope`
and in the journal. The two new pages read the workspace on each visit, with a 60 s in-process cache.

**Why no table.** The truth about a project lives in Lakebase, and a copy in our Postgres would be a
second truth that drifts — with a reconciliation problem this product has no reason to own. The
journal's job is the *conversation*, not the infrastructure.

**The one exception, and it is opt-in.** A deployed app with `APP_SESSION_USE_LAKEBASE=true` already has
a Postgres. If `[E-16]` (a cold project page) becomes a real complaint, the `ObjectCache` port gains a
Postgres adapter with the same TTL semantics and no schema change to the journal. The port exists so
that decision is a swap, not a migration.

---

## 7 · Where the fence now lives

`[F4]` found four policy functions with no caller. The fix is not to call them from the tool server
(which cannot import them) but to make the **same five values** reach both sides, and to test the rule
in both. This is the shape:

```text
Scope.for_session(id, folder, schema)
   │
   ├─ folder, schema, job_prefix ────────► routers (check_path, in-process)
   │                                            │
   │                                            └─ Verdict.ASK → approval panel
   │
   └─ the same five strings ─────────────► SubprocessToolRegistry.start()
                                                │  env: NBMCP_WRITE_*
                                                ▼
                                          tool server: _check_prefix / _check_path_scope
                                                │
                                                └─ refusal → a sentence the model reads
```

**What changes in `registry.start`:** one more variable.

```python
"NBMCP_WRITE_APP_PREFIX": f"agent-{session_id[:8]}-",
```

**What changes in the tool server:** `dbx_create_app` reads it. Everything else already works.

That is a two-line fix for a `[F3]`-class defect, and it is worth noticing *how* small it is: the
architecture was right, the wiring was one variable short, and no test could see it because both
prefixes were equal. The test that closes it uses two different prefixes.

---

## 8 · What this architecture deliberately does not do

| Not doing | Why, and what it would cost |
|---|---|
| A second renderer path for read-only documents | `viewer-head` + a body component is enough; a "viewer framework" is a layer for three files |
| A generic `InfraKind` union for future object types | a union of two is readable; a union of nine is a plugin system, and it should be built when the ninth arrives |
| Sharing code between the tool server and the app | the tool server must start alone (`_find_server` walks up for it); a shared package would make it a library of the app |
| Persisting object state | the workspace is the truth; a copy is a reconciliation problem we do not need |
| A background poller for app health | health is read when the page is open; a poller would spend quota on pages nobody is looking at |

---

## 9 · The change surface, in one table

A reviewer should be able to check this against the diff.

| File | Change | Why |
|---|---|---|
| `tools/databricks_notebook_mcp.py` | Lakebase tools rewritten on `/postgres`; `dbx_create_app` gains resources/scopes/prefix/verify; `psycopg2` → `psycopg`; `dbx_lakebase_branch`, `_database`, `_role`, `_compute`, `dbx_app_health` added | `[LB-1..5]`, `[AP-1..4]` |
| `tools/skills/lakebase-postgres.md` | rewritten: the app-resource contract, `PGHOST`, `LAKEBASE_ENDPOINT`, `psycopg` | `[F7]` |
| `tools/skills/databricks-apps.md` | rewritten: `resources`, `user_api_scopes`, `git_repository`, the refusal to report | `[F6]` |
| `mcp/databricks_notebook_mcp.py`, `mcp/skills/*` | **deleted**; `registry._find_server` keeps one location | `[F8]`, `[F9]` |
| `api/adapters/mcp/registry.py` | passes `NBMCP_WRITE_APP_PREFIX` | `[AP-2]` |
| `api/adapters/databricks/lakebase.py` | **new**: the `LakebaseAdmin` adapter | `[LB-1]` |
| `api/adapters/databricks/apps.py` | **new**: the `AppAdmin` adapter | `[AP-3]`, `[AP-4]` |
| `api/domain/scaffold.py` | **new**: the step table, pure | `[SCF-1]` |
| `api/domain/lakebase.py` | **new**: ref normalisation, capacity rules | `[LB-4]`, `[LB-5]` |
| `api/routers/lakebase.py`, `api/routers/apps.py` | **new**, same conventions as the existing routers | §4 |
| `api/main.py` | two adapters bound in `build()` | wiring |
| `api/ports/__init__.py` | two protocols | §3 |
| `web/src/domain/lakebase.ts`, `app.ts`, `scaffold.ts` | **new** | `[UI-3..5]`, `[SCF-1]` |
| `web/src/domain/docs.ts`, `route.ts`, `toolview.ts` | two kinds, two cases each | `[UI-1]`, `[UI-5]` |
| `web/src/domain/layout.ts` | `RAIL_TABS` gains `"data"` | `[UI-2]` |
| `web/src/components/LakebasePage.tsx`, `AppPage.tsx`, `DataTree.tsx` | **new** | `[UI-3]`, `[UI-4]`, `[UI-2]` |
| `web/src/App.tsx` | the fourth tab, the two renderers, two palette entries, two `⌘` rows | `[UI-1..5]` |
| `web/src/domain/keys.ts` | `⌘4` | `[UI-2]` |
| `web/src/styles.css` | the two pages' blocks | visual |
| `tests/test_packaging.py` | walks `tools/` as well | `[F1]` guard |
| `tests/test_tools_fence.py`, `test_fence_parity.py`, `test_scaffold.py`, `test_lakebase_adapter.py`, `test_lakebase_tools.py`, `test_apps_adapter.py` | **new** | each rule |
| `web/src/domain/*.test.ts` | route, docs, scaffold, lakebase, app | each rule |
| `web/scripts/lakebase-e2e.mjs` | **new**: the E2E scenes | [11](11-e2e-plan.md) |

**Nine new files in `web/src/domain` + `components`, six new Python modules.** That is the size of the
change, and it is not smaller because the product genuinely had no representation of either object; it
is not larger because every rule found a home in a layer that already existed.
