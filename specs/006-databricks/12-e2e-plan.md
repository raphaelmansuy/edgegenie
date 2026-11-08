# 12 · E2E plan and screenshots

[Index](README.md) · prev: [11 Decisions and risks](11-decisions-risks.md)

"On par or superior" is only checkable if it is captured. This document defines the evidence: the
before/after measurement, eleven e2e scenes, and the screenshots that must exist and be looked at.

Everything in `e2e/` is generated. Nothing in `e2e/` is hand-placed, because a hand-placed screenshot
is a drawing of the feature rather than the feature.

---

## The measurement, before and after

Produced by [`web/scripts/dock-audit.mjs`](../../apps/coding-agent/web/scripts/dock-audit.mjs) against
the deployed app. Run before a change and after it; the diff is the argument.

```bash
cd apps/coding-agent/web
APP_URL=$APP_URL BEARER_FILE=/tmp/bearer.txt WIDTHS=1600,1180,1024,900,760 \
  node scripts/dock-audit.mjs ../../../specs/006-databricks/e2e/before   # or /after
```

### Before — measured 8 November 2026

Source: [`e2e/before/audit.json`](e2e/before/audit.json).

| | 1600 | 1180 | 1024 | 760 |
|---|---|---|---|---|
| turns rendered with a document open | **0** | **0** | **0** | **0** |
| transcript visible with a document open | no | no | no | no |
| composer visible | yes | yes | yes | yes |
| model control visible | yes | yes | **no** | **no** |
| interactions to open the model list | 1 | 1 | 1 (shortcut only) | 1 (shortcut only) |
| chrome above the first line of code | 146 | 146 | 146 | 146 |

The zeroes in the first row are the bug this spec exists to fix.

### After — measured, 8 November 2026

Produced by the same script and by `dock-e2e.mjs`, against a local run of the built app.

| | 1600 | 1180 | 1024 | 760 |
|---|---|---|---|---|
| turn rendered while a document is open | **1** | **1** | **1** | **1** |
| the conversation survives opening a file | **yes** | **yes** | **yes** | **yes** |
| model control visible | **3** | **3** | **2** | **2** |
| the picker opens from that control | **yes** | **yes** | **yes** | **yes** |
| picker fully on screen | **yes** | **yes** | **yes** | **yes** |
| `⌘J` hides and shows | **yes** | — | — | **yes** |
| a resize never opens the drawer | — | — | — | **yes** |
| inert `.cell-run` buttons | **0** | **0** | **0** | **0** |

**30 of 30 e2e checks pass**; the report is [`e2e/scenes/report.json`](e2e/scenes/report.json) and the
screenshots are [here](e2e/screenshots/).

The target table below was written before the work; it is kept because it is what the checks assert. The column that must
change, and the columns that must not:

| | 1600 | 1180 | 1024 | 900 | 760 | Requirement |
|---|---|---|---|---|---|---|
| turns rendered with a document open | ≥1 | ≥1 | ≥1 | ≥1 | ≥1 (drawer open) | AD-1 |
| transcript visible | yes | yes | yes (drawer) | yes (drawer) | yes (drawer) | AD-2 |
| model control visible | yes | yes | **yes** | **yes** | **yes** | MC-1 |
| chrome above the first line of code | ≤150 | ≤150 | ≤150 | ≤150 | ≤150 | UX-2 |
| dead controls | 0 | 0 | 0 | 0 | 0 | UX-1 |
| dock width | 380 | 380 | overlay | overlay | overlay | AD-9 |

**A failure in the last three columns is a failure of this spec.** A failure in the chrome row is a
regression of [003](../003-improve-dev-ux-ui/08-databricks-gap-assessment.md).

---

## The measured widths (the layout the screenshots show)

```text
1600  rail 276 · centre 601 · inspector 340 · dock 380   four columns, all content
1180  rail 276 · centre 903 · inspector  -   · dock 420   the inspector yields to the conversation
1024  rail 276 · centre 747 · inspector  -   · dock 420   the dock is a drawer over the centre
 760  rail   -  · centre 760 · inspector  -   · dock 420   both side zones are drawers
```

At 1600 the four columns sum to 1597 of 1600 px, and the centre is 601 px — comfortably above
`CENTRE_MIN` (480). At 1180 the inspector has no column: that is [correction C1](11-decisions-risks.md#c1-three-columns-do-not-fit-at-1180-px),
and it is why the conversation is beside the code at every width instead of only above 1476.

## The eleven scenes

`web/scripts/dock-e2e.mjs`. Each scene is one assertion a person could describe in a sentence, so a
failure names a user-visible behaviour rather than a selector.

| # | Scene | Asserts | Requirement |
|---|---|---|---|
| 1 | **Fresh load** | no session is created; the dock shows suggestions for "nothing open"; nothing is modal | AD-5 |
| 2 | **Open a document** | the file renders in the centre; the dock chip names it; the Chat tab still exists and shares the session | AD-1, AD-6, FX-2 |
| 3 | **Ask about it** | a session is created with the focus as binding; the answer streams into the dock; the file stays visible the whole time | AD-5, FX-4 |
| 4 | **Bind a cell** | clicking `ask` on cell 2 makes the chip `… · cell 2` and focuses the dock composer | NB-1, FX-3 |
| 5 | **The agent writes** | the tool call writes the file; the open document reloads in place (rev bump) without losing the dock | AD-1 |
| 6 | **Approve inline** | an outside-folder write shows the approval in the dock; `Deny` reaches the endpoint and the agent is told | AD-8 |
| 7 | **Hide and show** | `⌘J` toggles the column at 1600 and the drawer at 760; the scroll position is kept | AD-3, AD-9 |
| 8 | **Never by itself** | resizing 1600→760 does not open the drawer | AD-4 |
| 9 | **Change the model** | the composer's control opens the picker; choosing one switches the next turn; the label updates in both triggers | MC-2, MC-3 |
| 10 | **Reload keeps it** | after a reload, the turns, the binding and the pinned model are all still there | PS-1, PS-2 |
| 11 | **Nothing is dead** | every visible button in the three panes has an observable effect | UX-1 |

**Scene 5 is the one that proves the product claim.** It is the only scene that shows the cycle the
request described: read → ask → the file changes → read again, without leaving the screen.

---

## Screenshots that must exist

Saved under `specs/006-databricks/e2e/after/`, named for what they show. Every one is inspected before
it is committed; a screenshot nobody looked at is a screenshot that lies.

| File | What it must show | Why it is on the list |
|---|---|---|
| `01-empty.png` | fresh load, dock with suggestions, nothing modal | the first impression |
| `02-doc-and-dock.png` | a notebook in the centre, the conversation on the right, the chip naming the file | **the thesis** |
| `03-cell-bound.png` | the chip naming a cell, the cell highlighted | the "in context to update" claim |
| `04-streaming.png` | a turn mid-answer in the dock | the dock is a live surface, not a log |
| `05-asking.png` | the inline approval | D4's deliberate inconsistency |
| `06-failed.png` | a provider error with `Retry` and `Change model` | the failure is designed, not default |
| `07-drawer-1024.png` | the dock as a drawer at 1024 | mid breakpoint |
| `08-narrow-760.png` | the dock as a drawer at 760, `⌘J` printed on the bar | narrow breakpoint |
| `09-model-composer.png` | the model picker open from the composer | the third request |
| `10-model-narrow.png` | the model control visible at 760 | MC-1 |
| `11-files-list.png` | the list view with four columns and a breadcrumb | parity |
| `12-dark.png` | 02 in dark theme | one design, two themes |
| `13-zoom-200.png` | 760 at 200 % zoom | E-11 |

The before state is already captured: [`e2e/before/`](e2e/before/) holds `w1600.png`, `w1180.png`,
`w1024.png`, `w760.png` and their `-doc.png` counterparts, plus `audit.json`.

---

## How the numbers are produced (and why they can be trusted)

`dock-audit.mjs` does not read CSS; it reads the rendered DOM:

| Number | Measurement |
|---|---|
| `transcriptVisibleWithDocOpen` | `getBoundingClientRect()` of `.transcript` has non-zero width and height, **with a document open** |
| `turnsRenderedWithDocOpen` | `document.querySelectorAll(".turn").length` at that moment |
| `modelChipVisible` | the trigger's rect width `> 0` |
| `modelInteractions` | click the trigger, then `isVisible(".picker")`; if the trigger is hidden, try `⌘⇧M` and record which path worked |
| `chromePx` | `top` of the first `.cm-content` / `pre.code`, i.e. the first line of code |
| `deadControls` | `.cell-run` count, plus the `dead-controls.e2e.mjs` walk |

Two honest limitations, stated because the alternative is a number that flatters the design:

1. **A measurement needs a session.** The audit sends one trivial prompt first, so a slow agent makes
   the audit slow. It records "no turn appeared" rather than failing, which means a scene can silently
   measure less than it claims — hence the screenshot check beside every run.
2. **`chromePx` depends on a document being open.** The first version of this script reported `null`
   at every width because it clicked a folder instead of a file; the fix is in the script's comment. The
   lesson is recorded in the script, not just here.

---

## The human check, which no number replaces

The five-minute test from [08 PO](08-lenses.md#1-product-owner), run once per release:

```text
Hand someone the app and a notebook. Say only: "make this notebook compute revenue by hour".
Watch. Do not help.

Failure signals
  · they look for a "Chat" tab                     → the dock did not announce itself
  · they open a file and the conversation vanishes → the bug is back
  · they ask where the model is                    → MC-1 regressed
  · they cannot find where the agent will write    → the fence regressed
  · they hunt for a way to run a cell              → R-7 (the removal needs a sentence somewhere)
```

Recorded as a note in this file per release, with the date and what happened. It is the only evidence
that covers the gap [R-5](11-decisions-risks.md#r-5-on-par-or-superior-is-still-an-adjective-medium)
names.

---

## CI

```bash
cd apps/coding-agent/web
npm run verify:spec-006     # links + anchors + ASCII alignment + wireframe generator
npm run verify:spec-mermaid # every mermaid block parses
npm run audit               # a11y + overflow + shell + CLS
npm run e2e:assistant       # the eleven scenes (needs a running app)
npm test                    # vitest
cd .. && .venv/bin/python -m pytest -q
```

`verify:spec-006` must pass before a document change is merged; `e2e:assistant` before a UI change is
deployed. The audit is run manually before and after, because it needs a real workspace and a bearer
token — that is the price of measuring the deployed app rather than a mock.
