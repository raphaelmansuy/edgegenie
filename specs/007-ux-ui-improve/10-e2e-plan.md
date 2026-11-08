# 10 — E2E plan

Part of [007](README.md). Requirements: [03](03-requirements.md). Edge cases: [09](09-edge-cases.md).

One script, `web/scripts/shell-e2e.mjs`, run against the local dev server and then the deployed app.
Every scene writes a screenshot to `specs/007-ux-ui-improve/e2e/screenshot/`, and **every screenshot
is inspected** before the scene is considered done — a scene that asserts without a picture can pass
while looking broken.

---

## How a scene is built

```
scene("S3 chords", [KB-2, KB-9, KB-10])
  measure(...)  → a value
  check(name, ok, detail)   → PASS/FAIL, with the value in the log
  shot("06-inspector-cmd-i.png")   → a picture, inspected by eye
```

Three rules, learned from the earlier rounds:

1. **Wait for the effect, not a duration.** `waitForFunction` on the real condition, then a short
   settle. Every flaky test in rounds 3–4 was a fixed sleep.
2. **Assert the thing the user sees.** Not "a class exists" but "the inspector is on screen and the
   cell prompt is not".
3. **Screenshot at the moment of the claim**, not at the end of the scene.

---

## S1 — skip links and the Tab budget · `KB-7`, `ZN-5`, `E-5`, `E-6`, `E-7`

| Step | Expect |
|---|---|
| Load the app, press Tab once | the "Skip to the work" link is **visible** (not merely focusable) |
| Press Enter | `document.activeElement` is `#doc-panel` |
| Press Tab once more | the next control is *inside* the centre, not the top bar |
| Reload, press Shift+Tab from the top | the second skip link ("the conversation") is reachable |
| Count Tabs from the top bar to `.cm-content` in a notebook | ≤ 12 |

Screenshots: `01-skip-visible.png` (the link as a user first sees it), `02-focus-in-main.png`.

## S2 — dialogs return focus · `KB-1`, `KB-3`, `E-1`, `E-2`, `E-4`

| Step | Expect |
|---|---|
| Focus the palette button, press `⌘K`, press Escape | focus is on `button.search-trigger` again (not `body`) |
| Focus the shortcut-sheet button, `⌘/`, Escape | focus is on that button again |
| Focus the composer, press `⌘K`, Escape | focus is back on the composer's textarea, with a visible ring |
| Open the folder picker from the home screen, Escape | focus is on `.fp-trigger` |
| Open the approval sheet (fake agent, permission scenario), Escape/deny | focus returns to the composer |

Screenshots: `03-palette-escape.png`, `04-sheet-escape.png`, `05-composer-focus.png`.

## S3 — the chords mean what the sheet says · `KB-2`, `KB-9`, `KB-10`, `KB-5`, `E-12`, `E-19`, `E-34`

| Step | Expect |
|---|---|
| Focus a cell, press `⌘I` | the **inspector** appears; no cell prompt |
| Press `⌘I` again | the inspector closes |
| Focus a cell, press `⌘⇧I` | the **cell prompt** opens, focused |
| Press Escape, then `⌘⇧I` twice | it toggles |
| Open the sheet (`⌘/`) | it lists `⌘I` inspector, `⌘⇧I` cell prompt, `⌘J` assistant, grouped by scope |
| Compare the sheet's rows with `SHORTCUTS` | every row present, no extra |

Screenshots: `06-inspector-cmd-i.png`, `07-cell-prompt-cmd-shift-i.png`, `08-sheet.png`.

## S4 — a cell is one Tab stop · `KB-4`, `ZN-4`, `E-9`

| Step | Expect |
|---|---|
| Focus a cell's section, press Tab | focus leaves the cell (next cell or the seam), does not walk 6 buttons |
| From the cell, press → | the first action button takes focus |
| Press → repeatedly | the ring moves; at the end it wraps |
| Press Home/End | jumps to the ends of the ring |
| Every button has a distinct accessible name inside the cell | counts match |

Screenshots: `09-cell-ring.png`.

## S5 — scroll · `SC-1`, `SC-3`, `SC-4`, `SC-5`, `E-20`, `E-21`, `E-23`, `E-25`

| Step | Expect |
|---|---|
| Open a 41-cell notebook | exactly one scroller: `.cells`; every editor reports `scrollHeight === clientHeight` |
| Wheel to the very bottom, wheel again | `document.scrollingElement.scrollTop` stays 0; no navigation |
| Read `getComputedStyle` of every scroller | `overscroll-behavior-y: contain`; `scroll-behavior` never `smooth` on `.cells`, `.dock-body`, `.transcript` |
| Agent banner appears, press **Show** | the changed cell is in view, and the jump was smooth (assert the option passed) |
| Focus an off-screen cell by link (`?cell=38`) | `.cells` scrolled; the page did not |
| Streamed answer | the dock stays pinned only while it was pinned |

Screenshots: `10-scroll-end.png`, `11-show-smooth.png`.

## S6 — zones · `ZN-1`, `ZN-2`, `ZN-3`, `ZN-6`, `E-27`…`E-31`

| Width | Expect |
|---|---|
| 1476 | four columns: rail 276, centre ≥ 480, inspector 340, dock 380 |
| 1440 | three columns; the inspector is hidden (no room), the dock has a column |
| 1135 | the dock is *focus* — the rail is a drawer, the centre ≥ 480 |
| 1024 | same as 1135 |
| 859 | the dock is an overlay with a clear scrim; the rail is a drawer |
| 800 | narrow: both side panels are drawers |
| Any | the page itself never scrolls; no horizontal overflow at the document level |
| Keyboard-resize the rail | width changes by 8 px per Arrow, 64 with Shift, announced via `aria-valuenow`; reload keeps it |
| Landmarks | one `banner`, `main`, ≥1 `navigation`, `complementary`; every icon button has a unique name |

Screenshots: `12-1440.png`, `13-1024-focus.png`, `14-800-drawer.png`, `15-dark.png`.

---

## The audit script (`shell-audit.mjs`), kept as a gate

It prints a machine-readable report and fails on:

```
✗ tabToCode > 12                                   (ZN-5)
✗ a focusable element with no visible focus style  (KB-3)
✗ document.scrollingElement.scrollHeight > innerHeight   (SC-4)
✗ a scroller with overscroll-behavior-y !== "contain"    (SC-3)
✗ a scroller with scroll-behavior: smooth                 (SC-1)
✗ two icon buttons with the same accessible name in a zone (ZN-4)
✗ a landmark missing                                  (ZN-3)
```

## Deployed verification

The same script, `APP_URL=https://coding-agent-….aws.databricksapps.com`, with a bearer token. The
deployed run is the one that counts: it is where rounds 3 and 4 found the regressions the local run
could not (a real token, a real agent, real latency).
