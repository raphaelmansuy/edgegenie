# 09. Edge cases

[Index](README.md) · prev: [08 Implementation plan](08-implementation-plan.md) · next: [10 E2E plan](10-e2e-plan.md)

Every failure I could name, with its mitigation and the test that would catch a regression. Grouped by
where the failure lives, because that is what determines who fixes it.

A row without a test is marked **manual** and appears in the inspection loop ([10](10-e2e-plan.md)); it is
not left blank, because "we did not think of a test" and "we did not think of the case" are different
failures and only the first is acceptable.

---

## Build, the inputs are wrong

| id | Failure | Why it happens | Mitigation | Test |
|---|---|---|---|---|
| `E-1` | A screenshot a page references is missing | `specs/006/…/e2e` was reorganised | The copy step resolves every referenced path **before** writing HTML, and names the path it could not find | `check.py --images`; build raises |
| `E-2` | `exams/results/` is absent (a clone with `--depth` and a filter, or a partial checkout) | Git LFS, a sparse checkout, a tarball of `src/` only | `claims.py` detects the empty directory and the site **says so**: the evidence page states that results are not present in this checkout, rather than printing 0% | `test_claims.py::test_missing_results_is_stated_not_faked` |
| `E-3` | A results file is truncated JSON (an interrupted run writing to disk) | The harness writes with `open(...)` and a killed process leaves half a file | The loader skips a file it cannot parse, **counts it**, and the ledger prints "1 unreadable result" | `test_claims.py::test_unreadable_result_is_counted` |
| `E-4` | Every result is a rejected batch | Someone cleans up the accepted runs | Zero claims; the build **fails** with "no claim could be derived", rather than shipping a page with a hole | `test_claims.py::test_no_accepted_runs_fails` |
| `E-5` | A doc referenced by the reference page was renamed | Renames happen | `pages.py` names the file; a missing one is a build error naming the path | `check.py --links` |
| `E-6` | Two runs of the build differ | A timestamp, a dict iteration order, a set | The build stamp is passed in; all iteration is over sorted lists | `[S9]` runs the build twice and diffs |

## Build, the output is wrong

| id | Failure | Why it happens | Mitigation | Test |
|---|---|---|---|---|
| `E-7` | An absolute `/assets/site.css` works locally and 404s on Pages | Pages serves a project from a subpath | Every path is relative, computed from the route's depth (`prefix = "../" * depth`) | `check.py --links` resolves on disk; `[S1]` loads from a subpath server |
| `E-8` | A heading is renamed and a cross-reference dies | The most common documentation defect there is | `check.py` resolves every `file#anchor` against the target's actual heading slugs | `check.py --links` |
| `E-9` | An unescaped `<` in prose breaks the markup | Markdown allows raw HTML; a `<` in a code span is fine, outside one it is not | Every text node is escaped at render; raw HTML is not passed through | `check.py --markup` parses with a real parser |
| `E-10` | JSON-LD is valid JSON but invalid schema, and a crawler ignores it | Nothing local complains | One `jsonld()` builder per type, tested against keys a crawler reads | `check.py --meta` |
| `E-11` | Mermaid fails to parse in the browser and renders a red error box | The parser is stricter than the author | The block's fallback is its own source, in a `<pre>`; the page is readable without it | `[S8]` with JS off |
| `E-12` | Two pages have the same `<title>` | Copy-paste of a route table row | `check.py` fails on a duplicate title or description | `check.py --meta` |
| `E-13` | A claim's number is edited in prose | Someone "fixes" 94% to 95% | Prose may only contain `{{CL-n}}`, never a digit-percent | `check.py --claims` |

## Claims

| id | Failure | Why it happens | Mitigation | Test |
|---|---|---|---|---|
| `E-14` | A denominator differs from the docs' | A failed run's own total is smaller | The exact `full_totals` rule, copied, and a test asserting the site's totals equal `make_tables.py`'s | `test_claims.py::test_matches_make_tables` |
| `E-15` | A rejected batch is counted | A new `_`-prefixed directory, or a renamed one | The same `SKIP` set; a test enumerates the excluded directories | `test_claims.py::test_rejected_batches_excluded` |
| `E-16` | A percentage is computed from the wrong pair of runs | Copy-paste between claim definitions | Each claim names its batches, and a test asserts the batch exists and its variant/model match | `test_claims.py` |
| `E-17` | A caveat is softened in an edit | The most likely drift of all, and the one that matters most | The caveat lives in `claims.py`, next to the number, not in the prose file | `[S3]` asserts every card has a non-empty caveat |
| `E-18` | A claim is silently dropped when its source disappears | A rename in `exams/results` | A missing source **fails the build**; `[CPT-4]` | `test_claims.py::test_missing_source_fails` |

## Layout and interaction

| id | Failure | Why it happens | Mitigation | Test |
|---|---|---|---|---|
| `E-19` | Horizontal scroll at 320 px | One long code line or one unbreakable URL | `overflow-wrap: anywhere` on prose and code; every table scrolls in its own wrapper | `[S7]` measures `scrollWidth > clientWidth` |
| `E-20` | The contents rail covers content at 1100 px | A fixed width that assumes 1440 | The rail appears only above 1100 px, and the column is `min(22ch, 200px)` | `[S7]` at 1100 |
| `E-21` | The theme flashes white on load | CSS applied before the attribute is set | The inline script runs in `<head>`, before the stylesheet | `[S7]` reads `data-theme` at first paint |
| `E-22` | The menu traps focus after closing | Focus restored to a hidden element | Focus returns to the button, which is always visible; `Escape` is the tested path | `[S7]` |
| `E-23` | A wide screenshot overflows its column | An `<img>` without `max-width` | `img { max-width: 100%; height: auto }` and declared dimensions | `[S7]` |
| `E-24` | A screenshot is unreadable when scaled to 720 px | A 2880 px capture in a narrow column | The caption says the capture width; a phone reader can open the file directly | manual, `[S3]` |
| `E-25` | Print output is black-on-black | Dark theme background, no print rule | A `@media print` block forces light tokens and hides the header | manual, `[S10]` |
| `E-26` | Zoom to 200% clips a heading | `white-space: nowrap` somewhere | No `nowrap` outside the nav pill; tested at 200% | `[S7]` |

## Content and truth

| id | Failure | Why it happens | Mitigation | Test |
|---|---|---|---|---|
| `E-27` | The page claims a cost saving | A well-meaning edit | `check.py` rejects a currency symbol or "cheaper" in prose | `check.py --claims` |
| `E-28` | The tour presents a rendered image as a UI photo | `docs/tutorial.md` uses rendered output images because SSO blocked capture | The tutorial page carries the same note the doc does; the tour uses only real screenshots | `[S6]`, manual |
| `E-29` | A screenshot is stale after a UI change | The app changed, the site did not | The tour's caption carries the app commit; `[S1]` records it | manual, [11](11-outcome.md) |
| `E-30` | The author section overstates a credential | Enthusiasm | Every claim in it is one of: a public URL, the book's publisher page, or a fact visible in the repository | manual, `[S4]` |
| `E-31` | A reader cannot tell what "we" means | One author, one study | `/about/` says it is one person's work; the home page says "we" only about measurements | manual, `[S4]` |

## Deployment and operations

| id | Failure | Why it happens | Mitigation | Test |
|---|---|---|---|---|
| `E-32` | Pages serves the repository root instead of the build | The source is set to "deploy from a branch" | The workflow uses `upload-pages-artifact` + `deploy-pages`; the README documents the setting | manual, one-time |
| `E-33` | A deploy publishes a broken page | The check runs after the upload | `check.py` runs **before** the artifact upload | workflow order |
| `E-34` | The site silently stops updating | A workflow permission change | The workflow fails loudly on a missing token scope; the footer's commit stamp makes a stale deploy visible | `[S10]` |
| `E-35` | A 404 shows GitHub's default page | Pages serves `404.html` from the root only | `404.html` is emitted at the root of the artifact | `[S10]` |
| `E-36` | Someone forks and the site breaks | A hard-coded `raphaelmansuy` in a path | Every repo URL is one constant; a fork changes one line | manual |

## Security and privacy

| id | Failure | Why it happens | Mitigation | Test |
|---|---|---|---|---|
| `E-37` | A screenshot shows a token or a workspace URL | A real capture from a real session | Every screenshot in `e2e/` was captured against the app with a placeholder identity; the tour note says workspace addresses are replaced | manual, at capture |
| `E-38` | The site leaks an internal hostname | A doc rendered verbatim contains one | `check.py` scans the rendered HTML for `databricks.com/` hosts and for `dapi` token prefixes | `check.py --secrets` |
| `E-39` | A third-party script is added later | Convenience | No `<script src>` may point outside the site's own `assets/` | `check.py --files` |
| `E-40` | A screenshot of the app includes another user's email | Multi-user workspace | Only the author's own workspace was captured, and the identity shown is the author's | manual |

---

## The four that would actually happen

Ranked by likelihood, from the defects this repository has already had:

1. **`E-8`, a renamed heading** — three of the existing specs have had a dead anchor. The checker exists
   because the repository's own `verify-spec-links.mjs` was written to catch it.
2. **`E-19`, horizontal scroll on a phone** — the app's `overflow-audit.mjs` exists for exactly this, and
   it found real defects. A long code line in a rendered doc is the most likely source.
3. **`E-29`, a stale screenshot** — 286 screenshots already exist and several are from different days.
   Without a commit stamp, nobody notices.
4. **`E-13`, a hand-edited number** — the repository's `inject_tables.py` exists because this happened.

Each of those four has an automated guard. That is not a coincidence: the guards were written in the order
the defects were found.
