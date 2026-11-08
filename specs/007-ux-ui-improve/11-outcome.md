# 11 — Outcome: what shipped, and what the screenshots changed

Part of [007](README.md). Requirements: [03](03-requirements.md). Plan: [08](08-implementation-plan.md).

---

## Delivered

| id | Requirement | State | Proof |
|---|---|---|---|
| `KB-1` | Dialogs return focus to their opener | done | `[S2]`, `21-deployed-focus-return.png` |
| `KB-2` | One owner per chord | done — `resolve()` | 8 unit tests |
| `KB-3` | Every control has a visible focus style | done (the composer field was the only gap) | `05-composer-focus.png` |
| `KB-4` | A cell is one Tab stop | done — buttons at `tabIndex={-1}`, arrows within | `09-cell-ring.png` |
| `KB-5` | The registry is the only source | done — handlers keyed by id, a test walks both ways | unit |
| `KB-6` | The sheet states scope | done — Anywhere / In a cell / In the message box | `08-sheet.png` |
| `KB-7` | Skip links | done — the first Tab stop, and they move focus | `01-skip-visible.png` |
| `KB-8` | One ordered meaning for Escape | done — `escapeTarget()` + a unit matrix | unit |
| `KB-9` | `⌘I` = inspector | done | `06-inspector-cmd-i.png` |
| `KB-10` | `⌘⇧I` = ask about this cell | done | `07-cell-prompt-cmd-shift-i.png` |
| `SC-1` | No programmatic `smooth` on data | done | `[S5]` |
| `SC-2` | One scroller per region | already held; now asserted | `[S5]` |
| `SC-3` | `overscroll-behavior: contain` | done — including the session list, which the test caught | `[S5]` |
| `SC-4` | Focus never scrolls the page | already held; now asserted | `[S5]` |
| `ZN-1`…`ZN-6` | Geometry, landmarks, Tab budget | holds; Tab-to-code **40 → 11** | `[S1]`, `[S6]` |

Measured before → after: Tab presses from the top bar to the code editor **40 → 11**. Registered
shortcuts **19 → 21**; bindings missing from the registry **1 → 0**; chords with two owners **1 → 0**.

## Four defects the screenshots found that the assertions did not

This is the value of looking at every picture, stated plainly:

1. **The skip link covered the wordmark**, then the navigator's tab strip. Fixed by centring it under
   the bar — two attempts, both wrong until seen (`01-skip-visible.png`).
2. **`⌘I` toggled a flag that rendered nothing.** At 1440 with the assistant open there is no room for
   a fourth column and `mode !== "wide"` was false, so the inspector was drawn *nowhere* while
   `aria-pressed` said "true" — a control reporting success while doing nothing. Fixed: `inspectorRoom`
   decides where it can be drawn, and the toggle reports what is **on screen**, not the intent.
3. **The inspector drawer covered the conversation** (dock `1060–1440`, inspector `1100–1440`). Fixed
   with `--dock-w` on `.app` and `body:has(.pane.assistant.dock-column)`: it now opens *beside* the
   conversation (inspector `720–1060`, no overlap). The facts must never cover what they describe.
4. **The session list chained its overscroll.** `SC-3` named three regions; the test found a fourth.

## Bugs in the work itself, found by its own tests

Recorded because they were mine, not the app's:

- **`resolve()` dropped every `when: "no-dialog"` row.** I read `when` as "only `always` rows apply
  outside a dialog", which made `⌘K`, `⌘/` and `⌘,` resolve to nothing. The unit test caught it before
  the browser could.
- **`useReturnFocus` restored nothing** for the five dialogs that mount and unmount: given a constant
  `true` it recorded on mount and had no close to observe. It now takes `"mount"` and restores in the
  unmount cleanup.
- **A passive effect recorded the wrong opener** — the dialog's own first field, because a child's
  effects run before its parent's. It is a `useLayoutEffect` now.
- **A `const` used before its declaration** crashed the app with a temporal-dead-zone error when the
  inspector geometry was first hoisted.

## Open, deliberately

- `⌘⇧I` is verified in Chromium (local and deployed); **not yet by hand in Safari and Firefox** (`E-11`).
- The cell's arrow ring has no visible hint; `Tab` leaving a cell is the requirement and works, but
  nothing on screen says ←/→ exists. A tooltip on the cell bar is the next increment.
- At 1440 px the inspector is a drawer because four columns need 1476 px. Hiding the assistant (`⌘J`)
  gives it a column; the sheet says so, the screen does not.

## Evidence

- `web/scripts/shell-e2e.mjs` — 6 scenes, 27 assertions, 15 screenshots.
- `web/scripts/deployed-shell-e2e.mjs` — 7 assertions against the deployed app, 3 screenshots.
- `web/scripts/shell-audit.mjs` — the measurement tool the assessment in `02` came from.
- Screenshots: `e2e/screenshot/` (15 local + 3 deployed), every one inspected.
