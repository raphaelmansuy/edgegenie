[Index](README.md) · prev: [09 Edge cases](09-edge-cases.md) · next: [11 E2E plan](11-e2e-plan.md)

# 10 · Roadblocks

What is actually in the way, what says so, and what the way past it costs. A roadblock here earns its
place only if it is **grounded**: a line of code, a vendor constraint, or a measurement. Anything that
could be fixed by writing the code is not a roadblock — it is work, and it is in
[08](08-implementation-plan.md).

Each entry: **the obstacle** · **the evidence** · **what it costs us** · **the way past** · **what is
left undone after we take it**.

---

## `[RB-1]` · The app cannot grant itself permission

**The obstacle.** A Lakebase project needs `CAN MANAGE` to create a branch, a database or a role. A
Databricks App acts as **the signed-in user** (this app's own design: `user_api_scopes`, the forwarded
token), and that user's `CAN MANAGE` is the ceiling. If they lack it, nothing the app does can obtain it.

**The evidence.**

```yaml
# databricks.yml:48-54 — this app's scopes, and every call it makes is on the user's token
      user_api_scopes:
        - sql
        - files
        - model-serving
```

```21:22:apps/coding-agent/tools/databricks_notebook_mcp.py
* Auth: ``DATABRICKS_HOST`` + ``DATABRICKS_TOKEN`` (PAT) or OAuth via the CLI.
```

The docs are explicit: *"You must have `CAN MANAGE` permission on the Lakebase project to add it as an
app resource"* and *"the app acts with the identity of the user who signs in to it ... only within the
scopes that the App Space allows."*

**What it costs us.** A first-time user in a shared workspace can be told *"create me a database"* and
receive `PERMISSION_DENIED`. No amount of engineering in this app changes that.

**The way past.** Three parts, none of which is a workaround:

1. **Report it as a state with an owner**, which is `[E-1]`: the platform's sentence, then *"ask the
   project's owner, or choose a project you own"*.
2. **Offer the projects the user can use.** `GET /projects` returns what they can see, and the page's
   *New project* control is rendered only when they can create one (`[E-4]`). Listing an action that
   always fails is the bug, not the refusal.
3. **Name the requirement before the attempt**, in the skill the agent reads, so the agent asks for the
   right thing on the first turn rather than discovering the wall at step 4.

**Left undone.** A user with read-only access on every project cannot use this workflow. That is correct:
it is a governance boundary, not a product gap. What they *can* do is open and inspect every project and
app they can see, which phase 3 delivers to the same account.

---

## `[RB-2]` · The app cannot create its own scopes

**The obstacle.** The app's `user_api_scopes` are declared at deploy time. A workspace that has never
granted `postgres` will refuse every Lakebase management call, and the app cannot add the scope to itself
— adding a scope is an `apps update` by an owner.

**The evidence.** The scope list is in `databricks.yml` (above) and is applied by `make deploy`. The
platform's own words in `adapters/databricks/http.py::ScopeMissing` exist for exactly this:

```python
        super().__init__(
            f"this app has not been granted the permission it needs{what}. This is an app setting, "
            "not your access. …")
```

**What it costs us.** The *first* deployment of a new feature can fail with a scope error even on a
workspace where the user is an admin.

**The way past.**

1. **Add `postgres` and `apps` to the declared scopes in this change.** The list in `databricks.yml`
   gains two entries; `make deploy` applies them; `make verify` probes the two new routes.
2. **Make the failure self-describing.** `ScopeMissing` already distinguishes "app mis-configured" from
   "you lack access". The new routes inherit it by using `DbxHttp` — no new code, and that inheritance
   is why the adapter is not written directly on `httpx`.
3. **Probe it at boot.** `/api/ready` gains one line per new capability, so a deploy that forgot the
   scope is visible in `make verify` rather than at the first user request.

**Left undone.** A workspace whose admin will not grant `postgres` gets a read-only Data tab. Acceptable
and stated.

---

## `[RB-3]` · The app cannot deploy an app from a Git repository it does not own

**The obstacle.** Two distinct walls, both measured in this repository:

1. Some workspaces **require** a Git repository to create an App at all (measured on
   `dbc-cb61f1e1-bd8e`, recorded in `app.create.json`).
2. Even where a workspace path is allowed, giving an app's **service principal** read access to a private
   repository needs a personal access token *owned by the caller*
   (`caller_credential_id` on `git_repository`) — a credential the app has no way to obtain on a user's
   behalf.

**The evidence.**

```1:12:apps/coding-agent/app.create.json
  "git_repository": {
    "url": "https://github.com/raphaelmansuy/opengenie",
    "provider": "gitHub"
  }
```

and the comment above it: *"The `git_repository` is required on a workspace that deploys apps from git
only (measured on `dbc-cb61f1e1-bd8e`: `apps create` refuses without it, and `apps deploy` refuses a
Workspace path)."*

**What it costs us.** On a git-only workspace the scaffold's step 6 produces a platform refusal, and the
card's promise cannot be completed by the agent alone.

**The way past.**

1. **Ask for the Git source as an optional argument** (`[AP-1]`). A user who has a repository passes
   `git_repository: {url, provider}` and the call works.
2. **Report the refusal verbatim, and never retry** (`[E-3]`). The agent is instructed: *"do not retry;
   report the `platform_error` verbatim and tell the user to deploy from git"*. A model that retries
   three times shows the user three identical walls.
3. **Verify the workspace capability before the attempt.** `dbx_create_app` reads the workspace's app
   settings once and, when a Git repository is required and none was supplied, refuses locally with the
   remedy — one call instead of a failed create that leaves nothing behind.
4. **Make the Workspace-path path work where it is allowed.** On a workspace that accepts a folder
   source (the `prod` target in `databricks.yml`), the scaffold writes the files with `dbx_write_file`
   and passes `source_code_path`. That is the common case and it does not need Git at all.

**Left undone.** A user on a git-only workspace with no repository gets the refusal and a documented
manual path. The alternative — creating a repository on the user's behalf — needs a Git credential the
app must not hold.

---

## `[RB-4]` · An app's Postgres role is created by the platform, not by us

**The obstacle.** The plan's first draft had a `create-role` step for the app's service principal. That
would have created a role keyed to *our* chosen name, while the platform creates a role keyed to the
service principal's client id when the `postgres` resource is attached:

> *"Databricks creates a PostgreSQL role in the selected database. The role name matches the service
> principal's client ID. … Databricks grants the service principal `CONNECT` and `CREATE`."*

**The evidence.** The vendor's app-resource contract, and this repository's own provisioning script,
which has to do it **by hand** for itself because it does not declare the resource:

```bash
# scripts/provision-lakebase.sh — needed because the app is created without a postgres resource
databricks postgres create-role "projects/${P}/branches/${B}" \
  --role-id "${APP_NAME}-sp" --replace-existing \
  --json "{\"spec\":{\"identity_type\":\"SERVICE_PRINCIPAL\",\"postgres_role\":\"${APP_SP}\",…}}"
```

**What it costs us.** A scaffold that creates a role itself produces an object the app cannot use, or a
duplicate of one the platform would have made.

**The way past.** Invert step 4: **declare the resource, then read the role back.** `dbx_create_app`
sends the `postgres` resource; the platform creates the role; `dbx_lakebase_role` (a read) asserts the
role exists for the app's service principal. That is still a proof (`[SCF-1]`), and it is a proof of the
object that actually works.

For **this** app's own deployment, the manual `provision-lakebase.sh` path stays, and the reason is
documented in the script already: the app's role must exist before the app starts, so it cannot be
created by an app that is not running.

**Left undone.** Two provisioning paths coexist: declarative for apps the agent creates, imperative for
this app itself. That is a real asymmetry, named rather than hidden, because the bootstrap case is
genuinely different from the managed case.

---

## `[RB-5]` · The fence cannot be shared code

**The obstacle.** The tool server runs as a **separate process** and cannot import `api.domain.scope`.
So the fence's rule exists twice, and `[F4]` found that three of its five functions have no caller at
all.

**The evidence.**

```python
# api/adapters/mcp/registry.py:68-73 — a new interpreter, the server file as argv
        proc = await asyncio.create_subprocess_exec(
            self._python, str(self._server), env=env, …)
```

`_find_server()` deliberately walks **up** from its own file so a deployment (which ships only the app
folder) can find the server. A shared package would invert that dependency: the server would need the
app's tree to start, and the comment in the file says why that matters first.

**What it costs us.** Two implementations of one rule is a drift risk, and a rule with no caller is a
false claim in a docstring.

**The way past.**

1. **Share the values, not the code.** `Scope.for_session` produces five strings; the registry passes all
   five as environment; the tool server reads them. One producer, two consumers, no import.
2. **Hold the two implementations to one table.** `tests/test_fence_parity.py` lists 20
   `(kind, name, prefix, expected)` rows and asserts `check_*` in `api/domain/scope.py` and
   `_check_prefix` in the tool server agree on every one. A drift fails the test, and the table is the
   single definition of the rule.
3. **Delete the functions that cannot be shared and are not used.** `check_job` and `check_instance`
   lose their only purpose if the tool server owns enforcement; either they gain a real caller (they do,
   as the table above) or they go. The plan keeps them **and** tests them against the table, so
   "the fence covers jobs and instances" becomes true rather than aspirational.

**Left undone.** Two files must be edited when a fifth kind of target is added. The parity table is the
compensation, and it is a better one than a shared import, because it can be read by a person.

---

## `[RB-6]` · The old Lakebase API still answers, with the old shape

**The obstacle.** The most dangerous roadblock in this list, because it does not fail. Since 2026-03-12
`POST /api/2.0/database/instances` creates an Autoscaling project, and reads keep returning
`read_write_dns`, `capacity`, `state: AVAILABLE` — fields of an object model the platform has migrated
away from. So a tool built on the old API *appears* to work.

**The evidence.**

| Source | Says |
|---|---|
| the Database Instance reference | *"For new workloads, Databricks recommends the Postgres API equivalent: Create a project."* |
| the upgrade guide | *"Since March 12, 2026, new Lakebase instances are created as Autoscaling projects"*; the upgrade of all Provisioned instances *"completed in July 2026"* |
| this repository | the tool server uses the old API (`tools/…:999-1032`); the scripts use the new one (`scripts/provision-lakebase.sh`) |

**What it costs us.** Silent, plausible, wrong output — worse than an exception. A host is reported that
resolves to nothing, and no branch or role exists to connect with.

**The way past.**

1. **Rewrite on `/api/2.0/postgres`** (`[LB-1]`), and assert the old field names appear nowhere:
   ```python
   for forbidden in ("read_write_dns", "instance_names", "/database/instances"):
       assert forbidden not in Path("api/adapters/databricks/lakebase.py").read_text()
   ```
   A test that greps the source is crude and exactly right here: the defect is a *vocabulary*, and the
   cheapest way to hold a vocabulary is to forbid the words.
2. **One vocabulary, checked across the repository.** The same test walks `tools/` and `scripts/` and
   fails if a *new* file uses the old vocabulary. Existing legacy reads (none, after this change) would
   be listed explicitly.
3. **Probe the new shape once, live.** The E2E plan's `[S2]` runs against a real project when a
   `DATABRICKS_HOST` is present, and skips with a printed reason when not — so the local suite stays
   hermetic and the deployed check is real.

**Left undone.** An *existing* Provisioned instance (pre-upgrade) may still need the old read path. The
adapter reads only the new one; a workspace whose project is old enough to be Provisioned-only gets a
refusal with the upgrade guide's link. Accepted: the upgrade completed in July 2026.

---

## `[RB-7]` · A cold Lakebase compute and a cold app both look like failures

**The obstacle.** Two different cold starts, both in the request path:

- a Lakebase compute suspended by scale-to-zero: the first connection waits for a resume;
- an app scaled to zero: the first HTTP request waits for a start.

Both exceed a naive timeout, and both are *normal*. Reporting either as "broken" is a false alarm that
teaches users to distrust the page.

**The evidence.** Scale-to-zero is on by default with a 24-hour inactivity timeout, and *"State in memory
or on local disk is lost when the app scales down"*. `api/main.py` already knows the Lakebase half:

```270:274:apps/coding-agent/api/main.py
    """Bring the registry onto the database, retrying until it is reachable.

    A Lakebase compute that was suspended takes a few seconds to wake, and a network that is not up
    at boot is not a reason to serve the seed for the life of the process.
    """
```

**What it costs us.** A health check that says `down` for a healthy app, and a project page that says
"unreachable" for a database that is merely asleep.

**The way past.**

1. **Two timeouts, not one.** 3 s → `running`; 15 s → `starting`; > 15 s → `unresponsive` (`[E-14]`).
   The middle state exists precisely so the honest answer ("it is waking") has a word.
2. **The Postgres connection gets `connect_timeout=20`**, and the error message names the cause: *"the
   compute is suspended; a connection resumes it"* rather than a bare driver timeout.
3. **The page distinguishes "no answer yet" from "an error".** A skeleton with a status is not an error
   block; `[UI-3]`/`[UI-4]` render them differently, and the test asserts a cold start shows a skeleton,
   never a red block.

**Left undone.** A user on a slow network will see `starting` for a genuinely fast app. The state word is
honest; the alternative (a shorter timeout) is a false `down`.

---

## `[RB-8]` · The tool surface is a context-window budget

**The obstacle.** Every MCP tool is advertised on **every** request. The measured result in this
repository is that a weak model degrades as the surface grows, and the `core` profile exists for that
reason. Six new tools is a real cost paid by every turn, including turns that have nothing to do with
Lakebase.

**The evidence.**

```71:81:apps/coding-agent/tools/databricks_notebook_mcp.py
# Tool profile. A coding agent advertises every MCP tool on every request, so
# fewer, better tools beat many. `core` registers the ~20 tools the exam suite
# showed are actually needed; `full` also registers the rarely-used lookups.
```

**What it costs us.** If the five new tools are added to `core`, every conversation pays for them.

**The way past.**

1. **Five tools, not seven** ([06 §7.1](06-lenses.md#7-ai-engineer)): `branch`, `database` and `role`
   are one tool with a `kind` argument where the bodies are the same shape, and `app_health` is small
   enough to earn its place because it is the scaffold's proof.
2. **`role` stays a read.** `[RB-4]` removed the create, so the tool is `dbx_lakebase_role` (a list) and
   not a mutator.
3. **A profile, not a fork.** The five join `core`; the rarely-used lookups (`lakebase_list`,
   `lakebase_compute`) join `full`. The count is asserted (`test_the_core_profile_has_25_tools`), so a
   future addition is a deliberate decision rather than a drift.
4. **Progressive disclosure for the rest.** `dbx_skill` already lets the agent read a playbook on demand;
   the Lakebase skill gains the exact call sequence, so the *parameters* do not need to be in the tool
   descriptions.

**Left undone.** A turn about notebooks now pays for five tools it does not use. Measured against the
alternative — an agent that cannot create a database — the trade is clear, and the profile mechanism
means it is reversible.

---

## `[RB-9]` · Two artefacts, one of which ships

**The obstacle.** `mcp/databricks_notebook_mcp.py` and `apps/coding-agent/tools/…` have diverged (987 vs
1104 lines); the skills are byte-identical duplicates; the deployed app reads the `tools/` copy. A fix
applied to the wrong one reaches nobody.

**The evidence.**

```text
$ wc -l mcp/databricks_notebook_mcp.py apps/coding-agent/tools/databricks_notebook_mcp.py
  987 mcp/databricks_notebook_mcp.py
 1104 apps/coding-agent/tools/databricks_notebook_mcp.py
```

and `registry._find_server()` prefers `tools/`.

**What it costs us.** Any future tool fix can silently miss production. This is the roadblock with the
worst multiplier: it is a one-line mistake that produces a "fixed" ticket and no change.

**The way past.**

1. **Delete the `mcp/` copies**, keep a `README.md` that says where the server went and why (a deletion
   with a signpost).
2. **Assert uniqueness.** `test_packaging.py::test_exactly_one_tool_server_exists` walks the repository
   and fails on a second file with that name, or a second copy of a skill — so re-introducing the
   duplication is caught at the moment it happens rather than a year later.
3. **One resolution order, with a comment.** `_find_server` keeps its walk, and the test asserts it
   resolves to the same path in the app tree and in the repository root.

**Left undone.** The README's tool table (28 tools) must be regenerated from the server, or it drifts
again. The site's own `check.py` culture applies: a number in prose that a script can compute should be
computed.

---

## `[RB-12]` · The API's field names are not the field names you would guess

**The obstacle.** Every wrong guess at a field name failed the same way: not an exception, but an
**empty string**. A page then renders a dash, a pill says `unknown`, and a poll waits for a state that
will never arrive. This is the most expensive class of defect in this spec because it looks like data.

**The evidence, measured** against `GET /api/2.0/postgres/projects/coding-agent-llm/...` on
2026-11-10, a live project in the dev workspace:

| Object | The field that exists | The field that does not, and was read |
|---|---|---|
| project | *(none)* — a project has **no** `state` | `status.state` → always empty |
| branch | `status.current_state`, `status.default`, `status.is_protected` | `status.state`, `status.is_default` |
| endpoint | `status.current_state`, `status.autoscaling_limit_{min,max}_cu`, `status.hosts.host` | `status.postgres_role` |
| role | `status.postgres_role`, `status.identity_type` | *(the endpoint carries no role at all)* |

A real endpoint's `status` keys, verbatim:

```text
autoscaling_limit_max_cu, autoscaling_limit_min_cu, current_state, disabled, endpoint_id,
endpoint_type, group, hosts, last_active_time, settings, suspend_timeout_duration
```

**What it costs us.** `dbx_lakebase_create` polled a *project* for a `state` it does not have, so every
create burned its full timeout and then reported `ready: false` for a project that was ready. A page
showed `—` where a user expected "ready". Nothing raised, so nothing was fixed.

**The way past.** Read the field the API sends, and when a fact is genuinely absent say so rather than
emitting an empty string: `dbx_lakebase_status` returns
`"a project has no state field; readiness is reported per branch and per compute"`. Tests name the
measured shape in their docstrings (`test_lakebase_tools.py`, "MEASURED …") so a rename fails loudly
with the path in the message instead of silently showing `—`.

**Left undone.** Field names are asserted against **recorded** payloads, not against the live API in
CI. A workspace-side rename still needs a human to notice. `dbx_lakebase_status` reports every field it
could not find, which is the cheapest available alarm.

---

## `[RB-13]` · Half a migration is worse than none: the tool server kept the user token

**The obstacle.** `[RB-10]` moved the **page** to the service principal and left the **tool server**
partly on the user token. Two call sites still reached `/api/2.0/postgres` through the user transport,
and a third — the endpoint lookup inside `_lakebase_connect` — did too, so a connection failed with an
error that looked like an auth problem in Postgres rather than a 403 on a management call.

**The evidence.** On the deployed app, commit `47ade33`, from a live session:

```text
dbx_lakebase_status('coding-agent-llm')      -> permission denied by the workspace (403)
dbx_lakebase_status('coding-agent-llm-dev')  -> permission denied by the workspace (403)
```

and the same two GETs, same workspace, same *person*, with a PAT:

```text
GET /api/2.0/postgres/projects/coding-agent-llm      -> 200  (the project, with its branches)
GET /api/2.0/postgres/projects/coding-agent-llm-dev  -> 404  NOT_FOUND
```

**The reasoning that identifies the defect, and not the id.** A wrong project id answers **404**, not
403 — measured. A 403 for *both* ids therefore cannot be about the id. The one identity that gets 403 on
a project it owns is a **user token**, because `postgres` is "always bound to the SP, not OBO". So the
call was made as the user, not as the app.

**What it costs us.** The whole Lakebase half of the product is unreadable from a session while every
test passes, because the tests fake the transport and never assert *which credential* it carried. A
`403` was then paraphrased to the user as a permissions problem on their project.

**The way past.**

1. **One helper per identity, chosen by API not by call site.** `_get_sp`/`_post_sp`/`_patch_sp` for
   `/api/2.0/postgres`; `_get`/`_post`/`_patch` for everything else.
2. **A structural test over the source.** `test_tool_server_identity.py` greps for a `_get`/`_post`/
   `_patch` whose path starts with the Postgres base and fails on any — so a future call site cannot
   reintroduce it silently.
3. **A refusal that names the identity it used.** "The request was made as the signed-in user's token,
   and this API cannot be called with a user token. That is a defect in this tool server" is actionable;
   "the signed-in user or this app's authorization does not allow it" is not, and invites a dead-end
   sign-in.
4. **Log the degradation.** A missing SP token file now warns at `WARNING`, not `DEBUG`, because it is
   the cause of a 403 three layers away.

**Left undone.** The tool server still *falls back* to the user token when no SP token file exists, so a
laptop keeps working. That fallback is why this failed quietly; `_refuse_response` now makes the failure
legible rather than preventing it.

---

## `[RB-14]` · A wrong id and a missing grant are different sentences

**The obstacle.** Three failure causes produced one message: a nonexistent id, a missing
`CAN MANAGE`, and a user token on a Postgres API. All said "permission denied by the workspace", which
reads as *you need a grant*. In a live investigation this produced six tool calls and two notebooks
written to chase a permission that was never the problem, and a final answer that could not report a
single measured fact.

**The evidence.** The platform distinguishes them clearly; only our message did not.

| Cause | Platform's answer | What we said |
|---|---|---|
| id does not exist | `404 NOT_FOUND` "Project with name 'projects/coding-agent-llm-dev' not found" | "permission denied" |
| the identity may not manage it | `403` | "permission denied" (correct) |
| a user token on a Postgres API | `403` | "permission denied" (wrong cause) |

**The way past.** Each cause gets its own words, and the id case gets its own recovery path:
`dbx_lakebase_status` catches `404`, lists the **known project ids**, and says
`"not_a_permission_problem": true` — because an agent told "permission denied" will go looking for a
grant, and an agent told "no project with id X; here are the ids that exist" will not.

**A product consequence worth stating.** `projects/coding-agent-llm-dev` is a *display name*
("coding-agent-llm dev") with a hyphen where the space was. That is the most natural wrong guess a
person or a model can make, so the tool must make it cheap to recover from rather than expensive to
diagnose. It now does.

---

## The register, sorted by what it costs

| Id | Roadblock | Can we fix it? | Cost if ignored |
|---|---|---|---|
| `[RB-13]` | **half the tool server still used the user token** | **yes** — one helper per API, a source-level guard | the Lakebase half is unreadable, with green tests |
| `[RB-14]` | a wrong id, a missing grant and a bad token said the same thing | **yes** — a sentence per cause; 404 names the ids | an investigation that cannot report one fact |
| `[RB-12]` | the API's field names are not the guessable ones | **yes** — read the measured names, say when absent | `—` where "ready" belongs, with no error |
| `[RB-10]` | **`postgres` cannot run as the user at all** | **yes** — the app's own service principal, and say so | a 403 no sign-in can fix |
| `[RB-11]` | the Postgres username is on a **role**, and a credential is bound to its **minter** | **yes** — read the role; mint per identity | an empty username, or a misleading refusal |
| `[RB-6]` | the old API answers with the old shape | **yes** — rewrite, assert the vocabulary | wrong output that looks right |
| `[RB-9]` | two artefacts, one ships | **yes** — delete + assert uniqueness | a fix that reaches nobody |
| `[RB-5]` | the fence cannot be shared code | **yes** — share values, parity table | a false claim in a docstring |
| `[RB-8]` | tools cost context on every turn | **yes** — five not seven, profiles | a slower, weaker agent |
| `[RB-7]` | two cold starts look like failures | **yes** — a `starting` state | false alarms |
| `[RB-4]` | the platform creates the role | **yes** — declare, then read back | an app that cannot connect |
| `[RB-3]` | git-only workspaces, and Git credentials | **partly** — report + optional git source | a scaffold that stops at step 6 |
| `[RB-2]` | scopes are declared, not self-granted | **partly** — declare them, probe at boot | a first deploy that fails |
| `[RB-1]` | the identity is the ceiling | **no**, by design | a first-time user who cannot start |

The last row is the only true roadblock, and it is the product behaving correctly: **Unity Catalog and
Lakebase permissions are the boundary, and an app that could bypass them would be a security defect.**
Everything above it has a way past, and each one names what it leaves behind.

`[RB-10]` and `[RB-11]` were added **after** the first deployment, because no amount of reading the code
had revealed them. Both are recorded with the probe output that established them, in
[12 Outcome](12-outcome.md).
