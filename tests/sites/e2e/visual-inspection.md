# Visual inspection ledger: the published site

Scope: every page in `site/dist` (the 26 routes in `sitemap.xml`, plus the 404), at 1440, 1024, 768 and 390 px,
light and dark, plus the mobile menu. The screenshots are written by
`tests/sites/e2e/site.e2e.mjs` to `tests/sites/e2e/screenshots/` and are not committed (CI keeps them as the
`site-e2e-screenshots` artifact).

## What is automated (every run, 162 page views, 0 failing)

- HTTP status, one `h1`, theme applied, every internal link resolves, no console or page errors.
- No sideways page scroll; no element outside the viewport except inside a deliberate scroller.
- No clipped text; every image loaded and has `alt`; no body text below 13 px; contrast at WCAG AA.
- No markup shown as text (`&mdash;`, `<strong>`, `{{token}}`); every Mermaid diagram rendered, labelled,
  and at a readable scale (or offered full size on a phone).
- Phone tap targets at least 24 px; the mobile menu opens and closes; the theme choice persists.

These assertions prove structure and legibility. They do not prove taste. The second half of this file
records what a person looked at.

## Visual review, by rounds

Each round, reviewers opened the screenshots one by one and graded each file pass / minor / major.

**Round 1 (all pages).** Major defects found and fixed:
bar charts drawn empty; HTML entities and tags printed as text; wrong or misleading screenshots (the model
picker showed a folder chooser; a dark figure showed an error); Mermaid diagrams drawing into each other and
one staying empty; a 404 page without its stylesheet; tables and code clipped on phones with no hint; a
tutorial callout printing a fenced block as backticks; a grouped bar chart whose series overlapped.

**Round 2.** Re-reviewed. Fixed: captions and provenance chips, footer alignment, header controls on the
right, the mobile menu scrim and close icon, two-column card grids at tablet widths, inline "On this page"
contents below 1100 px, short inline commands that split at hyphens, the reference index's rows and links.

**Round 3 (home, tour, evidence, install, about, 404, tutorial, safety).** No major defects reported.
Minor items reported, and their status now:

| Page | Item | Status |
|---|---|---|
| home | stray `·` at the start of a line in tool-card footers | fixed after review; not re-reviewed |
| home | divider lines in tool cards at different heights | fixed after review; not re-reviewed |
| tour | "Open full size" hint covered the screenshot on tablets | moved to a strip under the picture; not re-reviewed |
| tour | captions and figure scale | accepted |
| evidence | claim-card header alignment, CL-7 and CL-8 labels | changed after review; not re-reviewed |
| install | settings table cut off on phones | now a stacked list; not re-reviewed |
| install | false scroll shadow on code that does not overflow | now shown only when content overflows; not re-reviewed |
| about | lone third project card on tablets | now three columns; not re-reviewed |
| reference | two items numbered 010 | labels now carry the folder name; not re-reviewed |

**Round 3 for the reference documents (doc and spec pages).** Reviewed in round 1 only. The fixes made after
that round (diagram scaling and phone zoom, dark-theme diagram labels, the `xychart` overlap, the pipe-table
leak in spec 001, double-backtick code, stacked tables on phones with their column names, rail labels without
markup) are verified by the e2e assertions but have not been looked at by a person in a further round.

## What this means

The loop did not reach "no defects on any screen". Every major defect found in any round is fixed and every
page passes the automated gate. Several minor items above were changed after the last review and are unverified
by eye. The next round should re-review the reference documents and the items marked "not re-reviewed".
