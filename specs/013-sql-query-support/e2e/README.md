# SQL query browser evidence

[Specification](../README.md) · [Implementation outcome](../14-implementation-outcome.md) · [Target test scenarios](../11-test-e2e-plan.md) · [Machine report](report.json) · [Visual review ledger](visual-inspection.md)

The [harness](../../../apps/coding-agent/web/scripts/sql-query-e2e.mjs) drives the actual compiled OpenGenie app through Playwright Chromium, the app API, SQL service and encrypted SQLite journal. The deterministic local provider executes synthetic, table-free SQL. This local harness uses no live Databricks workspace, tokens, tables or production assets. Live dev checks use the separate authenticated harness described below. The only browser interception deliberately drops a create response **after** the real server has accepted it; response bodies are not replaced with fixtures.

Run from `apps/coding-agent/web`:

```bash
npm run build
npm run e2e:sql
```

Use the repository Python environment with SQLGlot 28.10.1 and installed Playwright Chromium. Local loopback access is required. The helper launches a disposable local server, isolates its settings/credentials and shuts it down after testing. The test restarts that server during a known-handle run to verify durable recovery.

To rerun functional checks while retaining the already inspected screenshot bytes, use `SQL_E2E_CAPTURE=0 npm run e2e:sql`. The report records this mode explicitly; a normal run always captures new images and requires another review.

The latest [report](report.json) contains 16 passing checks, request method/path metadata, zero browser runtime errors, and absolute paths to 18 screenshots saved in `screenshots/`. It intentionally excludes SQL request bodies, binding values and authorization headers. Tests verify:

- Navigator → library → native query tab; scoped favorites and filtered-empty state.
- Submit → pending/running → success, results and provenance; API restart/browser reload without resubmit.
- Typed named parameter, NULL rendering and server refusal of a multistatement mutation.
- Requested cancellation reconciled to terminal canceled.
- Save-copy review → real server acceptance → lost browser response → reload → identical operation key → one verified copy.
- Own run history independent of chat, light/dark themes, no page-wide overflow at 320/375/768/1024/1440px.
- Current SQL snapshot attached through the existing assistant; completed SQL proposal promoted to a private draft without execution.

Scenario labels refer to a **subset** of the full T01–T18 targets. They do not establish complete coverage of every scenario variant, all 64 risks, accessibility or native interoperability. The [implementation checkpoint](../14-implementation-outcome.md) lists remaining work explicitly.

Screenshots were opened and visually inspected after each meaningful UI iteration. The [ledger](visual-inspection.md) records the final observations and hashes. Rerunning the harness replaces screenshot evidence; review replaced images again before updating that ledger. Screenshot quality is a review judgment, not a proof of defect-free behavior.

## Initial rc.1 Databricks dev smoke (historical)

The user authorized deployment to the existing [dev app](https://coding-agent-7474647158015570.aws.databricksapps.com/#/queries), workspace `7474647158015570`, using CLI profile `opengenie-dev`. The public source branch is `codex/sql-query-support-dev-20261112`; [deployment.json](releases/v1.2.0-rc.1-deployment.json) records exact source/deployment IDs and approval history. [Compatible payload](compatible-deployment-review.md) and [transport fix](transport-fix-review.md) record reviewed publication contents.

Run from the repository root after verifying the deployment record:

```bash
node specs/013-sql-query-support/e2e/tools/deployed-smoke.mjs
```

The [live harness](tools/deployed-smoke.mjs) obtains the profile token in memory and sends it only to the exact verified app origin, with redirects blocked. All API/UI response bodies come from the deployed app. It checks identity, health/readiness, routes, capability gates, native metadata, owner-scoped private draft authoring, mobile layout and dark theme. It does not create a native Query or execute SQL. The report excludes tokens and SQL request bodies. The rc.1 SQL store was in-memory; restart durability was not qualified in that release.

The [live report](releases/v1.2.0-rc.1-deployed-report.json) is separate from the 16-check local report. Screenshot numbers 19–22 are live deployment evidence; numbers 01–18 are deterministic local scenarios. A successful live report and individually reviewed screenshot hashes are required before marking the deployment qualified for this gated development slice.

Initial rc.1 outcome: [v1.2.0-rc.1](https://github.com/raphaelmansuy/opengenie/releases/tag/v1.2.0-rc.1) was deployed to dev at `8e9e520`. All 10 live checks pass, including API/browser version agreement. All four final deployed screenshots were individually reviewed; [their manifest](releases/v1.2.0-rc.1-deployed-screenshots-manifest.json) records hashes, dimensions and observations. The spec checker validates both local and live evidence. The release-source local rerun retains 18 previously inspected `345d182` images, as explicitly recorded in its report; all 16 functional checks pass on `8e9e520`.

## Native SQL execution and recovery (rc.2 foundation)

[v1.2.0-rc.2](https://github.com/raphaelmansuy/opengenie/releases/tag/v1.2.0-rc.2) enables SQL execution and persistent recovery. The [native harness](tools/enabled-sql-smoke.mjs) shares [authenticated transport/readiness/capture helpers](tools/live-session.mjs) with the [actual server-replacement recovery check](tools/enabled-sql-recovery.mjs). The historical rc.1 harness intentionally expects execution to be disabled and is not the current release check.

```bash
node specs/013-sql-query-support/e2e/tools/enabled-sql-smoke.mjs
# After an authorized deployment of the identical commit and updating deployment.json:
node specs/013-sql-query-support/e2e/tools/enabled-sql-recovery.mjs
```

The final [report](deployed-report.json) records 17 passed checks, cold serverless startup from STOPPED, four table-free read-only statements, one policy refusal, native cancellation, browser reload and an actual app replacement with zero resubmissions. No UC data table was read and no native Query asset was written. The initial mobile-results locator was corrected for its success checkmark; the [continuation helper](tools/enabled-sql-finish.mjs) repeated remaining checks without another SQL submission, and the complete harness now contains the corrected selector.

Images 23–33 are rc.2; 19–22 are unchanged historical rc.1 evidence; 01–18 are unchanged deterministic local scenarios. All 33 retained files were individually inspected. [Current manifest](deployed-screenshots-manifest.json), [archived rc.1 manifest](releases/v1.2.0-rc.1-deployed-screenshots-manifest.json), [visual ledger](visual-inspection.md). The current report’s execution deployment and final recovery deployment share the same exact source revision.

## Actual-model SQL query integration (rc.3 foundation)

[Assessment](../16-ai-query-integration.md) · [Actual-model report](agent-report.json) · [Nine reviewed images](agent-screenshots-manifest.json) · [Final deployment](deployment.json) · [Exact app payload](agent-query-release-review.md)

```bash
node specs/013-sql-query-support/e2e/tools/agent-query-smoke.mjs
```

The actual configured `google_vertex/google/gemini-3.8-flash` model completed four new private test missions. Seven live checks assert real draft updates, one exact-source native run per execution mission, terminal result receipts, reload without resubmit, simultaneous human edit review/keep, explicit no-run behavior, injected-comment isolation, schema inspection before table SQL, stated grain and five real trip rows. No existing user draft/session was edited. Native Query assets were not written.

The transport holds the CLI token in memory, rejects foreign origins, and passes the genuine EventSource stream without buffering. Normal HTTP responses remain actual app responses. Evidence contains only these synthetic/public-sample mission identifiers, bounded receipt metadata and test assertions, without tokens or headers. Viewport captures 34–42 were individually inspected, including 375px conflict recovery and the existing dark theme. Informational reasoning remains distinct from verified tool actions; it is not falsely labeled verified execution.

The first attempts found a buffering error in the browser transport and a result locator ambiguous between editor and assistant tables. Saved receipts established actual execution; the transport/locator were corrected and the complete final suite passed. Subsequent visual review corrected positive-evidence handling for prohibitions and pending submissions whose matching terminal observations succeeded. The final [manifest](agent-screenshots-manifest.json) pins only the final, individually inspected bytes to exact source `7f104c7`. Diagnostic earlier-attempt reports are historical and are not current screenshot provenance. This is a workflow evaluation, not a general semantic text-to-SQL benchmark. The rc.2 cold-start/app-replacement evidence remains [archived](releases/v1.2.0-rc.2-deployed-report.json).

## Current CTE policy regression (rc.4)

[First-principles explanation](../17-cte-policy-correction.md) · [CTE machine report](cte-report.json) · [Seven inspected images](cte-screenshots-manifest.json) · [Exact payload](cte-release-review.md) · [Deployment](deployment.json)

```bash
CTE_REPRODUCTION=/path/to/local-readonly-reproduction.json \
node specs/013-sql-query-support/e2e/tools/cte-policy-smoke.mjs
```

The reproduction record contains `{"draft":{"id":"<owned-original-draft UUID>","text":"<exact SQL>"}}`, read from the authorized dev app. It is a local input, excluded from publication. The original record used in this session is retained in the task temporary directory; that path is not a portable test fixture. The harness reads the original before/after, creates new test drafts and never edits the original. It submits the exact CTE once, checks 60 unique ordered daily rows, then verifies reload without resubmit. Unknown-function and CTE-mutation attempts are refused before native submission. Light/dark/phone captures and actual horizontal panning to the last result column are checked. A separate real-model mission describes schema, updates the open draft and executes that source revision with matching terminal receipts.

Eight dev checks passed from exact revision `717c621`, including cold startup from STOPPED. Seven new captures 43–49 were individually opened and reviewed. The phone pan was additionally rechecked through the existing statement with zero submissions. Results are bounded previews; the evaluation does not establish arbitrary-function or all-model correctness. The backend adds 67 policy cases and passes all 2,061 tests with isolated Postgres enabled; 1,233 frontend tests, production build and 16 local SQL browser checks pass. Historical rc.3 deployment/AI reports are [archived](releases/v1.2.0-rc.3-deployment.json).

## Merged main requalification

[PR #17](https://github.com/raphaelmansuy/opengenie/pull/17) is merged; [main deployment outcome](../18-main-merge-deployment.md) records exact main `d2d4754`. [Current live report](merge-report.json) passes all eight checks on this deployment, including serverless startup from STOPPED, the exact 60-row daily CTE, reload without resubmission and a real AI edit/run mission. All seven captures 50–56 were individually opened and reviewed; [manifest](merge-screenshots-manifest.json). Existing release images remain unchanged. The [rc.4 deployment archive](releases/v1.2.0-rc.4-deployment.json) retains provenance for the earlier CTE report.

```bash
CTE_REPORT=merge-report.json CTE_SCREENSHOT_OFFSET=7 \
node specs/013-sql-query-support/e2e/tools/cte-policy-smoke.mjs
```
