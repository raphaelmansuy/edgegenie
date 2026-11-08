# 08 — Implementation plan

Part of [007](README.md). Requirements: [03](03-requirements.md). Architecture: [07](07-architecture.md).
Edge cases: [09](09-edge-cases.md). Scenes: [10](10-e2e-plan.md).

Four phases. Each ends green (unit + e2e) and each is independently shippable. Order is chosen so
that the *tests that catch the next phase's regressions* exist first: phase 1 adds the focus
contract, phase 2 uses it, phase 3 measures what phases 1–2 changed.

---

## Phase 1 — the focus contract and the registry (`KB-1`, `KB-5`, `KB-9`, `KB-10`, `KB-2`)

The riskiest phase, because it changes a visible chord. Done first, alone, so a regression is
attributable.

| # | Change | File |
|---|---|---|
| 1.1 | Add `owner` + `when` to `Shortcut`; add rows for `⌘J`, `⌘⇧I`; change `toggleInspector`'s label to say what it does | `domain/keys.ts` |
| 1.2 | `resolve(event, ctx)` — pure arbitration, most specific first | `domain/keys.ts` |
| 1.3 | Tests: every `SHORTCUTS.combo` is unique; every id in `handlers` exists in `SHORTCUTS`; `resolve` matrix | `domain/keys.test.ts` |
| 1.4 | `useHotkeys` delegates to `resolve`; keeps `isTyping` as an input to the context, not a second filter | `hooks/useHotkeys.ts` |
| 1.5 | `useReturnFocus(open, {fallback})` | `hooks/useReturnFocus.ts` (new) |
| 1.6 | Wire it into `Palette`, `ShortcutSheet`, `ProviderSettings`, `ApprovalSheet`, `FolderPicker` | 5 components |
| 1.7 | `NotebookEditor`: cell prompt moves to `⌘⇧I`; `⌘I` no longer handled there | `components/NotebookEditor.tsx` |
| 1.8 | Test: opening each dialog and pressing Escape returns focus to the opener | `useReturnFocus.test.tsx` (new) |

**Acceptance:** the shortcut sheet says `⌘I` inspector and it opens the inspector with a cell focused;
`⌘⇧I` opens the cell prompt; Escape from the palette puts focus back on the palette button.

## Phase 2 — reachability (`KB-7`, `KB-4`, `ZN-5`, `ZN-3`, `ZN-4`, `KB-3`)

| # | Change | File |
|---|---|---|
| 2.1 | `SkipLinks` component + `id="dock"`, `tabIndex={-1}` on `#doc-panel` and the dock | `components/SkipLinks.tsx` (new), `App.tsx` |
| 2.2 | Cell action buttons `tabIndex={-1}`; section handles ←/→ between them | `components/NotebookEditor.tsx` |
| 2.3 | `nextInRing(i, n, step)` pure helper + test | `components/Tree.tsx` or `domain/cellkeys.ts` |
| 2.4 | Composer's own focus ring | `styles.css` |
| 2.5 | Assert landmarks + unique names in the audit script | `scripts/shell-audit.mjs` |
| 2.6 | Measure the Tab budget; fail if > 12 to the code | `scripts/shell-audit.mjs` |

**Acceptance:** Tab on a fresh page shows "Skip to the work"; Enter moves focus into `main`; Tab from
there reaches the code in ≤ 12 stops; Tab from a focused cell leaves that cell.

## Phase 3 — the scroll rules (`SC-1`, `SC-3`, `SC-5`)

| # | Change | File |
|---|---|---|
| 3.1 | Remove `scroll-behavior: smooth` from `.transcript`, `.dock-body` | `styles.css` |
| 3.2 | `overscroll-behavior: contain` on `.cells`, `.dock-body`, `.transcript`, `.tree-body` | `styles.css` |
| 3.3 | Test: no element in the notebook view reports `scroll-behavior: smooth`; every scroller reports `contain` | `scripts/shell-audit.mjs` |
| 3.4 | Test: the page never scrolls while focusing an off-screen cell (`SC-4`) | `scripts/shell-audit.mjs` |

**Acceptance:** a wheel at the last cell does not navigate; no scroller in the notebook reports
`smooth`; the "Show" jump is still smooth (asserted).

## Phase 4 — the sheet tells the truth, and the docs (`KB-6`, `KB-8`)

| # | Change | File |
|---|---|---|
| 4.1 | Sheet groups by *scope* (Global / In a cell / In the message box) using `owner` | `components/ShortcutSheet.tsx` |
| 4.2 | `KB-8`: escape order asserted as a unit test over a pure `escapeTarget(ctx)` | `domain/keys.ts` + test |
| 4.3 | This folder's `10-e2e-plan.md` gains the screenshot list; the e2e writes into `e2e/screenshot/` | docs |

**Acceptance:** the sheet's three groups match the registry's owners; the Escape test matrix passes.

---

## The e2e (built alongside, extended per phase)

One script, `web/scripts/shell-e2e.mjs`, one scene per requirement group, screenshots to
`specs/007-ux-ui-improve/e2e/screenshot/`. Scene ↔ requirement ↔ screenshot:

| Scene | Requirements | Screenshots |
|---|---|---|
| S1 skip links | `KB-7`, `ZN-5` | `01-skip-visible.png`, `02-focus-in-main.png` |
| S2 dialogs return focus | `KB-1`, `KB-3` | `03-palette-escape.png`, `04-sheet-escape.png`, `05-composer-focus.png` |
| S3 chords | `KB-2`, `KB-9`, `KB-10`, `KB-5` | `06-inspector-cmd-i.png`, `07-cell-prompt-cmd-shift-i.png`, `08-sheet.png` |
| S4 the cell is one stop | `KB-4`, `ZN-4` | `09-cell-ring.png` |
| S5 scroll | `SC-1`, `SC-3`, `SC-4` | `10-scroll-end.png`, `11-show-smooth.png` |
| S6 zones | `ZN-1`, `ZN-2`, `ZN-6`, `ZN-3` | `12-1440.png`, `13-1024-focus.png`, `14-800-drawer.png`, `15-dark.png` |

Each scene runs at 1440 and one of 1024/800, in light and dark where colour is involved.

## Order of work, as five commits

1. `keys: owner, when, and resolve()` + tests — no behaviour change yet.
2. `focus: useReturnFocus in five dialogs` — `KB-1` lands.
3. `keys: ⌘I is the inspector, ⌘⇧I asks about the cell` — `KB-2`, `KB-9`, `KB-10`.
4. `a11y: skip links, one Tab stop per cell, a composer ring` — `KB-7`, `KB-4`, `KB-3`.
5. `scroll: no smooth on data, contain at the edges` + sheet by scope — `SC-*`, `KB-6`.

Steps 1–3 are one logical change and may be reviewed together; step 4 and 5 are independent.

## What "done" means, mechanically

```
npx tsc -b                     → 0 errors
npx vitest run                 → all pass, +≥ 18 new tests
.venv/bin/python -m pytest -q  → unchanged (no backend change)
npm run build                  → 0 errors, no new chunk over 12 KB
node scripts/shell-e2e.mjs     → all scenes pass, screenshots written
node scripts/shell-audit.mjs   → Tab-to-code ≤ 12, no missing focus style, no page scroll
```

## Risks, and how each is retired early

| Risk | Retire it by |
|---|---|
| `⌘⇧I` collides with a browser or OS shortcut | check the three target browsers + the deployed app in `[S3]`; if it collides, `⌘⌥I` is the fallback (`D9`) |
| Roving tabindex on cells confuses pointer users | the buttons stay visible on hover/focus; `[S4]` screenshots both modes |
| Skip links hurt CLS | absolute positioning; the audit asserts `body.scrollH === innerH` |
| Removing `smooth` feels abrupt for the "Show" jump | `Show` keeps `behavior:"smooth"` in JS; `[S5]` asserts it |
| A dialog's opener disappears while it is open | `useReturnFocus` falls back to a named successor (`[E-2]`) |
