[Index](README.md) · prev: [11 E2E plan](11-e2e-plan.md)

# 12 · Outcome

Written last, from the running app and the passing suites, not from the plan.

---

## The card, and what it actually was

> *"Lakebase and an app — Create a Lakebase database with one table and a small app that reads it. Show
> me the connection details."*

It was not a missing feature and it was not a prompt problem. It was five separate failures that
composed into one dead workflow:

| What the card needed | What was there |
|---|---|
| create a project | the Provisioned API, which still answered with the old shape |
| put a table in it | `import psycopg2`, a client in no requirements file |
| make a branch | no tool at all |
| attach the database to the app | `POST /apps {"name": …}`, three fields short |
| open either object afterwards | `DocKind` had three members, none of them these |

The most dangerous of the five was the first: **it did not fail.** The old endpoint creates an
Autoscaling project, so the create "succeeded" and every field read afterwards described an object
model the platform had migrated away from. A loud failure would have been found in a day.

## What was built

Six new Python modules, four new front-end modules, three new components, two skills rewritten, one
duplicate tree deleted.

| File | Change |
|---|---|
`tools/databricks_notebook_mcp.py` | Lakebase tools on `/api/2.0/postgres`; five new tools (`branch`, `database`, `role`, `tables`, `app_health`); `dbx_create_app` gains resources, scopes, a bounded wait and a `verified` flag; `psycopg2` → `psycopg`; the app prefix is its own variable; the path fence refuses `..`
`tools/skills/lakebase-postgres.md` | rewritten: the app-resource contract, `PGHOST`, `LAKEBASE_ENDPOINT`, `psycopg`
`tools/skills/databricks-apps.md` | rewritten: `resources`, `CAN_CONNECT_AND_CREATE`, `git_repository`, `0.0.0.0`, `/logz`
`mcp/databricks_notebook_mcp.py`, `mcp/skills/*` | **deleted**; `mcp/README.md` says where they went
`api/adapters/mcp/registry.py` | passes `NBMCP_WRITE_APP_PREFIX`
`api/domain/lakebase.py` | **new**: identity, the capacity rule, the state words
`api/domain/scaffold.py` | **new**: the seven-step table, `O(c + s)`, proof or nothing
`api/adapters/databricks/lakebase.py` | **new**: six reads, a cache keyed per credential, four blocks that cannot blank each other
`api/adapters/databricks/apps.py` | **new**: state, resources, and the five health words
`api/routers/infra.py` | **new**: 12 routes, same conventions as `/workspace/*`
`api/main.py` | the two adapters bound; the router included
`web/src/domain/lakebase.ts`, `app.ts`, `scaffold.ts` | **new**: the same three rules, in TypeScript
`web/src/domain/scaffold-steps.json` | **the single definition** both runtimes read
`web/src/components/Infra.tsx`, `LakebasePage.tsx`, `AppPage.tsx`, `DataTree.tsx` | **new**
`web/src/domain/docs.ts`, `route.ts`, `layout.ts`, `keys.ts`, `dock.ts`, `recent.ts`, `links.ts`, `binding.ts` | two document kinds, two routes, a fourth tab, `⌘4`, kind-aware suggestions
`web/src/App.tsx` | the fourth tab, two renderers, kind-aware palette groups
`web/src/styles.css` | the two pages' blocks, pills and rows
`tests/` | **five new files**, 126 new tests
`web/src/**/*.test.ts` | **four new files**, 75 new tests

**The deletion is the part worth noticing.** `mcp/` held a second tool server that had drifted 117
lines from the one that ships. Removing it, and asserting uniqueness, is what makes a future fix reach
production.

## The five defects the screenshots found

Every one of these passed its scene's assertions on the first run, or would have if the assertion had
been written loosely enough.

| # | Found in | Defect | Fix |
|---|---|---|---|
| 1 | `s6` (1st look) | The card built a **taxi notebook**. The demo's prompt picker had no Lakebase case, so the card fell through to `notebook` | a `lakebase` branch in `fake/agent.py`, and the card's own `scenario` field corrected |
| 2 | `s2`, `s3` | The dock offered **"Explain this notebook"** over a Lakebase project and over an app — a plausible button, wrong about its subject | `suggestionsFor` gained a case per kind |
| 3 | `s5` | A `PERMISSION_DENIED` offered **"Try again"** | `Block` withholds retry for a permanent refusal |
| 4 | `s7` | The scene asserted a drawer at 900 px; `modeFor` puts narrow at ≤ 820 — **the test was wrong, not the app** | the scene asserts the code's rule; the wireframe caption is corrected |
| 5 | my own S6 assertion | It accepted any infrastructure word, so it passed on the wrong scenario | it now names the objects, the plan total and the proof |

Defect 1 is the instructive one. A screenshot of a *different scenario* is the largest possible
mismatch between what a scene claims and what it shows, and the assertion was one `||` away from
catching it. [012] recorded the same lesson in a smaller form; this is the same lesson at the scale of
a whole workflow.

## Two things the implementation found that the spec did not

Recorded because a spec that hides its own gaps is not a record.

**The tool server's path fence accepted a `..` escape.** `_check_path_scope` compared a prefix, so
`/Users/me/agent_scratch/../other/x.py` matched the fence and passed. The app's own `check_path`
normalises and refuses it. Two implementations of one rule, and only one of them was correct — which is
exactly the class `[F4]` named, found by writing the parity test that `[RB-5]` specified. The tool
server now refuses `..`, and `tests/test_fence_parity.py` holds both sides to one table.

**`Scope.for_session` derives the same string for an app and an instance.** `agent-<id>-` for both. The
parity test cannot therefore distinguish "an instance name checked as an app" from "an app name checked
as an app" *at the scope level* — so that case lives in `test_tools_fence.py`, which uses five
deliberately different prefixes. Both files say so in a comment, because a test that passes for the
wrong reason is worse than no test.

## Three things the DEPLOYMENT found that nothing else did

The spec's `[RB-2]` predicted the first of these. The rest only exist once a real browser session, a
real `make deploy` and a real Postgres connection are in the loop.

| # | What the deployed app showed | Root cause | Fix |
|---|---|---|---|
| 1 | `make verify` failed: **`missing scopes: postgres, apps`** | `make deploy` was `provision sync deploy-only verify`, and `deploy-only` only shipped code — it never ran the `apps update` that sends `user_api_scopes`. The body builder lived in `deploy.sh`, which nothing called | `deploy` now calls `scripts/deploy.sh`, the one ordered path |
| 2 | The Data pane drew the **same "sign-in needs refreshing" box twice** | projects and apps are two calls that fail for one reason, and `DataTree` rendered one `PaneError` per call | `errorBoxes` collapses identical messages, keeps distinct ones |
| 3 | The message said **"clear this site's cookies"** and did not name the permission | the front end discarded the scope name `ScopeMissing` carries, and offered a prose remedy | it names the scope and points at the app's owner — see `[RB-10]`, which then removed the action entirely |

## `[RB-10]` · `postgres` cannot be an on-behalf-of-user scope, at all

**The strongest constraint in this spec, and the one I got wrong first.**

The deployed app showed a 403 on `/api/lakebase/projects` and `/api/apps`. The scopes were granted, the
upstream APIs answered 200 to the same identity, and the app offered a "Sign in again" button. The user
pressed it. It did nothing — and it could never have done anything, because Databricks' own platform
guide says:

> `postgres` — Lakebase (**always bound to the SP, not OBO**; see below)
>
> `secret`, Lakebase (`database` / `postgres`), and MLflow (`experiment`) resources are **always** bound
> to the service principal and **cannot run OBO**, even under `--auth-mode obo`.
> — *databricks-agent-skills*, `skills/databricks-apps/references/platform-guide.md`

So declaring the scope puts it in the app's `effective_user_api_scopes` and **never** in the forwarded
user token. `_user_token` returns the forwarded token, so every Lakebase call was unauthorizable by
design, and no number of sign-ins could change it. My "Sign in again" button was a dead end I built
myself — the exact defect class this spec exists to remove.

**The fix, and what it costs.** The two infrastructure read paths now authenticate as the **app's own
service principal** (`adapters/databricks/sp_token.py`, an `oauth-m2m` token built from the
`DATABRICKS_CLIENT_ID`/`SECRET` a Databricks App injects). That is the same mechanism
`adapters/llm/store/lakebase.py` has always used, which is why the model registry worked while this page
did not.

The consequence, stated rather than hidden: **these two panes show what the app may see, not what the
viewer may see.** That is the right model for a management surface — the app's SP owns the infrastructure
it created — but it is a different promise from the rest of the product, where Unity Catalog decides per
user. `[RB-1]` still governs what the *agent* may touch; this is the page reading what already exists.

## `[RB-11]` · The Postgres username is on a ROLE, and a credential is bound to its minter

Two facts, each of which produced a `403`/auth failure that looked like a permissions problem.

**1. `postgres_role` is not a field on an endpoint.** `tables()` built the username from
`endpoint.status.postgres_role`. Measured against a live endpoint, `status` has
`autoscaling_limit_max_cu, autoscaling_limit_min_cu, current_state, disabled, endpoint_id,
endpoint_type, group, hosts, last_active_time, settings, suspend_timeout_duration` — and no
`postgres_role`. So `user` was always `""`. The username lives on a **role object**, at
`role.status.postgres_role`.

**2. A Lakebase credential may only be used by the identity that minted it.** Decode `sub` from the
credential JWT and it is the user or service principal behind the token. Connecting with
`user=<someone else>` fails with `OAuth: User is not authorized` *even when that identity owns a
Postgres role*. My first probe minted one credential as the human and then tried to connect twice — as
the SP and as the human — and reported the SP as unauthorised. **The failure was in the probe, not the
product.** That is worth recording because it is the shape of most "it must be permissions" conclusions.

The corrected probe, run as an in-workspace job against the real database, reports six passes:

```
PASS the endpoint has a host
PASS the endpoint's status has NO postgres_role (reading it gave an empty user)
PASS the branch lists the identities that may connect —
     ad7545de-… (coding-agent-sp), raphael.mansuy@gmail.com (raphael-mansuy)
PASS the credential is bound to the minting identity — sub=raphael.mansuy@gmail.com
PASS connected and read information_schema as raphael.mansuy@gmail.com —
     current_user=raphael.mansuy@gmail.com; [('agent', 2), ('information_schema', 4), ('llm', 9), ('pg_catalog', 64)]
PASS this identity has a Postgres role on the branch
```

`scripts/lakebase_read_probe.notebook` is that probe, kept in the repository because a laptop genuinely
cannot run it: the endpoint is a private-link ingress, so port 5432 times out from here (measured, and
already documented by `env.sh`'s `DEPLOY_LAKEBASE_DIRECT="no"`).

**Why these matter more than the code size suggests.** All of them are the *same* failure this spec is
about, arriving from a direction the tests could not reach: **a check that cannot see a failure.** The
Makefile never saw that it was not configuring the app. The pane never saw that it was saying one thing
twice. The message never saw that it knew the answer and threw it away. And my probe never saw that it
was testing an identity combination the platform forbids — it reported `PERMISSION_DENIED` for a
symptom three layers away from the cause.

## Verification

| Gate | Result |
|---|---|
| `pytest` (backend) | **769 passed, 7 skipped** (was 643 + 7) |
| `vitest` (front end) | **741 passed, 0 failed** (was 655) |
| `tsc -b --noEmit` | clean |
| `make check` | all green |
| `make deploy ENV=dev` | **DEPLOYED AND CURRENT** — `SUCCEEDED`, `RUNNING`, 11/11 scopes effective |
| In-workspace Postgres probe | **6/6 checks**, including a real `information_schema` read |
| `lakebase-e2e.mjs` | **8/8 scenes**, 41 checks, screenshots in [`e2e/screenshots/`](e2e/screenshots/README.md) |
| `verify-spec-ascii.mjs` | **0 problems** across 22 boxes |
| `verify-spec-mermaid.mjs` | **8 diagrams, 0 failing** |
| `verify-spec-links.mjs` | 79 links, 0 problems |
| `cls-audit.mjs` | worst shift **0.0047** (budget 0.01) |
| A screenshot inspected | every one, with what it changed |

**Live:** https://coding-agent-7474647158015570.aws.databricksapps.com (dev workspace
`dbc-cb61f1e1-bd8e`, commit `7972cd1`).

**Two gates I could not run here, and a defect that hiding them exposed.** `a11y-audit.mjs` and
`overflow-audit.mjs` drive a real workspace: they open `Files`, search for a notebook named `taxi`, and
click the result. There is none in this environment, so both time out at that click. `make audits` used
to pipe each through `grep TOTAL`, which discarded the exit code — so it printed the CLS number, said
nothing about the two crashes, and exited 0. **That is the same defect as `[F3]`**: a check that cannot
see a failure reports success. The target now prints which audit could not run and says its results are
not a pass. The new pages are covered instead by `InfraPages.test.tsx` (11 tests, including the
missing-field and partial-failure cases) and by the scenes' own overflow assertions at 900 and 1480 px.

The tests that matter most, and why:

| Test | What it would catch |
|---|---|
`test_packaging.py::test_every_runtime_import_is_declared` | a dependency the **tool server** needs but nothing declares — the `[F1]` class. It now walks `tools/` as well as `api/`, and it failed on the old tree before the fix |
`test_packaging.py::test_exactly_one_tool_server_exists` | re-introducing the duplicate that made a fix reach nobody |
`test_tools_fence.py::test_an_app_name_is_checked_against_the_app_prefix_not_the_instance_prefix` | the `[F3]` defect, with five different prefixes so it cannot pass by coincidence |
`test_fence_parity.py` | the two fences drifting apart, including the `..` escape it found |
`test_scaffold.py::test_a_completed_call_without_the_proof_field_does_not_prove_the_step` | a `✓` with nothing behind it |
`test_lakebase_tools.py::test_the_adapter_never_speaks_the_provisioned_dialect` | the old API creeping back — a vocabulary test for a vocabulary defect |
`route.test.ts` (the three original kinds) | a regression in the existing grammar while adding two members |

## Still open, honestly

| Item | Why it is not closed |
|---|---|
| A scaffold against a real workspace | needs `CAN MANAGE` on a Lakebase project and an app quota; the adapter asserts every URL and body, and the E2E runs on recorded payloads. `[RB-1]` is the boundary |
| `a11y-audit.mjs` / `overflow-audit.mjs` against the new pages | both drive a real workspace (they search `Files` for a notebook) and cannot run here. The pages are covered by 11 component tests and by the scenes' own overflow checks. **The target itself was fixed**: it now says which audit could not run instead of exiting 0 |
| The Postgres API's exact field names on a 2026-11 build | taken from the vendor reference; the adapter reads `status.state`, `status.hosts.host` and the autoscaling limits, and a rename fails loudly with the path in the message rather than silently showing `—` |
| An app created from a Git source | `[RB-3]`: the app cannot obtain a Git credential on the user's behalf. It is accepted as an argument and the refusal is reported verbatim |
| The `role` step for a **pre-existing** app | the platform creates the role when the resource is attached; for an app created before this change, `dbx_lakebase_role` reports what exists and says what to do |
| Reading a table's row count on the page | the page lists **names** (one connection, `LIMIT 51`); a count per table is `O(t)` queries and lives in `dbx_lakebase_tables`, where an agent asked for it explicitly |
| The Data tab on a workspace with no Lakebase | shows two error blocks with the platform's sentence. Correct, and not pretty; `[RB-2]` says a scope must be granted by an owner |

## The one sentence, re-checked

> A card that offers to build a database and an app must end with both objects **created, opened,
> readable and provable on screen** — or say in one sentence what blocked it and what the user can do.

Measured against the running app:

| Part | Before | After |
|---|---|---|
| created | a project, with the wrong shape and no branch | a project, a branch, a database, a table, an app with its resource |
| opened | impossible: no document kind | a tab, a URL, a rail node, a palette entry, a tool row's *Open* |
| readable | a transcript row saying `created a database` | six blocks, each a fact from a call, each failing on its own |
| provable | the model's sentence | an HTTP status, a row count, and a plan where `✓` requires a proof |
| the refusal | a traceback the model paraphrased | the platform's sentence, one owner, no dead-end retry |

The app does all five now. The seventh step of the scaffold is the one that makes the claim true rather
than plausible: **`dbx_app_health` is the only thing in this workflow that could not be satisfied by
writing a convincing sentence.**
