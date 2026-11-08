# 01 — Five whys, then first principles

Part of [007](README.md). Requirements live in [03](03-requirements.md); the measured evidence for
every claim here is in [02](02-assessment.md).

---

## Why 1 — why this work?

Because on the deployed app a person can lose their place. Three ways, all measured:

1. **`⌘I` asks the agent about a cell instead of opening the inspector.** The cell prompt and the
   inspector share one shortcut; the cell wins wherever a cell has focus. The inspector opens
   "Show or hide the inspector" is written in the shortcut sheet and it is false ~90% of the time.
2. **The palette and the shortcut sheet return focus to `<body>`.** Escape closes them and the
   keyboard is nowhere — so the next Tab starts again at the top of the page.
3. **There is no skip link and the centre pane is not a landmark you can jump to.** Reaching the
   code from the top bar takes 40 Tab presses; reaching the conversation takes more.

## Why 2 — why does that matter?

Because this product's promise is *the agent changes your notebook while you watch*. A user who is
mid-edit is looking at a cell. If reaching the inspector costs them their place, they will not open
the inspector; if the palette costs them their place, they will not use the palette; and the two
surfaces that make the app trustworthy — scope and audit — go unread.

## Why 3 — why did it end up this way?

Because the shell grew per feature. Each feature added a shortcut to one `handlers` object and a
zones entry to one CSS file; nothing owned the *set*. Evidence: `"mod+i"` appears once in
`App.tsx:504` (the inspector) and is also bound by `NotebookEditor` for the cell prompt — two
owners, no arbitration. The palette and sheet each got their own dialog and neither got a
focus-return contract. The skip link was never written because no document asked for it.

## Why 4 — why was no one document asking?

Because 003 and 006 specified *features* (the notebook, the dock) and treated the shell as
scaffolding. The shell had a contract only in fragments: `SH-A1..A6` for the separator, `NB-2` for
cells, `006 AD-*` for the dock. Nobody owned "the whole keyboard" or "the whole scroll surface", so
no test asserted them either.

## Why 5 — why does that matter more than a missing feature?

Because the shell is the only surface every feature goes through. A missing feature costs one
capability; a broken shell costs *all* of them at once, and it does so invisibly — it shows up as
"the app feels fiddly", which nobody files a bug for. That is why this spec exists as its own
numbered set, with its own ids, and its own e2e with screenshots.

---

## First principles

Strip it back. A browser gives a person exactly four channels into an app:

| Channel | What it can express | What the app must therefore own |
|---|---|---|
| **Pointer** | position, button, drag, wheel | hit targets, drag semantics, wheel routing |
| **Keyboard** | focus order, keys, chords | a focus contract, a key registry, arbitration |
| **Screen reader** | landmarks, roles, names, live regions | structure, names, announcements |
| **Viewport** | width, height, DPR, zoom | one geometry model, one overflow story |

Everything about a shell is a policy over these four. Five irreducible rules follow, and every
requirement in [03](03-requirements.md) is a consequence of one of them.

### P1 — Focus is the cursor of the keyboard, so focus is app state

If focus can be lost, the keyboard is lost. Therefore: anything that opens must know where it came
from and put focus back there; anything that closes must hand focus to a *named* element, never to
`<body>`. A focus target that is removed must nominate a successor.

→ `KB-1..KB-4`.

### P2 — A chord has exactly one owner

If two handlers can answer the same chord, the winner is whichever ran first — which is
indistinguishable from a bug. Therefore: every chord has one owner, and where a context genuinely
changes the meaning, the *same* owner decides by context, in one place, testable as data.

→ `KB-5`, `KB-6`, `[D3]`.

### P3 — Scrolling is a budget, and the user owns it

Wheel and trackpad events are the one channel where a wrong answer is felt immediately. An inner
scroller that is not the thing under the pointer, a `smooth` scroll the user did not ask for, or a
nested scroller that traps the wheel are all the same bug: the app took the budget. Therefore: one
scrolling surface per axis per region, `overscroll-behavior` set deliberately, and no programmatic
scroll on a data update.

→ `SC-1..SC-5`.

### P4 — A zone must earn its pixels at every width

A column that cannot show its content is worse than a drawer, and an overlay that covers the work
is worse than a narrower column. Therefore: geometry is a pure function of viewport and intent,
with one priority order, and the centre is never sacrificed.

→ `ZN-1..ZN-4`. (`layout.ts` already implements this; this spec only *tests* and *states* it.)

### P5 — Reachability is a property of the whole page, not of a component

Any single component can be reachable and the page still be unusable if the path to it is long or
unnamed. Therefore: skip links, landmarks, and a measured Tab budget.

→ `KB-7`, `ZN-5`.

---

## The inversion this spec makes

The old model: *features own their keys; the shell is the leftover.*

The new model: **the shell owns the keys, the scroll and the focus; a feature requests a key.** In
practice that means one registry (`domain/keys.ts`) grows three fields — owner, `when`, and
`scope` — and one hook (`useHotkeys`) becomes the arbiter instead of a lookup table. Nothing else
in the app changes shape.

That is small on purpose. [08](08-implementation-plan.md) is four phases, and the largest is
"make `⌘I` mean the inspector again".
