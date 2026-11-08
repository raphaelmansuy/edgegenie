# 13 · The UX assessment, graded and iterated

[Index](README.md) · prev: [12 E2E and screenshots](12-e2e-plan.md) · next: [14 Genie Code gap analysis](14-genie-code-gap-analysis.md)

The request was: *assess any gaps with Databricks, bring the best possible UX/UI as of November 2026,
and use a proven iterative process to improve.* This document is that assessment, and the record of
what the iteration actually changed.

The method is a **graded rubric measured from the rendered DOM**, not an opinion. It is imperfect — it
cannot tell good spacing from bad — which is why every score is paired with a screenshot a person
still has to look at. Its value is that it is *repeatable*: run it before, run it after, and the diff
is the argument.

```bash
cd apps/coding-agent/web
APP_URL=http://127.0.0.1:8061 node scripts/ux-scorecard.mjs /tmp/score
```

---

## The rubric

26 items, 100 points, in six groups. Each is either true in the DOM at that width, or it scores zero.

| Group | Pts | What it is about |
|---|---|---|
| **context** | 25 | is the conversation visible beside the work, and does it state its subject |
| **model** | 12 | is the current model always visible and changeable, and is a switch explained |
| **execution** | 20 | can a cell run, show its output in place, state its timing, and be cleared |
| **agent** | 12 | are tool calls visible, is a failure actionable, is an approval answerable inline |
| **find** | 12 | tree and list, palette, `@` from where you are, recent work |
| **craft** | 19 | keyboard coverage, chrome ≤ 150 px, no overflow, no dead controls, dark mode |

The weighting is deliberate: **execution and context are 45 points between them**, because those are
the two things a coding assistant is judged by. A beautiful shell that cannot run a cell is not a
notebook.

---

## The score, measured

| | 1600 | 1180 | 1024 | 760 |
|---|---|---|---|---|
| **before this iteration** | 57 | 56 | 58 | 56 |
| **after** | **100** | **86** | **86** | 57* |

\* the 760 figure is not trustworthy — see [What the instrument cannot see](#what-the-instrument-cannot-see).
The narrow layout was verified by screenshot instead ([e2e/screenshots](e2e/screenshots)).

By group, at 1600 px:

| Group | Before | After |
|---|---|---|
| context | 63 | **100** |
| model | 40 | **100** |
| execution | **0** | **100** |
| agent | 24 | **100** |
| find | 36 | **100** |
| craft | 67 | **100** |

---

## The four gaps the assessment found, and what closed them

### G1 · A notebook could not run, so it was a code list — 20 points

**Gap.** Databricks' defining notebook feature is that a cell runs and shows its output beneath it.
Ours had nowhere for a result to go: the answer arrived in a different pane, and before
[006 P5](09-implementation-plan.md#p5-no-inert-controls-s) the run button did nothing at all.

**Closed by.** A real execution path, not a simulation:

- `api/domain/cellrun.py` — what a run *is*: state, duration, rows, and the engine's own words on
  failure. Pure, so every ugly case is tested without a warehouse.
- `POST /api/notebook/run-cell` — SQL on a warehouse, as the signed-in user, through the same
  `_pick_warehouse` the table preview uses (one definition, so the two cannot disagree).
- `web/src/domain/cellrun.ts` + `CellOutput.tsx` — the badge, the table, the message, the clear and
  the fold, all decided in the domain.

**Verified against the live warehouse**, not a fake:

```text
select 1 as one, 2 as two   →  done · 1 row · 2.5s · Serverless Starter Warehouse
                               one  two
                               1    2

print(1)                    →  not run · "python cells need a cluster. Ask the agent to run it,
                               or write the query as SQL to run it here."

select * from main.s.nope   →  failed · [TABLE_OR_VIEW_NOT_FOUND] The table or view `main`.`s`.`nope`
                               cannot be found. Verify the spelling…
```

**The rule that made it honest:** a control that cannot act is not offered. A Python cell's run button
is disabled with the reason in its title, and the server refuses it as a *state with a reason*, not an
error. That is [006 00 P4](00-why-first-principles.md) applied to the one control most likely to lie.

### G2 · The model's pin was a toast that disappeared — 12 points

**Gap.** Switching models said "Applies to your next message" in a toast, then the toast vanished. The
user is left guessing which model will answer, especially when the answer on screen came from the
previous one. Genie Code does not let you change models at all, so this is a place to be clearly
better rather than merely equal.

**Closed by** a **persistent pin**: when the last turn's model differs from the one that will answer
next, the dock says so, above the message box, and stays until it is no longer true:

```text
next message uses gemini-3.8-flash · the answer above came from llama-4-maverick
```

### G3 · A search that took four seconds looked frozen — craft and find

**Gap found while measuring.** The workspace has no name-search endpoint, so a search walks folders and
takes **4.2 seconds** on a real workspace. During that time the user saw four anonymous skeleton bars.
Four seconds of grey bars reads as *broken*, not as *working*.

**Closed by** making the wait state say what it is doing, and for how long:

```text
⟳ searching for "e2e" …                                    3s
[ skeleton ][ skeleton ][ skeleton ][ skeleton ]
This workspace is large, so folders are walked in order. The first matches appear as they are found.
```

### G4 · Two real bugs the rubric's scenarios exposed — correctness

Neither was visible in a screenshot; both came from *using* the product while measuring it.

**B1 · The notebook header became "cell 1", and running it failed.** An imported notebook whose first
line was `# Databricks notebook source` parsed that line as a cell. Pressing run sent it as SQL and the
warehouse answered `[PARSE_SYNTAX_ERROR] Syntax error at or near '#'`. Two fixes:

1. the parser strips the header whatever comment prefix the file uses (`--` *or* `#`), because the
   prefix is a property of the file, not of the language we were asked to parse;
2. a block that is *only* the header is not a cell — provenance is not executable code.

**B2 · The tree search never completed.** Depending the search effect on `roots` — a fresh array on
every render — aborted the in-flight request on each render, so the list stayed on its skeleton
forever. It only ever "worked" because the dependency list used to be shorter. The effect now depends
on the root **path**, a primitive that changes when the workspace does and not before.

---

## How the iteration actually went

Five rounds, each ending in a measurement. Recorded because the *process* is what was asked for, and
because four of the five rounds found that the instrument was wrong before the product was.

| Round | Change | Score at 1600 |
|---|---|---|
| 0 | baseline | 57 |
| 1 | cell execution (G1) | 57 — *the scorecard was opening a file, not a notebook* |
| 2 | scorecard finds a notebook | 60 |
| 3 | run a cell, not just render the button | 74 |
| 4 | wait for a *finished* run, not the element | 78 |
| 5 | session created before scoring; pin (G2); search state (G3) | **100** |

**The pattern worth keeping:** in rounds 1–4 the product was already working and the *measurement* was
lying — a wrong selector, a wrong element, a wait that returned too early. Each time, the honest move
was to fix the instrument and re-measure rather than to change the product to satisfy a broken ruler.
The two bugs in G4 are the exception: those were real, and the scorecard found them by accident
because it insisted on doing what a user does.

---

## What the instrument cannot see

Stated plainly, because a 100% score invites exactly the wrong conclusion.

| Blind spot | Why it matters |
|---|---|
| **Spacing, rhythm, colour harmony** | The rubric counts elements, not craft. A cramped layout scores the same as a generous one. This is why every round ended with a screenshot that was looked at. |
| **The 760 px score** | The narrow layout puts the navigator and the assistant in mutually exclusive drawers, so a scripted run cannot reach a notebook and scores the empty state. The layout was verified by screenshot; the number is not quoted as a result. |
| **Whether the answer was any good** | It grades the surface, not the agent. A perfect shell around a bad model is still a bad assistant. |
| **Delight** | No rubric in this document measures the feeling of using it. |

The score is a *floor*, not a ceiling: it says the things a 2026 coding surface must have are present
and reachable. It does not say the result is beautiful.

---

## What is still behind Databricks, deliberately

| Gap | Why it is still open |
|---|---|
| **Python/Scala cell execution** | Needs a cluster and a runtime this app does not own. The refusal names what would work. Running arbitrary code on the app's own compute would be a security hole, so this is a scope decision, not an oversight. |
| **A cluster picker, notebook scheduling, widget UI** | A workspace feature set. We are the assistant that works *in* a workspace, not a replacement for it. |
| **A results cache across reloads** | Output is per-document and in memory. Persisting it belongs with [P6](09-implementation-plan.md#status-what-is-built), which is specified and not built. |
| **Collaborative cursors** | [004](../004-crdt-collaboration/README.md) owns it. |

---

## What we do better than Databricks, measurably

Not a claim of superiority overall — a list of specific, checkable advantages, each with a test.

| Ours | Databricks [observed] | Evidence |
|---|---|---|
| The model is chosen, pinned per turn, and the pin is stated | no model choice at all | [07](07-model-selection.md), `dock-pin` |
| The write fence is on screen before the first keystroke | no equivalent concept | `fence-chip` |
| A failed turn keeps its model and offers Retry / Change model | — | scene 6 |
| The dock states its binding and the binding is data | `in context:` chip | [04](04-assistant-dock.md) |
| A search that says what it is doing and for how long | no progress narration | `tree-search-status` |
| A refusal names what would work instead | — | `cellrun.is_runnable` |

---

## What is published, and in what order to test it

Deployed to `coding-agent-7474654624275247.aws.databricksapps.com` on 8 November 2026, in the order
below. Each step is independently testable, so a failure names the feature.

| # | Published | Test it by | Expected |
|---|---|---|---|
| 1 | **Cell execution** (SQL on a warehouse, as you) | open a notebook from Files, press `run` on a SQL cell | a table under the cell, `done · 1 row · 2.7s · <warehouse>` |
| 2 | **A refusal that names the alternative** | press `run` on a Python cell | the button is disabled, tooltip says a cluster is needed, or the output says *not run* and what would work |
| 3 | **The conversation beside the document** | open any file | the dock stays on the right, chip says `in context: <file>`, the file is still visible |
| 4 | **Cell binding** | hover a cell, press `ask` | the chip becomes `<file> · cell 3`, the composer takes focus |
| 5 | **The model, always one control away** | look at the composer, then the top bar | a model control in both; the picker opens from either at any width |
| 6 | **The next-turn pin** | switch model, then look above the composer | `next message uses <model> · the answer above came from <other>` |
| 7 | **Files: tree and list** | Files tab → the two view buttons | a list with Name / Type / Folder, a breadcrumb, right-click for actions |
| 8 | **A search that says it is working** | type in the search box | `searching for "…" … 3s` with a spinner, then results |
| 9 | **`⌘J`** | press it at wide and at narrow width | hides and shows the assistant; at narrow it is a drawer that never opens by itself |
| 10 | **Both panels at a narrow width** | at ~900 px open the navigator, then the assistant | both open at once; neither covers the other |

**Verified live before publishing:** `POST /api/notebook/run-cell` returns
`{"state":"succeeded", "columns":["a"], "rows":[["1"]]}` from the serverless warehouse, and Python is
refused with a sentence naming SQL as the alternative. The deployed home screen renders 6 cards, the
dock, and 3 visible model controls, with no horizontal overflow.

## Re-running the assessment

```bash
cd apps/coding-agent/web
# a running app with a workspace token, then:
APP_URL=http://127.0.0.1:8061 WIDTHS=1600,1180,1024 node scripts/ux-scorecard.mjs specs/006-databricks/e2e/scorecard
```

The output is `scorecard.json` (per width, per item, pass or fail) plus a screenshot of each width in
light and dark. A change that lowers a score is a regression with a named item attached to it, which is
the whole point of grading rather than reviewing.
