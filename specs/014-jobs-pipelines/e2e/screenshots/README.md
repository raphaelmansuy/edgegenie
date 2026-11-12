# Screenshots

Produced by `node scripts/jobs-e2e.mjs http://127.0.0.1:8063` from the app running on this machine,
against the recorded payloads in
[`web/scripts/fixtures/jobs.json`](../../../apps/coding-agent/web/scripts/fixtures/jobs.json).
Each scene asserts its own pass criteria before the picture is taken, so a scene cannot save a pretty
image of the wrong state.

Reproduce:

```bash
cd apps/coding-agent
APP_AGENT_MODE=fake APP_DEMO_SCENARIO=jobs APP_DEV_USER=you@example.com \
  APP_DEFAULT_MODEL=fake/model-a APP_ALLOWED_MODELS='["fake/model-a"]' \
  .venv/bin/python -m uvicorn api.main:app --host 127.0.0.1 --port 8063

cd web && npm run build && node scripts/jobs-e2e.mjs http://127.0.0.1:8063
```

`npm run build` is not optional: the server serves `web/dist`, so a scene run against a stale bundle
photographs the previous build.

---

## The nine scenes

| File | Scene | What the picture shows | What inspection changed |
|---|---|---|---|
| `s1-shell-data-1480.png` | [S1](../11-e2e-plan.md#s1--the-shell-with-four-rail-groups) | four rail tabs, `Data` selected, four groups: Lakebase (1), Jobs (2, one `paused`), Pipelines (2, one `succeeded` and one `failed`), Databricks Apps (1, `running`) | **twice.** First the fixture globs (`**/api/jobs`) do not match a query string (`?limit=25`), so the rail said "Could not read jobs" over a fixture that was present — the assertion caught it. Then the heading assertion read the whole rail's text, which contains the hint "Databases, jobs, pipelines and apps you can see", and passed for the wrong reason; it now reads the `.tree-group` headings, whose text carries the count (`"Jobs2"`), so the label is the heading minus its trailing digits |
| `s2-job-1480.png` | [S2](../11-e2e-plan.md#s2--a-job-page) | the pill says **`failed`** (the last run's word), five blocks, the tasks in two levels with `after silver` on both level-2 rows, the schedule stated as **PAUSED** with "nothing will run until you resume it", the last run's duration on the Run-now tooltip, and "read as the app's service principal" in Settings | the "five blocks are on screen" check searched the body text, and a block heading is in its own element; it now asserts `getByRole("region", { name })` for each of the five, which is the same fact a screen reader reads |
| `s3-run-failed-1480.png` | [S3](../11-e2e-plan.md#s3--a-run-page-whose-task-failed) | `run 812345679` with the job named in the header, three task rows (`succeeded` 38 s, `failed` 64 s, `skipped`), the `AnalysisException` quoted with its column list, a collapsed stack trace, and Repair but no Cancel | **the run page named no job.** A pasted `#/run/812345679` was a bare number in a ticket; the adapter now resolves the job's name (through the job cache, so a run opened from a job costs nothing) and the header reads `agent_4ff4405d_daily_revenue · run 812345679` |
| `s4-run-live-1480.png` | [S4](../11-e2e-plan.md#s4--a-run-in-flight) | `running` in the busy tone, `gold` still running, `audit` **blocked** and waiting for `gold`, Cancel present, the sentence "re-reads it every 3 s while the tab is visible", and no red anywhere | nothing — the state was already right, which is why it is kept as the record that "in flight" is not "broken" |
| `s5-pipeline-1480.png` | [S5](../11-e2e-plan.md#s5--a-pipeline-page) | `sales_medallion`, pill **`succeeded`** while the pipeline's own state is `IDLE`, update `8a0b6d02`, three libraries by leaf name with their paths, configuration (catalog/schema/edition/serverless), and the ERROR event above the INFO one | nothing structural. The header shows `f0e1c4a2…` truncated with the full id on the copy button, which is the honest display of a UUID a person cannot read |
| `s6-refused-1480.png` | [S6](../11-e2e-plan.md#s6--a-refusal) | **one** grey banner: "This page could not be read." + `PERMISSION_DENIED … CAN_MANAGE_RUN` + "A retry cannot grant this." Then five blocks, each saying what **specifically** could not be read. No retry button. The composer accepts "still works" | **three times, and this is the most important file in the set.** (1) The refusal was rendered five times, once per block, while every assertion passed — "the sentence is verbatim", "no retry is offered" — and the page read as five separate problems. That is 013's [UI-6] defect, on a page. (2) After collapsing it, a call site in `Settings` had been missed, so it repeated the sentence under the banner: a per-call-site test cannot catch that, so the guard is now a count of `.infra-block-error` boxes. (3) With the repetition gone, every block fell back to its **empty** sentence — "This job has not run yet", "No runs in this job's history" — which are two **claims** a failed read cannot support. A block whose read failed now says what it could not read, and the `Block` component gained a fifth state (`unread`) so the empty sentence can never be reused for it |
| `s7-agent-turn-1480.png` | [S7](../11-e2e-plan.md#s7--a-job-creating-turn-end-to-end) | the mission: "Achieved", 4 tool calls, the job and run named in the answer, PAUSED stated, the `AnalysisException` quoted, and the job in **Outputs & references** as an openable row | **two.** The link assertion looked for an `<a href="#/job/…">`, and the mission's outputs are `<button>`s — so the check was asserting a DOM shape rather than the behaviour, and now looks for the output whose title is the job's ref. And an output's icon was `notebook ? <Notebook/> : <FileIcon/>`, so **a job appeared as a file**: `artifactIcon()` now maps every kind |
| `s8-narrow-620.png` | [S8](../11-e2e-plan.md#s8--narrow-620-px) | one column, no clipping, the pill still `failed`, the graph wrapped with each task's detail on its own line, nothing past the viewport | nothing — the task-row grid reflows at ≤ 700 px by design, and this is the record that it does |
| `s9-palette-1480.png` | [S9](../11-e2e-plan.md#s9--the-palette) | `⌘K`, type "medallion", one row under **PIPELINES**: `sales_medallion` with its UUID | **the palette could only find OPEN documents.** A job or pipeline you had just looked at, then closed, was unreachable by name — so the scene now opens both from the Data tab first (the real flow), and the palette lists recently-opened infrastructure objects as well as open tabs. The assertion also had to compare group headings case-insensitively, because the palette renders them upper-case |

## What inspection found, in order of seriousness

1. **A refusal stated five times on one page** (S6). Every assertion passed. Five identical boxes read as
   five separate problems, which is precisely the rule 013's [UI-6] established for the rail. The fix
   needed a *fifth* `Block` state, because the alternative — reusing `empty` — is worse: it makes the page
   claim "this job has not run yet" about a read it never completed.
2. **The palette could not find an object by name unless its tab was open** (S9). The palette listed open
   documents and sessions; a job the agent had just built and the user had just closed was unreachable
   except by searching the rail again. `[UI-5]` said "a tool call that names an object opens it"; this is
   the other half — an object you have opened should stay findable.
3. **A job rendered as a file in the mission's outputs** (S7). `MissionScreen`'s output row was
   `notebook ? <Notebook/> : <FileIcon/>`, a two-way branch written when there were three kinds. The object
   was openable and its icon said it was something else.
4. **A page could not state a page-level refusal at all** (S6, found by tests before the picture). `Block`
   renders `error` only when its `state` says so, and the job page's `state` expression fell through to
   `empty` on a page-level failure — so the sentence was passed as `error` and never shown. A page that
   fails must say why, not that there is nothing to show.
5. **The run page did not name its job** (S3). A pasted `#/run/<id>` is a number without context.
6. **Two cross-page controls dispatched events nobody listened to** (`opengenie:open-lakebase` from 013's
   app page, `opengenie:open-job` from this spec's run page). A dead dispatch renders an ordinary button,
   so only a test finds it: `docFromOpenEvent` is now one mapping with a test that names both events.

Rows 1–4 are the kind a unit test does not find, and rows 1 and 4 both involved an assertion that passed
while the screen was wrong. That is the argument for looking at the pictures, stated as evidence rather
than as a preference.

## The rule a picture has to pass

From [11](../11-e2e-plan.md#the-rule-a-picture-has-to-pass): it shows the state it claims, nothing is
clipped, the state word is present, it is legible at 100 %, and it looks like the rest of the app. Every
file above was checked against all five, and the three defects in rows 1–3 were found by the *fourth* and
*fifth* criteria — which no assertion checks.
