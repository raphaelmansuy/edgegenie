[Index](README.md) · prev: [10 Roadblocks](10-roadblocks.md) · next: [12 Outcome](12-outcome.md)

# 11 · E2E plan and screenshots

Eight scenes. Each asserts its own pass criteria **before** it takes a picture, so a scene cannot save a
pretty image of the wrong state. The pictures go to [`e2e/screenshots/`](e2e/screenshots/), and each one
is inspected and recorded in [that folder's README](e2e/screenshots/README.md).

That README's "what inspection changed" column is the point of the whole exercise: [012] found five
defects by looking at pictures every assertion had passed.

---

## How the scenes run

```bash
cd apps/coding-agent
# 1. the app, with the deterministic agent
APP_AGENT_MODE=fake APP_DEV_USER=you@example.com APP_DEMO_SCENARIO=notebook \
  .venv/bin/python -m uvicorn api.main:app --host 127.0.0.1 --port 8062

# 2. the scenes (they create their own sessions through the app's own API)
cd web && node scripts/lakebase-e2e.mjs http://127.0.0.1:8062
```

The scenes need the two object pages to have data, and a real workspace is not available in CI. So:

| Layer | In the scenes | Why |
|---|---|---|
| the **tools** | a fake app server replaying recorded ACP updates (`api/adapters/fake/scenarios/lakebase.json`, **new**) | deterministic, no model, no workspace |
| the **API routes** | `page.route('/api/lakebase/**')` with fixtures from `web/scripts/fixtures/lakebase.json` | the page's states are what is being photographed |
| the **shell** | the real app, the real rail, the real dock | the layout must be the real layout |

A scene that mocks the shell proves nothing about the shell. A scene that needs a workspace cannot run in
CI. The line is drawn at the API.

**Fixtures are recorded, not invented.** `web/scripts/fixtures/lakebase.json` holds the payloads a real
workspace returned (captured once, with the field names the adapter reads). A field the platform does not
send is not in the fixture, so a page that reads it shows `—` and the scene catches that.

---

## The scenes

### `[S1]` · The shell, with the new `Data` rail tab

**Question.** Does a fourth tab fit, and does it read as part of the navigator rather than bolted on?

**Pass criteria.**
1. Four tabs are present and their accessible names are `Sessions`, `Files`, `Catalog`, `Data`.
2. `⌘4` selects `Data`; `⌘1` still selects `Sessions`.
3. The rail is 276 px, the main column is ≥ 480 px, the dock is 380 px at 1480 px.
4. `document.documentElement.scrollWidth <= innerWidth + 2` (no horizontal overflow).
5. Each node kind in the tree renders a distinguishable glyph.

**Screenshot.** `s1-shell-data-1480.png`

---

### `[S2]` · A Lakebase project page

**Question.** Can a user tell what this project *is* and whether it is healthy, without asking the agent?

**Pass criteria.**
1. Six labelled blocks are present: project, compute, branches, databases, tables, used-by.
2. The compute block shows the range **and** the rule evaluated: `max − min = … ≤ 16`.
3. The branches block lists `production` marked as the default, and one other branch.
4. The "used by" block names the app and its permission verbatim.
5. No block renders `0` for a value it could not read — a missing field renders `—`.

**Screenshot.** `s2-project-1480.png`

---

### `[S3]` · A Databricks App page, running

**Question.** Does "is it working" have an answer on screen?

**Pass criteria.**
1. State is `RUNNING`, deployment is `SUCCEEDED`, and both are words not colours only.
2. The URL is an `<a href>` whose text is the host, not "click here".
3. The health row shows a status code and a duration, with the time it was taken.
4. The `/logz` link resolves to `https://{url}/logz`.
5. The resources block names the Lakebase branch and `CAN_CONNECT_AND_CREATE`.

**Screenshot.** `s3-app-1480.png`

---

### `[S4]` · Cold start: the app is waking

**Question.** Is a healthy-but-cold app distinguishable from a broken one?

**Pass criteria.**
1. The health block says `starting`, not `down` and not an error.
2. The block shows the elapsed time and the words "cold start".
3. The rest of the page is rendered normally (the state is local to the health block).
4. No red is used for this state anywhere on the page.

**Screenshot.** `s4-app-cold-1480.png`

---

### `[S5]` · A refusal: no `CAN MANAGE`

**Question.** Does a refusal tell the user who can fix it, and offer no dead end?

**Pass criteria.**
1. The platform's sentence is present **verbatim**, including `PERMISSION_DENIED`.
2. A line names the owner ("ask the project's owner").
3. Exactly one action is offered, and it is **not** a retry.
4. The composer still accepts a keystroke (the shell is not blocked by a page's failure).

**Screenshot.** `s5-refused-1480.png`

---

### `[S6]` · A scaffold, mid-flight

**Question.** Can a user see which of the seven steps is done, and that a step is only done with a proof?

**Pass criteria.**
1. Seven rows with keys `project, branch, table, resource, files, deploy, verify`.
2. Steps 1–4 are `✓`; step 5 is `▸`; steps 6–7 are `·`.
3. Every `✓` row has a proof value rendered beside it (not in a tooltip).
4. The dock's plan has the same states, and the two cannot disagree (asserted by comparing text).
5. No step is `✓` whose tool call is absent from the session's events.

**Screenshot.** `s6-scaffold-running-1480.png`

---

### `[S7]` · Narrow: 900 px

**Question.** Does the new tab survive the layout where the rail is a drawer?

**Pass criteria.**
1. At 900 px the rail is not a column; `☰` opens it as a drawer on the `Data` tab.
2. The dock keeps a 380 px column and the centre is ≥ 480 px.
3. Escape closes the drawer and focus returns to where it was.
4. No horizontal overflow at 900, 1180 and 1480.

**Screenshot.** `s7-narrow-900.png`

---

### `[S8]` · The palette finds the new objects

**Question.** Can a user who knows a name get to the object without the tree?

**Pass criteria.**
1. Typing `lakeb` lists projects under a `Lakebase` group.
2. Typing `tick` lists the app under `Apps`.
3. Choosing a row opens the right document (the URL changes to the expected hash).
4. A project with a display name that differs from its id is found by **either** string.

**Screenshot.** `s8-palette-1480.png`

---

## What each scene proves, and what it cannot

| Scene | Proves | Cannot prove |
|---|---|---|
| S1 | the shell accepts a fourth tab without breaking the arithmetic | that a user will find it |
| S2 | every fact on the page came from a call | that the facts are the *right* ones for a real project |
| S3 | the running state and its link | that the app genuinely serves traffic (that is `[AP-4]`, tested at the adapter) |
| S4 | a cold start reads as waking | the real latency of a real cold start |
| S5 | a refusal is a state with an owner | the platform's exact wording on a different workspace |
| S6 | the step rule is visible and honest | that the agent chose the right steps |
| S7 | the layout arithmetic holds with four tabs | the feel at 900 px with a real pointer |
| S8 | the palette finds the objects by name and id | the ranking on 400 projects |

The pattern in the right column is the same one [012] recorded: a scene proves a mechanism, not a
judgement. The judgements live in the screenshots' inspection notes.

---

## The screenshots, and the rule for accepting one

A picture is accepted when all of these are true, and the README records which one failed if not:

1. **It shows the state it claims.** The scene asserts it; the picture is the evidence.
2. **Nothing is clipped.** No label truncated to `…` where the truncation hides the meaning; no control
   under 24 px; no text overlapping a border.
3. **The state word is present.** A colour is never the only carrier of a state.
4. **It is legible at 100 %.** No 9 px text, no grey-on-grey below the contrast floor that
   `a11y-audit.mjs` enforces.
5. **It looks like the rest of the app.** Same header height, same row rhythm, same button shapes — a new
   page that invents its own chrome is a bug even when every assertion passes.

## Iteration log

The log is kept in the screenshots' README, one row per file, with the number of looks it took. A file
that took one look and changed nothing is recorded as such, because "inspected, nothing to change" is a
result and an empty column is not.
