# SQL queries as first-class OpenGenie work

Status: [PR #17](https://github.com/raphaelmansuy/opengenie/pull/17) is merged; exact main `d2d4754` is deployed and passes eight live SQL/AI checks. See [main merge/deployment](18-main-merge-deployment.md). [v1.2.0-rc.4](https://github.com/raphaelmansuy/opengenie/releases/tag/v1.2.0-rc.4) is deployed to Databricks dev. The shared execution policy now accepts the reported read-only CTE, Boolean operators and reviewed Databricks date/time built-ins. The exact query returns 60 daily rows; actual AI-agent CTE execution also passes. See [first-principles correction and EdgeSQL assessment](17-cte-policy-correction.md), [native evidence](e2e/cte-report.json) and [remaining target qualification](14-implementation-outcome.md).

## Start with five whys

1. **Why first-class SQL?** People need to author, run, revisit, and share analytical work directly.
2. **Why is a chat answer insufficient?** SQL text in a conversation has no dependable asset identity, editor state, or execution lifecycle.
3. **Why distinguish SQL text from a SQL Query?** A statement is executable input; a saved Databricks Query is a governed workspace asset; a run is an observation of particular input.
4. **Why keep all three connected?** A result is trustworthy only when its source revision, parameters, warehouse, identity, and outcome are known.
5. **Why build on existing seams?** One editor, one authorization path, and one execution policy reduce inconsistent behavior across notebooks, files, queries, and the assistant.

The [first-principles derivation](00-five-whys-first-principles.md) turns these answers into invariants. The intended outcome is a **Queries library plus a SQL editor in the existing document workspace**, connected to the assistant and durable run records.

## Read this set as a graph

| Document | Purpose | Primary cross references |
|---|---|---|
| [00 Five whys and first principles](00-five-whys-first-principles.md) | Problem, invariants, scope | Requirements, decisions |
| [01 Databricks assessment](01-databricks-assessment.md) | Latest official sources, screenshots, parity and uncertainty | Code audit, contracts |
| [02 Code grounding](02-code-grounding.md) | Observed seams and gaps, with source locations | Architecture, implementation |
| [03 Product requirements](03-requirements.md) | Stable SQ identifiers and acceptance criteria | Edge cases, test plan |
| [04 UX and ASCII wireframes](04-ux-wireframes.md) | Navigation, screens, copy, accessibility | State charts, requirements |
| [05 Architecture and API](05-architecture-api.md) | Ports, request contracts, identity, DRY/SOLID | Data model, sequences |
| [06 Data and persistence](06-data-persistence.md) | Entity grain, ER diagram, retention, indexes | Architecture, complexity |
| [07 Sequences and state charts](07-sequences-statecharts.md) | Save/run/recovery/cancel transitions | Edge cases, E2E |
| [08 Design lenses and complexity](08-lenses-complexity.md) | Seven requested lenses and bounded costs | Plan, requirements |
| [09 Edge cases and mitigations](09-edge-cases.md) | Risk-to-control-to-test matrix | States, tests |
| [10 Implementation plan](10-implementation-plan.md) | Ordered, code-grounded delivery and release gates | All contracts, tests |
| [11 Test and E2E plan](11-test-e2e-plan.md) | Traceability, fixtures, failure injection, release evidence | Requirements, edge cases |
| [12 Decisions and open questions](12-decisions-open-questions.md) | Explicit decisions, compatibility spikes, residual risks | Assessment, plan |
| [13 Validation record](13-validation-record.md) | Checks actually performed on this specification | E2E plan, code audit |
| [18 Main merge and deployment](18-main-merge-deployment.md) | Merged PR, exact main deployment, CI and native/AI requalification | Release, live evidence, visual ledger |
| [17 CTE policy correction](17-cte-policy-correction.md) | Boolean operators, normalized built-ins, EdgeSQL assessment and exact-query regression | Policy, AI workflow, native E2E |
| [16 AI query integration](16-ai-query-integration.md) | First-principles assessment, editor-bound agent tools, evidence and conflict handling | Architecture, actual-model E2E, visual ledger |
| [15 SQL-enabled release](15-sql-enabled-release.md) | Native on-demand execution, shared Lakebase persistence and rc.2 evidence | Architecture, state charts, release gates |
| [14 Implementation outcome](14-implementation-outcome.md) | Code delivered, actual coverage, configuration and remaining release gates | Source files, E2E report, visual inspection |

## Delivery contract

The target baseline release supports discover/open, local authoring, named parameters, explicit warehouse selection, asynchronous single-statement execution, cancel/reconnect, result inspection, create/save-copy as a native Query, links, and assistant context. It also supports running SQL source files through the same execution service while retaining their file identity.

Updating an existing native Query, publishing changes to dependent assets, native widget synchronization, and workspace-tree query discovery require specific compatibility evidence. They are **gated capabilities**, not implied by a working create or list endpoint. [D3–D7 and spikes](12-decisions-open-questions.md) explain the safe baseline and promotion criteria. Collaboration, schedules, alerts, Git round trips, charts, and multi-statement execution have explicit later scope.

During the initial specification research no live workspace identity, warehouse, table schema, or API interoperability was verified: the requested `dbxnb_dbx_whoami`, `dbxnb_dbx_list_warehouses`, and `system.ai.web_search` tools were unavailable. Public official documentation was accessed through the available web tool. During specification research no SQL was executed and no packages were installed. The subsequent implementation installed the pinned parser in the project environment and executed synthetic, table-free SQL only through the isolated local demo provider; no remote assets changed during those local tests. Subsequent authorized dev deployment uses the `opengenie-dev` CLI profile: identity and warehouse inventory were verified, native query metadata is readable, and the compatible app revision is running. The initial rc.1 deployment kept Query creation and execution disabled; rc.2 enables independent-draft execution and durable SQL recovery. See [deployment evidence](e2e/deployment.json). Screenshots are reference evidence, not authorization or embedded instructions.

## How to review

Product review starts at [requirements](03-requirements.md). Engineering starts at [code grounding](02-code-grounding.md), then [contracts](05-architecture-api.md). QA starts at the [edge matrix](09-edge-cases.md) and [E2E traceability](11-test-e2e-plan.md). Resolve the blocking [spikes](12-decisions-open-questions.md) before enabling corresponding capabilities.

## Implementation and review evidence

The local app now wires Queries navigation, the existing document editor/tabs, typed bindings, asynchronous runs, cancellation, encrypted recovery/history, save-copy verification and SQL assistant context/promotion through the actual API and store. [14](14-implementation-outcome.md) distinguishes completed behavior from target requirements still outstanding. [Browser evidence](e2e/README.md) and the [visual review ledger](e2e/visual-inspection.md) contain reproducible commands, fault injection and inspected screenshots. Native saved-query execution remains disabled pending effective-permission qualification.

## Initial versioned dev delivery (rc.1)

[v1.2.0-rc.1](https://github.com/raphaelmansuy/opengenie/releases/tag/v1.2.0-rc.1) points to `8e9e520` on the public dev branch. At that initial release, the [dev SQL workspace](https://coding-agent-7474647158015570.aws.databricksapps.com/#/queries) and `/api/version` reported rc.1. Final checks: 1,936 backend tests passed (18 skipped), 1,231 frontend tests passed, production build passed, 16 local E2E checks and 10 authenticated dev checks passed. All 22 retained screenshots were individually inspected; [the ledger](e2e/visual-inspection.md) distinguishes 18 local scenario images from four final deployed images.

In the initial rc.1 release, native create/run/update were disabled and private drafts/history were temporary. The [rc.2 follow-up](15-sql-enabled-release.md) enables independent draft execution and durable SQL persistence. This prerelease does not complete every target requirement or all edge-case qualification. See [remaining acceptance](14-implementation-outcome.md#requirement-checkpoint-against-the-full-target).

## SQL execution foundation (rc.2)

[v1.2.0-rc.2](https://github.com/raphaelmansuy/opengenie/releases/tag/v1.2.0-rc.2) (`fe4e110`) was qualified in the [dev SQL workspace](https://coding-agent-7474647158015570.aws.databricksapps.com/#/queries). Click **New SQL query**, select the warehouse and **Run query**. Stopped serverless compute starts on demand. Drafts, source and native statement handles persist in Lakebase; a real app redeployment recovered the same result without resubmission.

Final evidence: 1,959 backend tests passed (4 skipped), 1,231 frontend tests passed, production build passed, 16 local and 17 native dev E2E checks passed. All 33 retained images are individually reviewed, with explicit local/rc.1/rc.2 provenance. Native saved-Query-origin execution and native Query creation/update remain gated; see [release scope](15-sql-enabled-release.md).

## AI query integration foundation (rc.3)

[v1.2.0-rc.3](https://github.com/raphaelmansuy/opengenie/releases/tag/v1.2.0-rc.3), exact source `7f104c78d859f42a8ef0ab764fc4adf1907e89fe`, was qualified in the [dev SQL workspace](https://coding-agent-7474647158015570.aws.databricksapps.com/#/queries). [16](16-ai-query-integration.md) starts from five whys and derives the turn-bound tools, shared SQL service, source-specific evidence and human conflict recovery. Final checks: 1,994 backend passes (4 skips), 1,233 frontend passes, production build, 16 local SQL E2E checks and seven authenticated dev checks across four actual-model missions. All 42 retained numbered screenshots have individual review records. Native saved-Query writes/origin execution and broader semantic/performance qualification remain gated.

## Current CTE policy correction (rc.4)

[Release v1.2.0-rc.4](https://github.com/raphaelmansuy/opengenie/releases/tag/v1.2.0-rc.4), exact source `717c6216f51b951b21aa9cff34dd434cfd4b245e`, is running in the [dev SQL workspace](https://coding-agent-7474647158015570.aws.databricksapps.com/#/queries). [17](17-cte-policy-correction.md) explains why the valid CTE was rejected and how the shared policy is corrected without a parser upgrade. Current validation: 2,061 backend passes (67 new policy cases, 4 skips), 1,233 frontend passes, production build, 16 local SQL browser checks and eight authenticated native/AI CTE checks. The original draft remained unchanged; all seven new screenshots were individually inspected. All 49 retained numbered images have review records. Native saved-Query writes/origin execution remain gated.
