# 09. Edge cases

[Index](README.md) · requirements [03](03-requirements.md) · scenes [10](10-e2e-plan.md)

Each case has a sentence the user can read, or a behaviour, and the test that locks it.

| ID | Case | What happens | Test |
|---|---|---|---|
| E-1 | Cell is only `%skip` | Run is disabled. "This cell is only %skip" | `runAffordance` |
| E-2 | `%skip` then SQL | Left out of Run all. Run on its own sends the SQL, not the directive | `without_skip`, router |
| E-3 | `%skip` then nothing runnable, in a batch | Counted as skipped, with the batch reason | `runPlan` |
| E-4 | Run above on the first cell | The menu item is disabled. "Nothing above this cell can run" | menu title |
| E-5 | Run below on the last runnable cell | That cell runs. Later markdown is ignored, not "skipped" | `runPlan` ignores markdown |
| E-6 | Failure in the middle of a span | The walk stops. Later cells keep their previous output | NB-13 |
| E-7 | Stop between cells | `stopAll` is read before the next cell. II does the same | NB-12 |
| E-8 | Double-tap disarmed | D then J moves. The J is not swallowed | `cellkeys.test.ts` |
| E-9 | GG and Shift+G | First and last, even when a G is armed | `cellkeys.test.ts` |
| E-10 | Split at the end | No new cell | `splitCell` |
| E-11 | Merge on the last cell | The list is unchanged | `mergeWithNext` |
| E-12 | Cut with a multi-selection | Those cells leave, and the clipboard can paste them | `onClipboard` |
| E-13 | Paste with an empty clipboard | Nothing changes | `onClipboard` |
| E-14 | Filter matches nothing | "No rows match". Copy copies the header only | `presentRows` |
| E-15 | Sort with blanks | Blanks stay last ascending and descending | `presentRows` |
| E-16 | Numbers as text | `10` sorts after `2`, not before | `presentRows` |
| E-17 | A tab or newline in a cell | Becomes a space in the TSV, so the paste stays rectangular | `toTsv` |
| E-18 | `%skip` Python above a cell you run | It does not run, and it does not leave variables | `test_pyrun.py` |
| E-19 | `%skip` Python cell run on its own | Its body runs | `test_pyrun.py` |
| E-20 | Imported `# MAGIC %skip` | Language stays the notebook's. Source keeps the directive | round-trip tests |
| E-21 | Map while a batch is in flight | Not-yet-started cells in the batch are queued. Others idle or skip | `executionMap` |
| E-22 | Read-only notebook | No Run, no merge, no delete. The map still describes code cells | `readOnly` guards |
| E-23 | Many cells | Bars shrink. The list scrolls. Labels clip at 48 characters | `cellLabel` |

## Accepted limits

These are not bugs. They are [V1](06-lenses.md#v1).

| Limit | Why it stays |
|---|---|
| No debugger, widgets, comments, schedule, share, or cluster picker | The app cannot do the thing the control would promise |
| No persisted cell title | SOURCE has no field. The map derives a label [D5](07-architecture.md#d5) |
| Find is per cell | CodeMirror's find. A notebook-wide replace can corrupt a round-trip; it is out of scope |
| Python runs as the app, for administrators | Unchanged from [006](../006-databricks/14-genie-code-gap-analysis.md). The chip says so |
| Command-mode letters are not in the global hotkey registry | A bare `g` would type in the composer [D8](07-architecture.md#d8) |
