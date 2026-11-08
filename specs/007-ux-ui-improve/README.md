# 007 — The shell, the keys, and the scroll

**Status:** spec + implementation plan, then implementation (this folder is the record).
**Scope:** the *shell* only — zones, controls, scrolling, keyboard, focus. Not the agent, not the
notebook model, not the backend. Those are 003 and 006 and are cited, not restated.

---

## What this folder is

A cross-referenced set, written to be read in any order but complete when read in this one:

| # | Document | Answers |
|---|---|---|
| 01 | [Five whys and first principles](01-five-whys.md) | Why does this work exist at all, and what is irreducible? |
| 02 | [Measured assessment](02-assessment.md) | What is actually wrong, in numbers, with the file and line |
| 03 | [Requirements](03-requirements.md) | What must be true when it is done (`SH-*`, `KB-*`, `SC-*`, `ZN-*`) |
| 04 | [Wireframes (ASCII)](04-wireframes.md) | What each zone and each navigation state looks like |
| 05 | [Diagrams (Mermaid)](05-diagrams.md) | Sequences, states, and the data model of a view |
| 06 | [Six lenses](06-lenses.md) | The same system seen by six different owners |
| 07 | [Architecture](07-architecture.md) | Where each rule lives in the code, and why there |
| 08 | [Implementation plan](08-implementation-plan.md) | Phases, files, tests, order |
| 09 | [Edge cases](09-edge-cases.md) | Every failure I could name, its mitigation, its test |
| 10 | [E2E plan](10-e2e-plan.md) | The scenes, the screenshots, the pass criteria |
| 11 | [Outcome](11-outcome.md) | What shipped, and the four defects the screenshots found |
| 12 | [Hidden panels](12-hidden-panels.md) | `ZN-7`/`ZN-8`: a panel that can be hidden must be findable again |
| 13 | [Math](13-math.md) | `MD-1`…`MD-6`: LaTeX in markdown, and what "clunky" actually is |

Cross-reference convention: a requirement id is cited as `[SH-3]`, a decision as `[D7]`, an edge
case as `[E-12]`, a scene as `[S4]`. Every id is defined exactly once and linked from everywhere
else. If a document cites an id that is not in `03`/`09`, that is a bug in the document set.

---

## The one sentence

> A shell is finished when the user can reach every control and every pixel of content without a
> mouse, without losing their place, and without the app moving under their hands.

Everything below is an argument about that sentence. The assessment in `02` finds four places where
this app fails it today; the plan in `08` fixes those and nothing else.

## Prior art inside this repository

- `../006-databricks/15-shell-zones-audit.md` rounds 1–4 — what the zones became, and the four
  regressions found on the deployed app. This spec starts where that one ends.
- `../006-databricks/04-assistant-dock.md` — why the conversation is a column, not an overlay.
- `../001-perfect-shell` (if present) — the original separator/keyboard contract `SH-A1..A6`.
- `web/src/domain/layout.ts` — the only place a column width is decided. Untouched here.
