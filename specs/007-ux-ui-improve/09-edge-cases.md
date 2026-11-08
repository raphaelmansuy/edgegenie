# 09 — Edge cases

Part of [007](README.md). Requirements: [03](03-requirements.md). Each row names the case, why it is
plausible, the mitigation, and the test that proves it. A case without a test is a case I did not
actually handle.

---

## Focus (`KB-1`, `KB-3`, `KB-7`)

| id | Case | Mitigation | Test |
|---|---|---|---|
| **E-1** | The opener is the element that opened the dialog, but focus had moved inside the dialog before the user clicked something else in it | record `activeElement` at *open*, not at close | unit |
| **E-2** | The opener is removed while the dialog is open (its tab was closed by the agent, its row re-rendered) | `el.isConnected` check → named successor: next tab → composer → `main` | unit + `[S2]` |
| **E-3** | Two dialogs are open at once (the folder picker opened from the settings sheet) | the *stack* is last-in-first-out: the hook records per instance, so the inner one restores to the outer one's field | `[S6]` |
| **E-4** | Escape closes the dialog and the same keypress then stops the agent | `preventDefault` + `stopPropagation` in the dialog's own handler; `KB-8` orders it | unit |
| **E-5** | A skip link's target is not focusable | `tabIndex={-1}` on both targets, set in JSX so it is never conditional | `[S1]` |
| **E-6** | The user clicks a skip link with the mouse | it still moves focus (a click focuses the `<a>`); the handler focuses the target so Tab continues inside | `[S1]` |
| **E-7** | The centre pane is empty (nothing open) and "Skip to the work" is pressed | `#doc-panel` exists in every state (it is the tabpanel) and receives focus; the home screen is inside it | `[S1]` |
| **E-8** | The dock is hidden | "Skip to the conversation" points at a node that is not rendered | the link is rendered only when the dock is on screen (it is the same condition that renders the aside) |
| **E-9** | A cell's action ring: the cell is collapsed | the ring is computed over the *visible* buttons only | unit (`nextInRing` over a filtered list) |
| **E-10** | A cell's action ring: the last button's → wraps to the first | intentional, like a toolbar; `Home`/`End` jump to the ends | unit |

## Chords (`KB-2`, `KB-5`, `KB-6`, `KB-9`, `KB-10`)

| id | Case | Mitigation | Test |
|---|---|---|---|
| **E-11** | `⌘⇧I` is taken by "open the inspector in a new window" in a browser | it is not; verified in Chromium, Safari, Firefox by hand before implementation. If it ever is, `D9` falls back to `⌘⌥I` | `[S3]` |
| **E-12** | The user is typing in the composer and presses `⌘I` | modified chords resolve even while typing (`isTyping` only blocks *bare* keys) | unit + `[S3]` |
| **E-13** | The user presses `⌘I` while a *dialog* is open | `when: "no-dialog"` on the shell's rows; the dialog owns every chord but Escape | unit |
| **E-14** | Two registry rows share a combo | construction-time assertion in a test: `new Set(combos).size === combos.length` | unit |
| **E-15** | A binding exists in `handlers` but not in `SHORTCUTS` (the `⌘J` bug) | the test walks both directions; `App.tsx`'s handler keys must be a subset of the registry's ids | unit |
| **E-16** | A registry row exists but has no handler | the test allows it only for rows marked `external` (implemented by a component, like the cell keys) — and there are none permitted for `owner: "shell"` | unit |
| **E-17** | The cell prompt is open and `⌘⇧I` is pressed again | toggling: the second press closes it (same as today's `⌘I`) | `[S3]` |
| **E-18** | A non-Mac user presses `Ctrl+I` | `comboOf` maps `mod` to Ctrl off-Mac; the registry is platform-neutral | unit (existing) |
| **E-19** | `⌘I` pressed while the inspector is already open | toggles closed — the label says "Show or hide" | `[S3]` |

## Scroll (`SC-1` … `SC-5`)

| id | Case | Mitigation | Test |
|---|---|---|---|
| **E-20** | The user is reading the conversation and a turn streams in | no `smooth`, and the dock is pinned only when already at the bottom (`AssistantDock.pinned`) | `[S5]` |
| **E-21** | A trackpad flick at the last cell of a notebook | `overscroll-behavior: contain` stops the chain; the browser does not navigate | `[S5]` |
| **E-22** | `overscroll-behavior` unsupported (older Safari) | it degrades to today's behaviour; nothing breaks | manual note, no test |
| **E-23** | Focusing an off-screen cell | `scrollIntoView` is bounded to `.cells`; the page cannot scroll (`overflow: clip`) | `[S5]` |
| **E-24** | The "Show" jump when the user prefers reduced motion | `behavior: "auto"` under `prefers-reduced-motion` (already implemented) | unit (existing) |
| **E-25** | Two scrollers on one axis appear because a cell's output grid is tall | `.cell-output-grid` has `max-height: 320px; overflow: auto` — a *third* scroller inside the notebook. It is legitimate (a result table is its own surface) but must not chain the wheel to the notebook | `[S5]` asserts `contain` on it too |
| **E-26** | A nested scroller whose content fits (no scroll) | does not become a scroller; the audit only counts `scrollHeight > clientHeight` | `shell-audit2` |

## Zones and layout (`ZN-*`)

| id | Case | Mitigation | Test |
|---|---|---|---|
| **E-27** | 1135 px — one pixel below the dock's column threshold | the dock is an overlay/focus column, the centre keeps 480 | `[S6]` at 1135 |
| **E-28** | 859 px — one below focus mode | the dock is an overlay with a clear scrim; the rail is a drawer | `[S6]` at 859 |
| **E-29** | 480 px window | the centre is clamped to its minimum and the app scrolls horizontally *inside* the pane, never the page | `[S6]` at 480 |
| **E-30** | Zoom at 200% (effective width halves) | the layout reacts to `innerWidth`, so zoom is just a narrower window | `[S6]` via `deviceScaleFactor` |
| **E-31** | The keyboard resizes a zone past the share cap | `clampWidth` in `layout.ts` (already) | unit (existing) |
| **E-32** | A zone width stored from a wider window | `clampWidth` on read (already) | unit (existing) |

## Cross-cutting

| id | Case | Mitigation | Test |
|---|---|---|---|
| **E-33** | A screen reader announces the dock as "Assistant" but the user calls it "the conversation" | the skip link says "the conversation"; the aside's name stays "Assistant" (the product's own word in 006). Both are names for one region; `aria-label` matches the visible skip link text | `[S1]` |
| **E-34** | The shortcut sheet lists a chord that only works when a cell is focused | `KB-6`: group by scope, so "In a cell" is its own section | `[S3]` |
| **E-35** | A user with `prefers-reduced-motion` and a skip link | the link does not animate; it appears instantly | CSS (`@media` block already global) |
| **E-36** | High-contrast mode (Windows) | the focus ring uses `outline`, which high-contrast preserves; the accent backgrounds may be replaced by the OS | manual note |
| **E-37** | A dialog opened by a keyboard chord whose trigger is hidden by CSS at that width (the model chip below 1100px) | the fallback chain catches it: a hidden element is `isConnected` but not focusable, so `offsetParent === null` must also be checked | unit |
