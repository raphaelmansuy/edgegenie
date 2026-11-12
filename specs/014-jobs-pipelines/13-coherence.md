[Index](README.md) · prev: [02 Measured assessment](02-assessment.md) · next: [08 Implementation plan](08-implementation-plan.md)

# 13 · Coherence check: the spec against the code

Every claim the spec makes about the existing code, checked against the file, before a line was written.
This is the step that turns a plausible plan into a buildable one. Three outcomes per row:

* **✓ agrees** — the code says what the spec assumes.
* **✗ contradicts** — the spec was wrong and was corrected. The correction is named.
* **⚠ risk** — the code permits it but nothing enforces it, so the plan must add the enforcement.

A spec that reaches this table with no ✗ has not been read carefully enough. There are six, listed first.

---

## The six contradictions, and what changed

| # | The spec assumed | The code says | The correction |
|---|---|---|---|
| **C1** | the core tool budget could absorb six new tools | `_CORE` is exactly 25 and `test_tools_fence.py:211` asserts `== 25` | §`[TOOL-1]` became a **decision** with arithmetic: 28, three removed, three assertions. [07 §6](07-architecture.md#6-the-tool-budget-spent-deliberately) |
| **C2** | the pipeline fence could be a session ledger table in the app's database | the tool server is a **subprocess** with no database credential (`registry.py:73-83`) | the ledger is a **file** the app owns and passes by path. `[RB-3]`, and [05 §9](05-diagrams.md#9-er-what-the-product-stores-and-what-it-only-reads) was corrected |
| **C3** | the pages could read jobs with the user's token | `jobs` is **not** a grantable `user_api_scopes` value, and the code already says so at `tools/…:1031` | reads go through the **service principal**, writes through the tool server. `[RB-1]`, `[RB-2]` |
| **C4** | `dbx_create_job` already created a paused schedule, so `[JOB-4]` was documentation | it does (`:1092`), but it returns `"created PAUSED"` as a **string** — unparseable by the page | the return becomes `{"schedule": {cron, timezone, pauseStatus}}`. Phase 1.2 |
| **C5** | adding `DocKind` members would produce compile errors in ~6 places | `Record<DocKind, …>` appears in **two** files (`App.tsx:77`, `docs.ts:154`); the rest are `if` chains and a union in `route.ts:20`, `recent.ts:14` | the plan adds a **test** that every kind has a group, a route and an actions entry, because the compiler does not name them all. `[UI-1]` |
| **C6** | the E2E harness served `web/dist` from a build I would run | it does, and `lakebase-e2e.mjs` carries the note that a stale bundle photographs the previous build | `npm run build` is a **required step** in [11](11-e2e-plan.md), stated with its cost |

C3 and C1 are the ones that change the architecture. C5 is the one that would have produced a page that
compiles and is unreachable.

---

## A · The tool server

| Claim | File:line | Verdict |
|---|---|---|
| `dbx_create_job` uses `/api/2.1/jobs/create` | `tools/databricks_notebook_mcp.py:1094` | ✓ `F1` |
| it creates the schedule `PAUSED` | `:1092` | ✓, but see C4 |
| it does not validate the task graph | `:1082-1090` | ✓ `F3` |
| `dbx_run_job` sends `{"job_id": …}` with no idempotency token | `:1107` | ✓ `F2` |
| `dbx_run_job` re-reads the job and re-checks the prefix | `:1105-1106` | ✓ this is the pattern `[TOOL-4]` generalises |
| `dbx_list_jobs` returns no run state despite its docstring | `:861-873` | ✓ `F6` |
| `dbx_list_pipelines` reads the pipeline's `state`, not an update's | `:1126-1128` | ✓ `F5` |
| there is exactly one pipeline tool and it is a read | `:1121-1129` | ✓ `F4` |
| `_retry` does not retry a POST except 429/503 | `:276-296` | ✓, and it is why `[TOOL-5]` is needed at the *operation* level |
| `_sp_token()` falls back to the user token on a laptop | `:110-126` | ✓ `[E-15]` |
| `_refuse_response` names the identity in a 403 | `tools/databricks_notebook_mcp.py:172-205` | ✓ reusable for the job path |
| `_CORE` is a hand-maintained set of 25 and `dbx_list_jobs` is **not** in it | `tools/databricks_notebook_mcp.py:75-87` (measured: 25 entries) | ✓ `F6`, `[TOOL-1]` |
| the server is started with `NBMCP_PROFILE=core` | `api/adapters/mcp/registry.py:55` | ✓ C1 |
| the fence prefixes come from `Scope.for_session` | `registry.py:60-67`, `api/domain/scope.py:44-59` | ✓ `[TOOL-4]` |
| the tool server cannot import `api.domain` | `registry.py:73-83` (a subprocess, `python3 tools/…`) | ✓ `[RB-5]`, and it is why `job_graph.py` is a module |
| `dbx_run_notebook` falls back to running as the app on a `403` | `:1029-1036` | ✓ the pattern `[RB-1]` extends to jobs |

## B · The app

| Claim | File:line | Verdict |
|---|---|---|
| `_dbx_errors` maps 403/404/422/409/502 | `api/routers/api.py:498-512` | ✓ reused, not re-implemented |
| `infra.py` uses the SP token for reads | `api/routers/infra.py:24-46` | ✓ `[RB-1]`'s precedent |
| `app.state.lakebase` / `.apps` are wired in `build()` | `api/main.py:167-175` | ✓ two more lines, as `[07 §5]` says |
| `DbxHttp` maps 401/403 to `PermissionError` and distinguishes a missing scope | `api/adapters/databricks/http.py:47-97` | ✓ |
| `LakebaseBrowser` keys its cache by token | `api/adapters/databricks/lakebase.py:25-48` | ✓ reused for the three new caches |
| `page_blocks` runs independent reads and captures per-key errors | `lakebase.py` (`page_blocks`), `infra.py:113-122` | ✓ the job/pipeline page copies the shape |
| a session's `scope` is on the session detail | `api/routers/api.py:231` | ✓ the ledger's session id is available without a new route |
| there is **no** write route for infrastructure today | `api/routers/infra.py` — five GETs and one POST that only clears a cache | ✓ `[07 §5]`'s "browser has no write route" is already true |

## C · The front end

| Claim | File:line | Verdict |
|---|---|---|
| `DocKind` is a five-member union | `web/src/domain/docs.ts:8` | ✓ `F7` |
| `Record<DocKind, …>` in exactly two places | `App.tsx:77`, `docs.ts:154` | ✓ **C5** — the compiler does not name every site |
| `touched()` is two hand-written branches then a path regex | `docs.ts:93-112` | ✓ `F8` |
| the route grammar is a head-and-rest parser with a legacy branch | `route.ts:47-80` | ✓ three more heads |
| `makeDoc` handles a kind-specific key | `docs.ts:36-57` | ✓ three more cases |
| `recent.ts` has a kind union and a name rule | `recent.ts:14`, `:34`, `:67` | ✓ two more cases each |
| the dock has a per-kind suggestion branch | `dock.ts:72-121` | ✓ three more, and `[E-22]` guards the fallthrough |
| `DataTree` has two `useState` + two `useEffect` + two renderers | `DataTree.tsx:24-49`, `:69-97` | ✓ `F9` |
| `errorBoxes()` collapses identical failures | `DataTree.tsx:136-148` | ✓ `[E-23]` keeps it for four groups |
| `Block` / `Fact` / `StatePill` / `isPermanent` exist and are used by two pages | `components/Infra.tsx` | ✓ reused unchanged |
| `App.tsx` switches on `viewDoc.kind` for a page | `App.tsx:1009-1013` | ✓ three more arms |
| `KIND_GROUP` is a `Record<DocKind, string>` | `App.tsx:77-79` | ✓ |
| `⌘4` opens the Data panel | `keys.ts:127` | ✓ label changes; the chord does not |
| `modeFor` puts mid at ≤ 1180 and narrow at ≤ 820 | `layout.ts:103-105` | ✓ `[S8]`'s threshold, and 013's S7 correction |
| the centre's minimum is 480 px | `layout.ts:41` | ✓ F8's frame |
| `LakebasePage` is keyed by `doc.id` to avoid a cross-document race | `App.tsx:1009-1010` | ✓ and `useResource` adds a cancel for the same-document re-poll case |

## D · The contract between the two

| Claim | Where | Verdict |
|---|---|---|
| event vocabulary is held by a JSON fixture | `tests/test_event_parity.py`, `web/src/domain/event-parity.json` | ✓ the model for `jobs-table.json` |
| the fence is held to one table across two runtimes | `tests/test_fence_parity.py` | ✓ the model for the graph validation |
| the scaffold's steps live in one JSON both runtimes read | `web/src/domain/scaffold-steps.json`, `api/domain/scaffold.py:23` | ✓ and this spec adds **no** step to it |
| a step is `done` only on a proof field | `scaffold.py::_proved`, `scaffold.ts::proved` | ✓ a job-creating flow can use `job_id` as one |
| `test_deployment_envs.py` holds the scope list in three places | `tests/test_deployment_envs.py:33-40` | ⚠ **a new scope is not needed** — `jobs` cannot be requested. If it ever can, this test is the first thing that fails, which is correct |

## E · The environment

| Claim | Check | Verdict |
|---|---|---|
| Python tests pass on the current tree | `pytest -q -n 4` → **797 passed, 7 skipped** | ✓ baseline |
| front-end tests pass | `vitest run` → **749 passed, 64 files** | ✓ baseline |
| the ASCII verifier passes on 013 | `verify-spec-ascii.mjs ../../../specs/013-improve-coding` → **0 problems** | ✓ and it passes on this spec's `04` |
| the mermaid verifier parses 013's diagrams | 10/10 on this spec's `05` | ✓ |
| the link verifier is the gate for this folder | 43 internal links, 0 missing after `12` is written | ✓ |

The two baselines matter for a different reason: **the plan adds tests to an existing suite that is
entirely green.** A phase whose gate fails is therefore unambiguous — there is no pre-existing red to
hide behind.

---

## What the coherence check found that the plan had missed

Three additions, each now a numbered requirement or edge case rather than a note:

1. **`[E-26]`** — a model can lie about a run, and no tool fixes that. The mitigation is the *object* on
   screen; the check forced the spec to say so plainly instead of implying the tools prevent it.
2. **`[E-28]`** — a tool that leaves `core` becomes undiscoverable unless a skill names it. C1's
   arithmetic removed three tools; without this case the removal would have been silent.
3. **`[RB-3]`** — the ledger cannot be a table, because the reader has no database credential. This is
   C2, and it changed both `[TOOL-6]`'s mechanism and one diagram.

And one that was too pessimistic and is now **not** in the plan:

* the spec first assumed the *pages* would need a write route (a direct `POST /api/jobs/{id}/run`). The
  code shows there is no write route for infrastructure today, and `[07 §5]`'s argument — one fence, one
  process — is stronger than the ~1 s the direct call would save. So the pages have **no** POST, and
  `test_infra_routes.py` asserts it structurally, which is the version of that decision that survives a
  future contributor with a good reason.

---

## The one thing that cannot be checked from here

Whether a live workspace's Jobs 2.2 payload matches the field names the documentation lists. The fixtures
are built from the documentation and from 013's measured shapes for adjacent APIs. [11](11-e2e-plan.md)
records this as a required manual check against a real workspace, and [12](12-outcome.md) records what it
found.

Everything else in this document set was read out of this checkout.
