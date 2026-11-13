# Test strategy, E2E journeys and traceability

[Index](README.md) · [Requirements](03-requirements.md) · [Edge inventory](09-edge-cases.md) · [States](07-sequences-statecharts.md) · [Implementation](10-implementation-plan.md) · [Actual validation](13-validation-record.md)

T01–T18 below define the complete target qualification scenarios. A subset now has implemented unit/API/browser evidence: see [actual implementation coverage](14-implementation-outcome.md), [browser report](e2e/report.json) and [visual inspection](e2e/visual-inspection.md). A passing subset does not qualify an entire scenario or the full native release.

## Test layers

Pure domain tests cover source IDs/routing, UTF-16 ranges/hashes, parameter sets, SQL policy and state-transition invariants. Reducer/property tests enumerate every documented edge, illegal regressions and event ordering. Adapter contracts cover pages/IDs, create/get, native permissions, typed results, statuses, failures, retries and cancellation. Durable-store contracts run on memory/fake where useful, SQLite and an isolated Postgres schema, including CAS and unique-key races. API tests use FastAPI with injected ports and authenticated identities. Browser E2E drives actual app/API/store and fake Databricks transports; it must not mock away the policy or reservation layer.

Live interoperability is a separate, small suite in a verified disposable workspace. Confirm identity/warehouse first, describe any fixture table before SQL, state grain before any aggregation, page completely when claiming inventory, stop on permission failure and follow write-enable policy. Prefer table-free `SELECT 1`/literal fixtures for basic execution. No destructive statements, costs from large scans, or production Query publication are required for qualification.

## E2E scenarios

| ID | Journey and fault fixtures | Assertions / retained evidence |
|---|---|---|
| T01 | Library: empty, filtered empty, 3+ pages, duplicated page item, missing optional fields, invalid/repeated token, stale search and partial scan | Visible coverage, correct empty copy, one page per demand, dedup, filter reset and no missing-data claims. Request log proves no per-row text/ACL fetch. |
| T02 | Open same Query through library, recent, palette, native-ID link, then rename; cross-workspace and malformed IDs; file with same title | One tab per canonical identity; route parse/format round trips; no numeric-ID conversion; Back/Forward/refresh preserve selected source and do not execute. |
| T03 | New draft → type → switch/close tab → recover after reload; browser quota denial; second tab conflicting revision; dirty-close discard/export | Exact source/hash/caret recovery, explicit unsaved state, no native write on edit, conflict preserves both buffers, quota failure is visible. |
| T04 | Save/create copy with destination and collision; verify GET; edit while save in flight; create returns ID but GET503; create response lost; unsupported update | One POST, visible actual native ID/title, newer buffer stays dirty, created_unverified/create_unknown states, no blind retry/delete/import/publish. |
| T05 | Run selection/whole buffer with semicolon literals, comments, one trailing semicolon, multi-cursor, emoji range, multistatement script, CTE mutation, dynamic SQL/UDF, invalid/missing/NULL/decimal/date/timezone parameters and legacy widgets | Exact executable subset and typed payload; all forbidden inputs produce zero upstream submit calls; no SQL string interpolation; validation points to the field/source. |
| T06 | Pending → running → succeeded; immediate success; FAILED in HTTP200; unknown state; reorder terminal/pending responses; edit context while running | Stable run ID, authoritative terminal state, no second POST, old snapshot preserved, output visibly stale, warehouse wait distinct from app latency. |
| T07 | Double click, repeated key, concurrent API identical/different body, POST timeout before/after fake accepts, store failure at each dispatch boundary | Same-key same-body one attempt/POST; different body409; accepted-but-unacknowledged never replayed; durable unknown state and recoverable operation UI. |
| T08 | Cancel before dispatch, while pending, while running; success/failure races; lost ACK, deadline with/without token | Accurate cancel intent and final state, no false cancellation, pending cancel when auth unavailable, scope names exact run, no tab-close cancellation. |
| T09 | Browser reload/close, API restart, known-handle recovery, unknown-handle crash, token expiry, missing encryption/store | Same run and snapshot after restart, no new submit, sign-in recovery, no SP fallback, storage failure blocks unreserved execution, history without chat. |
| T10 | Identity matrix: user A/B, CAN VIEW/CAN RUN/CAN EDIT/CAN MANAGE, denied warehouse/UC, missing scope, deleted source, mismatched run/draft/chunk ID, stale preference | Permission-specific message and zero unauthorized upstream calls. Cross-user requests never fetch source/rows. New copy destination checked; no copied ACL promise. |
| T11 | Zero rows/no schema command, NULL/empty/literal null, BIGINT/DECIMAL exact values, duplicate labels, escaped HTML/JSON, timestamp, stale/expired/CLOSED result | Lossless ordinal rendering, result-state separation, no HTML execution, exact counts/truncation copy, successful run stays successful after expiry. |
| T12 | 4MiB output cap, malformed row width, absent manifest, wide schemas, multiple/expired chunks, 429/503/Retry-After, canceled fetch, no external download | Memory/DOM/output bounds; safe-read retries ≤2; no presigned URL/token exposure, no unsafe next-link fetch or lost truncation flag. |
| T13 | Attach saved Query/own snapshot/selection; denied/truncated context; SQL code-block promotion; dirty document patch conflict; injected comment/description/result; writes disabled; typed artifact refresh | Query kind validated end-to-end; untrusted-data wrapper/hash present; result rows opt-in; model content never changes policy; Apply local only; no automatic run/save; wrote-elsewhere opens explicit artifact. |
| T14 | Notebook SQL cells and `.sql` source file reuse; native `.dbquery.ipynb` and unsupported workspace kind | File remains file, Query remains Query; existing notebooks/tabs/output/chords/links unchanged unless explicitly migrated. No query persistence via workspace SOURCE overwrite. |
| T15 | Concurrent tabs/user scopes, external dirty refresh, stale poll, app draft CAS, ownership-fence loss and supported gated native-update race | No silent buffer loss, no terminal regression, no dispatch after ownership loss, no false atomic update claim, shared observer coalescing. |
| T16 | Full keyboard journey at 320/375/768/1024/1440px, light/dark, 200% zoom, forced colors, reduced motion; dialogs/menus/result paging; clipboard refusal | Visible non-obscured focus, named controls and statuses, no completion focus theft, no page-wide overflow, stable shell/dock scroll and no extra scrim. Retain screenshots and manual screen-reader observations. |
| T17 | 10k remote assets, 200KiB source, 100 params, 1,000×200 bounded cells, pathological nested input and rapid view churn | [Complexity budgets](08-lenses-complexity.md), one initial page, no N+1, bounded cache/parse/DOM and polling; measured p95 and memory profile on recorded hardware. |
| T18 | Capability disabled, read/create/run enabled independently, parser/provider incompatibility, native ID mappings, current/migrated Query fixtures, rollback mid-run | Honest native handoffs, no unsupported update/publish/widget/export claims, history/cancel after rollout disable, additive migration/packaging contracts. Live smoke proves create/get/reopen interoperability when enabled. |

## Requirement-to-test map

| Requirement | Qualifying scenarios |
|---|---|
| SQ-01 | T01, T02, T16 |
| SQ-02 | T01, T10, T17 |
| SQ-03 | T01, T17 |
| SQ-04 | T02, T14, T18 |
| SQ-05 | T03, T14, T16, T17 |
| SQ-06 | T03, T04, T09 |
| SQ-07 | T04, T10, T15, T18 |
| SQ-08 | T05, T06, T10 |
| SQ-09 | T05, T14 |
| SQ-10 | T05, T11, T18 |
| SQ-11 | T06, T07, T09, T15 |
| SQ-12 | T05, T10, T13, T18 |
| SQ-13 | T08, T09 |
| SQ-14 | T11, T12, T16, T17 |
| SQ-15 | T05, T06, T11, T13 |
| SQ-16 | T02, T09, T11 |
| SQ-17 | T10, T13 |
| SQ-18 | T03, T13, T15 |
| SQ-19 | T02, T14, T18 |
| SQ-20 | T04, T07–T12 |
| SQ-21 | T03, T11, T16 |
| SQ-22 | T07, T10, T12, T13, T17 |
| SQ-23 | T04, T15, T18, plus new native-update tests after SP-2 |
| SQ-24 | T14, T18 |

The [EC matrix](09-edge-cases.md) is the reverse risk-to-test map. Each test implementation must list its EC/SQ IDs in the test description or report. Add a coverage check that fails when any requirement or H edge has no qualifying test reference; references do not themselves prove a test passed.

## Fault injection and meaningful assertions

Implement fake transport checkpoints: before reservation; after reservation; after marking submitting; before remote acceptance; after remote acceptance; before handle persistence; before terminal commit; before cancel ACK. Count actual upstream requests and durable rows at every point. Test interleavings, not merely snapshots of UI strings. Include concurrent app-store requests from two clients and source changes from the native-editor fixture. Use deterministic clocks/backoff and no long real sleeps.

Security fixtures record outbound headers only through a redactor; assert the correct user token was used without printing it. Scan app logs and browser storage for token/result/SQL leakage using synthetic canaries. A missing permission returns denial, not an empty list or fallback credential. A policy refusal asserts zero Databricks submit calls, not just a disabled button.

Native-update tests are conditional on a verified provider contract. A disabled update capability passes baseline tests only if all update controls/tools refuse and Save copy/native handoff remain usable; it cannot be counted as tested in-place editing.

## Proposed files and execution

Add `tests/test_sqlquery.py`, `test_sqlpolicy.py`, `test_sqlrun_store.py`, `test_sql_api.py`, `test_query_adapters.py`, and frontend `domain/query*.test.ts` plus component tests. Add `web/scripts/sql-query-e2e.mjs` using the existing disposable-server helper with injectable fake query adapters; add a dedicated Playwright project/spec if the repository standard is consolidated during implementation. Do not add a second independent browser harness.

Run targeted pytest/Vitest suites first, then `npm run build`, SQL browser E2E, existing notebook/tab/deep-link/panel regression scripts and a11y/overflow checks. Use the repository environment and dependency tooling; do not install global packages. Record actual commands, versions, outcomes and artifacts only after implementation. The documentation checks are listed in [13](13-validation-record.md); actual product tests and remaining qualification gaps are recorded in [14](14-implementation-outcome.md).

## Release evidence

For each T: automated pass/fail, seed/fixture version, API request-count assertions, relevant EC/SQ IDs and sanitized screenshot/trace links. For live smoke: verified identity/workspace/warehouse, native create/get/open/run evidence and capabilities. For T16: manually inspect screenshots plus keyboard/screen-reader behavior; axe alone does not validate focus logic. For T17: raw timings, DOM cells, peak memory and call counts. No screenshot, test, performance result or native interoperability is claimed passed before it actually runs.

## SQL-enabled dev follow-up

The [rc.2 implementation and qualification record](15-sql-enabled-release.md) adds encrypted Postgres SQL persistence through the existing Lakebase coordinator and enables independent-draft execution. Native stopped-warehouse startup, parameter/NULL rendering, cancellation, reload and actual server replacement now have live evidence. Native saved-Query permissions/create/update and the remaining target matrix stay gated. See the [current machine report](e2e/deployed-report.json) and [visual ledger](e2e/visual-inspection.md).
