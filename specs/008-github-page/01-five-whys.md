# 01. Five whys, then first principles

[Index](README.md) · next: [02 Grounded assessment](02-grounding.md)

Most project pages start from "the other project has a landing page, so let us have one". That produces a
brochure: a hero, three icons, a star count. It is worse than no page, because it spends the reader's
attention and returns nothing checkable.

This document finds the constraint first — why a page is needed at all, and what it must contain to be
worth reading — and derives everything else from it.

---

## The five whys

The request, as stated: *"Genie Code in Databricks cannot [use] a specific AI model and is expensive;
OpenGenie solves this problem."*

**1 · Why does that matter to a reader?**
Because the choice of model is the reader's, not a vendor's. The repository measures it: the *same*
tools and rules scored **39%** with one model and **86%** with another (`docs/06-results-and-lessons.md`,
[CL-3](12-claims-ledger.md)). If the model is the largest lever on outcome, a product that pins the model
has pinned the outcome.

**2 · Why is a page the right response to that?**
Because the evidence for it is already in this repository and is not reachable from outside it. A reader
who finds `raphaelmansuy/edgegenie` on GitHub sees a README about *replacing Genie Code with a coding
agent* — a study — and not the thing that resulted from the study: an application, with a model picker,
a write fence and a screenshot of each. The repository's best asset is invisible from its front door.

**3 · Why is it invisible, if the README is 10 KB?**
Because the README optimises for a reader who has already decided. It opens on *"One sentence: you can get
most of what Genie Code does…"*, then eleven graded tasks, then a variant ladder. That is a lab report.
It answers "did the claim hold?" and never answers "what is this thing, what does it look like, and what
does it cost me?".

**4 · Why was it written that way?**
Because it was written while the work was a *study*, and the study's audience was its author. Findings
were the deliverable. Then `apps/coding-agent` was built, and the same README kept growing downwards with
tables and caveats rather than upwards with a product. The document's shape froze at the moment the work
changed kind.

**5 · Why does that matter beyond one typo?**
Because a first-party page is the only place where **a claim and its proof can be adjacent**. Everywhere
else — a blog post, a slide, a LinkedIn comment — the number and its source drift apart within a week.
This repository can put the score, the command that regenerates it, and the screenshot of the run on one
screen. That adjacency is the entire product of this page. Nothing else it could offer is scarce.

**The root cause:** *the work became a product and its front door stayed a lab report.* Every symptom
follows: no screenshot of the app above the fold, no install path a reader can follow, no licence, no
answer to "who is behind this", and a set of numbers whose method is three clicks away.

---

## First principles

Reduced until each statement is either true by construction or a product decision a reader can argue with.
There are seven.

### P1. A number without its regeneration command is a rumour

The repository's strongest habit is that `exams/inject_tables.py` rewrites the README's tables from
`exams/results/`. The site must inherit that habit, not imitate its output: every figure is computed at
build time by `site/claims.py` from the same JSON files, and the build **fails** if a figure in the prose
is not one of the computed values.

*Consequence:* `[CL-*]` ids (see [12](12-claims-ledger.md)) are the only way a number enters the HTML. A
hand-typed `94%` in `content/*.md` breaks `site/check.py`. This is `[PG-9]`.

### P2. The page must work with JavaScript off, and with images blocked

A GitHub Pages site is read in a terminal (`curl | less`), by a crawler, by a screen reader, and by
someone on a conference wifi with images off. Three of those four do not run JavaScript. So: content is
in the HTML at build time; the only script is progressive (Mermaid rendering, theme, the mobile menu,
copy buttons); every diagram has a text or table equivalent.

*Consequence:* diagrams are `<pre class="mermaid">` whose fallback is the readable source, and every page
has a real `<h1>`, ordered headings and a "skip to content" link. Tested by `[S5]`, `[S7]`.

### P3. Two glances about the same thing cannot share a slot

This is the rule [006](../../specs/006-databricks/00-why-first-principles.md) applied to a conversation
and a document; here it applies to **a claim and its evidence**. A reader comparing "94%" with the method
behind it should not navigate. So each claim's card carries its denominator, its run count and a link to
the ledger entry, and the ledger entry carries the command.

*Consequence:* the evidence page opens with the numbers and the caveats *side by side*, not with a
narrative that ends in a disclaimer.

### P4. A control that cannot act must not be shown

An earlier draft of the site had a "Live demo" button that led to a screenshot. That is the defect
[007 P4](../../specs/007-ux-ui-improve/01-five-whys.md) names in the app: a control that teaches the user
the product is unreliable. There is no hosted demo — the app needs a workspace token — so there is no
"Live demo" control. The tour is labelled a tour.

*Consequence:* `[PG-6]` requires that every call to action resolves to a page or a repository file that
exists, checked by link verification, not by eye.

### P5. The page is one of the project's outputs, so it is tested like one

This repository tests the app with 466 Python tests, 509 front-end tests and 14 Playwright scenes. A site
built to the same standard is not a courtesy; it is the same discipline applied to a second artefact. It
gets an audit (`site/check.py`: links, anchors, one `h1`, alt text, balanced markup, sitemap), a visual
pass (`site/shots.py`: every scene screenshotted and *looked at*), and an accessibility pass computed from
painted colours, not declared ones.

*Consequence:* `[PG-11]`, and the loop in [10](10-e2e-plan.md) — a screenshot that has not been inspected
is not evidence.

### P6. Cost is the reader's question, so it gets an honest answer, not a number

The repository explicitly refuses to publish a cost comparison: it measured tokens, not money, and had no
Genie Code usage history (`docs/07-decision-guide.md#cost-in-plain-words`). A page that says "10× cheaper"
would be inventing a fact to win an argument it has already won on merit.

*Consequence:* the site publishes the *shape* of the cost — token counts per setup, the fact that a
stronger model reads 3× more, the fact that a failed run costs twice — and says plainly what it cannot
know. `[CL-7]`. This is the hardest rule to keep, because a cheaper-sounding number would convert better.

### P7. The licence is part of the interface

"Can my employer use this?" is a first-minute question, and the repository had no `LICENSE` file at all.
An answer that requires reading `pyproject.toml` (which did not declare one either) is no answer.

*Consequence:* `LICENSE` at the repository root, Apache-2.0, referenced from the README's first screen,
the site footer, and every page's structured data. `[PG-12]`.

---

## What follows, as one claim

> If every number on the page is computed from the repository, and every claim sits next to its
> denominator and its command, then a suspicious reader can check the page in the time it takes to read
> it — and the page becomes evidence rather than marketing.

Everything in this set is engineering under that claim. `claims.py` is the computation. The ledger is the
adjacency. `check.py` is the enforcement. The seven lenses in [06](06-lenses.md) are the objections that
survived.

---

## What would falsify this

Stated so the design can be argued with rather than merely followed.

| If this were true | Then the design is wrong |
|---|---|
| Readers arrive only from a link in a discussion thread, already convinced, and never read a second page | The single long page should be *the* site; the seven routes are over-engineering. Counter-evidence: a tutorial reader and an evidence reader want different things, and one page serving both is 4,000 words. |
| The measured numbers are too small and clean to persuade anyone doing real work | Then the honest move is to lead with the *method* and the screenshots, and relegate the scores. The current order does the opposite. This is the weakest assumption on the page and is marked as such in [11](11-outcome.md). |
| A hosted demo becomes possible (an app with a scoped demo token) | Then `[P4]` inverts: a real demo is the strongest possible page, and everything else becomes support. |
| Apache-2.0 is the wrong licence for a Databricks App that customers deploy | Then `[P7]` needs a second pass with counsel; the site would have to say so. Not resolved here. |

These are revisited in [11 §What would change our mind](11-outcome.md#what-would-change-our-mind).
