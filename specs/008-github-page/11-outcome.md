# 11. Outcome: what shipped, and what the pictures changed

[Index](README.md) · prev: [10 E2E plan](10-e2e-plan.md) · next: [12 Claims ledger](12-claims-ledger.md)

Requirements: [03](03-requirements.md). Plan: [08](08-implementation-plan.md). Every screenshot is in
[`e2e/`](e2e/), and every one was opened and looked at before it was accepted.

---

## Delivered

| Requirement group | State | Proof |
|---|---|---|
| `PG-1` … `PG-18` | done, with one exception below | [S1](e2e/home/), [S2](e2e/home/home-claims.png), [S3](e2e/evidence/), [S4](e2e/about/) |
| `NAV-1` … `NAV-8` | done | [S5](e2e/states/nav-open-390-light.png), [S7](e2e/states/) — relative links, `aria-current`, three theme states, menu, skip link, rail, pager, anchors |
| `CPT-1` … `CPT-8` | done | [S3](e2e/evidence/evidence-card.png) reads all eight cards' value, caveat, source and run count |
| `AX-1` … `AX-9` | done | [S7](e2e/states/) measures contrast from painted colours in both themes; [S8](e2e/states/no-js-home.png) runs with JavaScript and images off |
| `PF-1` … `PF-7` | done | [S9](e2e/audit.json) checks weight and determinism; `check.py` fails on a missing file |
| `SEO-1` … `SEO-6` | done | `check.py --meta --sitemap`; [S10](e2e/states/404.png) |

**178 automated checks, 0 failing**, across 10 scenes — plus 14 claim tests, 9 `check.py` passes, 128 spec cross-references, 21 ASCII wireframe boxes and 12 Mermaid diagrams, all clean. The audit is
[`e2e/audit.json`](e2e/audit.json): every route's contrast findings, target sizes, overflow and page weight.

### The one requirement not met as written

`PG-4` says each of the seven pages is reachable from the header on every other page. It is, with one
nuance: the fifteen `/reference/<doc>/` pages belong to the **Reference** nav item and do not get their own
header entry. That is deliberate — fifteen more nav items would be a menu, not a header — and the reference
index lists them all. The requirement as written is about the seven, and those seven are reachable
everywhere.

---

## What the screenshots found that the assertions did not

This is the value of the inspection loop, stated plainly. Each of these passed every automated check.

1. **The mobile header overflowed by 18 px.** 390 px could not hold the wordmark, the Menu button, three
   theme buttons and the GitHub link. The audit caught the symptom (`scrollWidth 408 > 390`) but not the
   cause; the picture showed the GitHub icon hanging off the right edge. Fixed by dropping the button's
   *label* (the icon is unambiguous), moving the GitHub link into the menu, and keeping the wordmark — a
   lone glyph in a header is anonymous, and identity is worth 8 px.
2. **"3 runs" appeared next to "one run each" on every claim card.** The count was right (three missions
   were graded) and the caveat was right (each was run once), and together they read as a contradiction.
   Renamed to "3 graded runs" and joined with a separator. No assertion could have caught this: both
   numbers were correct.
3. **A Mermaid diagram stayed white on a dark page.** The repository's documents carry their own
   `%%{init: …}%%` block with light-theme colours, which overrode the site's theme. The diagram was legible
   and the contrast audit passed — because the audit measures text against its own painted background, and
   the SVG painted its own. Fixed by stripping the init directive at render time and re-rendering on a
   theme change; now asserted from the computed `fill` of the diagram's canvas.
4. **The footer's column labels were `<h4>`.** After an `<h2>` that is a heading-level skip, and a screen
   reader's outline gained four headings that were not sections. The markup check caught this one, which is
   why it is listed as *found by a test* rather than by an eye — but it was found by looking at the outline
   in the first place.
5. **The 404's cards were `<h3>`** for the same reason, and its links were absolute, so every one 404'd
   from the 404. Fixed by making the page's own links relative and its card titles text.

## Defects the tests found, that a reader would have hit

Recorded because they were mine, and because each now has a check that fails if it returns.

| Defect | How it was found | Now |
|---|---|---|
| Raw HTML in the content files was escaped, so the whole home page rendered as one paragraph | `[S2]` found zero cards | `trusted_html` for first-party prose, escaping for repository documents |
| The HTML block parser ended at the *first* closing tag, splitting nested cards | `[S1]` reported unbalanced markup | depth counting, so a nested `<div>` is one block |
| GitHub's heading slug does not collapse spaces, so `Step 4 · Point…` is `step-4--point-…` and every doc cross-reference died | `check.py --links` | `slugify` matches GitHub exactly, with the double hyphen |
| A document's own title anchor disappeared when the page supplied the `<h1>` | `check.py --links` | an empty anchor alias is emitted |
| Every page had zero or one `h1` by accident | `[S1]` | `page()` emits the heading unless the body has one; `check.py` fails on zero or two |
| `CL-6` read 82% instead of 95% | reading its own output | the repeatability claim names its three batches; a Copilot batch cannot be mistaken for a repeat |
| `CL-7` rendered `671%` | reading its own output | claims have a `kind`; a token count is never formatted as a percentage |

The last two are the ones worth remembering: both were *arithmetically correct and semantically wrong*, and
both were caught by looking at the rendered page rather than by a test. Both now have a test.

---

## The numbers this work produced

| Measure | Value |
|---|---|
| Routes built | 23 (7 first-party, 15 reference, 1 404) |
| Automated checks | 178, 0 failing |
| Screenshots captured and inspected | 43, in `e2e/` |
| Site size (HTML + CSS + JS, all routes) | under 400 KB per page; the whole text of the site is ~600 KB |
| Third-party runtime dependencies | 0 (Mermaid is vendored, fonts are system) |
| Third-party build dependencies | 1 (Pygments, for syntax colouring; optional) |
| Lines of site code | 2,418 Python, 813 CSS, 213 JavaScript, 604 Node (the screenshot harness), 4,940 including the tests and the wireframe generator |

## What is still open

| Item | Why it is open | Next step |
|---|---|---|
| No hosted demo | The app needs a token for the reader's own workspace | Needs a scoped demo token and a cost model for strangers spending inference; a product decision, not a page decision |
| The tutorial's step images are renderings, not UI photos | Single sign-on blocked automated capture; `docs/tutorial.md` says so, and the tutorial page repeats it | Capture them by hand in a browser, once |
| 43 screenshots are not in CI | `site/shots.mjs` needs Playwright, which is the app's dependency | A CI job that installs it and runs `--all`, uploading the diff as an artifact |
| No Firefox or Safari pass | Chromium only | One night of manual checks, recorded here |
| The tour's screenshots carry no commit stamp | They are the app's, captured on other days | Add the app's commit to each caption |
| `PG-4`'s fifteen reference pages have no header entry of their own | Deliberate; see above | A second-level nav in the rail, if the reference section grows |

## What would change our mind

From [01](01-five-whys.md#what-would-falsify-this), revisited with what the work taught:

- **If readers never leave the home page**, the seven-route structure is over-engineering and one long
  page would serve better. Nothing in this work tests that; it needs real traffic, which this repository
  does not have.
- **If the measured numbers are too small to persuade**, the honest response is to lead with the method
  and the screenshots and relegate the scores. The current order does the opposite, and that is the
  weakest judgement on the page.
- **If a hosted demo becomes possible**, `[P4]` inverts: a demo is the strongest page a project like this
  can have, and everything else becomes support for it.
- **If Apache-2.0 is wrong for an app customers deploy inside their own workspace**, the licence needs a
  second pass with counsel. Not resolved here.

## Reproducing this outcome

```bash
bash site/verify.sh              # build, 14 claim tests, 9 check passes, 10 scenes, 178 checks
bash site/verify.sh S7           # one scene
python3 specs/008-github-page/tools/draw_wireframes.py --check
cd apps/coding-agent/web && node scripts/verify-spec-ascii.mjs ../../../specs/008-github-page
```

The last two are the wireframes of [04](04-wireframes.md): generated on a grid, then parsed by the
repository's own ASCII checker, which reports `21 boxes, 0 problems`.
