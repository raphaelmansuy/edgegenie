# 08 · UX/UI gap assessment against Databricks

[Index](../README.md) · related: [01 Current state](../01-current-state-audit.md) · [02 Requirements](../02-requirements.md)

Assessment of the implemented editor surface against the Databricks notebook UI, measured on
7 November 2026. Every number below came from `getBoundingClientRect`, not from looking.

The reference is the Databricks workspace notebook: tab strip, a compact toolbar, cells with a
per-cell run affordance, and Genie Code as a right-hand assistant.

---

## The headline number

**234 px of vertical chrome before the first cell**, in a 900 px viewport. That is 26 % of the
window spent on things that are not the document.

| Band | Height | What it holds |
|---|---|---|
| topbar | 52 | brand, model, search, layout menu, theme, shortcuts, refresh |
| doc tabs | 38 | open documents |
| **viewer head** | **128** | filename, language badge, reload, path, 6 action buttons |
| editor bar | 40 | fence chip, dirty state, Save |
| **total** | **234** | |

Databricks spends about **150 px** on the equivalent (tab strip + one toolbar row), and puts the
document actions in that toolbar rather than in a block above the document.

The `viewer-head` is the outlier and the clearest defect: **128 px** to show a filename and six
buttons, three of which (`Explain`, `Fix errors`, `Document`, `Optimize`) are *prompts* that belong
behind one "Ask" control, not four equal-weight buttons competing with the file name.

---

## Gaps, in order of impact on the experience

### G1 · The header is a block, not a bar (128 px)

Databricks: one row. Ours: three stacked rows (title, path, six buttons), because the action buttons
wrap.

The buttons are also the wrong *kind* of control. `Explain / Fix errors / Document / Optimize` are
four variations of "ask the agent to do something to this file". Databricks would express that as a
single assistant affordance. Four buttons:
- consume the width that forces the wrap;
- imply four equal-weight outcomes when they are variations of one;
- and sit above the code, so they compete with it for attention.

### G2 · No per-cell output, and no cell execution state

Databricks shows, under each cell: the output (a table, a chart, text), the elapsed time, and a run
counter (`[14]`, `[15]`). Ours has a run affordance per cell but **nowhere for a result to go** — the
answer arrives in the transcript in the middle pane, which means:
- you cannot see code and its output together;
- running a cell moves your attention to a different pane;
- the "notebook" is really a code list.

This is the single biggest functional gap, and it is why the surface reads as a *code editor with
cells* rather than a notebook.

### G3 · The tab strip is thin on identity

Databricks tabs carry a notebook icon, a language dot, a modified marker, and a close affordance on
every tab. Ours carries an icon and a close. No dirty marker, no language, no path on hover.

The dirty marker matters most: with cells editable and saves debounced, "which of my open documents
has unsaved work" is a question the strip should answer.

### G4 · No breadcrumb

Databricks shows `demo / display_unity_catalog_tables` above the editor. Ours shows the raw absolute
path as a copy button. The path is useful (it is the fence) but a breadcrumb also answers "where am
I" at a glance, which a single truncated string does not.

### G5 · The assistant pane is context-only

Databricks' right pane is Genie Code: a chat with suggestions, history and connectors. Ours is the
inspector: session metadata, working scope, skill reads. The *conversation* is in the centre pane.

That is a deliberate 003 decision (the editor replaces the transcript in the centre), but it means
the right pane is inert — you cannot ask from it. A person reading Databricks will look right and
expect to type.

### G6 · Cell controls have no language switcher

Databricks has a `Python ▾` control per cell (Python / SQL / Scala / R). Ours shows the language as a
static badge. A `%sql` cell in a Python notebook is common enough to warrant the control.

### G7 · Nothing shows execution history or timing

Databricks numbers runs and shows `Completed in 4.2 s`. Ours shows a run button with no feedback
until the transcript updates.

---

## What we do better, and should not lose

Stated because a gap assessment that only lists deficits invites regressions:

| Ours | Why it matters |
|---|---|
| **The write fence is visible before you type** (`in your folder` / `no session — will ask`) | Databricks has no equivalent concept. It is the product's promise, and it is on screen. |
| **Per-cell attribution** (`agent wrote this · ran 4.2s`) | Tells you who changed what, in the surface where you would change it. |
| **Draft recovery** | An unsaved buffer survives a reload and is offered back. |
| **Keyboard-first**: ⌘S, ⌘K, ⌘↵, ⌘B/⌘I, ⌘/ | Databricks' notebook is mouse-heavy. |
| **A real conflict story** (a choice, never a verdict) | Databricks relies on a single writer. |
| **Diff review** (planned, P5) | No equivalent. |

---

## The fix plan, in order

Each item is measured before and after; the target is **≤ 160 px** of chrome, down from 234.

| # | Change | Expected saving | Requirement |
|---|---|---|---|
| F1 | Collapse `viewer-head` into **one bar**: name, language, path, and a single **Ask ▾** menu holding the four prompts | **128 → 40** | ED-7, UX-1 |
| F2 | Move the fence chip and Save into that same bar (drop the separate editor bar) | **40 → 0** | WR-5 |
| F3 | Add a **dirty dot** to tabs | — | CX-5 |
| F4 | Show the path as a **breadcrumb**, not one raw string | — | UX-1 |
| F5 | Add a **per-cell output slot** (result, timing, run number) | — | NB-6 |
| F6 | Add a **language control** per cell | — | NB-2 |

F1 and F2 are the ones that change how the app *feels*: they take 168 px of stacked blocks and make
them 40 px of one bar, which is what Databricks looks like.

> **F5 is the largest job and the largest win.** Without an output area a notebook is a code list.
> It requires `doc_run_cell` to return its result to the cell rather than only to the transcript,
> which is a real change to the run path — see [03 P4](../05-implementation-plan.md).

---

## What this assessment does not claim

- It does not claim Databricks is the ideal. Its right pane is a marketing surface
  ("Connect your tools"), and its notebook has no fence, no attribution and no draft recovery.
- It does not ask to copy the visual language. Ours is deliberately warmer and quieter; the target
  is *density and structure*, not colour.
- It does not cover the transcript or the palette, which 001 assessed.

[Back to the index](../README.md)
