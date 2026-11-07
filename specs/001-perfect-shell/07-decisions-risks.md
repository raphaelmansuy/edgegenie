# 07 · Decisions, alternatives and risks

[Index](README.md) · prev: [06 Edge cases & tests](06-edge-cases-testing.md)

## Decisions taken, with the alternative that was rejected

### D1 · A pure layout module, not component-local state

**Chosen:** `domain/layout.ts` owns bounds, defaults, clamping, `columns()` and (de)serialisation.

**Rejected:** keeping widths in `useState` inside `App` and writing inline styles. It is fewer files,
but geometry becomes untestable without a browser, and the bounds arithmetic — the only part that can
be *wrong* — ends up inside JSX.

**Cost:** one more file and an indirection. **Benefit:** the bounds are unit-testable and the same
numbers cannot drift between the separator, the CSS and the persistence layer.

### D2 · Columns via a CSS custom property, not inline `gridTemplateColumns`

**Chosen:** `style={{ "--layout-columns": columns(...) }}` and one CSS rule reading `var()`.

**Rejected:** `style={{ gridTemplateColumns: columns(...) }}`. It works, but it inlines a value the
inspector cannot show, and it makes the fallback invisible. The custom property keeps the default and
the override in one readable place, and lets a themed stylesheet or forced-colors mode override it.

### D3 · Layout is per browser, never per account

**Chosen:** `localStorage`, one namespaced key.

**Rejected:** a `ui_preference` table keyed by user. It would sync across devices — and would also mean a
layout chosen on a laptop fights one chosen on a desktop, plus a migration and a privacy question about
what else ends up in that row. The Databricks lens in [04](04-lenses.md) is decisive: no path, no
identity, geometry only.

### D4 · Drawers below 1180 px rather than a three-column squeeze

**Chosen (already in place, kept):** below 1180 the inspector becomes an overlay; below 820 the rail
does too; both start closed.

**Rejected:** shrinking all three columns. Measured alternative: at 900 px, three columns would give the
centre ~300 px — narrower than a code line. An overlay that the user summons is better than a column
that is always too narrow.

### D5 · Tab strip scrolls; it does not shrink indefinitely

**Chosen:** tabs shrink to a readable minimum (~90 px), then the strip scrolls, the active tab always
visible, hidden count shown.

**Rejected:** infinitely shrinking tabs (unreadable) and a dropdown replacing the strip (loses
recognition). The count is the compromise that keeps "how many are there" answerable at a glance.

### D6 · Search stays client-side, and becomes honest rather than faster

**Chosen:** keep the bounded walk (120 dirs, 8 s), add spinner, partial count, cancel.

**Rejected:** a server-side index. It would be faster, but the Databricks workspace API has no
name-search endpoint ([01 F5](01-shell-audit.md)), so an index would be a service to run, warm and
invalidate — a product decision well beyond a shell spec. The shell's obligation is honesty about the
wait, which is requirement SH-D2.

### D7 · Reset is a command, not a confirmation dialog

**Chosen:** "Reset layout" in the palette and the shortcut sheet, applied immediately.

**Rejected:** a confirm dialog. Layout is trivially recoverable (set the widths again) and the dialog
costs a click every time. A toast with an Undo would be the right refinement if users ask — noted as a
follow-up, not shipped.

### D8 · No new visual language

**Chosen:** reuse the existing tokens; add only `--z-*` and `--sep-*`.

**Rejected:** a refreshed type scale and spacing system. The accessibility audit is at zero findings;
changing tokens now risks a regression for no measured gain. Any visual work should be its own spec
with its own before/after audit.

## Risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | A resize re-renders the transcript and reintroduces the freeze seen earlier | medium | high | SH-A6: no transcript state in the drag path; e2e resizes during a streaming turn and asserts completion ([06 A7](06-edge-cases-testing.md)) |
| R2 | Deleting the duplicate `.layout` rule changes widths somewhere unnoticed | medium | medium | P3 comes after P0 produces columns; the rect table in [01](01-shell-audit.md) is re-measured before and after, and must match |
| R3 | Persistence makes a bad layout permanent | medium | medium | Reset in two places (SH-B3); corrupt input falls back (SH-B2); bounds re-clamp on read (B8) |
| R4 | Pointer capture breaks on Safari or with a touchscreen | medium | medium | fall back to `pointermove` on `document`; a manual device check is in the matrix ([06 A11](06-edge-cases-testing.md)) |
| R5 | Tab strip scroll fights the transcript's auto-scroll | low | medium | Different containers, different scroll owners; asserted in e2e (C1, E2) |
| R6 | A drawer plus a popover breaks stacking | medium | low | z-index scale (P8) lands **before** any new popover is added |
| R7 | Sessions are in memory only, so a shell that remembers layout forgets conversations | **certain today** | high for the product | Out of scope here; recorded in [001/18](../001-databricks-coding-agents/18-gap-analysis.md#residual-gaps-not-done). Flagged to the PO lens as the next thing to fund |
| R8 | Two audits running at once against one deployment give a false failure | known | low | documented; run one at a time ([06](06-edge-cases-testing.md#how-these-are-run)) |

## Open questions for the owner

1. **Should the composer be resizable too?** It grows to 8 lines. A drag handle on it would be
   consistent, but it is the third-most-requested thing in every chat UI and the least used. Proposal:
   not in this spec; revisit after real usage.
2. **Should the rail remember its scroll position per tab?** Sessions/Files/Catalog each have their own
   list. Cheap to add (three numbers), but it makes the persisted blob six fields instead of five and
   adds a "why did my tree jump" class of bug. Proposal: yes, but in a follow-up.
3. **Should a layout be exportable?** A "copy my layout" string is nice for support ("send me your
   layout"). Proposal: no — the reset button solves the only real problem.
4. **Do we want a compact density?** [001/20](../001-databricks-coding-agents/20-accessibility.md) lists
   it as missing. It is a token change plus a stored enum, which fits this module cleanly. Proposal:
   next visual spec, not this one.

## Traceability

| Requirement group | Where implemented | Where tested |
|---|---|---|
| SH-A (layout is the user's) | P0, P1, P5 | `layout.test.ts`, `audit:shell`, e2e A |
| SH-B (state remembered) | P0, P2 | `layout.test.ts`, `audit:shell` remembers |
| SH-C (navigation complete) | P4 | `DocTabs.test.tsx`, e2e C |
| SH-D (feedback honest) | P7 | e2e D |
| SH-E (frame stable) | P5, P3 | e2e E, overflow audit |
| SH-F (zones addressable) | P6, P1 | `audit:a11y` (landmarks) |
| SH-G (implementation healthy) | P3, P8, P9 | `rg` guards in P3/P8, all audits |
