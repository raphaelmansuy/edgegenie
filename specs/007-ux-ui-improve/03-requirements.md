# 03 — Requirements

Part of [007](README.md). Every id is defined here exactly once. Rationale: [01](01-five-whys.md).
Evidence for each "today" column: [02](02-assessment.md). Tests: [10](10-e2e-plan.md).

---

## KB — Keyboard and focus

| id | Requirement | Today | Rule it serves |
|---|---|---|---|
| **KB-1** | Closing any dialog, popover or sheet **returns focus to the element that opened it**. If that element is gone, focus goes to a named successor (the next tab, the composer, the centre pane) — never `<body>`. | Fails: palette and sheet → `<body>` | P1 |
| **KB-2** | Every chord has **one owner**. Where the meaning depends on context, the same owner decides by context. | Fails: `⌘I` = inspector *and* cell prompt | P2 |
| **KB-3** | Every focusable control has a **visible focus indicator** while focused by keyboard (outline or ring ≥ 2px, contrast ≥ 3:1 against both neighbours). | Fails: composer textarea relies on its wrapper | P1 |
| **KB-4** | A cell is **one Tab stop**: the cell itself. Its six action buttons are reachable by arrow keys once the cell is focused, not by six Tabs. | Fails: 6 stops before the text | P1, P5 |
| **KB-5** | The shortcut registry is **the only source**: every binding in `App.tsx` exists in `SHORTCUTS`, and every entry in `SHORTCUTS` works. A test asserts both directions. | Fails: `⌘J` unlisted | P2 |
| **KB-6** | The sheet **shows the chord that actually works** in the user's current context, and groups by scope. | Fails: `⌘I` says inspector | P2 |
| **KB-7** | A **skip link** is the first Tab stop: "Skip to the work" (centre pane), then "Skip to the conversation". Both are visible on focus and move focus, not just scroll. | Missing | P5 |
| **KB-8** | Escape has a **single, ordered meaning**: close the topmost transient (dialog → popover → drawer → cell edit), then stop the agent if it is running, then do nothing. It never stops the agent while a dialog is open. | Partially: order exists in `App.tsx`, but Stop lives in the composer's own keydown | P2 |

## SC — Scrolling

| id | Requirement | Today | Rule |
|---|---|---|---|
| **SC-1** | No programmatic `smooth` scrolling on a data change. Smooth is allowed only when the **user** asked for a jump (Show, a cell link, "open at cell N"). | Fails: `.transcript`, `.dock-body` | P3 |
| **SC-2** | **One scrolling surface per region per axis.** The notebook scrolls as one; a cell never becomes a second scroller. | Holds — lock it with a test | P3 |
| **SC-3** | Scrolling regions set `overscroll-behavior: contain`, so a trackpad flick does not navigate the browser history. | Fails on `.cells` | P3 |
| **SC-4** | Focus never scrolls the page: focusing an off-screen cell scrolls only its region. | Holds (`overflow: clip` on the page) — test it | P3 |
| **SC-5** | A wheel over a region that cannot scroll in that direction leaves the event to its parent; the app never swallows it. | Holds today (no ancestor scroller) — assert it | P3 |

## ZN — Zones, controls, navigation

| id | Requirement | Today | Rule |
|---|---|---|---|
| **ZN-1** | Geometry is a pure function of viewport and intent; the centre never drops below `CENTRE_MIN`. | Holds (`layout.ts`) | P4 |
| **ZN-2** | A zone that cannot show its content becomes a drawer, never an overlay over the work. | Holds (round 2) | P4 |
| **ZN-3** | Every zone is a **landmark** with an accessible name: `banner`, `navigation` (×2, named), `main`, `complementary`. | Mostly: the dock is `aside`; the inspector is `aside`; `main` exists | P5 |
| **ZN-4** | Every icon-only control has an accessible name, and every name is unique within its zone. | Holds — assert it | P5 |
| **ZN-5** | The **Tab budget** from the top bar to the code is ≤ 12 stops, and to the composer ≤ 8. Measured, not estimated. | Fails: 40 | P5 |
| **ZN-6** | Resizing a zone is possible by pointer **and** keyboard, announces its value, and survives a reload. | Holds — assert it | P4 |
| **ZN-7** | A panel that can be hidden **must** have a control to show it again, **at the edge it comes from**, enabled in every reachable state, with a name a person reads. | Fails → [12](12-hidden-panels.md) | P1, P5 |
| **ZN-8** | That control is asserted by **hit-test** at every width and in every session state: presence in the DOM is not presence on screen. | New | P1, P5 |

## The two new shortcuts

| id | Chord | Meaning | Why this one |
|---|---|---|---|
| `KB-9` | `⌘/Ctrl+I` | **Inspector** (scope, audit, model facts) | It is what the sheet already promises; the inspector is the rarer, more deliberate act. |
| `KB-10` | `⌘/Ctrl+⇧I` | **Ask the agent about this cell** | Same family as the inspector (both "more info"), one modifier away, and cells are where you use it. |

`⌘J` (dock) is promoted from an unlisted binding to a registry entry with a label, so it is
discoverable and covered by `KB-5`.

---

## Non-goals

- The notebook cell model (`003`), the agent (`006`), the dock's content (`006`), the home screen's
  layout (`006` round 4). This spec touches them only where a *key* or a *scroll* crosses the seam.
- A theme switch by keyboard exists (`⌘⇧L`) and is not re-designed.
- No new dependency. No new bundle chunk. The registry stays a plain array.

## Acceptance, in one table

| When | Then |
|---|---|
| I open the palette and press Escape | the control I opened it with has focus again (`KB-1`) |
| I focus a cell and press `⌘I` | the inspector opens — not a cell prompt (`KB-2`, `KB-9`) |
| I press `⌘⇧I` in a cell | the cell prompt opens (`KB-10`) |
| I press Tab on a fresh page | a visible "Skip to the work" appears and moves focus to the centre (`KB-7`) |
| I Tab from the top bar | I reach the code in ≤ 12 stops (`ZN-5`) |
| I focus a cell and press Tab | I leave the cell, not walk its six buttons (`KB-4`) |
| The agent streams an answer | nothing eases, jumps or animates the transcript (`SC-1`) |
| I flick a trackpad at the last cell | the browser does not navigate away (`SC-3`) |
| I resize a zone by keyboard | it announces the new width and survives a reload (`ZN-6`) |

## MD — Math in markdown

| id | Requirement | Rule |
|---|---|---|
| **MD-1** | A code fence or an inline code span is **never** math, and a stray `$` never swallows the text after it. | P3 |
| **MD-2** | Math takes the theme's ink in both themes: no second palette, no KaTeX black on a warm surface. | P4 |
| **MD-3** | An inline formula does not tear a paragraph apart: the line's leading is the same as prose's, and a fraction gets the room it needs without doubling the line. | P4 |
| **MD-4** | A wide display formula scrolls inside its own box and never widens the panel it is in. | P3, P4 |
| **MD-5** | A half-streamed formula reads as progress, not as an error. | P1 |
| **MD-6** | A formula that cannot be typeset is shown as readable source, marked once the turn ends; it never throws into the transcript. | P1 |
| **MD-7** | A markdown FILE opens **rendered**, with a one-click toggle to its source, because a `.md` file is prose and its formulas are the point. | P4 |
| **MD-8** | `$4$` is math and `$5 and $10` is money: the test is a closing `$` with no space before it, never "the content looks like a number". | P3 |
