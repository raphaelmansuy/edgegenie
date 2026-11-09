# Validation and delivery record

The mission workspace is implemented. [Requirements](01-product.md), [code and lenses](02-code-and-lenses.md), [design](03-ux-ui.md), [architecture](04-architecture.md), [implementation plan](05-implementation-plan.md) and [risk matrix](06-edge-cases-tests.md) form the specification. [Browser evidence](e2e/README.md) and the [image-by-image ledger](e2e/visual-inspection.md) record validation.

## What shipped

- One mission overview for the active session, regardless of assistant placement. Running work leads with the reported plan; ended work leads with the outcome, outputs and evidence.
- Foreground selection ahead of queued instructions, a mission history picker, last-achieved/last-completed shortcuts and an explicit return to current work.
- A pure mission read model with separate execution, observation and proof states. Achievement requires completed execution and nonempty, fully verified evidence resolving to successful matching calls in that turn.
- Exact source inspection through the existing ToolCard, per-turn outputs, existing document navigation and a persistent Mission overview return control. Generated outputs refresh open documents without taking over the reader's view.
- Responsive light/dark presentation, keyboard tabs, full request disclosure, bounded phone headings and a 44px WebKit phone picker. Completed phone views avoid duplicate operational cards and use a compact centre composer.
- Existing RunStatus, approval and restore paths remain in use. Failed/blocked/archived status language is accurate; archived/offline/recovery sessions no longer expose usable retry or follow-up send actions.
- Shared proof validation in the overview and transcript prevents contradictory verdicts. A late metadata response no longer drops streamed plan, duration, blockers, audit passes or usage.

No new database, SQL, migration, endpoint, execution engine, web font or production dependency was added. Superseded SessionHome code/styles were removed. SRP boundaries, callback interfaces and reuse decisions are described in [02](02-code-and-lenses.md).

## Measured checks

| Check | Result | Evidence |
|---|---|---|
| Frontend tests | **599 passed in 56 files** | [Verification record](e2e/verification.json) |
| Production build | Passed: TypeScript + Vite | [Verification record](e2e/verification.json) |
| Mission browser acceptance | **11 passing acceptance groups**, 23 screenshots; Chromium and WebKit | [Final report](e2e/iteration-03.json) |
| Existing durable-session regression | **9 passing acceptance groups**, 13 screenshots | [Regression report](e2e/regression/report.json) |
| Runtime errors | None in either passing browser report | [Final](e2e/iteration-03.json), [regression](e2e/regression/report.json) |
| Geometry and text contrast | All 23 final mission captures passed their automated checks | [Per-screen audits](e2e/iteration-03.json) |
| Visual review | **42 retained screenshots individually opened and inspected**: 36 acceptance/regression images and 6 earlier images | [Inspection ledger](e2e/visual-inspection.md) |
| Mermaid | Four diagrams parsed with the real Mermaid parser | [Architecture](04-architecture.md) |
| ASCII | Three wireframes: row widths and every border column verified | [Wireframe validator](../../apps/coding-agent/web/scripts/verify-mission-wireframes.mjs) |
| Cross-references and diff | Internal links checked; `git diff --check` clean | [Verification record](e2e/verification.json) |

The production build retains a warning about JavaScript chunks above 500kB, also present before this change. The mission screen adds no library dependency.

## Iteration and visual findings

[Iteration 01](e2e/iteration-01.json) established desktop, dark, phone and long-content baselines. Inspection found excessive phone status/composer height, overly tall objectives and completed outcomes below the plan. These were improved with compact operational controls, a compact composer, bounded titles with complete request disclosure and outcome-first completed views.

[Iteration 02](e2e/iteration-02.json) is a deliberately retained failed contrast run: the inherited code-block copy hover turned text white on a light surface. Mission copy controls now use the existing quiet variant; the final offline capture includes readable copied feedback while hovered.

[Final iteration 03](e2e/iteration-03.json) adds source inspection, responsive/history/failure/archive states and WebKit. Visual inspection led to explicit failed/archived operational language, consistent proof verdicts across both surfaces, safe archived actions, honest ready-without-a-mission wording and a shared SVG picker indicator so WebKit honors the intended touch height. Evidence capture scrolls the complete source body into view. Every retained image has an observation and content hash in the [inspection manifest](e2e/visual-inspection.json).

## Requirement closure

| Requirements | Validation |
|---|---|
| M-01–03 | Actual submission/return, foreground queue precedence, stop, picker and last-achieved browser journeys; pinned-history component tests |
| M-04–06 | Unit proof-integrity matrix, real local normalized tool/evidence stream, source disclosure, per-turn artifact tests, invalid-source fixtures and shared transcript verdicts |
| M-07 | Keyboard arrows/Home/End, selected-turn Activity, complete request disclosure and mobile conversation open/close |
| M-08 | Offline/reconnect, permission departure/decision, restart/restore, queued stop, archived action absence; restore/stop rejection component tests |
| M-09 | Output navigation and return; unavailable-workspace error on the real local app; editor rendering through an explicitly labelled notebook fixture |
| M-10 | 320/375/390/760/1024/1440/1920px coverage across the two suites; light/dark, native WebKit SSE, text contrast and manual screenshot inspection |
| M-11–12 | Existing stream reuse, late-metadata regression tests, no fixture mutation/unexpected API calls, successful build and reproducible browser reports |

## Reproduce

Run in `apps/coding-agent/web` with the repository's existing dependencies and Python virtual environment:

```sh
npm test
npm run build
npm run verify:spec-011
npm run e2e:mission
E2E_OUTPUT="$PWD/../../../specs/011-ux-coding-mission/e2e/regression" npm run e2e:long-running
```

Both browser runners own disposable local servers and journals. The mission runner clears deployment/provider environment settings, uses deterministic fake ACP and disables real tool execution. It tests real HTTP, acceptance, subprocess protocol, persistence and SSE; browser fixtures are separately identified in the report. Screenshot re-generation requires a new visual review and updated inspection hashes. Mermaid parsing uses the existing `verify-spec-mermaid.mjs` with Mermaid available through its documented `MERMAID_PATH` option.

## Limits

Databricks identity and warehouse tools were unavailable, and no connected workspace host was configured. **No live Databricks write, warehouse execution, production Lakebase run or live LLM result is claimed.** A fake ACP tool result tests transport and presentation, not a real notebook creation. The app's unavailable-workspace message is verified; a labelled object fixture separately verifies that the output can render in the editor.

The finite [edge-case matrix](06-edge-cases-tests.md) covers identified failure classes. Visual review found no remaining mission-screen defect in those tested states; it is not a user study or an objective guarantee of perfection.
