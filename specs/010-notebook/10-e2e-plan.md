# 10. E2E plan

[Index](README.md) · wireframes [04](04-wireframes.md) · edges [09](09-edge-cases.md)

The scenes run against the app with the workspace mocked, so a result, a failure, and a skip are
visible without a warehouse. The script is `apps/coding-agent/web/scripts/notebook-e2e.mjs`.
Pictures land in `specs/010-notebook/e2e/screenshots/`.

## Scenes

| ID | What it must show | Asserted before the picture |
|---|---|---|
| S1 | The notebook, the bar, three code cells, the map rail | Run all visible. Map has one bar per code cell. Markdown is not a bar |
| S2 | After Run all: one table, one skip, one failure, Fix with agent | States succeeded then failed. Status mentions skipped. Map tones ok, skip, failed |
| S3 | The map list open, First failed | The failed label is in the list. First failed is a button |
| S4 | The result filtered to one row | The filter says 1 of 3 |
| S5 | The run menu | Run all above and Run all below are both visible |
| S6 | Command mode and the shortcut sheet's Command mode section | The sheet contains "Merge with the cell below" |
| S7 | The same notebook, dark | No horizontal overflow |
| S8 | The same notebook at 860 px | Run all still in view. No horizontal overflow |

## The inspection loop

1. Run the scene. It asserts, then it takes the picture.
2. Open the picture and look at it: alignment, clipping, contrast, a control that says one thing and does another.
3. If it is wrong, change the CSS or the copy, and take it again.
4. Stop when a pass finds nothing to change.

A picture that was not opened does not count. The notes from that look are in [11](11-outcome.md).
