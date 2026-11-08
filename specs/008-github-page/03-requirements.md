# 03. Requirements

[Index](README.md) · prev: [02 Grounding](02-grounding.md) · next: [04 Wireframes](04-wireframes.md)

Every requirement has an id, a way to check it, and a test that fails today if it is not met. Ids are
defined here **once**; every other document in this set and the build scripts cite them.

Six groups:

| Prefix | Group | Count |
|---|---|---|
| `PG-` | Page and content | 18 |
| `NAV-` | Navigation and routing | 8 |
| `CPT-` | Claims, numbers and provenance | 8 |
| `AX-` | Accessibility | 9 |
| `PF-` | Performance and robustness | 7 |
| `SEO-` | Discoverability and metadata | 6 |

---

## PG. Page and content

| id | Requirement | Verified by |
|---|---|---|
| `PG-1` | The site names the product **OpenGenie** on every page, and states once, in the first screen, that it is the application built out of the Genie-Code-replacement study. | `[S1]` assertion; `[S2]` |
| `PG-2` | The first screen after the hero states the three differentiators — *choose the model*, *the write fence*, *proof, not promises* — each linking to the page or file that implements it. | `[S2]` |
| `PG-3` | A screenshot of the running application appears within the first two viewport-heights on the home page, with a caption naming the screen and the width. | `[S1]` measures `img.src` above the fold |
| `PG-4` | Seven first-party pages exist: `/`, `/tour/`, `/tutorial/`, `/evidence/`, `/install/`, `/reference/`, `/about/`. Each is reachable from the header on every other page. | `[S5]` crawls every route, both ways |
| `PG-5` | Every page ends with a single next action, and no page has more than one primary (filled) button above the fold. | `[S1]` counts `.btn-primary` |
| `PG-6` | Every call to action resolves to a page that exists **in the build** or a URL under the repository's own paths. No control is decorative. | `site/check.py` link pass |
| `PG-7` | The tutorial is the repository's tutorial, rendered from `docs/tutorial.md` — not retyped. Section anchors match the source headings. | `[S6]` compares the rendered anchor set with the source's |
| `PG-8` | The reference section renders `docs/*.md` and the five specification READMEs verbatim, with a link back to the source file on GitHub. | `[S6]` |
| `PG-9` | Every number on the site is produced by `site/claims.py` from `exams/results/*.json`, and the build fails if prose contains a percentage that is not a computed claim. | `site/check.py --claims` |
| `PG-10` | Every page states its own freshness: the build date and the commit it was built from. | `[S8]` |
| `PG-11` | The build is reproducible: two runs over the same source produce byte-identical HTML except for the commit stamp. | `[S9]` |
| `PG-12` | `LICENSE` exists at the repository root (Apache-2.0), is linked from the README's first screen and from every page's footer. | `site/check.py --files`; `[S1]` |
| `PG-13` | An `/about/` page carries the author section: portrait, role, a paragraph on why the project exists, LinkedIn, GitHub, the repository, the book, and the other projects. | `[S4]` |
| `PG-14` | The tour is labelled a tour and each screenshot carries the width and theme it was captured at, so a reader knows what they are looking at. | `[S3]` reads every caption |
| `PG-15` | No page claims a cost saving in money. The cost section states what was and was not measured. | `site/check.py --claims` scans for currency and "cheaper" |
| `PG-16` | The site states, in the safety section and the tour, what the fence does **not** cover (a token with write rights is a token with write rights). | `[S3]` |
| `PG-17` | The tutorial page says its step images are renderings of real notebook output, not photographs of the web UI, exactly as `docs/tutorial.md` does. | `[S6]` |
| `PG-18` | 404 is a real page in the site's own design, with the seven routes, not the GitHub default. | `[S10]` |

---

## NAV. Navigation and routing

| id | Requirement | Verified by |
|---|---|---|
| `NAV-1` | Every link is **relative**, so the same build works at a project subpath, a user root, and `file://`. | `site/check.py` resolves every `href` on disk |
| `NAV-2` | The current page is marked `aria-current="page"` in the header, and nowhere else. | `[S1]` |
| `NAV-3` | The header carries a theme control with three states (system / light / dark) that persists and never flashes the wrong theme on load. | `[S7]` measures paint after reload |
| `NAV-4` | Below 860 px the navigation collapses to one button that is keyboard operable, reports `aria-expanded`, and closes on `Escape`. | `[S7]` |
| `NAV-5` | Every page has a "skip to content" link as its first tab stop. | `[S5]` |
| `NAV-6` | Long pages carry an "On this page" table of contents, hidden below 1100 px (where it would cost content width). | `[S5]`, `[S7]` |
| `NAV-7` | Previous/next links at the foot follow the reading order in [04 §route order](04-wireframes.md#route-order), and the first page has no previous. | `[S5]` |
| `NAV-8` | Anchors survive re-rendering: every heading gets a GitHub-compatible slug, and a deep link to any heading opens at that heading. | `[S6]` |

---

## CPT. Claims, numbers and provenance

| id | Requirement | Verified by |
|---|---|---|
| `CPT-1` | The ledger ([12](12-claims-ledger.md)) is the only place a number is *defined*; the site renders ledger entries, it does not restate them in prose. | `[S9]` |
| `CPT-2` | Each claim card shows: value, denominator (`143/152`), run count, model, and one sentence of caveat. | `[S3]` |
| `CPT-3` | Every claim links to the run files it came from, and those paths exist in the repository. | `site/check.py` |
| `CPT-4` | A claim whose source file is missing fails the build rather than being dropped silently. | `[S9]` |
| `CPT-5` | Percentages are rounded once, at render, from exact fractions; `143/152` reads 94%, and the denominator is always printed. | `[S9]` |
| `CPT-6` | The tokens-per-task figures are labelled "tokens", never converted to money. | `site/check.py --claims` |
| `CPT-7` | Rejected and superseded runs (`_`-prefixed batches) are counted nowhere except the ledger's own footnotes. | `[S9]` |
| `CPT-8` | The page states the sample size of every claim set (8 development tasks, 3 held-out) next to the score, not in a footnote. | `[S3]` |

---

## AX. Accessibility

Target: **WCAG 2.2 AA**, computed from painted colours, the same method as `web/scripts/a11y-audit.mjs`.

| id | Requirement | Verified by |
|---|---|---|
| `AX-1` | Body text ≥ 4.5:1, large text and UI boundaries ≥ 3:1, in light and dark, on every route. | `[S7]` computes contrast from painted pixels |
| `AX-2` | One `h1` per page; heading levels never skip. | `site/check.py`; `[S5]` |
| `AX-3` | Every image has an `alt` that describes what it shows, not what it is (`alt="three-pane editor at 1440 px"`). Decorative images have `alt=""`. | `site/check.py` rejects `alt="screenshot"` |
| `AX-4` | Every interactive control has an accessible name; every link's text is meaningful out of context. | `[S7]` |
| `AX-5` | Focus is always visible, and the focus ring clears 3:1 against both the element and its background. | `[S7]` |
| `AX-6` | Targets are ≥ 24×24 CSS px; primary actions ≥ 44×44. | `[S7]` |
| `AX-7` | The page survives 200% zoom and 320 px width with no horizontal scroll and no clipped text. | `[S7]` |
| `AX-8` | `prefers-reduced-motion: reduce` removes every transition and every scroll animation. | `[S7]` |
| `AX-9` | The page is usable with images disabled and JavaScript disabled: content, order and links intact. | `[S8]` runs with JS off; `site/check.py` counts images |

---

## PF. Performance and robustness

| id | Requirement | Verified by |
|---|---|---|
| `PF-1` | Each page's transfer (HTML + CSS + JS + above-fold images) is under 400 KB; the whole site under 6 MB excluding screenshots. | `[S9]` sums file sizes |
| `PF-2` | No layout shift on load: every image declares `width` and `height`, every font is either local or `font-display: swap`. | `[S7]` measures CLS |
| `PF-3` | Mermaid is loaded only on pages that contain a diagram, and a diagram that fails to render falls back to its readable source. | `[S8]` |
| `PF-4` | The site has no build-time network dependency: `mermaid.min.js` and all fonts' fallbacks are vendored or system. | `[S9]` builds with networking disabled |
| `PF-5` | Every page is valid, balanced HTML: `site/check.py` parses with a real parser and fails on an unclosed tag. | `[S9]` |
| `PF-6` | Screenshots are served at their capture resolution, `loading="lazy"` below the fold, `decoding="async"`, and each is under 500 KB. | `[S9]` |
| `PF-7` | A missing screenshot or a missing doc fails the build with the path named; nothing is skipped quietly. | `[S9]` |

---

## SEO. Discoverability and metadata

| id | Requirement | Verified by |
|---|---|---|
| `SEO-1` | Every page has a unique `<title>` (≤ 60 chars), a `meta description` (≤ 160), and a canonical URL. | `site/check.py` |
| `SEO-2` | Open Graph and Twitter card tags on every page, with an image that exists and is 1200×630. | `site/check.py` |
| `SEO-3` | `sitemap.xml` lists every route; `robots.txt` points at it. | `site/check.py` |
| `SEO-4` | JSON-LD: `SoftwareApplication` on `/`, `Person` on `/about/`, `BreadcrumbList` on every page. | `site/check.py` parses the JSON |
| `SEO-5` | Structured data names the licence (`Apache-2.0`) and the code repository. | `site/check.py` |
| `SEO-6` | Semantic landmarks: `header`, `nav`, `main`, `footer`, each once, each labelled where there is more than one. | `[S5]` |

---

## What is deliberately *not* required

Stated so a reviewer does not read absence as oversight.

| Not required | Why | Reference |
|---|---|---|
| A hosted live demo | The app needs a workspace token; a fake one would be a lie | [P4](01-five-whys.md#p4-a-control-that-cannot-act-must-not-be-shown) |
| A money figure | Never measured | [P6](01-five-whys.md#p6-cost-is-the-readers-question-so-it-gets-an-honest-answer-not-a-number) |
| A JavaScript framework | Seven static pages do not need one; a framework would add 40 KB and a supply chain | [D3](07-architecture.md) |
| Blog / changelog / versioned docs | Nothing to publish yet; would be empty furniture | [11](11-outcome.md) |
| Translation | One author, one language; a stale translation is worse than none | — |
| A cookie banner | No cookies, no analytics, no third-party script | [PF-4] |
