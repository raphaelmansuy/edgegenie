# 06. Six lenses

[Index](README.md) · prev: [05 Diagrams](05-diagrams.md) · next: [07 Architecture](07-architecture.md)

The same site, seen by the six people who will judge it. Each lens states what it optimises for, what it
**vetoes**, and what actually changed because of the veto. A lens that changed nothing is a lens that was
not applied, so every row below names a decision or a requirement.

The pattern is the one [006 §lenses](../006-databricks/08-lenses.md) and
[007 §lenses](../007-ux-ui-improve/06-lenses.md) used, and for the same reason: a single voice optimises
for one thing and calls it quality.

---

## 1. Product Owner

**Optimises for:** a reader deciding in ninety seconds whether this matters to them, and a second reader
deciding whether to trust it.

**Vetoes:**

| Veto | Why | Changed |
|---|---|---|
| A hero that says "AI for Databricks" | True of forty products; it says nothing | The hero names the *problem*: one model, opaque bill (`[PG-1]`) |
| Burying the model choice as "finding #2" | It is the only differentiator a reader cannot get elsewhere | Promoted to claim 1, with the file that implements it (`[PG-2]`) |
| A "Get started free" button | There is no free tier and no hosted app; the button would lie on the first click | Two honest actions: *Read the tour*, *Install it* (`[PG-5]`, `[P4]`) |
| A testimonials or logos strip | There is nothing to put in it. Inventing one ends the page's credibility | Omitted; `/evidence/` is the social proof (`[PG-4]`) |
| "10× cheaper" | Never measured, and the repository says so explicitly | The cost section publishes the shape and the gap (`[PG-15]`, `[P6]`) |
| A roadmap | Nothing is committed beyond what shipped | Omitted; open items are in [11](11-outcome.md) as defects, not promises |

**What it added:** the *What this is not* block ([Screen 3](04-wireframes.md#screen-3-home-continued-what-it-is-not-and-the-footer)).
It costs a third of the home page and buys the only thing a page like this can own: being believed.

---

## 2. Full-Stack Developer

**Optimises for:** a build a stranger can run in one command, on a machine with no `node_modules`, and a
deploy that cannot publish a broken page.

**Vetoes:**

| Veto | Why | Changed |
|---|---|---|
| A JavaScript framework | Seven pages of mostly text. Next or Astro would add a toolchain, a lockfile and a supply chain for a `for` loop | Python 3 + Pygments only (`[D3](07-architecture.md#d3-python-and-no-framework)`) |
| A CDN for Mermaid | A build that needs the network fails on a plane, and a third-party script is a third-party risk | Vendored `mermaid.min.js`, loaded only on pages with a diagram (`[PF-4]`, `[PF-3]`) |
| Hand-written HTML per page | Seven copies of a `<head>` is seven chances to forget a canonical tag | One `page()`, one `<head>` (`[SEO-1]`, `[D5](07-architecture.md#d5-one-page-function)`) |
| Deploying from a local script | A deploy that only works on the author's laptop is not a deploy | GitHub Actions: build, check, deploy (`[PG-11]`) |
| `check.py` importing `build.py` | A verifier that shares code with the thing it verifies inherits its blind spots | `check.py` reads only `site/dist` (`[D2](07-architecture.md#d2-dependencies-point-one-way)`) |

**What it added:** the claim-provenance mechanism. A prose `94%` that is not a computed claim fails the
build (`[PG-9]`, `[CPT-1]`), which is the only way a page like this stays true after the third edit.

---

## 3. Database Expert

**Optimises for:** one definition per fact, and no second copy that can disagree.

**Vetoes:**

| Veto | Why | Changed |
|---|---|---|
| Copying `docs/06`'s tables into the site | The repository already generates them with `inject_tables.py`. A third copy is a third thing to drift | The site renders `docs/*.md` and computes its own from the same JSON (`[D1](07-architecture.md#d1-the-docs-are-the-source-of-truth)`) |
| Recomputing a score in a template | Rounding in two places produces 94% and 94.1% for the same fact on one page | One `claims.py`, rounded once, at render (`[CPT-5]`) |
| Counting `_`-prefixed batches | Those are the rejected runs: the Copilot adapter failure, the port collision, the pre-fix V1 | The same `SKIP` rule as `exams/make_tables.py` (`[CPT-7]`) |
| A denominator of "the run's own total" | A failed run's grader returns early, so its total is smaller; `143/152` and `60/63` are not comparable | Denominator = the perfect run's total, per mission (`[CPT-2]`) |
| An aggregate without a sample size | 100% of 3 tasks is not 100% of 8 | Every card prints its task set (`[CPT-8]`) |

**What it added:** the *grain* statement, borrowed from `AGENTS.md` ("state the grain before
aggregating"): each claim card says what one row is before it says what the mean is.

---

## 4. UX Designer

**Optimises for:** a reader who is skimming, on a phone, with one thumb, deciding whether to keep reading.

**Vetoes:**

| Veto | Why | Changed |
|---|---|---|
| Three levels of navigation | Seven pages and a contents rail is already generous | One header, one rail, previous/next (`[NAV-6]`, `[NAV-7]`) |
| Scroll-jacking and parallax | It reads as a demo of the site, not of the product | No scroll effects; one transition, on theme change (`[AX-8]`) |
| A modal for screenshots | A reader comparing screens must be able to scroll between them | Images inline, lazy, captioned (`[PG-14]`) |
| Hover-only affordances | Half the readers are on a touch screen | Every action is a visible control (`[AX-4]`) |
| A 90-word intro | The claim must land in the first line | Two-line headline, then the claim (`[PG-2]`) |
| A contents rail on mobile | It would take 200 of 320 px | Rail only above 1100 px; menu sheet below 860 px (`[NAV-4]`) |

**What it added:** the *one primary button* rule (`[PG-5]`). Two equally weighted buttons is a page that
has not decided what it wants, and the reader pays for that indecision.

---

## 5. Front-End Designer

**Optimises for:** the page looking like the product it describes, at every width, in both themes, with
type that holds together.

**Vetoes:**

| Veto | Why | Changed |
|---|---|---|
| A separate colour palette | The site would look like a different product from the app | Tokens derived from `apps/coding-agent/web/src/styles.css` (`[D6](07-architecture.md#d6-the-palette-is-the-apps-palette)`) |
| Purple gradient hero | The 2024 default, indistinguishable from every other AI page | Warm paper, one accent, the app's own `--blue-600` (`[D6]`) |
| A web font for body text | Inter is ~100 KB over the wire, and the first paint waits for it | A system font stack for body text (`[PF-2]`) |
| Fixed-width screenshots | A 2880 px image in a 720 px column is unreadable and heavy | `width`/`height` declared, scaled to the column, lazy below the fold (`[PF-6]`) |
| Dark mode as an inversion | Inverting a warm paper palette gives grey soup | A restated dark palette, as the app does (`[AX-1]`) |
| A theme that flashes | The default `system` setting means most readers would see one wrong paint | An inline script sets `data-theme` before the CSS (`[NAV-3]`) |

**What it added:** contrast computed from painted pixels rather than declared colours — the same method
`apps/coding-agent/web/scripts/a11y-audit.mjs` uses, which is how the app found its own dark-mode
contrast bug.

---

## 6. Marketing and Growth Expert

**Optimises for:** being found, being linked to, and being forwarded. Not for converting a page that has
nothing to sell.

**Vetoes:**

| Veto | Why | Changed |
|---|---|---|
| Analytics and a cookie banner | The page's whole claim is that it does not need to be taken on faith; a tracker undercuts it | No analytics, no third-party script, no cookie (`[PF-4]`) |
| An email capture | There is no list, no product and nothing to send | Omitted |
| "Revolutionary", "seamless", "10×" | Every one is unfalsifiable, and a technical reader discounts the whole page on the first | Adjectival claims removed in review ([copy rules](08-implementation-plan.md#copy-rules)) |
| A generic OG image | A link preview is the most-seen image of the project | One 1200×630 card naming the product and the claim (`[SEO-2]`) |
| A page per keyword | Five near-duplicate pages dilute the one that matters | Seven pages, each answering a distinct question (`[PG-4]`) |
| Hiding the author | An anonymous technical claim is worth less than a signed one | `/about/` with a face, a book and a LinkedIn (`[PG-13]`) |

**What it added:** `sitemap.xml`, one canonical URL and JSON-LD (`SoftwareApplication` with the licence
and the repository, `Person` on `/about/`, breadcrumbs everywhere), so a search engine can answer "what
is this, who made it, what may I do with it" without a human reading the page (`[SEO-3]`, `[SEO-4]`,
`[SEO-5]`).

---

## Where the lenses disagreed

Recorded because a set of lenses that never conflicts was not really applied.

| Question | Product Owner | Growth | Resolution |
|---|---|---|---|
| Lead with the study's score, or with the product? | Product: the screenshot sells | Study: the score is the differentiator | Both, in that order: screenshot above the fold, one score immediately after ([Screens 1–2](04-wireframes.md)) |
| Does `/evidence/` deserve its own page? | Yes: it is the trust asset | No: it splits the traffic | Yes, and the home page's *What this is not* block links to it from the exact sentence that raises the doubt |
| Is the tutorial on the site or a link to GitHub? | On the site: leaving loses the reader | On the site: it is the most shareable page | On the site, rendered from the same file, so there is one copy (`PG-7`) |
| Dark mode by default? | Either | Dark converts better on social | Follow the OS and never flash (`NAV-3`): a growth preference does not get to overrule a preference the reader already expressed |

---

## What no lens could fix

Stated so the set does not read as complete.

- **There is no hosted demo.** Every lens wanted one. It needs a scoped demo token and a cost model for
  strangers spending tokens, which is a product decision outside this work (`[P4]`).
- **The numbers are small.** Eight development tasks and three held-out tasks will not persuade a reader
  who wants a benchmark. The only honest response is to print the sample size beside the score
  (`[CPT-8]`) and let the reader discount it.
- **The author is one person.** A team page would serve procurement better. There is no team.
