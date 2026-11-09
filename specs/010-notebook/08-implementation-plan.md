# 08. Implementation plan

[Index](README.md) · decisions [07](07-architecture.md) · edges [09](09-edge-cases.md)

The order is the dependency order. A later phase does not invent a rule an earlier phase owns.

| Phase | What | Files | Proves |
|---|---|---|---|
| 1 | Keys as data, including double-taps and range chords | `web/src/domain/cellkeys.ts` | NB-1 |
| 2 | `%skip`, spans, filter, sort, copy | `web/src/domain/cellrun.ts`, `api/domain/cellrun.py` | NB-2, NB-3, NB-5 |
| 3 | Parser keeps `%skip` | `notebook.ts`, `api/domain/notebook.py` | NB-7 |
| 4 | Python batch omits `%skip` unless that cell was asked for | `api/domain/pyrun.py` | NB-8 |
| 5 | The server strips `%skip` before SQL | `api/routers/api.py` | V3 |
| 6 | Merge and split | `notebook.ts` | NB-6 |
| 7 | The map | `minimap.ts`, `Minimap.tsx` | NB-4 |
| 8 | Wire the walker, the menu, the sheet, the fold | `EditorSurface`, `NotebookEditor`, `CellOutput`, `ShortcutSheet`, `App.tsx` | NB-9, NB-11, NB-13 |
| 9 | Tests named in [03](03-requirements.md) | the `*.test.ts` and `tests/test_*.py` files | all of the above |
| 10 | Scenes and the inspection loop | [10](10-e2e-plan.md) | the pictures |

## What not to do in any phase

- A second run loop for "above".
- A title field that does not survive SOURCE.
- A hotkey row for the letter `g`.
- A cluster control.

## Effort

The domain is the risk. The components are a projection of it. If a scene disagrees with a unit test,
the scene is wrong or the test is, and we do not "fix" it in CSS.
