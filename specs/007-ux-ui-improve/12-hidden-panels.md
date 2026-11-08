# 12 — A hidden panel must always be findable (`ZN-7`)

Part of [007](README.md). Requirements: [03](03-requirements.md). Rounds 1–4: [11](11-outcome.md).

---

## The report

> "I have closed the right panel; but there is not panel to make it re appear — audit the full
> application, make sure there is always a control that makes a hidden panel appear."

## What the audit found — four separate defects, only one of them "missing"

I first tried to reproduce the literal claim (no control at all) and could not: at every width and in
both session states, the top-bar toggle hid and restored all three zones. The audit script proved
that, and it was the wrong question. The four real defects were:

| # | Defect | Evidence |
|---|---|---|
| **1** | **The layout menu had no Assistant row.** It listed Navigator, Inspector, Reset, Shortcuts. A user who hides the conversation and opens the menu named *Layout and panels* — the obvious place — finds no way back. | menu items read `Navigator ⌘B, Inspector ⌘I, Reset layout, Keyboard shortcuts…` |
| **2** | **The inspector's every control was disabled without a session.** The toggle, the menu row, all of it. The state in the report was exactly this: a notebook open with "No session", inspector hidden, and nothing able to bring it back. | `inspectorAvailable={Boolean(active)}` → `disabled` |
| **3** | **With no session the inspector rendered a blank body** even when reachable: no folder, no explanation. A panel that opens onto nothing reads as broken. | `.insp-body` innerText length 0 for the session field |
| **4** | **There was no control where the panel would be.** This is the actual root cause of the report. The only way back was one of eleven unlabelled icon buttons in the top bar, three of which look almost identical. A control that exists 900 px away, among lookalikes, is not a control a user finds. | the report itself; and the first screenshots of the fix, where the handles rendered **under the 52 px top bar** and were invisible |

Defect 4 is a *discoverability* failure, and it is the one worth generalising: **an invariant that
holds in the DOM is not the same as an invariant that holds on screen.**

## What was built

### 1. Edge handles — `components/EdgeHandles.tsx`

A handle appears on the edge its panel slides out from, **only while that panel is hidden**, and
never otherwise:

```
┌───────────────────────────────────────────────┬────┐
│ tabs                                          │    │
│                                               │ ▸  │ ← CONTEXT (inspector)
│   the notebook                                │    │
│                                               │ ▸  │ ← CHAT (assistant)
│                                               │    │
└───────────────────────────────────────────────┴────┘
```

- a real `<button>` with `aria-label`, `title` (which includes the chord) and a vertical word:
  **CONTEXT**, **CHAT**, **FILES** — the word is what turns an anonymous icon into a labelled control;
- the glyph says *which* panel, the word says it again in a form that is read at a glance;
- absolutely positioned in the centre pane's own padding, so it costs no layout;
- the set is derived from what is hidden (`handlesFor`), so a new zone cannot silently forget one —
  the panels e2e fails instead.

Three iterations were needed, all found by looking at the picture:

1. anchored to the viewport, the handles sat at `y=8` — **under the top bar**, present and invisible;
2. fixed to `.pane.main`, the chevron pointed *outward*, which reads as "push away";
3. inside a `writing-mode: vertical-rl` label, the chevron rotated to point **down**, reading as
   "collapse". Removed; icon + word carry it.

### 2. The layout menu lists all three zones

`dockVisible` / `onToggleDock` added, with the tick reflecting what is **on screen**.

### 3. The inspector no longer requires a session

`wantsInspector = inspShown` (was `Boolean(active) && inspShown`). With no session it now describes
the workspace instead of refusing to open: the fence (naming the folder a new session would use), the
tools, and — in Audit — a line saying the log fills as the agent works.

## The invariant, as a test (`ZN-8`)

`web/scripts/panels-e2e.mjs`, 6 widths × 2 session states, 42 assertions:

```
For every zone Z, at every width W, in every session state S:
  hide Z  ⇒  an ENABLED control exists  ⇒  it is HIT-TESTABLE  ⇒  Z is drawn again
  and      ⇒  an edge handle offers it while hidden, and none while shown
  and the layout menu lists all three, enabled, in every state
```

"Hit-testable" is `document.elementFromPoint` at the control's centre — not
`offsetParent !== null`, which is what let defect 4 through the first audit: a control clipped by an
`overflow: hidden` ancestor is present, unclickable, and reported as fine.

## Result

All 42 assertions pass at 1440, 1135, 1024, 900, 800 and 700 px, with and without a session. The
screenshots `30`–`34` record: everything hidden, everything restored, the inspector with no session,
the handles in place, and a 3× crop of the handles themselves.

## The general rule this adds to `03`

> **`ZN-7`** — A panel that can be hidden MUST have a control to show it again **at the edge it comes
> from**, enabled in every state the app can reach, with a name a person reads.
>
> **`ZN-8`** — That must be asserted by hit-test at every width and in every state, because presence
> in the DOM is not presence on screen.

## Still open

- The handles are 26 px wide; below `700 px` the centre pane is narrow enough that they overlap the
  first column of cells. Not fixed here: at that width a panel is a full overlay anyway, and moving
  them would need a different placement rule rather than a smaller number.
- The top-bar toggles remain three unlabelled icon buttons among eleven. They work and now have
  titles, but the icon set does not distinguish "panel" from "layout" strongly. A second increment.
