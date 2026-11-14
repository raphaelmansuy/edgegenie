# 015 — Notebook Markdown as a readable document

Status: **implemented and locally verified**. See [implementation evidence](13-implementation-evidence.md)
for shipped behavior, executed tests, screenshots and verification limits.
Assessment baseline: commit `548666c`, 14 November 2026. Evidence is local source inspection,
the two user-supplied Databricks screenshots, and the official references in [02](02-code-grounding.md).

**Primary user rule:** when a Markdown cell is not being edited, interpret its Markdown and
display styled content. Raw source is an explicit editing surface, not the normal resting view.

Start with [the five whys and first principles](01-five-whys.md). Then use this reading order:

| Document | Decision it supports |
|---|---|
| [01 — Five whys](01-five-whys.md) | Why this work exists; invariants before solution choices |
| [02 — Code grounding](02-code-grounding.md) | Observations, source locations, screenshots, external evidence |
| [03 — Product requirements](03-requirements.md) | Scope, dialect, priorities, measurable acceptance |
| [04 — UX and ASCII wireframes](04-ux-wireframes.md) | Reading, editing, navigation, narrow layout, keyboard operation |
| [05 — Architecture and data model](05-architecture.md) | DRY/SOLID seams, logical ER, read/edit/save sequences |
| [06 — Statecharts](06-statecharts.md) | Display, edit, save, media, and async transition rules |
| [07 — Rendering and trust](07-rendering-security.md) | Grammar, URLs, images, math, untrusted agent content |
| [08 — Expert lenses and complexity](08-lenses-performance.md) | Seven requested perspectives and complexity budgets |
| [09 — Edge-case register](09-edge-cases.md) | Named failures, mitigations, and mandatory test coverage |
| [10 — Implementation plan](10-implementation-plan.md) | Ordered changes, file targets, dependencies, exit gates |
| [11 — Tests and traceability](11-tests-traceability.md) | Requirement-to-test and risk-to-test coverage; E2E scenarios |
| [12 — Decisions and rollout](12-decisions-rollout.md) | Decisions, deliberate compatibility limits, release/rollback |
| [13 — Implementation evidence](13-implementation-evidence.md) | Actual changes, test results, measurements and limits |
| [Validation record](VALIDATION.md) | Checks performed on this specification, distinct from future product tests |

## Assessment

OpenGenie already renders nonempty Markdown cells in its notebook editor. The improvement is
to make that rendering a coherent document surface: real heading hierarchy, a defined Markdown
dialect, explicit Edit/Preview controls, safe navigation/media, and consistent behavior in the
read-only viewer. The current renderer shares compact answer styling and parses a limited subset
([grounding](02-code-grounding.md#c1)). This is a presentation and interaction redesign with
targeted correctness work, not a replacement notebook storage format.

P0 delivers styled reading by default, explicit editing and formatting, reliable preview transitions,
safe rich syntax, and save/keyboard/performance regression gates. P1 adds authenticated workspace
images and a heading outline; those must not delay the primary reading-mode rule. Phase boundaries
and exceptions are normative in [03](03-requirements.md#scope-and-priority).

## How the documents connect

Requirement IDs `MD-01`–`MD-18` are defined once in [03](03-requirements.md#requirements).
Risks `E01`–`E48` are defined once in [09](09-edge-cases.md#register).
Test groups `T01`–`T20` are defined once in [11](11-tests-traceability.md#test-groups).
Implementation phases `P0`–`P6` are defined in [10](10-implementation-plan.md#phases).
Priorities **P0/P1** in the product document are release priorities; phase IDs use the word
**phase** to avoid confusing the two.

Every risk has a mitigation and a test group. This is a bounded coverage model, not a claim that
every future input has been enumerated. Generated/fuzz tests, runtime fallbacks, and rollout gates
cover unknown combinations; failures extend the register before release.

## Diagram convention

ASCII wireframes use printable ASCII and fixed-width boxes. Mermaid diagrams use pastel blue,
mint, lavender, amber, and rose with dark text. Color supplements state labels; it never carries
meaning alone. Mermaid in these documents does **not** imply Mermaid execution inside notebook cells.

Related foundations: [notebook spec 010](../010-notebook/README.md),
[editor specification](../003-improve-dev-ux-ui/README.md),
[UI specification](../007-ux-ui-improve/README.md).

