# 06. Eight lenses

[Index](README.md) · requirements [03](03-requirements.md) · edges [09](09-edge-cases.md)

Each lens owns one veto. A veto is a thing that must not ship even if every other lens wants it.

| Lens | Cares about | Veto |
|---|---|---|
| Product owner | A person who knows Databricks is not punished for that knowledge | [V1](#v1) No control for a capability we do not have |
| Full-stack | One walk for every run span, called from the keyboard and the menu | [V2](#v2) A second runner "just for the menu" |
| Database | SQL runs as the user, on a warehouse; `%skip` never reaches the engine | [V3](#v3) Sending `%skip` as SQL |
| UX | Every refusal is a sentence, before the click | [V4](#v4) A disabled Run with no reason |
| UI | The map, the bar, and the result share one column and do not scroll the bar away | [V5](#v5) The map inside the cell scroller |
| Front-end | Keys are data. The sheet reads the same list the editor does | [V6](#v6) A shortcut that exists only in a comment |
| System design | The server is the authority on what may execute | [V7](#v7) A client-only `%skip` the API would still run as text |
| Databricks | The published semantics: above excludes, below includes, batch stops, `%skip` is a batch directive | [V8](#v8) Continuing after an error "to show more" |
| Notebook | Edit and command never share a letter. Merge and split do not invent cells | [V9](#v9) Split at the end of a cell |

The request named eight lenses. Databricks and the notebook are both here, so the table has nine rows.
The eight the request named are the first eight; the ninth is the editor's own craft, and it earned a
veto of its own.

## V1

No cluster picker, debugger, widget bar, comment thread, schedule, or share. [P7](01-five-whys.md#p7-do-not-draw-a-control-for-a-thing-the-app-cannot-do).

## V2

`runIds` is the only walker. The menu, Run all, and Alt+Shift all call it. [D4](07-architecture.md#d4).

## V3

`without_skip` strips the directive before `run_sql`. [NB-3](03-requirements.md).

## V4

`runAffordance` returns a title for every disabled cell, and the menu items do the same.

## V5

`.nb-stage` is a row: cells scroll, the map does not. The bar stays above both, which [007](../007-ux-ui-improve/README.md) already required for Run all.

## V6

`COMMAND_HELP` in `cellkeys.ts` is what the sheet renders. [NB-9](03-requirements.md).

## V7

The same rule exists in `api/domain/cellrun.py` and `web/src/domain/cellrun.ts`, and both have a test. [D2](07-architecture.md#d2).

## V8

The loop breaks when `result.state !== "succeeded"`. That is the SQL-warehouse rule in the Oct 2026 run docs, and it was already our Run all rule.

## V9

`splitCell` returns the original list when the caret has nothing after it. [NB-6](03-requirements.md).
