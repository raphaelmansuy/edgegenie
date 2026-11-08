# 008. The OpenGenie public site

**A specification and implementation plan for `https://raphaelmansuy.github.io/opengenie/`: the page that
explains why Genie Code's fixed model and metered bill are a problem, what OpenGenie does instead, and how
to run it — with the evidence on the same page, not in a PDF.**

> **Status:** specification, implementation plan, and the implementation (this folder is the record).
> 8 November 2026.
> **Scope:** a new static site (`site/`), a rewritten root `README.md`, an Apache-2.0 `LICENSE`, the Pages
> workflow (`.github/workflows/site.yml`), and the screenshots under `e2e/`. It touches **no** application
> code in `apps/`, `api/`, `mcp/` or `exams/`; those are cited, never restated.
> **Relation to earlier specs:** renders the results of [001 · Databricks coding agents](../001-databricks-coding-agents/README.md),
> [005 · Every model, one picker](../005-llm-models/README.md), [006 · On par with Genie Code](../006-databricks/README.md)
> and [007 · The shell, the keys, and the scroll](../007-ux-ui-improve/README.md). It **replaces** none of them and
> **copies** none of them: the site renders those files at build time.
> **Audience:** product, full-stack, database, UX/UI, front-end, growth.

---

## The one sentence

> A reader who has never heard of this repository should be able to answer four questions in ninety seconds —
> *what is wrong with the default, what does this do instead, does it work, how do I run it* — and every
> number they read should be one a script can regenerate from this repository.

Everything in this folder is an argument about that sentence.

---

## What this folder is

Written to be read in this order, but complete when read in any order:

| # | Document | Answers |
|---|---|---|
| 01 | [Five whys and first principles](01-five-whys.md) | Why does a public page exist at all, and what is irreducible about it? |
| 02 | [Grounded assessment](02-grounding.md) | What is actually in this repository, counted, with the command that counts it |
| 03 | [Requirements](03-requirements.md) | What must be true when it is done (`PG-*`, `NAV-*`, `CPT-*`, `AX-*`, `PF-*`, `SEO-*`) |
| 04 | [Wireframes (ASCII)](04-wireframes.md) | What every page and every navigation state looks like, to the column |
| 05 | [Diagrams (Mermaid)](05-diagrams.md) | Build sequence, content model, state machines, the claims pipeline |
| 06 | [Six lenses](06-lenses.md) | The same site seen by six owners, and what each one vetoes |
| 07 | [Architecture](07-architecture.md) | Where each rule lives in the code, and why there |
| 08 | [Implementation plan](08-implementation-plan.md) | Phases, files, tests, order, acceptance criteria |
| 09 | [Edge cases](09-edge-cases.md) | Every failure I could name, its mitigation, its test |
| 10 | [E2E plan](10-e2e-plan.md) | The scenes, the screenshots, the pass criteria, the inspection loop |
| 11 | [Outcome](11-outcome.md) | What shipped, what the screenshots changed, what is still open |
| 12 | [Claims ledger](12-claims-ledger.md) | Every number on the site, its source, and how it is re-derived |

Cross-reference convention: a requirement is cited as `[PG-3]`, a decision as `[D4]`, an edge case as
`[E-11]`, an e2e scene as `[S3]`, a first principle as `[P2]`. Every id is defined exactly once — in `03`,
`09`, `01` or `08` — and linked from everywhere else. A document that cites an undefined id is a bug in
this set, and `site/check.py` fails the build on a link that does not resolve.

---

## The problem this page has to solve

The repository already contains the answer, spread over 27 markdown files, 174 result JSON files, and
~27,500 lines of code. That is the right shape for an engineer who has already decided to care, and the
wrong shape for everyone else.

| Reader | Arrives wanting | Today they must |
|---|---|---|
| A Databricks data engineer | "Can I stop paying per-seat for autocomplete?" | read `docs/07-decision-guide.md`, then four other documents |
| A platform lead | "Is the claim backed by anything?" | find `exams/results/`, trust a table with no method |
| A developer evaluating the app | "What does it look like?" | open a local checkout and run it |
| A recruiter / peer | "Who built this?" | guess from a git log |

The page exists to collapse those four journeys into one scroll plus one link per journey. It does **not**
replace the docs; it is a map of them.

---

## What ships

```
site/                        the static site generator and its inputs
  build.py                   render every route; the only file that writes HTML
  content/*.md               the prose of the seven first-party pages
  claims.py                  derive every published number from the repository
  check.py                   fail the build on a broken link, anchor, image or claim
  shots.py                   capture and inspect the site (Playwright)
  static/                    site.css, site.js, icons, author and project images
  dist/                      the build output (git-ignored; CI rebuilds it)
README.md                    rewritten: the page in text, in one screen
LICENSE                      Apache-2.0
.github/workflows/site.yml   build → check → deploy to Pages on every push to main
specs/008-github-page/
  01..12                     this set
  e2e/                       every screenshot, one folder per scene, plus the audit JSON
```

## What is reused, not copied [D1]

| Source in the repository | What the site does with it |
|---|---|
| `docs/tutorial.md` and `docs/e2e/screenshots/tutorial/*.png` | rendered as `/tutorial/`, images copied at build time |
| `specs/006-databricks/e2e/**/*.png` | the product tour, copied by a manifest, never duplicated in git |
| `exams/results/*/*.json` | every score on `/evidence/`, aggregated by `site/claims.py` |
| `docs/01-big-picture.md`, `docs/04-safety-and-governance.md`, `specs/*/README.md` | the `/reference/` section, rendered verbatim |
| `apps/coding-agent/web/src/styles.css` | the design tokens the site's palette is derived from |

A number that appears on the site and in `docs/` is computed by one function. A paragraph appears in one
file and is rendered in two places. That is the DRY rule of this work, stated once, in
[07 §DRY](07-architecture.md#d4-one-source-per-fact-the-claims-registry), and tested by `[S6]`.
