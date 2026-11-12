[Index](README.md) · prev: [05 Diagrams](05-diagrams.md) · next: [07 Architecture](07-architecture.md)

# 06 · Lenses

Seven owners, one system. Each section is written as the objection that owner would actually raise,
then what the design did about it. Where a trade-off remains, it is named — a lens that never objects
is a lens that was not consulted.

Each lens ends with the requirements it forced, so a reviewer can trace an opinion to a decision.

---

## 1 · Product Owner

**The objection.** *"You are adding two object types to a product whose thesis is 'the model is yours
and the writes are fenced'. A Lakebase project and a Databricks App are infrastructure: they cost money
per hour, they outlive the conversation, and one of them is visible to the whole workspace. Adding a
build button for them changes what this product is — from a coding assistant to an IaC console. Is that
what we are shipping?"*

**The answer.** No — and the distinction is the reason for `[SCF-2]`. This is not an IaC console: there
is no desired-state file, no plan/apply, no drift detection. It is the **end of a conversation** that
already happens. The card in the product already asks for exactly this workflow, and the transcript
already claims to have done it. The choice is not "add infrastructure management" versus "stay a
coding assistant"; it is "finish the workflow the product already advertises" versus "keep claiming
work that produced nothing the user can see".

Three product decisions follow.

**1.1 · The unit of value is a *working* pair, not two objects.** A project with no table is a cost with
no use. An app with no database is a broken app. So the workflow is scored on the pair, and
`[SCF-1]`'s seven steps are the scorecard. This is why a scaffold that stops at step 3 does not create
an app: half a pair is worse than none, because it looks finished and costs money.

**1.2 · Cost is visible at the moment of creation.** Both objects cost money when idle — a Lakebase
compute until it scales to zero, an app until its compute stops. `[UI-3]` and `[UI-4]` show the idle
policy and the compute size, so the user learns the cost model from the page rather than from a bill.
This is a deliberate product choice: we do not hide the meter.

**1.3 · The fence is the promise, so it must be true.** The README's second rule is *"writes stay
inside the fence"*. Today that is true of paths and SQL and false of apps. `[SCF-4]` is a product
requirement, not a code tidy-up: a promise in the README that the code does not keep is the most
expensive kind of debt, because it is the one a customer quotes back.

**What we are *not* doing, and would say no to.** A Lakebase admin console (PG parameters, HA, read
replicas, instant restore); an app builder with a visual editor; a scheduler for scaffolds. Each is a
plausible product; none is this one. The link to Databricks is the escape hatch for all three, and it is
in every frame.

**Metrics this change is judged on.** Not "tools added". Three numbers:

| Metric | Before | Target |
|---|---|---|
| The card's request reaching two working objects, on the first try | 0 of the steps past the create | ≥ 1 in 2 attempts, with the second attempt succeeding after a shown refusal |
| Turns ending in an object the user *opened* | not measurable (no kinds) | every scaffold turn ends with ≥ 1 openable object |
| The user asking "is it running?" in a second turn | every time | never for a scaffold whose step 7 succeeded |

Forced: `[SCF-1]`, `[SCF-2]`, `[SCF-4]`, `[UI-3]`, `[UI-4]`.

---

## 2 · UI/UX expert

**The objection.** *"You are adding a fourth rail tab to a shell whose three tabs were chosen
deliberately, and a document kind that is not a document — a Lakebase project is not something you
read, it is something you operate. Putting it in the same tab strip as a notebook invites the user to
think they can edit it."*

**The answer.** Three responses, and one concession.

**2.1 · It *is* a document in one specific sense, and that is the only sense the shell needs.** A tab
is a place you return to, and a URL is a thing you paste into a ticket. Both are true of a project and
of an app. The tab strip already mixes a notebook (editable), a file (editable) and a table
(read-only). A fourth read-only surface is not a new idea in this shell; it is the same idea with a
different subject.

**2.2 · The editor is where the difference is stated, not the tab.** `[UI-3]` and `[UI-4]` render no
editor, no save, no dirty marker, and no `⌘S` target. What they render is a *state* and one **Open in
Databricks** link (`viewer-head`'s existing `ExtLink`). The user learns "this is a viewer" from the
absence of a save button and the presence of an external link — which is how every read-only surface
in every product teaches it.

**2.3 · Why a fourth tab and not a section inside `Files`.** Concession first: a tab is expensive
navigation real estate, and we are spending one. The measure:

| Option | Cost | Why rejected |
|---|---|---|
| A folder in `Files` | 0 new tabs | a Lakebase project is not a workspace path; it would need a fake path, the exact bug `canonicalPath` exists to prevent |
| A section in `Catalog` | 0 new tabs | the Catalog tab is Unity Catalog, governed by a different API and a different permission model; mixing them teaches the wrong mental model |
| A fourth tab `Data` | one tab | the two object types share a lifecycle (build → run → verify) and a cost concern, which is exactly what a tab is for |
| No navigation, palette only | 0 tabs | an object you can only reach by remembering its name is not openable in the sense `[P4]` means |

The tab is named **Data** rather than **Lakebase** because the next object type this product grows — a
Lakeflow pipeline, a Genie space — belongs here too, and a tab named after one vendor product will not
survive that.

**2.4 · The one thing the frames changed after being looked at.** S7 exists because the first draft of
the narrow layout dropped the composer to a shorter string and left it on the border row. The fix was
not the string: the composer had no row of its own. That is a reminder that a wireframe is inspected,
not only specified — and the screenshots in [e2e](e2e/screenshots/README.md) are inspected the same way.

**2.5 · Keyboard and focus, stated once.** `⌘4` selects `Data`; `⌘1..3` are unchanged. The rail is a
tablist with arrow-key roving, which it already is. A project page's first focusable element is the
same as a notebook's (`viewer-head`'s reload), so `Tab` from the tab strip does not land on an external
link and leak the user out of the app — the first-tab-stop rule from [012].

Forced: `[UI-1]`, `[UI-2]`, `[UI-3]`, `[UI-4]`, `[UI-5]`, `[UI-6]`.

---

## 3 · Full-stack development expert

**The objection.** *"Five new API routes, two new document kinds, a fourth renderer, and a cache — for
two object types. Every one of those is a place to be inconsistent with the SSE stream, the durable
session, and the fence. Can this be additive instead of a second stack?"*

**The answer.** It can, and the test is that no existing file grows a `switch` that did not already
have one.

**3.1 · The routes follow the shape that exists.** `api/routers/api.py` already groups
`/workspace/*` and `/catalog/*`. The new groups are `/lakebase/*` and `/apps/*`, with the same
conventions: the user's token for every call (`_user_token`), `_dbx_errors` for status mapping, a
`LookupError → 404`, a `PermissionError → 403`. Nothing new is invented; the adapter contract in
`api/adapters/databricks/http.py` is reused, which is why a `ScopeMissing` refusal already produces the
right sentence.

**3.2 · The domain stays pure.** The rule "a step is done only with a proof" is
`api/domain/scaffold.py` — a pure function from `(plan entries, tool calls)` to
`[{step, state, proof}]`. It has no I/O, so it is tested with two lists and no fixture. The UI's
`domain/scaffold.ts` mirrors it in the same way `domain/fence.ts` mirrors `check_path`, and a test
holds the two to the same table. This is the DRY boundary: **one rule, two runtimes, one test table.**

**3.3 · The two new kinds are data, not branches.** The renderer switch is one component
(`DocBody`) with five cases; four of them already exist. The rail's tree is a generic `TreeRow` fed by
one adapter per kind, which is how `FilesPane` and `CatalogTree` already work. `DocKind` is a union in
one file; adding a member produces a compile error where a union is exhaustively switched, which is the
mechanism that makes "additive" enforceable rather than aspirational.

**3.4 · The cache is a port, not a table.** `ObjectCache` is a protocol with two adapters: memory (a
dict with a timestamp) and, when there is a session store, Postgres. The page asks the port; the port
decides. This is the same shape as `ModelCatalog` in [005], and it means a test of the page never needs
a database.

**3.5 · What is deliberately duplicated, and why.** The five fence values are computed once
(`Scope.for_session`) and passed to the child process as environment. The *rule* is duplicated
(`check_path` vs `_check_path_scope`) because the tool server cannot import the app. That duplication is
tested by a shared table (`tests/test_fence_parity.py`) rather than removed by a dependency, because a
tool server that imports the app is a tool server that cannot be started alone.

Forced: the route shape, `ObjectCache` as a port, `domain/scaffold` purity, the parity test.

---

## 4 · Database expert

**The objection.** *"You are about to have three different ways to reach Postgres in one repository:
the app's own `psycopg` pool, the tool server's `psycopg2` import, and now a third in the new tools.
Pick one. And you have said nothing about what a credential costs, what happens when a connection
leaks, or which branch a write lands on."*

**The answer.** Fair, and the first clause is `[F1]` and `[F2]` in one sentence.

**4.1 · One client: `psycopg` v3.** It is in `requirements.txt`, it is what `llm/store` uses, and it is
async-capable. `psycopg2` is removed from the tool server. That reduces three clients to two (the
app's pool and the tool's per-call connection), and the two have different lifetimes for a reason: the
app holds a pool for its own journal; the tool makes one connection, runs one statement batch, and
closes it.

**4.2 · One credential per call, and that is a feature.** `POST /api/2.0/postgres/credentials` returns a
token with a ≤ 60-minute life. The tool mints one per call. The alternative — cache the token in the
tool server process — would put a credential in a process that the agent can make run arbitrary
`sql`, which is exactly the thing a short-lived token exists to prevent. Cost: one extra API call per
SQL batch, which is ~100 ms against a database round trip. Accepted.

**4.3 · The branch is a parameter, not an ambient fact.** Every SQL call names its branch and resolves
*that branch's* read-write endpoint. A scaffold writes to `agent-<session>` and never to `production`,
for the same reason it writes to a scratch folder and never to a repo: the user's production data is
not a test fixture. `[LB-3]` states it and S2 shows it (`SQL RUNS ON THIS BRANCH ONLY`).

**4.4 · The connection is always closed, in a `finally`.** The current tool does this correctly
(`finally: conn.close()`); the rewrite keeps it and adds a `connect_timeout` so a suspended compute
produces a sentence in 20 s rather than a hang. A suspended compute waking is normal: the error names
it (`compute is suspended; a connection will resume it`) instead of surfacing `could not connect`.

**4.5 · The autoscaling rule is enforced here, because it is a database rule.** `max − min ≤ 16`,
`max ≤ 64`, scale-to-zero only under 32. These are not UI niceties; they are the platform's constraints,
and `[LB-4]` puts them in the tool so an agent that reasons "let me be generous" learns the rule.

**4.6 · The one thing we cannot do.** An app's Postgres role is created by the **platform** when a
`postgres` resource is attached — `Databricks creates a PostgreSQL role ... the role name matches the
service principal's client ID`. So a scaffold does not create that role; it attaches the resource and
lets the platform do it, then *reads it back* to prove it exists (`[SCF-1]` step 4). This is a real
correction to the plan's first draft, which had a `create-role` step that would have created a role
matching our prefix instead of the app's identity.

Forced: `[LB-1]`…`[LB-5]`, `[AP-1]`, and the shape of step 4 in `[SCF-1]`.

---

## 5 · System-design expert

**The objection.** *"This makes the app's own availability depend on the availability of two more APIs.
A project page that fans out to four endpoints on an API whose quota you do not control turns a fast app
into a slow one, and a Lakebase outage into a page that will not load. Where is the isolation?"*

**The answer.** Isolation is by *field*, not by page, and that is a deliberate departure from the
usual "one page, one call" rule.

**5.1 · Four parallel reads, four independent failures.** `[E-11]` requires it: a project page whose
branches call fails still shows the project, the compute and the databases, and says in the branches
block that it could not read them. A single aggregate endpoint would make one slow call hide four fast
facts — and would make a partial failure indistinguishable from an empty one, which is the bug class
`[UI-3]` names ("a value that could not be read must say so rather than render as 0").

**5.2 · A bounded cache, with a stated TTL.** 60 s for an object, 15 s for a health check. The health
check is shorter because "is it working" is time-sensitive; the object is longer because it changes on
a scaffold timescale. Both are in `ObjectCache`, both are tested for "works with an empty cache".

**5.3 · The rail's list is a `GET`, not a fan-out.** The rail needs names and states, which one call
per kind returns. It never expands a project to read its branches: the tree fetches lazily on expand,
which is what `CatalogTree` already does and why it stays fast on a large metastore.

**5.4 · What this does to the app's own tail latency.** A project page costs four calls at ~120 ms each
in parallel, so ~150 ms typical, bounded by a 20 s timeout per call (`DbxHttp.TIMEOUT`). The page renders
skeleton blocks immediately, so perceived latency is the shell's, not the API's. This is the same
pattern `(007)` established for the file tree.

**5.5 · The failure mode that is not covered.** If the Lakebase **Postgres API** is down, the project
page shows four error blocks and the rail shows a stale list. That is the correct behaviour and it is
not the app being down: the notebook, the dock and the conversation keep working, because they do not
depend on those calls. The test asserts it (`[E-11]`: with all four routes failing, the composer still
sends).

Forced: `[UI-3]`'s per-field honesty, `[E-11]`, the `ObjectCache` TTLs, the lazy tree.

---

## 6 · O(n) expert

**The objection.** *"You have written 'list projects', 'list branches', 'list apps' and 'count rows'.
On a workspace with 400 projects, 30 branches each and 500 apps, which of those walks is on the
keystroke path? And the rail lists them on every page load."*

**The answer.** Three of them are, and each is bounded. This is the section that changes the *shape* of
two requirements rather than their content.

**6.1 · The rail is O(1) calls, O(n) rows, O(visible) work.** One `GET /projects`, one `GET /apps`, no
fan-out. Rows render in a virtualised list only when the count passes a threshold; below 200 they are
plain rows because virtualisation is a lie at that size. Cost: `O(p + a)` payload, `O(p + a)` row
creation, and no per-row network call until a row is expanded.

**6.2 · The dangerous walk is "which apps use this project".** Naively it is `O(apps)` calls, and each
`GET /apps/{name}` returns resources — so it is `O(a · r)` work for a badge. Two mitigations, both
applied:

| Naive | This design |
|---|---|
| `GET /apps` then `GET /apps/{n}` per app, reading `resources` | one `GET /apps`, reading `resources` from the **list** payload when present; the per-app call only for an app the list truncated |
| recompute on every visit | `ObjectCache`, 60 s, keyed by project |

So the badge is `O(a)` API items in one response, and `O(a)` matching — not `O(a)` round trips.

**6.3 · Table and row counts are the expensive one, and they are computed once per page.** A count per
table is `O(t)` queries on the project's database. That is affordable only because it is bounded and
cached, and it is why `[UI-3]` shows counts as a *summary* with a refresh affordance rather than live per
scroll. The bound is `LIMIT 50` tables: past that the block says "50 of N, open in Databricks for the
rest", which is the honest version of a truncated list rather than a silent one.

**6.4 · The step-matching in `[SCF-1]` is O(steps · calls), which is fine — and was not.** The first
draft matched each plan entry against every tool call with a token-overlap score, the approach
`evidence.limit_to` uses for requirements. That is `O(s · c · tokens)` per render, and a render happens
per streamed token. The fix is the same one `[012]` applied to `isEvidenceHeading`: **one pass**. Group
the calls by tool name once (`O(c)`), map each step to the tool names it accepts (`O(s)` constant
lookup), then each step reads its group in `O(1)`. The whole function is `O(c + s)`, and the test
asserts it on 2 000 calls in under 5 ms.

**6.5 · What is deliberately O(n) and stays so.** The palette searches projects and apps by substring
over the cached list, which is `O(p + a)` per keystroke with no debounce, because that list is small and
already in memory. Adding a server-side search for two object types would be an index and a round trip
for a list that fits in a kilobyte.

Forced: the rail's one-call design, the app-badge bound, the `LIMIT 50` with its honest sentence, and
`[SCF-1]`'s one-pass matching.

---

## 7 · AI Engineer

**The objection.** *"You are about to hand a model six more tools, each with a parameter that must be a
resource path it has to remember across ten turns. The measured result in this repository is that a
weak model gets worse as the tool surface grows, and that a model will happily claim a deployment it
never made. What makes you think it will get this right?"*

**The answer.** The strongest objection in this document, and it changed the tool design twice.

**7.1 · Seven tools became five, and each returns the next call's argument.** The first draft had one
tool per object (`project_create`, `branch_create`, `database_create`, `role_create`,
`endpoint_get`, `app_create`, `app_health`). That is seven names to hold and seven chances to drop a
prefix. The design now returns the *next* identity in the previous call's answer:

```json
{"project": "projects/pg-tickets", "branch": "projects/pg-tickets/branches/production",
 "next": "call dbx_lakebase_branch(project='projects/pg-tickets', branch='agent-abc12345')"}
```

A model does not have to remember a path; it has to copy one it just saw. This is why the tool count is
five and not seven, and why the `next` line exists in every mutating tool's answer — the same
progressive-disclosure trick `dbx_skill` uses for skills.

**7.2 · The proof requirement is enforced outside the model.** `[SCF-1]` does not ask the agent to report
seven steps correctly. The *app* computes the step table from the tool calls it observed. A model that
says "created the app, it is running" over a transcript with no `dbx_create_app` call produces a plan
whose step 6 is `pending` — and the supervisor's existing rule (`evidence.verify`) already reports a
citation to a call that never happened. The model's prose cannot promote a step.

**7.3 · The refusal is written for the model to act on, not only for the user to read.** The tool
server already learned this: a 401/403 raises `PermissionError("… Do not retry; use another tool or
report it")`. The new tools carry the same instruction for the two refusals a model actually retries:

| Refusal | What the model is told |
|---|---|
| name outside the prefix | `do not choose another name; the prefix is fixed for this session` |
| `max − min > 16` | `reduce the maximum to min + 16, then call again` |
| app refused (git-only workspace) | `do not retry; report the platform_error verbatim and tell the user to deploy from git` |

The third is the one that matters: without it, a model retries a deployment three times and the user
sees three identical failures.

**7.4 · One tool is read-only by construction.** `dbx_app_health` takes a URL and does a `GET`. It has
no `_need_writes`, no prefix check, and no state. A capability that cannot write is worth having even
when it is trivial, because it is the one the scaffold's last step needs and the one a model can use
freely.

**7.5 · What the model is told about the branch.** The session rules (`session_rules` in
`agent_config.py`) already state the folder and the schema. They gain one line for the branch, in the
same voice: *"SQL on a database you create runs on branch `agent-<id>`, never on `production`."* A rule
in the system prompt is cheaper than a refusal at the tool, and the measured result in this repository
is that written rules are what took a weak model from 19 % to 94 %.

**7.6 · The honest limit.** A model can still call `dbx_lakebase_sql` with `DROP TABLE` on a branch it
owns. That is allowed on purpose: it is the user's branch, the fence permits it, and the destructive-SQL
approval already exists for the shared case. What the design refuses is a *silent* destructive action,
not a deliberate one.

Forced: five tools not seven, the `next` hint, the app-computed step table, the model-facing refusals,
the branch rule in the session prompt.

---

## What the lenses changed, in one table

| Lens | Changed | Requirement touched |
|---|---|---|
| PO | the workflow is scored on the *pair*; a scaffold stops rather than half-finishing | `[SCF-1]`, `[SCF-2]` |
| PO | the fence becomes a requirement because the README promises it | `[SCF-4]` |
| UX | a fourth tab (`Data`), justified against three alternatives | `[UI-2]` |
| UX | no editor, no save, no `⌘S`: read-only is taught by absence plus an external link | `[UI-3]`, `[UI-4]` |
| Full-stack | `ObjectCache` is a port with a memory adapter, so a page test needs no database | `[UI-3]` |
| Full-stack | the step rule is one pure module per runtime, held to one test table | `[SCF-1]` |
| Database | one client (`psycopg` v3); a credential per call, never cached | `[LB-3]` |
| Database | the branch is a parameter on every SQL call | `[LB-3]` |
| Database | **step 4 reads the app's role back; it does not create one** | `[SCF-1]` |
| System design | four parallel calls, four independent failures; never one aggregate endpoint | `[UI-3]`, `[E-11]` |
| O(n) | the app-per-project badge reads the list payload, not one call per app | `[UI-3]` |
| O(n) | step matching is `O(c + s)`, one pass, not a scoring loop per render | `[SCF-1]` |
| O(n) | table counts are capped at 50 with an honest sentence | `[UI-3]` |
| AI | five tools, not seven; every answer names the next argument | `[LB-2]`, `[AP-1]` |
| AI | the plan is computed by the app from observed calls, not reported by the model | `[SCF-3]` |
| AI | refusals are phrased as instructions the model can follow | `[UI-6]`, `[AP-1]` |
