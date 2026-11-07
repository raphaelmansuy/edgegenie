# 02 · Requirements

[Index](README.md) · prev: [01 Audit](01-shell-audit.md) · next: [03 Architecture](03-architecture.md)

Each requirement is testable, names the axiom it serves, and names the finding it closes. IDs are
stable: `SH-` for shell, and the tests in [06](06-edge-cases-testing.md) cite them.

## A · Layout is the user's

| ID | Requirement | Axiom | Closes |
|---|---|---|---|
| SH-A1 | The navigator and the inspector are resizable by dragging a 4–6 px separator between them and the centre column. | A2 | F1 |
| SH-A2 | Each zone has a minimum width (rail 200, inspector 260) and a maximum (40% of viewport each, and never leaving the centre column under 480 px). A drag beyond a bound stops at the bound, it does not fight the pointer. | A2 | F1 |
| SH-A3 | Widths are adjustable by keyboard: the separator is focusable, `←`/`→` resize by 8 px, `Shift` makes it 64 px, `Home` resets to default. | A2, A6 | F1 |
| SH-A4 | Double-clicking a separator resets that zone to its default width. | A2 | F1 |
| SH-A5 | The composer grows with its content from one line to a maximum of 8 lines, then scrolls; when empty it is one line. The reading surface reflows by exactly the height gained or lost. | A2 | F8 |
| SH-A6 | A resize in progress does not drop input: the pointer is captured, the transcript does not re-render, and the drag is `requestAnimationFrame`-throttled. | A1, A5 | F1 |

## B · State is remembered

| ID | Requirement | Axiom | Closes |
|---|---|---|---|
| SH-B1 | Rail width, inspector width, rail visibility, inspector visibility, active rail tab and open document list survive a page reload. | A3 | F2 |
| SH-B2 | Persisted layout is per-browser, versioned under one key, and validated on read: a corrupt or future-versioned value falls back to defaults rather than breaking the shell. | A3 | F2 |
| SH-B3 | A "Reset layout" action exists in the palette and restores every default in one step. | A3, A6 | F2 |
| SH-B4 | Persistence never blocks a frame: reads happen once at mount, writes are debounced (≥150 ms) and wrapped so a quota error is ignored. | A1 | F2 |
| SH-B5 | Layout state is *not* sent to the server: it is this browser's preference, not the account's. | A3 | — |

## C · Navigation is complete

| ID | Requirement | Axiom | Closes |
|---|---|---|---|
| SH-C1 | When the active tab is outside the visible strip, the strip scrolls it into view (nearest, not centre) — on select, on open, and on `Ctrl+Tab`. | A5, A6 | F3 |
| SH-C2 | The strip never scrolls the page; only itself. Tabs shrink to a minimum, then the strip scrolls. | A1 | F3 |
| SH-C3 | When tabs overflow, a count of hidden tabs is shown at the end of the strip, and activating it lists them. | A6 | F3 |
| SH-C4 | Closing the active tab activates the neighbour to its right, else its left; closing the last document returns to Chat. | A5 | — |
| SH-C5 | `⌘1/2/3` select rail tabs; `Ctrl+Tab`/`Ctrl+Shift+Tab` cycle documents; `⌘W` closes the current document and never the chat. | A6 | — |
| SH-C6 | Every zone toggle is symmetric: the same chord that hides also shows, and a visible control exists for both directions. | A6 | F7 |

## D · Feedback is honest

| ID | Requirement | Axiom | Closes |
|---|---|---|---|
| SH-D1 | An operation expected to exceed 400 ms shows a spinner at the point of work within 150 ms of starting. | A4 | F5 |
| SH-D2 | Workspace search shows a result count as soon as the first page arrives, and states when the walk was cut short ("first matches"). | A4 | F5 |
| SH-D3 | Any operation over 1 s can be cancelled from the UI, and cancelling restores the previous results rather than emptying the list. | A4 | F5 |
| SH-D4 | Long operations do not block input: the composer, the palette and the trees stay usable while a search or a turn runs. | A1, A4 | F5 |

## E · The frame is stable

| ID | Requirement | Axiom | Closes |
|---|---|---|---|
| SH-E1 | Starting a turn does not move the composer: its height is unchanged when text is sent and the box is cleared. | A5 | F8 |
| SH-E2 | Opening or closing a panel does not re-wrap the transcript's text: content width changes only by the panel's width, once, in one frame. | A5 | — |
| SH-E3 | Auto-scroll happens only when the reader is already at the bottom, and at most once per animation frame. | A5 | — |
| SH-E4 | No layout shift greater than 0.1 CLS on load at 1440 px. | A5 | — |

## F · Every zone is addressable

| ID | Requirement | Axiom | Closes |
|---|---|---|---|
| SH-F1 | The transcript is a named landmark (`role="region"` with an accessible name, or `<section aria-label>`), reachable by screen-reader landmark navigation. | A6 | F6 |
| SH-F2 | The composer is a named landmark with the same property. | A6 | F6 |
| SH-F3 | The separators between zones are `role="separator"` with `aria-orientation="vertical"`, `aria-valuenow`/`aria-valuemin`/`aria-valuemax` for the zone they control, and an accessible name. | A2, A6 | F1 |
| SH-F4 | Focus order follows visual order at every width, including when panels are drawers. | A6 | — |
| SH-F5 | Focus never lands on a hidden zone; hiding a zone that contains focus moves focus to the nearest sensible control (the restore handle). | A6 | — |

## G · The implementation stays healthy

| ID | Requirement | Axiom | Closes |
|---|---|---|---|
| SH-G1 | One source of truth for the layout grid. No duplicate `.layout` rule; no literal column widths outside the layout module. | A1 | F4 |
| SH-G2 | A single z-index scale as tokens; no raw `z-index` above the scale's lowest layer outside it. | A1 | F9 |
| SH-G3 | Layout decisions live in one module with unit tests; components render, they do not compute geometry. | A1 | F4, F9 |
| SH-G4 | Every requirement above is covered by a named test, and the shell audit fails the build when a regression appears. | A1 | all |

## Acceptance in one table

A run is acceptable when, on the deployed app, all of these hold at once:

| Check | Command | Pass |
|---|---|---|
| Shell audit | `npm run audit:shell` | 0 findings; resizable **yes**; remembered **yes** |
| Overflow | `npm run audit:overflow` | 0 across ≥28 checks |
| Accessibility | `npm run audit:a11y` | 0 findings |
| Keyboard/shell e2e | `npm run e2e:shell` | all steps |
| Product e2e | `npm run e2e:live` | 19/19 |
| Unit | `pytest`, `vitest` | 150+, 74+ |
