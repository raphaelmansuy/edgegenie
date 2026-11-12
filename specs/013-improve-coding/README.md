# 013 · Lakebase and Databricks Apps as first-class coding targets

**Status:** specification, implementation plan **and implementation** · 10 November 2026
**Built and running.** Five new Python modules, four new front-end modules, three new components, two
skills rewritten, one duplicated tool server deleted. **769 Python tests, 733 front-end tests, 8/8 E2E
scenes**, and every screenshot inspected — the [outcome](12-outcome.md) records the five defects the
pictures found, four of which passed their assertions first.
**Scope:** the two Databricks object types a data engineer builds *with* an agent and cannot see in
this app — **Lakebase Postgres** and **Databricks Apps** — from the tool the agent calls, through the
API, to the screen the user reads. Not the agent runtime (001), not the notebook model (010), not the
deployment of this app itself (017/021). Cited, not restated.

> **The report this starts from.** On the deployed app, the card *"Lakebase and an app"* offers
> *"Create a Lakebase database with one table and a small app that reads it. Show me the connection
> details."* The agent has five tools for that job. Three of them fail on the first real call — one
> because a dependency is not installed, one because the endpoint it calls no longer describes a
> Lakebase project, one because a prefix check reads the wrong variable. And the app can create neither
> object as a *document*: there is no way to look at a project, a branch, an app, its resources, its
> health or its logs after the turn that made it. The card promises a workflow the product does not
> finish.

---

## What this folder is

| # | Document | Answers |
|---|---|---|
| 01 | [Five whys and first principles](01-five-whys.md) | Why is "build me a database and an app" the least finished workflow in the app? |
| 02 | [Measured assessment](02-assessment.md) | What is actually wrong: file, line, and what the platform says |
| 03 | [Requirements](03-requirements.md) | What must be true when it is done (`LB-*`, `AP-*`, `SCF-*`, `UI-*`) |
| 04 | [Wireframes (ASCII)](04-wireframes.md) | Every screen, every state, every recovery path |
| 05 | [Diagrams (Mermaid)](05-diagrams.md) | Sequence, state and E/R: the workflows drawn out |
| 06 | [Lenses](06-lenses.md) | The same work seen by seven owners |
| 07 | [Architecture](07-architecture.md) | Where each rule lives, and why there |
| 08 | [Implementation plan](08-implementation-plan.md) | Phases, files, tests, order |
| 09 | [Edge cases](09-edge-cases.md) | Every failure I could name, its mitigation, its test |
| 10 | [Roadblocks](10-roadblocks.md) | What is in the way, grounded in code, and the way past each |
| 11 | [E2E plan](11-e2e-plan.md) | Scenes, screenshots, pass criteria |
| 12 | [Outcome](12-outcome.md) | What shipped, and what the screenshots found |
| — | [E2E screenshots](e2e/screenshots/README.md) | What it actually looks like, each one inspected |

Cross-references: a requirement is `[LB-3]`, an edge case `[E-12]`, a scene `[S4]`, a roadblock
`[RB-5]`. Each id is defined once — in `03`, `09` or `10` — and cited everywhere else. A citation that
is not in one of those three is a bug in this document set. (Findings `F1`–`F9` are the exception: they
are the *evidence*, defined in [02](02-assessment.md), and cited without brackets so they cannot be
confused with a defined id.)

Builds on:
[001](../001-databricks-coding-agents/README.md) the app, its ports and its fence ·
[005](../005-llm-models/README.md) the catalogue ·
[006](../006-databricks/README.md) Genie Code parity ·
[010](../010-long-running/README.md) durable sessions ·
[011](../011-ux-coding-mission/README.md) the mission view ·
[012](../012-ux-improve/README.md) the input, scroll and connection contract.
It replaces none of them; it finds where the product stops short of a workflow it advertises.

---

## The one sentence

> A card that offers to build a database and an app must end with both objects **created, opened,
> readable and provable on screen** — or say in one sentence what blocked it and what the user can do.

Today it does neither. It creates what it can, reports it in prose, and gives the user no way to look.

## The finding, in one table

Every row was measured against the code in this checkout, not remembered.

| # | Finding | Evidence | Kind |
|---|---|---|---|
| **F1** | `dbx_lakebase_sql` — the only tool that can create a schema, a table or seed a row — imports `psycopg2`, which is in **no** requirements file. The app's own dependency check walks `api/` only, so it never sees `tools/`. The card's first data step raises `ModuleNotFoundError`. | `tools/databricks_notebook_mcp.py:1028`; `requirements.txt`; `pyproject.toml`; `tests/test_packaging.py:26-50` | **defect** |
| **F2** | The three Lakebase tools use `/api/2.0/database/instances`, the **Database Instance** API. Since 2026-03-12 that call *creates an Autoscaling project*, and the objects it returns (`read_write_dns`, `capacity`) are the Provisioned shape. There is no tool for a project, a branch, an endpoint, a database or a role — the five things the docs now describe. | `tools/databricks_notebook_mcp.py:992-1046` | **defect** |
| **F3** | `dbx_create_app` checks its name against `INSTANCE_PREFIX`, not an app prefix. The session's `Scope` *has* an `app_prefix` and a `check_app()`, and neither is reachable from the tool server: no `NBMCP_WRITE_APP_PREFIX` is passed in. So the app fence is decorative and the instance prefix is doing the work. | `tools/databricks_notebook_mcp.py:1055`; `api/domain/scope.py:38-60,146-153`; `api/adapters/mcp/registry.py:50-65` | **incoherence** |
| **F4** | `check_sql`, `check_job` and `check_instance` are called **only from tests**. The API routes call `check_path` for a save; nothing else in `api/` consults the fence. Four of the five policy functions in the module that calls itself "the write fence" have no production caller. | `api/domain/scope.py`; `rg 'check_app\|check_job\|check_instance' api/` → no call sites | **incoherence** |
| **F5** | The app can create a Lakebase project and an app, and then cannot open either. `DocKind` is `"notebook" \| "file" \| "table"`; the route grammar knows the same three; the rail has three tabs. Nothing on screen names a project, a branch, an app or a deployment. | `web/src/domain/docs.ts:4`; `web/src/domain/route.ts:17`; `App.tsx:785` | **gap** |
| **F6** | The *Databricks Apps* skill tells the agent to call `dbx_write_file` for `app.yaml` and then `dbx_create_app`. Deploying needs `resources` (a `postgres` resource with a branch and a database), a `user_api_scopes` list, and — on a git-only workspace — a `git_repository`. The tool sends `{"name": …}` and nothing else, so the app it creates has no database to connect to. | `tools/skills/databricks-apps.md`; `tools/databricks_notebook_mcp.py:1058-1068` | **gap** |
| **F7** | The lakebase skill's connection snippet has a hard-coded `psycopg2.connect(...)` and no `LAKEBASE_ENDPOINT`, `PGHOST`, or `CAN_CONNECT_AND_CREATE` — the four names the current app-runtime docs use. A developer who follows it writes an app that cannot start on the platform. | `tools/skills/lakebase-postgres.md:20-27` vs the app-resource contract | **gap** |
| **F8** | Two copies of the tool server exist (`mcp/` and `apps/coding-agent/tools/`) and have **diverged**: 987 vs 1104 lines, with the app's copy carrying the token-file read, the 401/403 hook and the run bridge. The repository's own deployment ships the app copy; the `mcp/` copy is what the README's tool table describes. | `diff mcp/databricks_notebook_mcp.py apps/coding-agent/tools/…` | **drift** |
| **F9** | The four skills are duplicated byte-for-byte in two directories, so a fix to one is invisible to the other — and the deployed app reads the `tools/skills/` copy. | `md5 mcp/skills/*.md` == `apps/coding-agent/tools/skills/*.md` | **drift** |

F1, F2 and F3 are the defects: the card cannot do what it says. F5 is why the workflow has no ending
even when the tools work. F4, F8 and F9 are the architectural finding, and they are one finding:
**there is no single place that owns "what the agent may create, and what the user can then look at".**
The fence was written for paths and SQL; the two newest object types were bolted on beside it, and the
seam shows in four different files.

## What is *not* wrong

Worth stating, because the fix must not disturb it.

| Works today | Where |
|---|---|
| Lakebase **as this app's own store**: OAuth-token connection, token refresh at 45 min, pool lifetime 40 min | `api/adapters/llm/store/lakebase.py` |
| The `postgres` API the deployment scripts already use (`databricks postgres get-project`, `create-role`, `generate-database-credential`) | `scripts/provision-lakebase.sh` |
| The write fence's *runtime* contract: `NBMCP_WRITE_PATHS`, `NBMCP_WRITE_SCHEMAS`, job prefix enforced server-side | `tools/databricks_notebook_mcp.py:182-246` |
| Apps as a *deployment target* for this repository: two workspaces, two transports, verified after deploy | `databricks.yml`, `scripts/env.sh`, `Makefile` |
| The evidence supervisor: a claim with no tool call is reported as unproven | `api/domain/supervisor.py`, `api/domain/evidence.py` |

The asymmetry is the point of the whole spec: this app is an expert at **being** a Databricks App and
at **using** Lakebase, and a beginner at **helping a user build** either.

## The four principles this rests on

1. **A scaffold is a proof, not a paragraph.** An agent that says "created the database and the app,
   here are the connection details" has told the user nothing they can check. Every step of a scaffold
   is a call that returned a fact — a project id, an endpoint host, a row count, an HTTP status — and
   the screen shows the fact, not the sentence. This is [001 rule 3] applied to infrastructure.
2. **An object the agent created is an object the user can open.** If a turn can produce a Lakebase
   project or a Databricks App, the app must be able to open it, name it, link to it, and show its
   live state. Otherwise the user's next question ("is it running?") has no answer in the product.
3. **The platform's refusal is the message.** A missing `CAN MANAGE`, a git-only workspace, a
   git-only app, a capacity below the minimum, a branch id that already exists: each is a sentence the
   platform wrote, addressed to the user, and repeating it verbatim with one action beside it beats
   any paraphrase we invent. [012] made this rule for a connection state; this is the same rule for a
   permission.
4. **A policy function with no caller is a lie in a comment.** `check_app` has tests and no users.
   Either a path exists that calls it, or it is deleted; "the fence covers apps" must be true of the
   running server, not of the module's docstring.

Everything below is an argument about those four sentences.

---

## Reading order for a reviewer short on time

1. [02 Measured assessment](02-assessment.md) — the nine findings with line numbers. Ten minutes.
2. [10 Roadblocks](10-roadblocks.md) — which of them cannot be fixed from here, and why (Lakebase's
   API moved; an app cannot create an app with a git source it does not own). Ten minutes.
3. [08 Implementation plan](08-implementation-plan.md) — the order, and what each phase proves.
4. [12 Outcome](12-outcome.md) — written last, from the running app, with the screenshots.

## The implementation, in one table

| Phase | What it made true | Gate |
|---|---|---|
| 1 | the product's **existing claims** are true: the tool server can import its Postgres client, speaks the current API, and fences an app by the app prefix | `test_packaging.py`, `test_tools_fence.py` (both fail on the old tree) |
| 2 | the agent speaks the API **as it is**: projects, branches, databases, roles, endpoints, credentials, and an app with the resource that lets it connect | `test_lakebase_tools.py`, `test_fence_parity.py` |
| 3 | the user can **see and open both objects**: a `Data` tab, two document kinds, two pages, five ways in | `route.test.ts`, `InfraPages.test.tsx`, `tsc` |
| 4 | it **looks right and fails gracefully**: eight E2E scenes, every screenshot inspected | `lakebase-e2e.mjs` 8/8 |
