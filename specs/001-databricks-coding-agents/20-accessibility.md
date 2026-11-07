# 20 · Accessibility and quality gates

What this document is: the accessibility standard this app holds itself to, how each part of it is
verified by a machine on every run, and what is still not covered. It exists because "accessible" is
a claim that must be checkable, not a adjective in a README.

The target is **WCAG 2.2 level AA**, plus the platform expectations that the best SaaS products of
2026 actually ship (keyboard parity, visible focus, honouring OS preferences), plus the two audits
that catch the failures people actually see: content spilling out of its box, and layout breaking
under zoom.

## How it is verified

Three executable audits, all runnable against localhost or the deployed app:

```bash
cd apps/coding-agent/web
npm run audit:a11y       # WCAG contrast, names, targets, ARIA, focus, zoom, motion, forced colours
npm run audit:overflow   # nothing spills its box, at 1480/1180/900/760 px
npm run e2e:shell        # keyboard: palette, panes, tabs, Enter vs Shift+Enter
npm run e2e:live         # the product workflow, 19 steps, real agent
```

Both audits exit non-zero on a finding, so neither can rot silently. The last runs against the
**deployed** app: `audit:a11y` 0 findings, `audit:overflow` 0 findings across 24 checks,
`e2e:shell` all steps, `e2e:live` 19/19. Unit suites: 150 pytest, 72 vitest.

## What the audit checks, and why each item is there

| Check | Standard | Why it is on the list |
|---|---|---|
| Contrast of every text node with its **painted** background (alpha blended, walking up the tree) | WCAG 1.4.3 AA: 4.5:1 body, 3:1 large | The usual failure is text that passes on white and fails on a tint; blending finds that |
| Accessible name for every control | WCAG 4.1.2 | An icon-only button with no name is unusable with a screen reader |
| Target size ≥ 24×24 CSS px | WCAG 2.5.8 AA | Small icon buttons are the most common miss; prose links are exempt |
| A visible focus indicator on **every** control reachable by Tab | WCAG 2.4.7, 2.4.11 | Verified by pressing Tab 45 times, not by calling `.focus()` — `:focus-visible` only matches real keyboard use |
| One `h1`, no skipped heading levels | WCAG 1.3.1 | Structure for people who navigate by heading |
| `role="tab"` with `aria-controls` and a `tabpanel` | ARIA APG | A tab strip that does not name its panel is a lie to assistive tech |
| No positive `tabindex` | WCAG 2.4.3 | Tab order must follow reading order |
| Dialog has `aria-modal` and a name | ARIA APG | Palette and shortcut sheet are modal; the rest of the page is inert to a reader |
| Text is not clipped at 200% zoom | WCAG 1.4.4 | Reflow, tested at 720 px wide at 2× density |
| No transition or animation under `prefers-reduced-motion` | WCAG 2.3.3 | Preference honoured, measured per element |
| Every control still visible in **forced-colors** (Windows high contrast) | WCAG 1.4.1, 1.4.11 | A control that vanishes is not usable without colour |
| Content stays inside its own shape, at four widths | craft | The defect this pass started from: a `×` that looked outside its tab |
| A 300-character unbroken token cannot widen its column | craft | Injected deterministically, so a real model's worst output is covered without waiting for it |

## Defects this pass found and fixed

| Finding | Severity | Fix |
|---|---|---|
| 28 controls with no visible focus | serious | They had none for *programmatic* focus only; real Tab was fine. The audit was rewritten to drive the keyboard, which is what a person does |
| Text at **4.44:1** on the pastel tints (needed 4.5) | serious | `--ink-3` darkened to `#5c6373`, `--green-700` to `#24623d`; contrast is now computed against the blended background |
| `⌘⏎` keycap text at **1.04:1** — effectively invisible | serious | Keycaps carry `--ink-2`; they are the only place a shortcut is explained |
| 29 targets under 24×24 px (`rail-collapse` 16×19, model `<select>` 17 px tall, `Open` pills 86×22, `ext-link` 15×19, doc `×` 18×18) | moderate | Minimum 24×24 hit area on each; visual marks stay the same size |
| Zero `h1` on every screen; two on the empty state | moderate | The top bar is the `h1`; the empty state's promise is an `h2` |
| Rail and inspector tabs had no `aria-controls` | moderate | Both tablists now point at a `tabpanel`; the doc tab strip shares one panel |
| Working-folder input had no accessible name | moderate | `aria-label` and a placeholder |
| The `×` read as outside its tab | craft | It was a sibling of the tab; it is now inside the tab's own shape, with symmetric inset, and its tint appears only under the pointer |

## A note on running these audits

Run **one** audit at a time against a deployed app. Two headless browsers streaming from the same
app at once made a page report "crashed" in a run of this suite; the same page, alone, loaded in 4 s,
held a steady 10 MB heap and 176 DOM nodes through a whole turn, and the suite then passed 19/19.
That was contention in the harness, not a defect in the product — but it is worth knowing before
reading a red result as a product bug.

## Below the best, stated plainly

- **No screen-reader run.** Roles, names and relationships are asserted by role-based queries and by
  the audit above, but VoiceOver or NVDA has not been driven against the app. That is the gap between
  "conforms in tests" and "confirmed usable".
- **No automated axe-core run.** The audit implements the checks directly so its rules are readable,
  but a maintained ruleset would catch things this one does not think of.
- **Live-region politeness is coarse.** The transcript is `aria-live="polite"`; a long streaming
  answer will read as a wall of text. Better: announce the turn's completion, not each token.
- **No high-contrast theme of our own.** Forced-colors is respected; a designed high-contrast dark
  theme is not shipped.
- **Density is not user-adjustable.** There is one comfortable density; the best products offer a
  compact mode for people who scan a lot.
