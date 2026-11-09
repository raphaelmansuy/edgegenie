# 010. The notebook, as a document

**A specification and the implementation: make OpenGenie's notebook the thing Databricks documented
on 27 October 2026 — a document you select, run in ranges, skip on purpose, and read from a map —
without inventing a cluster, a debugger, or a share button the app cannot honour.**

> **Status:** implemented and inspected, 9 November 2026.
> **Why this is 010:** [008](../008-github-page/README.md) is the public site and
> [009](../009-attach-file-clipboard-support/README.md) is attachments. This folder is the notebook.
> **Sources:** [Navigate the notebook editor](https://docs.databricks.com/aws/en/notebooks/notebook-editor)
> (updated 27 Oct 2026), [Run notebooks](https://docs.databricks.com/aws/en/notebooks/run-notebook),
> [Notebook outputs](https://docs.databricks.com/aws/en/notebooks/notebook-outputs).
> **Builds on:** [003](../003-improve-dev-ux-ui/README.md) (cells), [006](../006-databricks/README.md)
> (run, output, fix), [007](../007-ux-ui-improve/README.md) (keys and scroll).

---

## The one sentence

> Press Esc and the cell is a thing you can move, run, and skip; press Run all and the notebook stops
> at the first failure, names what it left out, and shows you where that failure is.

---

## Read in this order

| # | Document | Answers |
|---|---|---|
| 01 | [Five whys and first principles](01-five-whys.md) | Why a notebook is not a list of editors |
| 02 | [Grounding](02-grounding.md) | What the code already did, and what the Oct 2026 docs add |
| 03 | [Requirements](03-requirements.md) | `NB-*`, each with its test |
| 04 | [Wireframes](04-wireframes.md) | The bar, the cell, the map, the result |
| 05 | [Diagrams](05-diagrams.md) | Sequence, state, ER |
| 06 | [Lenses](06-lenses.md) | Eight owners, and the one thing each vetoes |
| 07 | [Architecture](07-architecture.md) | `[D1..D8]`, DRY and SOLID |
| 08 | [Implementation plan](08-implementation-plan.md) | The order the code was written in |
| 09 | [Edge cases](09-edge-cases.md) | What was envisioned, and the two limits we will not fake |
| 10 | [E2E plan](10-e2e-plan.md) | Scenes, and the inspection loop |
| 11 | [Outcome](11-outcome.md) | What the screenshots changed |

A requirement is `[NB-3]`, a decision `[D4]`, an edge `[E-7]`, a scene `[S2]`, a principle `[P2]`,
a veto `[V5]`. Each id is defined once.

---

## What this is

The editor already had cells, command mode for a handful of keys, Run all for SQL, outputs, and
Fix with agent ([006](../006-databricks/14-genie-code-gap-analysis.md)). What it did not have is the
document Databricks describes: a map of execution, a run that means "above" or "below", a cell the
author marked `%skip`, and a result you can filter without leaving the cell.

---

## What this is not

A cluster picker, a debugger, widgets, comments, schedule, and share. Each of those needs a
capability this app does not have. Drawing the control would be the inert-button bug
[006](../006-databricks/00-why-first-principles.md) already forbids. They are listed in
[09](./09-edge-cases.md) so they are not rediscovered as bugs.
