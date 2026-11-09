# 07. Architecture

[Index](README.md) · requirements [03](03-requirements.md) · plan [08](08-implementation-plan.md)

## D1

A notebook on screen is a list of cells. The SOURCE text is produced when we save, by the serializer
that already round-trips. Runs are not in that text. They are a map from cell id to `CellRun`, owned
by `EditorSurface`, so a reorder does not orphan a result.

## D2

`%skip` is recognised in two places because there are two processes:

- `withoutSkip` in `web/src/domain/cellrun.ts` (line 35) decides the plan and the Run button.
- `without_skip` in `api/domain/cellrun.py` (line 83) strips the line before the warehouse sees it,
  and `pyrun.plan` omits a skipped cell from a batch.

They are not a shared package. They are a shared sentence, locked by a test on each side. That is the
same compromise the SOURCE parser already made, and the corpus test is why it has not drifted.

## D3

`executionMap` in `web/src/domain/minimap.ts` (line 64) takes cells, runs, the runnable ids, and the
batch in flight. It returns rows. `Minimap.tsx` paints them. The component does not decide a tone.

The list has two layouts, chosen by the notebook's own width. At 760px and above the pin (or focus
inside the list) gives it a column, so the cells narrow and the source stays readable. Below that
(the app with the assistant and the inspector both open) a column leaves the title one syllable
wide, so the list floats over the right edge instead. Crossing the rail with the pointer does not
open it: that used to cover the cell the user was reading.

## D4

`spanIds` (line 153) names the list. `runIds` in `EditorSurface.tsx` walks it. Run all passes
`clearAll`. A span does not. Keyboard chords and the cell menu both call `runIds`. There is no second
loop.

## D5

Cell labels are derived (`cellLabel`). SOURCE has no title field, so a title stored only in React
would vanish on reload and disagree with Databricks after a save. The map uses a heading, then a
comment, then the first line of code.

## D6

Command mode is `commandKey` (line 86). The editor translates a command into one cell operation
(`mergeWithNext` at line 218, `splitCell`, clipboard, selection). CodeMirror owns edit-mode chords
and reports them as `EditorChord`, including the Alt+Shift run spans and split.

## D7

Results are a pure function: `presentRows` and `toTsv` (line 183). The input box and the header
buttons are the only state, and they live in the output, not in the run.

## D8

H dispatches `opengenie:shortcuts`. The app opens the sheet it already had. The sheet renders
`COMMAND_HELP` under the registry, so command-mode letters are not added to the global hotkey table
(a bare `g` there would fight the composer).

## SOLID, in the places it would have been cheaper to ignore

| Principle | Where it shows |
|---|---|
| Single responsibility | Plan, map, keys, and the walker are four modules. The components render. |
| Open/closed | A new span is a new argument to `spanIds`, not a new component. |
| Liskov | Every run is a `CellRun`. The map reads `state` and nothing engine-specific. |
| Interface segregation | `NotebookEditor` receives `onRunCells(ids)`. It does not know about warehouses. |
| Dependency inversion | The editor depends on `commandKey` and `spanIds`, not on CodeMirror's keymap. |

## DRY, and the one duplication we kept

The walker is one. The skip sentence is two, on purpose ([D2](#d2)). The shortcut list is one
(`COMMAND_HELP`). The tone words are one (`toneWord`).
