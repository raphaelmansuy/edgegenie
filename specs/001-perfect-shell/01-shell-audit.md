# 01 · Shell audit: what actually exists

[Index](README.md) · prev: [00 Why](00-why-first-principles.md) · next: [02 Requirements](02-requirements.md)

Every number here was measured on the running app, not read off a design. The command that produces
them is `web/scripts/shell-audit.mjs`; runs at 1600/1440/1180/900/760 px.

## The zones as they are

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ TOPBAR  1600×52 — brand (h1) · model select · status pill · ⌘K trigger · keys · ⟳     │
├────────────┬─────────────────────────────────────────────────────┬───────────────────┤
│ RAIL       │ MAIN                                                │ INSPECTOR         │
│ 276×848    │ 822×848 at 1440                                     │ 340×848           │
│ at 1440    │                                                     │                   │
│            │ ┌─────────────────────────────────────────────────┐ │ Context:          │
│ Sessions   │ │ STRIP 822×37 — path · counts · open-in-Databricks│ │  working scope    │
│ Files      │ ├─────────────────────────────────────────────────┤ │  session          │
│ Catalog    │ │ DOC TABS (only when a doc is open)              │ │  skill reads      │
│            │ ├─────────────────────────────────────────────────┤ │                   │
│ tree /     │ │ TRANSCRIPT 822×664                              │ │ Audit:            │
│ list       │ │   (78% of the centre column)                    │ │  turn log         │
│            │ ├─────────────────────────────────────────────────┤ │                   │
│            │ │ COMPOSER 822×147                                │ │                   │
│            │ └─────────────────────────────────────────────────┘ │                   │
└────────────┴─────────────────────────────────────────────────────┴───────────────────┘
```

### Measured, at every width

| width | topbar | rail | main | inspector | strip | transcript | composer | reading share | splitters | remembers layout |
|---|---|---|---|---|---|---|---|---|---|---|
| 1600 | 1600×52 | 276×848 | 982×848 | 340×848 | 982×37 | 982×664 | 982×147 | 0.78 | 0 | **no** |
| 1440 | 1440×52 | 276×848 | 822×848 | 340×848 | 822×37 | 822×664 | 822×147 | 0.78 | 0 | **no** |
| 1180 | 1180×52 | 252×848 | 927×848 | — (drawer) | 927×37 | 927×664 | 927×147 | 0.78 | 0 | **no** |
| 900 | 900×52 | 252×848 | 647×848 | — (drawer) | 647×37 | 647×664 | 647×147 | 0.78 | 0 | **no** |
| 760 | 760×52 | — (drawer) | 760×848 | — (drawer) | 760×37 | 760×664 | 760×147 | 0.78 | 0 | **no** |

Reading share is constant at **0.78**: the composer takes 147 px and the strip 37 px of every centre
column, at every size. On a 900 px-tall screen that is 18% of the work area fixed overhead, and it
does not shrink when the composer is empty.

## Zone roles as implemented

| Zone | DOM | Role | Behaviour today |
|---|---|---|---|
| Topbar | `header` | `banner` | Brand is the `h1`; model select; status pill; ⌘K trigger; shortcut sheet; refresh |
| Rail | `nav` | `navigation` | Three tabs (Sessions/Files/Catalog), each a `tab` with `tabpanel`; collapse button; restore handle |
| Doc strip | `div[role=tablist]` | tab strip | Tabs with close; Arrow/Home/End; `⌘W`; `overflow-x: auto` |
| Transcript | `div` | **none** | `aria-live="polite"`, auto-follow when at bottom |
| Composer | `div` | **none** | Enter sends, Shift+Enter newline, `@`, `/`, history |
| Inspector | `aside` | `complementary` | Context/Audit tabs; no collapse control, only `⌘I` and a 24 px handle |

Two zones — the transcript and the composer — have **no landmark and no accessible name**. A screen
reader offers no way to jump to either.

## Findings, in severity order

### F1 · Panels cannot be resized — severe

`0` elements with `role="separator"`, `0` with `.resizer`, `resize` never set on any pane. Widths are
CSS literals: `276px` and `340px` at ≥1181 px, `252px` at ≤1180 px.

Against [A2](00-why-first-principles.md): *"Space is a resource the user allocates."* Today the user
cannot. A wide result table in a 822 px column at 1440 scrolls horizontally while 340 px of inspector
sits half-empty.

### F2 · Layout state is not persisted — severe

`localStorage` holds exactly two keys: a stream cursor per session, and prompt history. Panel
visibility (`railShown`, `inspShown`), the active rail tab, and the open document list are React
state only. **Measured:** hide the rail, reload → the rail is back. Every visit re-applies the
designer's defaults.

Against [A3](00-why-first-principles.md).

### F3 · The tab strip does not manage its own overflow — severe

`.doc-tabs { overflow-x: auto }` with no `scrollIntoView` for the active tab, no overflow menu, and no
scroll affordance. Opening enough documents leaves the active tab scrolled out of view. There is one
`scrollIntoView` in the codebase and it belongs to the palette.

Against [A5](00-why-first-principles.md) and [A6](00-why-first-principles.md).

### F4 · Two competing layout definitions — moderate (latent)

```css
/* line 66 */  .layout { grid-template-columns: 232px minmax(0, 1fr) 372px; }
/* line 363 */ .layout { grid-template-columns: 276px minmax(0, 1fr) 340px; }
```

The second wins by source order. The first is dead but **identical in specificity**, so any future
edit to it silently does nothing — the worst kind of dead code. The `no-inspector` variant is
duplicated the same way, with yet another pair (244 px vs 276 px).

### F5 · Search gives no progress and cannot be cancelled — moderate

Workspace search measures **4.29 / 4.09 / 4.19 s** for three consecutive queries. The UI shows the
word "searching…" for the whole time, in a tree that has no spinner, no cancel, and no result count.
Against [A4](00-why-first-principles.md).

### F6 · Two zones have no landmark or accessible name — moderate

The transcript and the composer are unnamed `div`s. The audit in
[001/20](../001-databricks-coding-agents/20-accessibility.md) passes because it checks contrast,
names of *controls*, and ARIA coherence — but landmark navigation is a different question, and these
two zones are not reachable by it.

### F7 · The inspector has no visible collapse control — moderate

The rail has `‹` and a restore `›`. The inspector has neither: only `⌘I` and a 24 px handle that
appears when it is already hidden. A mouse user cannot hide it; a keyboard user can. That asymmetry
is exactly what [A6](00-why-first-principles.md) forbids.

### F8 · The composer occupies 147 px even when empty — minor

The reading share is a constant 0.78. An empty single-line composer reserves the same height as a
five-line draft. Against [A2](00-why-first-principles.md) in spirit: fixed allocation where the
content does not need it.

### F9 · Zone layering is ad hoc — minor (latent)

`z-index` values in use: `1, 2, 3, 20, 39, 40, 41, 50`. There is no token scale, and `40`/`41` exist
only because the drawer was placed above and below its scrim by trial. This will break the first time
a popover is added inside a drawer.

## What is already right, and must not regress

- **Layout arithmetic.** At every width, `main.right == viewport.width - inspector.width` with no dead
  space, and `main.width` grows by exactly the rail's width when the rail is hidden (measured: 822 →
  1099 at 1440). The grid is correct; it is only inflexible.
- **Zero overflow** across 28 checks at four widths, including an injected 300-character token.
- **Zero accessibility findings** on the deployed app (contrast, names, targets, focus, ARIA, zoom,
  motion, forced-colors).
- **Keyboard coverage**: 16 shortcuts in one registry, a discoverable sheet at `⌘/`, a palette at
  `⌘K`, WAI-ARIA trees and tabs with roving focus, and a palette that traps focus (verified: eight
  consecutive Tab presses stayed inside the dialog).
- **Overlay discipline on narrow screens**: below 1180 px the inspector and below 820 px the rail
  become drawers with a scrim, and both start closed so they never cover the reading surface.

## The gap in one sentence per severity

| # | Finding | Severity | Axiom broken |
|---|---|---|---|
| F1 | No resizing | severe | A2 |
| F2 | No persistence | severe | A3 |
| F3 | Tab strip does not track its active tab | severe | A5, A6 |
| F4 | Duplicate `.layout` definitions | moderate | A1 (maintainability) |
| F5 | Search has no progress or cancel | moderate | A4 |
| F6 | Transcript and composer have no landmark | moderate | A6 |
| F7 | Inspector has no visible collapse control | moderate | A6 |
| F8 | Composer height is fixed when empty | minor | A2 |
| F9 | No z-index scale | minor | A1 |
