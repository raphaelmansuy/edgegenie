# 02. Grounding

[Index](README.md) · prev: [01](01-five-whys.md) · next: [03 Requirements](03-requirements.md)

What was true in the tree before this work, and what the current Databricks docs add. Nothing here is
a guess about a screen I did not read.

## What Databricks documents (27 Oct 2026)

Read from the live docs, not from memory:

| Fact | Where |
|---|---|
| Edit mode and command mode. Esc leaves the text. Enter enters it. | notebook-editor |
| Command mode: A/B insert, DD delete, GG first, Shift+G last, O toggles output, Shift+M merges, ⌘C/X/V, ⌘A, Shift+arrows extend, II cancels, 00 clears, H opens shortcuts, Space scrolls | notebook-editor, command-mode table |
| Shared: Shift+Enter run and advance, ⌘Enter run selected, Alt+Enter run and insert, Alt+Shift+Enter run all, Alt+Shift+Up run above (exclusive), Alt+Shift+Down run below (inclusive) | notebook-editor, shared shortcuts |
| On a SQL warehouse, a multi-cell run stops at the first error. Interrupt stops the rest. | run-notebook, "Runtime 14+ or a SQL warehouse" |
| `%skip` leaves a cell out of Run all, Run above, and Run below | run-notebook |
| A result table can be searched, sorted, and copied | notebook-outputs |
| The execution minimap paints one bar per executable cell: idle, skipped or queued, running, success, failure. Hover lists titles. Click jumps. "First failed" and "Last run" are explicit. | notebook-editor, "Cell execution minimap" |

Cell titles in Databricks are metadata. Our SOURCE round-trip has no field for them
(`api/domain/notebook.py`). The map therefore *derives* a label from a heading, a comment, or the
first line of code ([D5](./07-architecture.md#d5)). A title you type and that a save would drop is
not a title.

## What the app already did

| Piece | Where | Still true |
|---|---|---|
| Cells, SOURCE round-trip | `web/src/domain/notebook.ts`, `api/domain/notebook.py` | yes, plus `%skip` kept as a directive |
| A short command mode (A B DD M Y arrows Enter run chords) | `web/src/domain/cellkeys.ts` | extended, not replaced |
| Run all, stop on first SQL failure, Python as one job | `EditorSurface.tsx` | now any list of ids, not only "all" |
| Output under the cell, Fix with agent | `CellOutput.tsx` | plus filter, sort, copy |
| Run all bar, warehouse chip, clear | `NotebookBar.tsx` | the count is the batch while a span runs |

## The gap this spec closes

1. Command mode did not match the published table: no GG, Shift+G, O, Shift+M, clipboard, selection, II, 00, H, Space, or the Alt+Shift run chords.
2. There was no Run above / Run below.
3. `%skip` was parsed as a language named `skip`, so the cell could not run and the directive was lost on the way back to SOURCE.
4. There was no execution map.
5. A result table could not be filtered, sorted, or copied.

## What was deliberately left

Debugger, variable inspector, widgets, comments, schedule, share, notebook-wide find, Unity Catalog
autocomplete. See [09](./09-edge-cases.md) and [V1](./06-lenses.md).
