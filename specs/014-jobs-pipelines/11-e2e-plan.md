[Index](README.md) · prev: [10 Roadblocks](10-roadblocks.md) · next: [12 Outcome](12-outcome.md)

# 11 · E2E plan

Nine scenes. Each asserts its own pass criteria **before** it saves a picture, so a scene cannot
photograph the wrong state: `lakebase-e2e.mjs` proved that a loose assertion passes over a taxi notebook
(013's S6), and this file's assertions name objects.

Every screenshot is then **looked at** against five criteria, and what the look found is written in
[`e2e/screenshots/README.md`](e2e/screenshots/README.md). A screenshot nobody looked at is a screenshot
nobody can defend.

---

## How the scenes run

```bash
# 1. the app, in fake mode, with the pipeline scenario available
cd apps/coding-agent
APP_AGENT_MODE=fake APP_DEMO_SCENARIO=jobs APP_DEV_USER=you@example.com \
  APP_DEFAULT_MODEL=fake/model-a APP_ALLOWED_MODELS='["fake/model-a"]' \
  .venv/bin/python -m uvicorn api.main:app --host 127.0.0.1 --port 8063

# 2. the bundle the server serves
cd web && npm run build

# 3. the scenes
node scripts/jobs-e2e.mjs http://127.0.0.1:8063
```

`npm run build` is not optional: the server serves `web/dist`, so a scene run against a stale bundle
photographs the previous build. That mistake cost 013 a full run of eight scenes, and it is written here
so it costs nothing this time.

**The pages are photographed against recorded payloads** (`web/scripts/fixtures/jobs.json`), not a live
workspace: a scene that needs a real job cannot run in CI, and a scene that mocks the *shell* proves
nothing about the shell. The shell here is the real app; only the API responses are fixtures.

---

## The nine scenes

### `[S1]` · The shell with four rail groups

**What it proves.** A fifth rail tab was not added, four groups live in the existing one, and the four
independent loads do not paint over each other.

**Fixture.** Two Lakebase projects, two jobs (one `failed`, one `succeeded`), one pipeline, one app.

**Assertions.**

| Check | Threshold |
|---|---|
| the rail tabs are still exactly four, named | `["Sessions","Files","Catalog","Data"]` |
| four group headings, in order | `Lakebase`, `Jobs`, `Pipelines`, `Databricks Apps` |
| the failed job's row says `failed` | a visible word, not only colour |
| no horizontal overflow at 1480 px | `scrollWidth <= innerWidth + 2` |
| `⌘4` selects Data from another tab | `aria-selected` flips |
| no console errors | zero |

**Screenshot.** `s1-shell-data-1480.png`

---

### `[S2]` · A job page

**What it proves.** Five blocks, the header's word derived from the **last run**, the graph drawn in
levels, and the paused schedule stated in words.

**Fixture.** `daily_revenue`, two runs (the latest `TERMINATED`+`FAILED`), three tasks in two levels,
schedule `PAUSED`.

**Assertions.**

| Check | Threshold |
|---|---|
| the header pill reads `failed` | `textContent.toLowerCase() === "failed"` |
| the class is not `tone-busy` | a failed run is not "working" |
| `Last run` block names the failing task | text contains `gold` |
| the graph puts `gold` below `silver` | `taskLevels` order, asserted in the DOM order of `.job-task` |
| the schedule says paused **and** says nothing will run | `/PAUSED/` and `/until you resume/` |
| `Resume schedule` exists and is the only schedule control | exactly one button |
| no overflow | as S1 |
| no console errors | zero |

**Screenshot.** `s2-job-1480.png`

---

### `[S3]` · A run page whose task failed

**What it proves.** Every task's own state, and that a failure quotes the platform's exception.

**Fixture.** run `812345679`: `silver` SUCCESS with an exit value, `gold` FAILED with an
`AnalysisException`, `audit` SKIPPED.

**Assertions.**

| Check | Threshold |
|---|---|
| three task rows, each with a state word | `silver`/`gold`/`audit` present with words |
| `silver` shows its exit value | text contains `1234` |
| `gold`'s error is quoted, not paraphrased | text contains `cannot resolve` and `fare_amount` |
| `audit` reads `skipped`, never `failed` | exact word |
| `Cancel` is **absent** on a finished run | zero matching buttons |
| `Repair` is **present** | one button |
| no console errors | zero |

**Screenshot.** `s3-run-failed-1480.png`

---

### `[S4]` · A run in flight

**What it proves.** A running task is not called "running" only by a spinner, a queued task reads "not
started", and Cancel is available — with the asynchronous consequence stated.

**Fixture.** run `812345680`: `silver` SUCCESS, `gold` RUNNING, `audit` BLOCKED.

**Assertions.**

| Check | Threshold |
|---|---|
| the header reads `running` | exact word |
| `gold`'s row says it is not finished | text contains `not finished` |
| `audit` says it is waiting for `gold` | text contains `waiting` |
| `Cancel` is present | one button |
| the page states cancellation is asynchronous **after** the click | text contains `asynchronous` |
| no red tone anywhere | `.tone-bad` count is 0 |
| no console errors | zero |

**Screenshot.** `s4-run-live-1480.png`

---

### `[S5]` · A pipeline page

**What it proves.** The header follows the **last update**, not the pipeline's `state` — the `F5` defect
this page exists to not repeat.

**Fixture.** `sales_medallion`, pipeline `state: "IDLE"`, last update `COMPLETED`, three libraries, two
events.

**Assertions.**

| Check | Threshold |
|---|---|
| the header reads `succeeded` although the pipeline is `IDLE` | `/succeeded/` and **not** `/succeeded/` derived from `IDLE` |
| the `Last update` block names the update id | `8a0b6d02` |
| three libraries with their paths | count is 3 |
| `Full refresh` states what it re-reads | text contains `re-read` |
| `Stop` is absent (no active update) | zero matching buttons |
| an ERROR event is above an INFO event | DOM order |
| no console errors | zero |

**Screenshot.** `s5-pipeline-1480.png`

---

### `[S6]` · A refusal

**What it proves.** One block's denial leaves its siblings, no retry is offered for a permanent refusal,
and the platform's sentence is verbatim.

**Fixture.** the job payload with `project` → `{error: "PERMISSION_DENIED: ... CAN_MANAGE_RUN ..."}` on
two of five blocks.

**Assertions.**

| Check | Threshold |
|---|---|
| `PERMISSION_DENIED` appears verbatim | text match |
| `CAN_MANAGE_RUN` is named | text match |
| **no** `Try again` button | zero |
| the `Tasks` block still renders | its region exists with content |
| the composer accepts a keystroke | typed text is in the value |
| no console errors | zero |

**Screenshot.** `s6-refused-1480.png`

---

### `[S7]` · A job-creating turn, end to end

**What it proves.** The whole loop: a prompt, an agent that creates and runs a job, and two clickable
objects on screen — the defect `F8` describes is gone.

**Fixture.** a fake-agent scenario `jobs` whose turn calls `dbx_create_job` and `dbx_run_job` with
recorded results.

**Assertions.**

| Check | Threshold |
|---|---|
| the mission reports the plan complete | `/2 of 2/` |
| the dock binds the job | `daily_revenue` in the dock's binding |
| the answer's job reference is a link | an `<a>` whose href starts `#/job/` |
| a second turn asking "why did it fail?" offers **job** suggestions | none matching `/notebook/` |
| no console errors | zero |

**Screenshot.** `s7-agent-turn-1480.png`

---

### `[S8]` · Narrow, 620 px

**What it proves.** One column, no clipping, no horizontal scroll, and the header still carries the state
word.

**Assertions.**

| Check | Threshold |
|---|---|
| no horizontal overflow | `scrollWidth <= innerWidth + 2` |
| the header's pill still reads `failed` | exact word |
| the five blocks are stacked, not clipped | each `getBoundingClientRect().right <= innerWidth` |
| the rail is not a column at this width | `.rail` is absent or `< 40 px` |
| no console errors | zero |

**Screenshot.** `s8-narrow-620.png`

---

### `[S9]` · The palette finds the new objects

**What it proves.** A job and a pipeline are reachable by name from `⌘K`, and a run is not (a run belongs
to a job).

**Assertions.**

| Check | Threshold |
|---|---|
| typing `daily` finds the job | an option whose text contains `daily_revenue` |
| typing `medallion` finds the pipeline | an option containing `sales_medallion` |
| a palette row for the job is grouped under `Jobs` | group text |
| no `run` entries appear with no run open | zero options under a `Runs` group |
| no console errors | zero |

**Screenshot.** `s9-palette-1480.png`

---

## The rule a picture has to pass

From 013's `11`, kept word for word because it is the right rule:

1. **It shows the state it claims.** The assertion and the picture agree; if they disagree, the assertion
   is wrong or the code is.
2. **Nothing is clipped.** No element extends past the viewport, no text is ellipsised where it carries
   meaning, no block is behind another.
3. **The state word is present.** Colour is never the only carrier.
4. **It is legible at 100 %.** Body text ≥ 12.5 px; monospace values ≥ 11.5 px.
5. **It looks like the rest of the app.** The same `Block`, the same `Fact`, the same pill, the same
   spacing. A page that looks different for no reason makes the user think it behaves differently.

A file that fails any of the five is a defect in the code, not in the picture.

---

## What each scene would have caught

A scene is worth its seconds only if it catches something. The predicted defects:

| Scene | The defect it is designed to catch |
|---|---|
| S1 | a fifth rail tab, or four groups where one failed call blanks another |
| S2 | a header reading the **job's** state (which does not exist) — the `RB-12` trap |
| S3 | `SKIPPED` rendered as `failed`, or a `TERMINATED` run shown as a success |
| S4 | Cancel hidden while a run burns compute, or "running" conveyed by a spinner alone |
| S5 | `succeeded` derived from `IDLE` — the `F5` defect, on screen |
| S6 | a `Try again` on a `CAN_MANAGE_RUN` refusal |
| S7 | the turn ending in text with no clickable object — the `F8` defect |
| S8 | a clipped task graph, or a horizontal scrollbar |
| S9 | a job findable only by a deep link |

## Cost

Nine scenes, one browser, ~45 s wall clock, one bundled build. No network beyond `127.0.0.1`. The whole
suite runs on a laptop and in CI without a Databricks token, which is the property that makes it
runnable on every commit rather than before a release.

## The one thing this plan cannot prove

That a **real** workspace's Jobs API answers the way the fixtures say. The fixtures were built from the
documentation's own field lists and from the shapes 013 measured for adjacent APIs, and they are
therefore a description of what the docs promise — not a recording of a live call. If a live call
differs, the fixture is wrong and the adapter is wrong with it.

That gap is closed by one manual step, recorded in [12 Outcome](12-outcome.md): a single run against a
real workspace, with the response shapes compared field by field against `fixtures/jobs.json`. It is
listed there as a **required** check, not a nice-to-have, because a fixture that drifts from the platform
is a test that passes forever.
