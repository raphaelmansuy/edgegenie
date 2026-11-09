# 11. Outcome

[Index](README.md) · scenes [10](10-e2e-plan.md) · decisions [07](07-architecture.md)

The scenes in `apps/coding-agent/web/scripts/notebook-e2e.mjs` all passed. The pictures are in
`e2e/screenshots/`. Each one was opened, and the layout changed where the picture showed a lie.

## What the pictures changed

| Picture | What was wrong | What changed |
|---|---|---|
| 01, 02 | The status ended in an ellipsis, then broke as "1 ran · 1 failed · 1" / "skipped" | The sentence stays one line. The chip wraps before the words do |
| 02 | The cell said "Serverless St…" | The warehouse name no longer ellipsizes. The output bar wraps |
| 03 | Pinning the list squeezed "Revenue by hour" into one syllable per line | Under 760px the list floats. The title stays a title. See [D3](07-architecture.md) |
| 03 | Hovering the rail covered the cell the pointer was crossing | The list opens on pin or focus, not on hover |
| 03 | `select * from missing_ta…` | The row wraps, so the failed statement is whole |
| 05 | The menu stayed open into the next scene, and Escape did not close it | Escape closes the menu when no dialog is up |
| 06 | Focusing Close scrolled the title off, then the command list off | Focus does not scroll. The shot scrolls Command mode to the top of the sheet |
| 08 | The inspector drawer covered the cells, and the run menu was still open | The shot closes both before it photographs |

Idle bars use a mid ink so three unrun cells read as three cells. The shortcut sheet's Close button
takes focus without scrolling the list away.

The notebook chrome uses the same popover, menu row, and table as gr8r-studio: a 10px card with the
shared pop shadow, 30px rows that rest on the secondary surface, and a result table with a 500-weight
header and hairline dividers. OpenGenie's own tokens stay the palette.

## What the pictures show

- **01 idle.** Four cells. The bar says `2 cells can run · 1 skipped`. Three bars, one per code cell. Markdown is not a bar.
- **02 run.** A three-row table, the `%skip` cell with no output, then `TABLE_OR_VIEW_NOT_FOUND` and Fix with agent. The bar says `1 ran · 1 failed · 1 skipped`. The bars are green, grey, red.
- **03 map.** The list names cell 2 done, cell 3 skipped, cell 4 failed, with the statement in full. First failed and Last run are buttons.
- **04 filter.** The box says `night` and the count says `1 of 3`. One row remains.
- **05 menu.** Run all above and Run all below, on the cell that produced the table.
- **06 shortcuts.** Command mode, from Enter through H, including merge, the run spans, and clear.
- **07 dark.** The same map, table, and failure on the dark theme.
- **08 at 860.** The status is still one line. The failed statement and Fix with agent are on screen. No horizontal overflow.

## What is still not true

These were refused in [01](01-five-whys.md) and [06](06-lenses.md), and the pictures do not pretend otherwise.

- No cluster picker. Python still runs as the app.
- No debugger, widgets, comments, schedule, or share.
- No notebook-wide find and replace.
- Cell titles are derived. SOURCE has no title field, so the map does not invent one that would vanish on save.
- `%skip` is a batch directive. Running that cell on its own still runs the statement under it.
