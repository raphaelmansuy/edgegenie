# Implementation outcome and release boundary

[Index](README.md) · [First principles](00-five-whys-first-principles.md) · [Official assessment](01-databricks-assessment.md) · [Target requirements](03-requirements.md) · [Architecture](05-architecture-api.md) · [Edge matrix](09-edge-cases.md) · [Plan](10-implementation-plan.md) · [Test targets](11-test-e2e-plan.md) · [Decisions](12-decisions-open-questions.md) · [Browser evidence](e2e/README.md) · [Visual inspection](e2e/visual-inspection.md)

Implemented 2026-11-12 under the subsequent user instruction to implement and retain visually inspected E2E screenshots. This is a working full-stack development slice with a native API adapter, subsequently deployed to the authorized dev workspace. Native identity, warehouse inventory and Query metadata access are verified. The [rc.2 follow-up](15-sql-enabled-release.md) also qualifies independent-draft execution, stopped-warehouse startup and encrypted Lakebase restart recovery. It does **not** establish the complete R1 acceptance contract; native Query asset permissions/create/update and broader failure-matrix qualification remain open.

Current follow-up: [rc.4 CTE policy correction](17-cte-policy-correction.md) is deployed at `717c621`, building on [rc.3 AI integration](16-ai-query-integration.md). It adds editor-bound agent tools, matching terminal receipts and concurrent-human-edit recovery. The tables below retain the rc.2 baseline measurements; the current rc.3 results are recorded at the end.

## Delivered behavior and code

| Responsibility | Implementation and observed behavior |
|---|---|
| Navigation and identity | [App](../../apps/coding-agent/web/src/App.tsx), [routes](../../apps/coding-agent/web/src/domain/route.ts), [document kinds](../../apps/coding-agent/web/src/domain/docs.ts), [recents](../../apps/coding-agent/web/src/domain/recent.ts): Queries navigator, Home actions, palette, UUID routes, existing tabs/working set and account/workspace-scoped recents. Numeric editor IDs are rejected rather than converted. |
| Query library | [QueryLibrary](../../apps/coding-agent/web/src/components/QueryLibrary.tsx): metadata-only demand paging, cache search, own/favorite filters, app-specific favorites, filtered-empty state and independent own-run history. Cache capped at 1,000 assets; evictions explicitly mark search as partial. |
| Authoring | [QueryEditor](../../apps/coding-agent/web/src/components/QueryEditor.tsx) uses the existing [EditorHost](../../apps/coding-agent/web/src/editor/host.ts) and CodeMirror adapter. Local edits, private draft snapshots, selected-range dispatch, explicit warehouse/catalog/schema and named typed bindings. Truncated native source is read-only. |
| Explicit persistence | [QuerySaveDialog](../../apps/coding-agent/web/src/components/QuerySaveDialog.tsx), [typed client](../../apps/coding-agent/web/src/api/queries.ts) and [SQL service](../../apps/coding-agent/api/services/sql_service.py): review destination, create/save-copy, verify returned asset through GET, then promote the tab to native identity. No native PATCH/update route. Persist the exact create intent/key before dispatch; lost acknowledgments survive reload and Check again reuses the same request. |
| Policy and types | [sqlpolicy](../../apps/coding-agent/api/domain/sqlpolicy.py), [domain contracts](../../apps/coding-agent/api/domain/sqlquery.py): one conservative parsed read-only SELECT/compound query, fail closed when parser missing, no SQL interpolation, typed values, UTF-16 selections, source/token/depth bounds, canonical input fingerprints. SQLGlot 28.10.1 is pinned in both project manifests; dialect choice belongs to the provider adapter. |
| Execution lifecycle | [SqlService](../../apps/coding-agent/api/services/sql_service.py): reserve intent before submission, save known statement handle, bounded polling, own history, explicit unknown-outcome acknowledgment and cancellation reconciliation. Stale poll cannot regress a terminal state. Submit uncertainty never automatically replays the provider POST. |
| Durable journal | [SqliteQueryStore](../../apps/coding-agent/api/adapters/durable/query_sqlite.py): independent encrypted journal, atomic operation keys, source/draft CAS, workspace/user scope, deterministic recent index, indexed active-run counts and single-server file ownership lock. Restart reuses the same encrypted store and known handles. |
| Native and local adapters | [queries adapters](../../apps/coding-agent/api/adapters/databricks/queries.py) implement the same small provider protocol. Native uses the shared [HTTP transport](../../apps/coding-agent/api/adapters/databricks/http.py) with user token and bounded responses. Local demo executes table-free examples on an isolated SQLite engine and simulates asynchronous status/cancel. It is not a Databricks SQL compatibility emulator. |
| HTTP/composition | [SQL router](../../apps/coding-agent/api/routers/sql.py), [composition root](../../apps/coding-agent/api/main.py), [settings](../../apps/coding-agent/api/config.py): separate routes, bounded body middleware including chunked requests, typed error boundary, current request principal, no production app-token fallback. All UI calls reach this composition, not a parallel mock route. |
| Results | [SqlResults](../../apps/coding-agent/web/src/components/SqlResults.tsx): exact string/NULL values, ordinal duplicate columns, bounded row/column DOM pages, visible truncation, stale output, execution snapshot, source hash, cancellation and expiry states. Explicit copy acts on visible rows only. |
| Assistant | [context resolver](../../apps/coding-agent/api/services/context.py), [attachment contract](../../apps/coding-agent/api/domain/context.py), [Markdown](../../apps/coding-agent/web/src/components/Markdown.tsx): current edited source captured as an owner-scoped draft, server resolves its revision/hash under an untrusted-data wrapper. SQL code blocks open in a private draft after streaming ends; promotion does not execute or save. Result rows and binding values are excluded from attachment defaults. |
| Visual integration | [SQL styles](../../apps/coding-agent/web/src/sql.css), [shared asset icon](../../apps/coding-agent/web/src/components/AssetIcon.tsx): existing semantic theme, panel resolver, dock, editor and tab controls. Responsive SQL editor/results switches on narrow screens. Shared asset icon map replaces duplicated maps in three consumers. |

## DRY and SOLID applied

- **Single responsibility:** domain validates SQL/source values; service coordinates intent and authorization; store owns atomicity/encryption; adapters own external protocols; HTTP boundary handles typed inputs/errors; components render library/editor/results/save review.
- **Open/closed and dependency inversion:** `QueryProvider` and `QueryStore` protocols are injected at the composition root. Policy and lifecycle do not import vendor HTTP or SQLite implementations. Dialect selection is injected through the provider. An existing architecture test caught and drove removal of a raw vendor literal from core policy configuration.
- **Interface segregation and substitution:** native/demo providers implement the same narrow operations. Demo behavior includes delay, terminal status and cancel races. API tests inject a counting/fault provider through this seam. SQLite and Postgres adapters implement the same journal protocol. Shared domain functions enforce replay/expiry/capacity policy; real Postgres contracts verify CAS, encryption, owner isolation, atomic reservations and recovery. The Postgres adapter receives the existing connection coordinator through an injected operation runner.
- **DRY:** one SQL service, one parameter policy, one typed client and canonical ID/hash functions. Existing editor/theme/tabs/clipboard/errors/context fence are reused. A shared asset-kind icon map prevents query rendering from diverging across chips, composer and tabs.
- Existing notebook SQL execution is intentionally unchanged. Migrating its synchronous facade to the new lifecycle remains an explicit plan item; this slice does not claim the cross-surface execution consolidation is finished.

## Actual test evidence

| Check | Result and practical limit |
|---|---|
| Complete backend suite | **1,959 passed, 4 skipped**, 7 warnings, after integrating the current public app baseline and fixing decoded warehouse responses. Includes all app suites, 53 original SQL tests, nine new SQL Postgres contracts and enabled existing Postgres migration/reconnection suites. Warnings include Starlette compatibility and subprocess event-loop cleanup warnings in the existing Genie-feature tests; no failing assertion. Skips are not passes. |
| SQL backend tests | **53 passed**: compression decoded once, decoded-size limit enforcement, parser refusal/allow corpus, typed values/NULL, Unicode selection, encryption/reopen, duplicate reservation, CAS/owner lock, cross-user reads, no unauthorized submit, unknown submit, terminal/cancel races, HTTP200 FAILED/CLOSED, create/get, origin preservation, cancel intent after authorization failure, body bounds including chunked input, context fencing and missing-parser gate. [Test source](../../apps/coding-agent/tests/test_sqlquery.py). |
| Complete frontend suite | **1,231 passed in 83 files** on the compatible deployment baseline, including SQL domain and existing editor/tab/panel/route regressions. The complete frontend suite was rerun successfully after the final wording correction and version cut. [SQL domain tests](../../apps/coding-agent/web/src/domain/query.test.ts). |
| Production web build | TypeScript and Vite pass. Existing base/CodeMirror chunk-size warnings remain; query views are lazy chunks. |
| Local browser E2E | **16 checks pass**, zero browser runtime errors, 18 retained screenshots. Real browser → app API → encrypted SQLite journal → deterministic local provider. Includes API restart, browser reload, a provider-accepted create with browser acknowledgment lost, exact-key recovery after reload, and no execution on assistant promotion. [Report](e2e/report.json), [harness](../../apps/coding-agent/web/scripts/sql-query-e2e.mjs). |
| Deployed dev smoke | **17 checks pass**, zero browser runtime/transport errors: version/identity, metadata/capabilities, native execution from a stopped serverless warehouse, named binding/NULL, multistatement refusal, native cancellation, mobile/dark UI, own history, reload and actual app replacement. [Live report](e2e/deployed-report.json). Independent draft execution is exercised; native saved Query asset creation/update and origin execution remain gated. |
| Screenshot inspection | All 33 retained screenshots opened and visually reviewed individually: 18 local, four historical rc.1 and eleven native SQL rc.2 images. Iterations fixed toolbar overlap, dirty-state wording, singular row copy, early theme/layout captures, proposal-button contrast, save retry presentation and the assistant fixture prompt. [Per-image ledger](e2e/visual-inspection.md). |
| Static/spec validation | New backend files pass Ruff; working diff passes whitespace checks. Documentation traceability, links, ASCII geometry and Mermaid syntax are checked separately in [13](13-validation-record.md). |

The final test counts refer to release commit `fe4e110` in the isolated worktree `/private/tmp/opengenie-dev-git-fuce8rn5`. Use a checkout of tag `v1.2.0-rc.2` with the project dependencies installed to reproduce them. The original user checkout retains its existing branch and unrelated working changes. The full 1,959-pass run sets `TEST_SQL_PG_DSN`, `TEST_PG_DSN` and `TEST_JOURNAL_PG_DSN` to separate disposable local test databases. Without a configured test server, database-specific tests explicitly skip. Run product checks from the release checkout’s stated directories:

```bash
cd apps/coding-agent
.venv/bin/python -m pytest -n 4 -q
.venv/bin/ruff check api/domain/sqlquery.py api/domain/sqlpolicy.py api/adapters/databricks/queries.py api/adapters/durable/query_sqlite.py api/services/sql_service.py api/routers/sql.py tests/test_sqlquery.py
cd web
npm test
npm run build
npm run e2e:sql
```

Use the existing project environment with pinned dependencies and installed Playwright Chromium. The latest local E2E run recaptured all 18 screenshots from compatible revision `345d182`; every final image was reopened and inspected. The final dev wording correction and version badge are shown in four separately inspected live screenshots. Local functional checks were rerun from final release source with screenshot retention enabled; the 18 local image bytes retain explicit `345d182` provenance. Screenshot mode is explicit in the report. The browser harness needs local loopback access; its disposable server strips deployment credentials/settings and does not contact Databricks. It leaves only synthetic evidence in the requested folder. Broad standalone legacy browser/a11y/performance/screen-reader suites were not run; passing unit regressions do not substitute for them.

## Requirement checkpoint against the full target

“Local” means the implemented behavior has local test evidence; it does not mean every clause of the linked SQ row is qualified. The [64-edge target matrix](09-edge-cases.md) remains a release inventory, not a claim that all edges have been executed.

| Target | Checkpoint and remaining acceptance |
|---|---|
| SQ-01 | Local navigator/Home/palette/new draft and tabs; native editor landing/last permitted asset qualification remains. |
| SQ-02 | Local library, bounded page API and metadata; large/repeated-token/migrated asset fixtures and live coverage remain. |
| SQ-03 | Cached title/description, owner and app favorites; modified-this-week filter and scanned-count accounting are not implemented. |
| SQ-04 | UUID route/tab/recent contracts tested; native ID/path interoperability remains SP-1/SP-5. |
| SQ-05 | Existing editor/undo/theme and local recovery; schema-backed completion, full caret retention and keyboard qualification remain. |
| SQ-06 | Browser recovery, explicit draft/create snapshots and visible storage failure; opt-out/sign-out purge/download fallback and full dirty-close flows remain. |
| SQ-07 | Local create/copy/verify and lost-response recovery; native create defaults off pending SP-1. Update remains off. |
| SQ-08 | Explicit context and accessible-warehouse validation; native stopped-warehouse startup verified for the dev principal. Cross-principal CAN USE fixture matrix remains. |
| SQ-09 | Whole/selection policy and Unicode unit tests; selection browser/multicursor/fragment matrix still needs qualification. |
| SQ-10 | Typed named bindings, exact matching/NULL/date/numeric validation; native widget/default conversions remain SP-4. |
| SQ-11 | Local and native reservation/statement handle/polling; browser reload and an actual dev app replacement recover the same native statement/result without submission. Token renewal and exhaustive crash-point matrix remain SP-7. |
| SQ-12 | Parser, principal isolation and fail-closed native saved-query run gate; effective Query CAN RUN lookup remains SP-3. |
| SQ-13 | Local cancel/terminal races plus observed native Canceled; cancel intent retries when an authorized observation resumes (API fixture tested); no background cancellation without an observing authorized request and no deployed auth-expiry matrix. |
| SQ-14 | Bounded INLINE first result chunk and lossless rendering; additional chunks are not fetched and are labeled truncated. Exhaustive large-result fixtures remain. |
| SQ-15 | Immutable SQL/hash and visible stale output; UI provenance does not yet expose every context/revision field from the target. |
| SQ-16 | Own recent 50 runs and source-snapshot opening; full history pagination/native history handoff remain. |
| SQ-17 | Owner-scoped draft/query context and server fence; selection excerpts and explicit result-row context remain. |
| SQ-18 | SQL block → private draft without dispatch; local patch preview/apply and native typed artifact/MCP tool integration remain. |
| SQ-19 | Documented UUID native link generation; live link/native round-trip verification remains SP-1. |
| SQ-20 | Typed sanitized error boundary and unknown-outcome recovery; granular 429/Retry-After, expired-token reconnect and full operations status need more work. |
| SQ-21 | Inspected light/dark/375px/768px screens and overflow checks at five widths; keyboard-only, 200% zoom, forced colors and screen-reader qualification remain. |
| SQ-22 | Hard input/output/cache/concurrency bounds and encrypted scoped journal; physical retention purge, full telemetry and performance/privacy matrix remain. |
| SQ-23 | Native updates absent; no false CAS/publish guarantee. SP-2 remains closed. |
| SQ-24 | Capability flags and explicit bounded scope; no collaboration/export/widgets/Git/scheduling parity claim. |

## Configuration and operation

| Setting / condition | Behavior |
|---|---|
| Fake agent plus no workspace host | Isolated demo provider; create/run enabled for local tests. Never use this mode as evidence of workspace access. |
| `APP_SQL_RUN` | Defaults false in Settings; enabled in the rc.2 app deployment configuration. True additionally requires parser and a durable journal. Saved-query origin still fails closed pending verified effective-permission mapping. Independent user-authored drafts can use the Statement API when enabled. |
| `APP_SQL_CREATE` | Defaults false for native provider. Only enable after SP-1 destination/create/get/native-open qualification. Native adapter also checks the flag. |
| `APP_SQL_DB_PATH` | Persistent SQL SQLite file. Otherwise `<APP_SESSION_DB_PATH>.sql` when a session SQLite path exists. When no SQL SQLite path is configured, an existing Postgres/Lakebase session deployment selects the Postgres SQL store if a recovery key is available or execution is requested. |
| `APP_SQL_KEY` | Explicit Fernet key for SQL recovery. Postgres otherwise derives a separate stable SQL key from the existing deployment KEK; SQLite still requires an explicit key in production. Development can create a mode-0600 key sidecar. Back up key and encrypted file together through the deployment’s normal secret/backup process; do not expose the key in diagnostics. |
| Multiple workers/replicas | SQLite file ownership and the shared Postgres coordinator’s advisory owner lock enforce one active server. This is a single-active-server design, not distributed failover. Independent replica files are not a shared journal. |
| In-memory store | Demo/test only for execution. Native execution capability is disabled without a durable path. Opening the store can still fail on missing/invalid key, permissions or disk errors; API fails closed. |
| Rollback | Turn off new create/run. Existing own-run status/cancel/history remain routable; no native assets or journal rows are deleted. |

Rows/SQL are not logged by the SQL error boundary. Live run records omit result rows and binding values; encrypted synthetic upstream statements in the demo retain rows so tests can resume. Draft reads expire after seven days and public run source is hidden after seven days; **physical ciphertext purge is not implemented**. Do not enable a retention-constrained production pilot until expiry/purge and backup retention are implemented and verified. Unresolved create metadata persists in scoped browser storage to prevent unsafe new keys; after the server’s 24-hour key window, the UI fails closed rather than automatically creating again. Manual native reconciliation is still required for an accepted create whose handle never arrived.

The session-required Databricks MCP tools were unavailable; the authenticated CLI/SDK verified the actual dev identity and warehouse inventory. The user authorized public publication and dev deployment. Initial release candidate `v1.2.0-rc.1` (`8e9e520`) was deployed in workspace `7474647158015570`, with native Query metadata, private draft editor and all 10 live checks passing. Live editor smoke exposed a gzip transport bug, fixed in `0f63b19`; a subsequent inspected wording correction and version cut are included in the final revision. UC fixture access, native effective-permission mapping and saved-Query asset create/run round trips remain unqualified; independent-draft native execution is qualified in rc.2. Existing unrelated changes and the original working index were preserved; commits and deployment integration use an isolated worktree. See [deployment record](e2e/deployment.json), [compatible payload](e2e/compatible-deployment-review.md) and [transport fix](e2e/transport-fix-review.md).

## Initial released dev candidate (rc.1)

- [GitHub prerelease v1.2.0-rc.1](https://github.com/raphaelmansuy/opengenie/releases/tag/v1.2.0-rc.1), exact commit `8e9e520fb0a0a244a758f13daab96c08517161f5`.
- [Dev Queries workspace](https://coding-agent-7474647158015570.aws.databricksapps.com/#/queries), deployment `01f1de58bbcb18228bf8d92ed9b8e056`; running commit verified through the Databricks app deployment API, API version and browser version badge.
- [Release payload](e2e/version-release-review.md), [deployment record](e2e/deployment.json), [final live screenshot hashes](e2e/deployed-screenshots-manifest.json). Existing scopes/resources are unchanged. Stable release remains v1.1.0.
- The final full backend rerun initially hit sandbox denial of a localhost socket in an existing MCP subprocess test. Rerunning with the required socket access passed all 1,936 tests. No application change was needed for that environment restriction.

## SQL-enabled foundation (rc.2, historical)

[Release v1.2.0-rc.2](https://github.com/raphaelmansuy/opengenie/releases/tag/v1.2.0-rc.2) points to `fe4e1109a18495a1bcb0e58908655c1dea3ed908`. Deployment `01f1de5e4a341e8293928592df9ddbf7` was qualified at that source. The prior identical-source deployment performed native execution from STOPPED; the final replacement verified persistence of the same draft, statement ID and result with zero resubmissions. [17-check native report](e2e/deployed-report.json), [11 inspected rc.2 images](e2e/deployed-screenshots-manifest.json), [code/persistence contract](15-sql-enabled-release.md).

SQL draft execution is now enabled in dev. Native Query creation/update and saved-Query-origin execution remain gated. After additive schema migration 005, rollback must use schema-5-compatible code with execution disabled; older schema-4 builds intentionally fail the schema-ahead guard. Existing identity scopes/resources and unrelated user working changes are preserved. Integration and release commits remain in the isolated release worktree.

## AI query integration foundation (rc.3, historical)

[Release v1.2.0-rc.3](https://github.com/raphaelmansuy/opengenie/releases/tag/v1.2.0-rc.3) points to `7f104c78d859f42a8ef0ab764fc4adf1907e89fe`, deployed as `01f1de694b321347a8d654ebb982a162`. The [first-principles assessment](16-ai-query-integration.md) describes 31 reviewed app files and four narrow agent tools sharing the existing SQL service. The [actual-model report](e2e/agent-report.json) verifies edit/run/source/result identity, reload without resubmission, concurrent local edit preservation, explanation-only despite an injected SQL comment, and schema inspection before a five-row native NYC taxi sample.

Current validation: 1,994 backend passes / 4 skips / 7 warnings with isolated Postgres enabled; 1,233 frontend passes; production build passed; 16 local SQL E2E checks passed; seven live checks across four actual configured-model missions passed. Nine new screenshots were individually reviewed; all 42 numbered retained images have hash-backed review records. See [visual ledger](e2e/visual-inspection.md), [current deployment](e2e/deployment.json) and [exact payload review](e2e/agent-query-release-review.md). App scopes/resources and the original user working tree/index were preserved. Native saved-Query writes/origin execution, arbitrary-model SQL correctness and broad accessibility/performance qualification remain open.

## Current CTE execution correction (rc.4)

[Release v1.2.0-rc.4](https://github.com/raphaelmansuy/opengenie/releases/tag/v1.2.0-rc.4) is active at `717c6216f51b951b21aa9cff34dd434cfd4b245e`. The [first-principles explanation](17-cte-policy-correction.md) separates parsing, application policy and UC authorization, and records the EdgeSQL assessment. The exact screenshot query returned 60 daily rows on a new draft after on-demand serverless startup; a real-model CTE mission also succeeded. Original user source/version remained unchanged. Final validation: 2,061 backend passes / 4 skips, 1,233 frontend passes, production build, 16 local SQL E2E checks, eight native/AI checks and seven individually reviewed new screenshots. [Current report](e2e/cte-report.json), [image review](e2e/cte-screenshots-manifest.json), [payload](e2e/cte-release-review.md). Existing resource/scope configuration and native saved-Query gates are preserved.
