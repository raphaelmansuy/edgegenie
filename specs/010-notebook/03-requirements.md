# 03. Requirements

[Index](README.md) · prev: [02](02-grounding.md) · next: [04 Wireframes](04-wireframes.md)

Each requirement names the test that fails if it regresses. Principles: [01](01-five-whys.md).

## The document

| ID | Requirement | Test |
|---|---|---|
| NB-1 | Command mode matches the chords in [01 P2](01-five-whys.md#p2-two-modes-and-they-do-not-share-a-letter): A/B, DD, GG, Shift+G, O, Shift+M, J/K/P/N, Shift+arrows, ⌘A, ⌘C/X/V, II, 00, H, Space, and the run chords. A second tap is required for D, G, I, and 0. Any other key disarms. | `cellkeys.test.ts` |
| NB-2 | Run all, Run above, and Run below are one walker. Above excludes the anchor. Below includes it. The first result that is not `succeeded` stops the walk. | `cellrun.test.ts` (`spanIds`), `EditorSurface` `runIds` |
| NB-3 | A cell whose source starts with `%skip` is omitted from every batch, with a reason that says so. Running that cell on its own executes the text after the directive. A cell that is only `%skip` cannot run. | `cellrun.test.ts`, `tests/test_cellrun.py` |
| NB-4 | The map has one bar per code cell. Markdown is not a bar. Tones are idle, skip, queued, running, ok, failed. First failed and last settled are the jump targets. The label is a heading, else a comment, else the first line. | `minimap.test.ts` |
| NB-5 | A result can be filtered by substring, sorted (numbers as numbers, blanks last either way), and copied as TSV of the *visible* rows. | `cellrun.test.ts` (`presentRows`, `toTsv`) |
| NB-6 | Merge joins a cell with the next and keeps the first cell's id, kind, and language. Split at the caret creates a cell; split at the end does not. | `notebook.test.ts` |
| NB-7 | `%skip` imported from SOURCE stays a directive in the notebook's language. It is not a language called `skip`. | `notebook.test.ts`, `tests/test_notebook_roundtrip.py` |
| NB-8 | A `%skip` Python cell is omitted from a batch, including as a dependency. When that cell is the one you asked to run, its body runs. | `tests/test_pyrun.py` |
| NB-9 | H in command mode opens the shortcut sheet, and the sheet has a Command mode section taken from `COMMAND_HELP`. | `ShortcutSheet.tsx`, scene [S5](./10-e2e-plan.md) |
| NB-10 | The Run control on a cell that cannot run is disabled and its title is the reason. No control offers a cluster, a debugger, or share. | existing `runAffordance` tests; [V1](./06-lenses.md) |

## While it runs

| ID | Requirement | Test |
|---|---|---|
| NB-11 | The bar's sentence counts the batch in flight, not the whole notebook. | `runAllLabel` fourth argument |
| NB-12 | Stop (the button, or II) ends the walk between cells. Cells already running report; cells not started do not start. | `runIds` reads `stopAll` between cells; scene [S2](./10-e2e-plan.md) |
| NB-13 | Run all clears every output first. A span clears only the cells it will run, so an earlier result stays. | `EditorSurface.runIds` |

## What "better" means here

| ID | Requirement |
|---|---|
| NB-14 | The map's list names the cell. Databricks' minimap does this on hover; ours is also a button, so it is not hover-only. |
| NB-15 | A skipped cell says why *before* you press Run all, in the bar's skipped count and in the map. |
