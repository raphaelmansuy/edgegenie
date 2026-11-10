[Index](README.md) · next: [02 Measured assessment](02-assessment.md)

# 01 · Five whys, and the first principles underneath

The symptom, stated the way a user reports it:

> "I asked for a daily job. It said it created one and printed some JSON. I cannot find the job, I do
> not know if it ran, and the id in the message does nothing when I click it."

Five whys, each answer a fact from this checkout or from the platform documentation.

---

## 1 · Why can the user not find the job?

Because there is **no screen that can represent one**. `DocKind` (`web/src/domain/docs.ts:8`) has five
members — `notebook`, `file`, `table`, `lakebase`, `app` — and the shell is honest about it: the tab
icon map, the route grammar (`route.ts:20`), the recent list (`recent.ts:14`), the palette groups
(`App.tsx:77-79`), the dock's suggestions (`dock.ts:104-121`) and the `ACTIONS_FOR` table
(`docs.ts:154`) each enumerate that union. A sixth kind is a compiler-guided change across six files;
a job id has nowhere to land. This is [F7].

## 2 · Why did the product never grow a sixth kind?

Because 013 added the *fifth* (`lakebase`, `app`) by hand, and the pattern that made those two work
stops one object type later. 013's [UI-1] said *"an object the agent created is an object the user can
open"* and delivered two readers: `LakebasePage` and `AppPage`. It did not deliver the *reducer* that
maps a tool call to an object — `touched()` (`docs.ts:93`) — for anything but paths and those two
reads. So the sixth object type is not a new concept; it is the same concept with two more cases, and
the reason it did not happen is that `touched()` was written per-kind instead of from a table. This is
[F8].

## 3 · Why is `touched()` per-kind?

Because each kind's identity genuinely differs: a notebook is a canonical path, a Lakebase project is
`projects/{id}` however it is spelled, an app is its name reduced from a URL, and a table is
`catalog.schema.table`. That is a real reason, and it produced a chain of `if` statements that is
correct and does not scale. The DRY answer is not "one regex": it is **one table of `(tool pattern →
kind → id extractor)`**, so a new kind is a row. That table is [JOB-9] and it is the single most
important structural change in this spec, because the seventh object type will arrive.

## 4 · Why does the agent's answer even claim success?

Because the tool does return a real `job_id`. `dbx_create_job` (`tools/databricks_notebook_mcp.py:1094`)
calls `POST /api/2.1/jobs/create` and gets one back. The tool is not lying. What it does not do is
anything that makes the *claim checkable*: it returns a `next` hint that says *"call
dbx_run_job(job_id, wait_seconds=300)"* and the agent may or may not. And when it does, the run's
outcome lives only in the transcript — `_run_summary` (`:912`) is a string, and the product's evidence
supervisor (`api/domain/supervisor.py`) can see a tool call happened but has no object to point at.

## 5 · Why is the outcome only in the transcript?

Because the product's whole model of a run is a **notebook run**, and a notebook run is a thing this app
executes itself (`dbx_run_notebook`, `_run_via_app`, `api/services/pyrun_service.py`). A job run is
executed by the *platform*, on compute this app does not own, possibly hours after the turn ended. There
is no `RunKind` distinction in the product, so a job run has no representation. The pipeline case is
worse: there is no tool to start one at all ([F4]).

---

## The first principles

Three sentences that decide everything after them.

### P1 · A scheduled object has two lives, and the product only has words for one

A job has a **definition** (its settings: tasks, dependencies, schedule, timeout) and a **history** (its
runs, each with a terminal result). The definition is what the agent edits; the history is what the user
reads. A page that shows only the definition answers "what did you build?" and never "is it working?".
So every job and pipeline surface in this spec shows the **last run's outcome in its header**, and the
run list is a first-class block, not a sub-tab buried behind a click.

### P2 · The terminal field is the only honest source of a state word

The platform gives a job run a `life_cycle_state` and a `result_state`, and a pipeline a `state` and a
list of `latest_updates[].state`. In both cases the *first* is the one that is always present and the
*second* is the one that answers the question. 013's [RB-12] recorded the identical mistake for Lakebase:
a project has no `state`, the page read one anyway, and the header said "loading" forever over a healthy
project. The rule that follows compiles:

* the state word comes from a **pure function whose input is the whole payload** (`runWord()`,
  `pipelineWord()`), not from a field access at the call site;
* an unknown value is rendered **verbatim and lowercase**, never mapped to a cheerful synonym;
* a value that could not be read renders `—`, never `0` and never `ready` (013's [UI-3]).

### P3 · The fence is a promise about *names*, and names are what a job is

`dbx_create_job` already refuses a name that does not start with `NBMCP_WRITE_JOB_PREFIX`
(`:1073`). `dbx_run_job` re-reads the job and re-checks the prefix before running it (`:1105-1106`),
which is the right pattern: **the fence is re-checked at the moment of the action, from the object the
platform returned**, not from the argument the caller passed. Every new tool in this spec follows that
pattern, and one of them (stop a pipeline update) is the first place it *cannot*: a pipeline id is a
UUID with no session prefix, so the fence has to be a **different rule** — "a pipeline this session
created, recorded in the session's own ledger" — and that rule has to be written down rather than
improvised. It is [TOOL-6] and [E-17].

---

## What changes in the product's sentence

Before:

> "Created job `agent_4ff4405d_daily_revenue` (id 812345678901) with tasks `silver` → `gold`. Run it with
> `dbx_run_job`."

After:

> "Created **`agent_4ff4405d_daily_revenue`**, daily at 06:00 UTC — **paused**, as every agent-made
> schedule is. It has not run yet. **Run now** starts compute; the last run took 1 m 42 s."

The second sentence names the two things that are clickable, states the schedule's pause state (a
deliberate product decision, [JOB-4]), says plainly that there is no history, and puts the cost next to
the button. Nothing in it is a claim the page cannot prove.

---

## Why "paused by default" is not a footnote

Creating a job with a schedule in Databricks means creating something that will start compute at 06:00
tomorrow, forever, whether or not the user still wants it. The current tool already does the right
thing — `body["schedule"] = {..., "pause_status": "PAUSED"}` (`:1092`) — and no screen says so, so the
user's mental model is "I made a job that runs at 06:00" when the truth is "I made a paused job".

The spec keeps the behaviour and makes it visible in three places: the job page's schedule block, the
transcript sentence, and the "Resume schedule" control, which is the one action that turns a paused job
into a recurring cost. That control is [JOB-5], and it is the only control in this spec that can create
an unbounded future cost from a single click.
