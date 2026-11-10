[Index](README.md) · prev: [08 Implementation plan](08-implementation-plan.md) · next: [10 Roadblocks](10-roadblocks.md)

# 09 · Edge cases

Every failure I could name, the mitigation, and the test that holds it. An `[E-*]` cited from a
requirement is defined here and nowhere else.

Format: **Trigger** (what makes it happen) · **Behaviour** (what the user or the agent gets) · **Test**
(the name that fails when the mitigation is removed).

---

## A · The workspace refuses, or is not configured

### `[E-1]` · The Lakebase API returns 403 with no `CAN MANAGE`

**Trigger.** The user can read a project but not create one; or can create a project but not a branch.
**Behaviour.** The tool returns the platform's sentence plus one line naming who can grant it. The page
renders it in the block that failed. **No retry button** — a `CAN MANAGE` grant does not appear between
two clicks.
**Test.** `test_lakebase_adapter.py::test_a_403_names_the_capability_and_offers_no_retry`, asserting the
message contains `CAN MANAGE` and that `client.post` was called exactly once.

### `[E-2]` · The user's token lacks a Lakebase scope

**Trigger.** The app was granted `sql` and `files` but not `postgres`, so every call returns
*"Provided OAuth token does not have required scopes: postgres"*.
**Behaviour.** `ScopeMissing` (already in `adapters/databricks/http.py`) is raised, and its message says
**this is an app setting, not your access**, names the scope, and offers "sign in again" as the action.
This is the single most expensive confusion in the category: the user asks the wrong person.
**Test.** `test_a_missing_scope_is_told_apart_from_a_denied_acl` — the same status code, two different
sentences.

### `[E-3]` · The workspace refuses to create an app without a Git repository

**Trigger.** Measured on `dbc-cb61f1e1-bd8e`: `apps create` refuses a workspace-path source and requires
`git_repository`.
**Behaviour.** `dbx_create_app` returns `{"created": false, "platform_error": "<verbatim>"}` and the
agent is instructed not to retry. The UI shows the refusal with one action: *Copy the error*. The
remedy sentence names the git path.
**Test.** `test_apps_adapter.py::test_a_git_only_refusal_is_reported_verbatim_and_not_retried`.

### `[E-4]` · The user may use Lakebase but not create projects

**Trigger.** `GET /projects` succeeds and `POST /projects` returns 403.
**Behaviour.** The Data tab lists what exists and offers no *New project* control — the control is
rendered only when a create has not been refused in this session. A refusal is not a design goal, but
offering a button that always fails is.
**Test.** `DataTree.test.tsx::test_the_new_control_is_absent_after_a_create_refusal`.

---

## B · The fence

### `[E-5]` · The agent tries to create an app outside the session prefix

**Trigger.** The model picks a name a user would pick: `tickets-app`.
**Behaviour.** `PermissionError("write blocked: app name must start with 'agent-4ff4405d-' (got
'tickets-app')")`. The approval panel is **not** offered: an approval cannot widen a prefix, so
presenting one would be a lie about what can be granted. The agent is told not to choose another name.
**Test.** `test_tools_fence.py::test_an_app_outside_the_prefix_is_refused_with_the_prefix_in_the_message`
and `::test_no_approval_is_offered_for_a_prefix_refusal`.

### `[E-6]` · The instance prefix and the app prefix are the same string

**Trigger.** Today. The check passes for the wrong reason.
**Behaviour.** Phase 1.4 makes them separate variables; the test uses *different* values so a regression
to one variable fails.
**Test.** `test_tools_fence.py::test_the_two_prefixes_are_checked_separately` — the test that would have
caught `[F3]`.

### `[E-7]` · A name that is valid for us and invalid for the platform

**Trigger.** A Lakebase project id is `[a-z][a-z0-9-]*`, ≤ 63 chars. A model produces
`My_Tickets_DB`.
**Behaviour.** Local validation refuses **before the call**, with the pattern quoted, and the model is
told the transformation (`lowercase, hyphens, start with a letter`) rather than "invalid name".
**Test.** `test_lakebase_tools.py::test_an_invalid_project_id_is_refused_locally` — asserts **zero** HTTP
calls.

---

## C · The scaffold

### `[E-8]` · A step blocks; later steps must not run

**Trigger.** The table step fails (a permission on the schema, a bad column, a timeout).
**Behaviour.** Steps 1–2 stay `done` with their proofs, step 3 is `blocked` with the reason, steps 4–7
are `pending`. **No app is created.** The dock shows `blocked`, and the centre shows the step list with
the failing step expanded.
**Test.** `test_scaffold.py::test_a_blocked_step_stops_the_chain` plus a scripted scenario asserting zero
`POST /api/2.0/apps` calls.

### `[E-9]` · A step is reported `completed` but returned no proof

**Trigger.** A tool returns `{"ok": true}` for a create, or the mapper drops the payload.
**Behaviour.** The step stays `pending`, with a note *"the call completed but returned nothing this step
can check"*. A `completed` status is not a proof; the **proof field** is.
**Test.** `test_scaffold.py::test_a_completed_call_without_the_proof_field_does_not_prove_the_step`.

### `[E-10]` · The same step is proved twice

**Trigger.** The agent retries a create after a transient 5xx and both calls complete.
**Behaviour.** The step takes the **last** successful proof; duplicates do not create duplicate rows. The
plan shows one line per step, always.
**Test.** `test_scaffold.py::test_a_repeated_proof_keeps_one_row_and_the_latest_value`, and the
front-end's `stepsFrom` has the same case.

### `[E-11]` · Every read on the project page fails

**Trigger.** The Postgres API is down, or every token scope is missing.
**Behaviour.** Four blocks show four errors (or one shared `PaneError` if they are identical), the tab
stays open, the URL is still valid, and **the composer still sends** — the conversation does not depend
on the page.
**Test.** `LakebasePage.test.tsx::test_a_total_read_failure_leaves_the_shell_working`.

---

## D · The app, once it exists

### `[E-12]` · The app is created and never reaches `RUNNING`

**Trigger.** A build failure in `requirements.txt`, a missing `app.yaml`, a crash at import.
**Behaviour.** `dbx_create_app` returns after ~90 s with `{"created": true, "verified": false, "state":
"DEPLOYING", "next": "read the logs at https://…/logz"}`. It does **not** claim success. The App page
shows `DEPLOYING` with the `/logz` link and the elapsed time.
**Test.** `test_apps_adapter.py::test_a_deployment_that_never_runs_returns_verified_false`.

### `[E-13]` · The app answers 500

**Trigger.** The scaffolded app's own bug — the most likely outcome of code a model wrote.
**Behaviour.** Health is `failing` with the status code; the page offers *Ask the agent to fix it*, which
sends a prompt **containing the status code and the first log line**. That is the workflow the whole card
implies and that no current surface can express.
**Test.** `AppPage.test.tsx::test_a_failing_app_offers_the_logs_and_a_fix_prompt`.

### `[E-14]` · The app scaled to zero and the first request is slow

**Trigger.** The platform's idle policy (24 h default, or a shorter one the user set).
**Behaviour.** `starting`, not `down`. The health check retries the GET once at 3 s and reports
`starting` with the elapsed time. The page says *"cold start: the app was idle"*.
**Test.** `test_apps_adapter.py::test_a_slow_first_response_is_starting_not_down`.

### `[E-15]` · The app's Postgres resource points at a branch that was deleted

**Trigger.** The user deletes the branch after the app was created.
**Behaviour.** The App page's resources block shows the resource with a warning, and a health check is
`failing`. The agent is not asked to guess: the block names the missing branch.
**Test.** `AppPage.test.tsx::test_a_resource_pointing_at_a_missing_branch_is_marked`.

---

## E · Data and SQL

### `[E-16]` · A SQL call runs on `production` because the branch was omitted

**Trigger.** A model drops the `branch` argument.
**Behaviour.** The default is `production` **only for a read**; a statement classified as a write
defaults to **refusing** with *"a write must name a branch other than production"*. This is the one place
the product overrides a default, and it does so because the cost of being wrong is the user's live data.
**Test.** `test_lakebase_tools.py::test_a_write_without_a_branch_is_refused` — asserts no credential was
minted, so no connection was opened.

### `[E-17]` · A credential expires mid-batch

**Trigger.** A batch longer than the token's remaining life (≤ 60 min, usually much less).
**Behaviour.** The connection is opened per call, not per batch; a long batch is the user's choice and
gets the driver's error, mapped to *"the credential expired; call again"*. No silent retry, because a
retried `INSERT` is a duplicate.
**Test.** `test_lakebase_tools.py::test_an_expired_credential_says_so_and_does_not_retry_a_write`.

### `[E-18]` · A row count is expensive

**Trigger.** A table with 40 million rows.
**Behaviour.** The count is `LIMIT`-bounded in time (a statement timeout) and the page shows `≥ 1,000` when
it times out, with a note. It never shows `0` for "could not count".
**Test.** `test_lakebase_tools.py::test_a_timeout_reports_a_lower_bound_not_zero`.

### `[E-19]` · The database name contains a quote or a semicolon

**Trigger.** A model passes `databricks_postgres"; DROP DATABASE x; --`.
**Behaviour.** Identifiers are validated against `^[A-Za-z_][\w$]*$` before any connection string is
built. A refusal, not an escape: an identifier that needs escaping is not an identifier.
**Test.** `test_lakebase_tools.py::test_an_identifier_with_a_quote_or_semicolon_is_refused`.

---

## F · The UI

### `[E-20]` · A deep link to an object that does not exist

**Trigger.** A pasted link to a deleted project, or a typo.
**Behaviour.** The route parses (it is well formed), the page loads, the read returns 404, and the block
says *"this project does not exist, or you cannot see it"* with the Data tab as the action. Never a
blank page, never a router error.
**Test.** `route.test.ts` (it parses), `LakebasePage.test.tsx::test_a_404_is_a_state_not_a_crash`.

### `[E-21]` · A malformed hash

**Trigger.** `#/lakebase/`, `#/app/`, `#/lakebase//branches/`.
**Behaviour.** `EMPTY_ROUTE`, the start screen. The existing parser contract, extended to the new kinds.
**Test.** `route.test.ts::test_a_malformed_infra_hash_opens_the_app`.

### `[E-22]` · A project id with a character that must be encoded

**Trigger.** A project id cannot contain `/`, but a branch ref can contain nested segments, and a user
can paste a full path.
**Behaviour.** `formatRoute` encodes per segment (as it already does for notebook paths) and `parseRoute`
decodes per segment. `projects/pg_tickets/branches/agent-4ff4405d` survives a round trip.
**Test.** `route.test.ts::test_a_branch_ref_round_trips`.

### `[E-23]` · The fourth rail tab at 900 px

**Trigger.** The narrow layout, where the rail is a drawer.
**Behaviour.** `⌘4` opens the drawer on the Data tab — the same behaviour `⌘1..3` already have — and
Escape closes it ([012]'s precedence). The tab strip does not wrap: four tabs at 276 px is 4 × 60 + gaps,
which fits; at 200 px (the rail minimum) the labels shorten to their first three characters' worth of
width via the existing `.rail-tab` rules.
**Test.** `layout.test.ts` (the tab count is data), and S7 in the E2E suite at 900 px.

### `[E-24]` · Two tabs for one object

**Trigger.** A project opened from the rail and from a tool row, with `pg_tickets` and
`projects/pg_tickets`.
**Behaviour.** One tab, because `makeDoc` normalises through `project_ref` ([LB-5]). This is the exact
defect `canonicalPath` fixed for notebooks, and the test is the same shape.
**Test.** `domain/docs.test.ts::test_two_spellings_of_a_project_make_one_doc`.

### `[E-25]` · The composer is used while a project page is open

**Trigger.** The user types a question about the project.
**Behaviour.** The project rides along as the binding — `in context: pg_tickets` — and the message's
attachment is the project's **ref**, which the server resolves to a fenced block. `[012]`'s rule holds:
the composer is never disabled by a page's loading state.
**Test.** `LakebasePage`/`AssistantDock` integration: a page whose blocks are loading does not block
sending.

---

## G · Operations

### `[E-26]` · The tool server starts but the SDK is absent

**Trigger.** A deployment whose `requirements.txt` lost `psycopg`.
**Behaviour.** The server starts (the import is inside the function), and the first SQL call returns
*"this tool server is missing its Postgres client; this is a deployment problem"* — a sentence, not a
traceback. `[F1]`'s permanent mitigation is the widened packaging guard; this is the runtime backstop.
**Test.** `test_lakebase_tools.py::test_a_missing_client_is_a_sentence_not_a_traceback`.

### `[E-27]` · The cache serves a deleted object

**Trigger.** A project deleted in the Databricks UI, within the 60 s TTL.
**Behaviour.** The page shows it for up to 60 s, then a 404. Acceptable, and stated: the TTL is the
staleness bound. A manual refresh bypasses the cache.
**Test.** `test_object_cache.py::test_a_delete_is_visible_after_the_ttl_and_on_refresh`.

### `[E-28]` · Two users, two tokens, one process

**Trigger.** A shared app instance.
**Behaviour.** No cache entry is shared across tokens. This is the bug `CatalogBrowser` already fixed
(`_walks` keyed by credential); `ObjectCache` keys on a hash of the token's identity, and the test is the
same shape as `test_the_table_name_cache_is_per_credential`.
**Test.** `test_object_cache.py::test_two_tokens_do_not_share_an_entry`.

---

## The table a reviewer should read

| Id | Severity if unhandled | Mitigated in | Test exists |
|---|---|---|---|
| `[E-1]` `CAN MANAGE` | user asks the wrong person | adapter + page | yes |
| `[E-2]` missing scope | user asks the wrong person | existing `ScopeMissing` | yes |
| `[E-3]` git-only workspace | agent retries 3× | tool instruction | yes |
| `[E-5]` prefix refusal | an approval that cannot help | tool | yes |
| `[E-6]` shared prefix | fence silently wrong | phase 1.4 | yes |
| `[E-8]` chain not stopped | an app over a missing table | scaffold | yes |
| `[E-9]` false proof | a ✓ with nothing behind it | scaffold | yes |
| `[E-12]` never runs | "deployed" for a broken app | tool + page | yes |
| `[E-14]` cold start | "down" for a healthy app | health states | yes |
| `[E-16]` write on production | **the user's live data** | tool refusal | yes |
| `[E-24]` two tabs | two views of one object | `project_ref` | yes |
| `[E-28]` shared cache | one user's object list to another | cache key | yes |

`[E-16]` is the only one whose cost is data rather than confusion, and it is the one place the design
overrides a platform default rather than passing it through.
