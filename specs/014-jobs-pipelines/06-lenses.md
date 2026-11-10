[Index](README.md) · prev: [05 Diagrams](05-diagrams.md) · next: [07 Architecture](07-architecture.md)

# 06 · Lenses

Seven owners, one system. Each section is written as the objection that owner would actually raise,
then what the design did about it. Where a trade-off remains, it is named: a lens that never objects is
a lens that was not consulted.

Each lens ends with what it forced, so a reviewer can trace an opinion to a requirement.

---

## 1 · Product Owner

**The objection.** *"You are about to build a scheduler console. This product's thesis is 'the model is
yours and the writes are fenced'. A job runs at 06:00 whether or not anyone is looking, on compute we do
not own, and it can fail silently for a week. Adding a Run button and a Resume-schedule toggle changes
what this product is — from a coding assistant into an ops console. Is that the product?"*

**The answer.** No, and the boundary is exact. This spec adds **no scheduler**. It does not choose a
cron, does not create a trigger, does not decide a retry policy. The agent writes what the user asked
for; the page **shows what was written and what happened**. The difference between an ops console and
this is the difference between *operating* a system and *finishing a sentence*: every screen here
answers a question the user's own turn created, and there is no surface that invites a user to browse
jobs for fun.

Three product decisions follow.

**1.1 · The unit of value is a run, not a job.** A job with no runs is a configuration file. The card
promises *"run it once and prove the run succeeded"*, and the product cannot presently prove it. So the
job page's headline is the last run's outcome, "Run now" is a first-class control, and the run page is a
document kind of its own — not a modal off a job. `[RUN-1]`, `[JOB-2]`.

**1.2 · We do not hide the meter, and we do not make it easy to leave running.** Run now states the
compute and the expected duration. Full refresh states the tables. Resume schedule is the only control
that creates an unbounded future cost, so it is the only one that asks. This is the same posture 013
took with Lakebase's idle policy: the cost model is taught by the page, not discovered on the bill.
`[JOB-5]`, `[JOB-6]`, `[PIPE-3]`.

**1.3 · A schedule the agent creates is paused, and the product says so out loud.** The current tool
already creates paused jobs — the right behaviour nobody can see. Keeping it and *saying* it converts a
silent non-event into a decision the user can make in one click. `[JOB-4]`.

**What we are not doing, and would say no to.** A cron builder. A visual DAG editor. A log viewer. A
"run with parameters" form. A cost dashboard. Each is a plausible product; none of them is this one, and
each has a Databricks link in the header as the escape hatch.

**Metrics this change is judged on.** Not "tools added".

| Metric | Before | Target |
|---|---|---|
| Job-creating turns that end with an openable job | not measurable (no kind) | every one |
| "Is my job working?" asked in a *second* turn | every time | never, for a job whose page loaded |
| Runs started twice by one click | possible | 0 (`[TOOL-5]`, `[RUN-4]`) |
| Pipelines the product can create | 0 | ≥ 1 shape (serverless, UC) |

Forced: `[JOB-2]`, `[JOB-5]`, `[JOB-6]`, `[PIPE-3]`, `[RUN-1]`, `[UI-1]`.

---

## 2 · UI/UX expert

**The objection.** *"You are adding three document kinds to a tab strip that already holds five, two
new groups to a rail that already holds two, and three pages whose subject is a table. A run page is
almost the same page as a job page. Why is this not one page with tabs?"*

**The answer.** Three responses, one concession.

**2.1 · A run is a document because a user pastes it into a ticket.** The one thing people do with a
failed run is send it to someone. `#/run/812345679` is that artifact. A tab inside the job page cannot
be pasted, and 010's whole deep-link grammar exists because a conversation became shareable. So the run
gets a route, and its layout reuses the job page's block rhythm rather than inventing one — the
similarity the objection notices is deliberate and costs no new components.

**2.2 · The job page's block order is a usability argument, not an aesthetic one.** "Is it working?"
(Last run) outranks "what did you build?" (Tasks) outranks "how do I change it?" (Schedule, Settings).
A user reading top-down gets the answer first and the detail second. Reading order is the only
hierarchy that survives a narrow window, where blocks stack instead of flowing.

**2.3 · Three kinds, not one kind with a `subtype`.** A `Doc` with `kind: "infra", subtype: "job"` would
make every exhaustive `Record<DocKind, …>` a `switch` with a nested `switch`, and the compiler would stop
naming the places that must change. 013 already proved the flat union works: adding `lakebase` and `app`
produced six compile errors, each one a place that needed a decision. `[UI-1]` keeps that property.

**The concession.** The palette gains three groups, and the palette is a list a user scans. So the
three new groups are named after what a user *says* — `Jobs`, `Pipelines`, `Runs` — and a run is never
listed unless it is open (a run belongs to a job; the palette is for objects, and 400 runs would swamp
it). `[UI-2]`.

**What the objection changed.** The `Data` tab's four groups are loaded by **one** primitive. The first
draft copied `DataTree`'s two-`useState` pattern four times, which is four places to get the
error-collapsing rule wrong. `[UI-2]` requires a group table and a `useResource` hook, so the fifth
group is a row.

Forced: `[UI-1]`, `[UI-2]`, `[UI-6]`, `[UI-7]`, `[JOB-2]`.

---

## 3 · Full-stack development expert

**The objection.** *"Three pages, three kinds, four rail groups, five new tool families, a ledger table,
and a parity test between two runtimes — and you want it DRY. Where does the duplication actually go?
Name the abstractions or this becomes six copies of the same fetch-and-render."*

**The answer.** Six abstractions, each with a count that justifies it.

| Abstraction | Replaces | Count now | Why not fewer |
|---|---|---|---|
| `Block` (013) | a hand-written loading/empty/error/ready per section | 16 sections | reused unchanged; its 4 states are the whole story |
| `useResource(key, fetcher)` | `useState` + `useEffect` + `setLoading` + `catch` per call | 9 call sites | a hook is not worth it at 2 call sites; at 9 it is the difference between one error rule and nine |
| `TOUCHED` table (`docs.ts`) | 5 hand-written `if` branches in `touched()` | 8 kinds | a table is what makes the 7th kind a row (`[UI-5]`) |
| `GROUPS` table (`DataTree`) | 4 × (`useState` + `useEffect` + renderer) | 4 groups | the rows differ only in data (`[UI-2]`) |
| `RUN_ACTIONS` table | `if (active) … else if (failed) …` in three components | 6 states × 3 controls | the matrix is the spec (`[RUN-2]`, `[RUN-3]`) |
| state tables (`jobs.py` / `jobs.ts`) | a `Map` in a component and a `dict` in an adapter | 27 words | one table, two runtimes, one parity test (`[UI-8]`) |

**Nothing else is abstracted.** The three pages are three components, because a job's blocks and a
pipeline's blocks genuinely differ: a job has tasks and a schedule, a pipeline has libraries and events.
A single `InfraPage` parameterised by a block list would be a worse component than three obvious ones,
and the shared behaviour (fetch, refuse, render `—`) already lives in the two abstractions above.

**What the objection changed.** `[TOOL-1]` exists because the first draft added nine tools and did not
notice the 25-tool budget. The budget is a real cost on every turn, so the plan spends three existing
slots rather than pretending the budget is elastic.

Forced: `[TOOL-1]`, `[UI-2]`, `[UI-5]`, `[UI-8]`, and the `useResource` + `RUN_ACTIONS` choices recorded
in [07 §3](07-architecture.md#3-the-six-abstractions-and-the-count-that-justifies-each).

---

## 4 · Database expert

**The objection.** *"You drew caches. Caches with a TTL are how a page shows last week's schedule beside
a fresh run. And you put a pipeline ledger in a table, which means a write path into the session store
for a *permission* decision — that is a coupling I would refuse."*

**The answer.** Two changes, and one refusal.

**4.1 · Only immutable facts are cached, and each with its own key.** A terminal run never changes
(`[RUN-5]`: its duration is computed from two timestamps that are frozen), so it is safe to cache for as
long as the process lives. A job's `settings` change, so its TTL is 30 seconds and the page's Refresh
bypasses it. A pipeline's *last update* is a pointer, so it is never cached; only the pipeline's
*libraries and configuration* are, with a 60-second TTL. Three tables, three lifetimes — which is
exactly the argument the objection makes against one.

**4.2 · The cache key includes the identity that read it.** 013's `_Cache` keys on `hash(token)` for
exactly this reason ([E-28] there). An entry that answers one user's request from another user's read
is a data leak, not a stale page. This spec reuses that class rather than writing a second cache, and a
test asserts two tokens see two entries.

**4.3 · The ledger is a session row, not an authorization service.** The objection is right that a
permission decision should not live in a cache. It does not: the *authorization* is the platform's
(does this token carry the right to stop this pipeline?). The ledger answers a narrower, weaker
question — *"did this conversation create it?"* — and its purpose is to stop an agent being talked into
stopping a pipeline a data team depends on. So the ledger row is written once, at create, in the same
transaction as the tool call that made it, and it is never consulted for a read.

**What the objection changed.** `[TOOL-6]`'s wording: the refusal says "this pipeline is not in this
session's ledger", never "you do not have permission", because the second sentence would send the user
to an admin for a grant that cannot help.

Forced: `[TOOL-6]`, `[E-17]`, the three-cache split in [07 §4](07-architecture.md#4-where-each-policy-lives).

---

## 5 · System-design expert

**The objection.** *"Your job page makes five platform calls per view, and its run list makes one per
job in the rail. What happens at 200 jobs, or when a workspace's Jobs API is slow? And what stops the
browser polling a run forever?"*

**The answer.** Four bounds, each a number.

**5.1 · A page is `O(1)` calls, and the number is written down.** Five, fixed, independent, in parallel.
The `Runs` list is `limit=5`, not "all". No page fans out over a list. The one place that could — a job
list with each job's last run — is `[TOOL-9]`'s `O(1 + n/100)` paging with an explicit `runsUnread` list
for what could not be read, and the rail asks for **25 jobs, one page, and does not read runs at all**;
the last-run word in a rail row comes from the list payload where the platform supplies it and is
omitted otherwise. A rail that fans out is a rail that takes 40 seconds on a slow workspace.

**5.2 · Polling is bounded by the tab, not by a counter.** 3-second interval while
`document.visibilityState === "visible"`, none while hidden, and it stops at the first terminal state.
No N-attempt cap, because a 40-minute job is legitimate and a cap turns a working run into "unknown". A
tab hidden for ten minutes resumes with one immediate read, not a burst.

**5.3 · The read path degrades per block.** A refused or slow call renders inside its own block. This
is 013's `page_blocks` with `return_exceptions=True`, reused, and it is why five calls in parallel is
safe: one hanging call costs one block, not the page.

**5.4 · Nothing in the write path retries a non-idempotent call.** The existing `_retry` already refuses
to retry a POST except on 429/503. `[TOOL-5]` makes `run-now` idempotent anyway, so even a caller's retry
cannot double-launch.

**What the objection changed.** The rail's job rows do **not** show a run state. The first draft had
them, reading `runs/list` per job; at 25 jobs on a cold workspace that is 25 round trips before the rail
paints. The state moved to the job page and the palette, where it is one call for one object.

Forced: `[TOOL-9]`, `[E-9]`, `[E-10]`, `[E-11]`, and diagram 8 (the polling machine).

---

## 6 · O(n) expert

**The objection.** *"Every one of your tables is a lookup in a render path. `touched()` runs on every
streamed tool event; `taskLevels()` runs on every render of a job page; the rail renders four groups on
every layout change. Show me the complexity, and show me where it becomes `O(n²)`."*

**The answer.** Four functions, each with its bound stated and its hot path named.

| Function | Complexity | Hot path | Why it cannot degrade |
|---|---|---|---|
| `touched(name, args, result)` | `O(k)` where `k` = table rows (8), each a single regex test — **not** `O(len(args))` for the common case, because the table is scanned before any parse | every tool event of every turn | a table of constants; the first matching row short-circuits, and the path regex touches the string only when reached |
| `taskLevels(tasks)` | `O(v + e)` (Kahn), `v` = tasks, `e` = edges, plus `O(v log v)` for a stable display order | every render of a job page | `v ≤ 100` in practice; the function is memoised per settings object, and a cycle returns `{levels: [], cycle: [...]}` rather than throwing |
| `compute(calls, steps)` (013, reused) | `O(c + s)` | every streamed token on the mission screen | already grouped by name once; unchanged, and the reason it is grouped is documented there |
| `groupsToRender` (rail) | `O(g)` where `g` = 4, plus a fixed `.map` per group's data | every layout change / resize | 013's `errorBoxes` was already `O(loads)`; the group table keeps it at `g` |

**Where it would be `O(n²)`, and where the design refuses to go.** `taskLevels` implemented as "for each
task, scan all tasks for its dependencies" is `O(v²)`. It is written as an adjacency build plus Kahn,
which matters because the same function is used by the **validator** `[TOOL-3]`, where `v` is whatever a
model sent. A model that sends 500 tasks is not hypothetical, and `O(v²)` there is a 250 000-edge scan
inside a request.

**The one deliberate linear scan.** `runsUnread` in `[TOOL-9]` is built by iterating the jobs list once,
`O(n)`, after the paged reads. It is linear in the *page*, not in the workspace, and it exists so the
agent can tell "no runs" from "not read" — a correctness property that costs one pass.

**What the objection changed.** `[JOB-3]` requires the *pure* function and names Kahn's algorithm,
because the first draft's "sort tasks until stable" was `O(v² log v)` and would have run on every
streamed token — the same trap 012 recorded in the evidence-heading scan.

Forced: `[JOB-3]`, `[TOOL-3]`, `[TOOL-9]`, `[E-11]`.

---

## 7 · AI-engineer expert

**The objection.** *"Your tools return JSON for a model to read. A job page returns five objects for a
browser to render. Somewhere between them a model has to decide what to do next — and the thing that
makes that hard is not the schema, it is that a job failure has a *cause* in a *different* object. Do
your tools carry the cause, or do they carry a status code and hope?"*

**The answer.** Three rules about what a tool returns to a model, and they are stricter than what a page
needs.

**7.1 · A tool returns the fact that decides the next action, not the whole object.** `dbx_job_run_status`
already does this well: `_task_outputs` returns each task's `exit_value`, `error` and a tail of
`error_trace`, because *"the exit value and the error are what an agent needs to decide its next step"*.
This spec extends the same rule to the tools it adds:

* `dbx_pipeline_events` defaults to `level in ('ERROR','WARN')`, because a model reading 200 INFO lines
  spends its context on nothing;
* `dbx_pipeline_status` includes the **last update** and, when it failed, the first error event's
  message — so "why did it fail?" is answerable without a second tool call;
* `dbx_list_jobs` carries `runsUnread`, so a model can say "I could not read 3 of them" instead of
  inferring "they have no runs".

**7.2 · A refusal is a sentence a model can act on, and the action is in it.** `[TOOL-3]`'s sentence
names the offending key and the transformation (*"task keys must be unique; you sent `silver` twice"*),
not a rule ("keys must be unique"). The difference is measurable: the existing fence tests already
assert that a refusal contains the prefix and the offending name, because a model given a bare "denied"
tries another name.

**7.3 · The skill is where the model learns the choice, and the choice is the hard part.** The
`etl-pipelines` skill currently says "orchestrate with a job" and nothing about pipelines, which is why
"build me a pipeline" produced a job ([F4]). `[PIPE-1]` rewrites it as a **decision table** — the user's
words on the left, the object on the right, and the reason. A model does not need a schema; it needs to
know which of two objects the sentence asked for.

**What the objection changed.** The plan adds one tool that exists only for a model:
`dbx_job_failure_context(job_id)`, which reads the latest failed run and returns *the failing task, its
error, the tables that task's notebook reads with their real columns, and the last successful run's
duration*. That is four facts from three calls, assembled server-side, because making a model do it is
three chances to conclude "the job is broken" instead of "the column was renamed". It is in the budget
by removing `dbx_lakebase_tables` from `core` (`[TOOL-1]`).

Forced: `[TOOL-1]`, `[TOOL-3]`, `[TOOL-8]`, `[TOOL-9]`, `[PIPE-1]`, and the evidence-in-the-tool rule
below.

---

## What all seven lenses agree on

One sentence, reached from seven directions: **the product must not let a turn end with a claim it
cannot show.** The Product Owner says it costs money to leave unproven; the UI expert says a user
cannot paste a JSON blob into a ticket; the full-stack expert says the duplication to do otherwise is
unaffordable; the database expert says a durable record of *what was created* is the only way to fence
it later; the systems expert says a fan-out rail is a slow rail; the complexity expert says the
validator and the renderer must share one graph function; the AI engineer says a model given a status
code writes a story, and a model given an error writes a fix.

The evidence rule that follows is the one this spec adds to the repository's constitution:

> A tool that **changes** a scheduled object returns the object's identity **and** the identity of the
> run or update that proves it. A tool that returns neither has not finished the action.
