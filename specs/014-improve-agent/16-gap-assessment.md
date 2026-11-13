# 16 · Gap assessment and closure record

13 November 2026. **The full spec release gate remains open.** This is a semantic assessment of all
64 requirements, implementation changes and actual evidence. A test reference proves the behavior it
asserts; it is not a claim that every acceptance criterion or deployment has passed. The completeness
skill's generic requirement-marker scanner does not understand `AG-*`, so no coverage percentage is
inferred from marker counts.

## Gaps closed in this pass

| Gap | Final behavior | Evidence |
|---|---|---|
| Accepted turn and normalized turn could diverge on a crash | Journal event, recovery snapshot, normalized turn and retry receipt commit together on shared SQLite/PostgreSQL transactions; memory commits under one acceptance lock | `test_agent014_transactions.py`; 67 PostgreSQL contracts |
| Old SQLite ledgers occupied a separate database | Existing encrypted rows import once, losslessly, into the shared journal; import marker prevents replay; prior file/key remain intact | Legacy import and rollback tests |
| Continuation cap could reset after wake-up pruning | Consumed operation receipts, including older pages, enforce the five-continuation cap | 110-operation pruning regression; PostgreSQL browser recovery |
| Settings intent/audit and mode snapshot could disagree | Mode/preference/budget changes batch with their outbox; mode route holds the session lock and snapshot uses the new mode | Failure-injection tests and full app restart test |
| Services imported model adapters | Registry selection moved into composition; resolver, health and credential services receive factories through ports | Import-graph check across every service |
| Attachment reads duplicated asset implementations | Ordinary attachments use the same registered handlers; cells delegate to the notebook handler; new registered kinds pass validation without another dispatcher | New-kind unit/owner-bound HTTP tests; all-services kind-dispatch architecture check |
| Legacy internal route could run agent code as app identity for administrators | Creation/resume grant nothing; internal submission/poll refuse even retained legacy grants; human Run remains independently authorized | Internal-route and administrator policy tests |
| S13 fallback lacked a port/deployment check | Isolation/verifier/runner ports and negative/unknown-grant checks exist; a separate identity declaration fails boot, build and deployment until an adapter is qualified | `test_agent014_run_identity.py` and `check-run-identity.py` |
| No per-session storage reporting or guarded cascade | On-demand owner storage report; archived owner+administrator purge with exact confirmation, no active observers/operations or unacknowledged resources; active journal/ledger rows cascade together | Storage browser desktop/mobile/error/retry; purge rollback, isolation and refusal contracts |
| Table creates had no resource lifecycle | Intent stores absent-table candidates before submit; successful native observation produces one durable resource; cleanup checks native table ID, owner, schema, metadata and Delta data version; SQL mutations say no undo | Eleven table lifecycle contracts; live table/browser and exact native absence checks |
| Unknown cleanup was easily confused with deletion | Pending SQL cleanup retains its handle; reconciliation distinguishes observed deletion from unproven absence; explicit acknowledgement can keep resources | Contract tests; keep-resource browser screen |
| Catalogue/system reads interpolated caller text into SQL | Named STRING parameters bind search text and identifiers; catalogue describes metadata then uses one capped SELECT | Hostile quote/backslash contracts and live catalogue parameter proof |
| App logs had no ingestion path | Bounded user-only CLI log reader, private OAuth cache, deadline and output caps, redaction, no identity fallback; qualified CLI pinned/checksummed at build time | Five log contracts, three packaging tests; earlier preinstalled-CLI read passed. Bundled live authentication remains open below |
| Generated bundles had not been validated by the actual CLI | Actual job and pipeline handler plans validate with zero warnings and zero deploy/native mutation calls | `as-code-bundle-validation.json` |
| Expanding transcript mounted unbounded history | At most 30 turns and 20 result rows per grid mounted; previous/newer/latest navigation reaches every turn; stale ledger-page responses are discarded | `scale-window-02.json`: all 200 turns reachable, p95 scroll frame 17.3 ms |
| Lazy ready sessions displayed Starting | Status says ready until actual provisioning begins | Peek regression and inspected storage rerun |
| Deep instruction traversal dropped the user file | User/workspace instruction roots retained under the cap; contents remain escaped preference data; refusal stops traversal | Preference, refusal and user skill list/load contracts |
| ACP vocabulary coverage was assumed | Frozen official schema vocabulary/hash checked; missing `compaction_summary_chunk` mapped; unknown kinds counted and logged once | `acp-v1-updates.json`, parity tests |
| Pinned built-in tool deny policy had no actual negative probe | Captured real gpt-oss request tool catalogues from OpenCode 1.18.19 offered only `todowrite`, with neither `skill` nor `task` | `native-tool-negative.json` |
| Requirement coverage named hypothetical test files | All 64 rows now name existing representative files/selectors, statuses and remaining qualification; a test enforces paths and selectors | `requirement-evidence.json`, traceability test |

## Remaining gates

1. **Bundled CLI log authentication (AG-35).** Two user-only live log attempts with the pinned binary
   failed. No alternate identity was attempted; raw logs, credentials and CLI error bodies were not
   retained. Live attempts stopped under the working agreement. A synthetic offline cache lookup
   succeeded, so that does not establish the cause of the live refusal. Earlier observation with the
   preinstalled CLI is separate evidence and does not qualify the new packaged binary.
2. **Product exams and baseline (AG-54 and phase gates).** The complete original+new 17-mission suite on
   two models has not passed or been compared with the original pre-change baseline. That historical
   baseline was not captured before changes. Existing real M9 scores remain gpt-oss 12/12 and Maverick
   6/12. They must not be replaced with grader reference scores or a reconstructed baseline labelled
   historical. The latest live table mission also ended blocked after unsupported SQL observations;
   its table resource lifecycle passed separately. No false mission completion was accepted.
3. **Full real-agent/fault qualification.** Actual negative built-in probe passed, but the complete
   timed wait/timeout matrix, token rotation during a long turn, ten-minute native-job recovery,
   200-turn native resume and recording of every advertised P6 feature remain. Existing deterministic
   and PostgreSQL contracts cover these mechanisms, not every real timing/platform combination.
4. **Deployed qualification.** Live user scopes match the bundle, but this checkout has not been synced
   or deployed. Native/as-code job, pipeline and app lifecycle exams at each deployed identity tier,
   system-table grants/lag, and separate run identity S13 are not established by local contracts.
   Separate execution stays disabled, as allowed by task 2.6's S13 fallback.
5. **Release quality matrix.** Full WCAG 2.2 AA audit of every new state, active-operation population
   load, exhaustive named crash injection and parent-commit-fails demonstration for every acceptance
   criterion remain. Individually inspected screenshots are evidence for their captured states.

The guarded history purge erases the active logical journal/ledger and session-owned blobs/history.
It is not a compliance claim about database backups, filesystem snapshots or old retained migration
files. The legacy `.agent` migration backup is deliberately preserved; operators must apply their
backup retention policy separately. Filesystem erasure and database commit are not one distributed
transaction; retrying failed purge is idempotent.

## Historical validation before the first-principles follow-up

- Final `make check`: **876 Python passed, 19 skipped; 639 frontend passed; TypeScript passed**.
- Disposable PostgreSQL: **67 passed**, sequential shared-journal acceptance, CAS, changes, retention,
  storage, purge rollback and recovery.
- Production frontend build passed; existing chunk-size advisory remains.
- `storage-04`: four screenshots, on-demand/keyboard/refresh/mobile/503/recovery passed.
- `scale-window-02`: five screenshots, bounded navigation/result pages/reset/mobile passed.
- `assets-gap-final`: fourteen screenshots, including explicit resource acknowledgement, passed.
- `operations-gap-final`: six screenshots, all tabs closed, continuation, process restart, durable
  wake receipt, native-handle retention and cancellation passed on PostgreSQL.
- `live-table-01`: four lifecycle screenshots passed. `live-table-02` failed a first-card assertion
  because later refused SQL observations preceded the successful create. `live-table-03` resumed that
  same session, selected the original native handle and completed review/cleanup **without another
  CREATE**. It passed four lifecycle screenshots; the model mission stayed blocked. Both owned table
  fixtures, schemas and folders were cleaned.
- `assets-context-final` and `assets-context-02` each retained six screenshots, then failed a harness
  assertion attempting to obtain resolved private context from a public API. The probe stopped.
  Owner-bound shared-reader and actual HTTP tests prove content delivery and that public responses
  omit that private context. The corrected public-reference assertion is saved but was not rerun.
- `storage-01`/`storage-02` retain failed responsive harness iterations; the corrected `storage-04`
  passed. No failed iteration is counted as a completed E2E flow.
- **All 325 retained PNGs were individually opened**, including every failure/intermediate capture.
  Their exact hashes are in `screenshot-inspections.json`.

## All 64 requirements

The complete selector map is [requirement-evidence.json](e2e/requirement-evidence.json). The references
below are representative; status and qualification are assessed above, not calculated from file names.

| Requirement | Assessment | Representative evidence |
|---|---|---|
| [AG-01](03-requirements.md#ag-01) | Implemented; representative tests pass | [test_agent014_trust.py](../../apps/coding-agent/tests/test_agent014_trust.py) |
| [AG-02](03-requirements.md#ag-02) | Implemented; representative tests pass | [test_agent014_trust.py](../../apps/coding-agent/tests/test_agent014_trust.py) |
| [AG-03](03-requirements.md#ag-03) | Implemented; qualification remaining | [test_genie_features.py](../../apps/coding-agent/tests/test_genie_features.py) |
| [AG-04](03-requirements.md#ag-04) | Implemented; representative tests pass | [test_agent014_trust.py](../../apps/coding-agent/tests/test_agent014_trust.py) |
| [AG-05](03-requirements.md#ag-05) | Implemented; representative tests pass | [test_agent014_assets.py](../../apps/coding-agent/tests/test_agent014_assets.py) |
| [AG-06](03-requirements.md#ag-06) | Implemented; representative tests pass | [test_agent014_trust.py](../../apps/coding-agent/tests/test_agent014_trust.py) |
| [AG-07](03-requirements.md#ag-07) | Implemented; representative tests pass | [test_agent014_trust.py](../../apps/coding-agent/tests/test_agent014_trust.py) |
| [AG-10](03-requirements.md#ag-10) | Implemented; representative tests pass | [test_agent014_changes.py](../../apps/coding-agent/tests/test_agent014_changes.py) |
| [AG-11](03-requirements.md#ag-11) | Implemented; representative tests pass | [test_agent014_changes.py](../../apps/coding-agent/tests/test_agent014_changes.py) |
| [AG-12](03-requirements.md#ag-12) | Implemented; qualification remaining | [test_agent014_changes.py](../../apps/coding-agent/tests/test_agent014_changes.py) |
| [AG-13](03-requirements.md#ag-13) | Implemented; representative tests pass | [test_agent014_trust.py](../../apps/coding-agent/tests/test_agent014_trust.py) |
| [AG-14](03-requirements.md#ag-14) | Implemented; representative tests pass | [test_agent014_changes.py](../../apps/coding-agent/tests/test_agent014_changes.py) |
| [AG-15](03-requirements.md#ag-15) | Implemented; representative tests pass | [test_agent014_changes.py](../../apps/coding-agent/tests/test_agent014_changes.py) |
| [AG-16](03-requirements.md#ag-16) | Implemented; representative tests pass | [test_agent014_table_resources.py](../../apps/coding-agent/tests/test_agent014_table_resources.py) |
| [AG-17](03-requirements.md#ag-17) | Implemented; representative tests pass | [test_agent014_changes.py](../../apps/coding-agent/tests/test_agent014_changes.py) |
| [AG-18](03-requirements.md#ag-18) | Implemented; representative tests pass | [test_agent014_trust.py](../../apps/coding-agent/tests/test_agent014_trust.py) |
| [AG-30](03-requirements.md#ag-30) | Implemented; qualification remaining | [test_agent014_assets.py](../../apps/coding-agent/tests/test_agent014_assets.py) |
| [AG-31](03-requirements.md#ag-31) | Implemented; qualification remaining | [test_agent014_trust.py](../../apps/coding-agent/tests/test_agent014_trust.py) |
| [AG-32](03-requirements.md#ag-32) | Implemented; qualification remaining | [test_agent014_assets.py](../../apps/coding-agent/tests/test_agent014_assets.py) |
| [AG-33](03-requirements.md#ag-33) | Implemented; qualification remaining | [test_agent014_assets.py](../../apps/coding-agent/tests/test_agent014_assets.py) |
| [AG-34](03-requirements.md#ag-34) | Implemented; qualification remaining | [test_pyrun.py](../../apps/coding-agent/tests/test_pyrun.py) |
| [AG-35](03-requirements.md#ag-35) | Partial | [test_agent014_app_logs.py](../../apps/coding-agent/tests/test_agent014_app_logs.py) |
| [AG-36](03-requirements.md#ag-36) | Implemented; representative tests pass | [test_sqlquery.py](../../apps/coding-agent/tests/test_sqlquery.py) |
| [AG-37](03-requirements.md#ag-37) | Implemented; qualification remaining | [test_agent014_assets.py](../../apps/coding-agent/tests/test_agent014_assets.py) |
| [AG-38](03-requirements.md#ag-38) | Implemented; qualification remaining | [test_agent014_assets.py](../../apps/coding-agent/tests/test_agent014_assets.py) |
| [AG-39](03-requirements.md#ag-39) | Implemented; qualification remaining | [test_agent014_assets.py](../../apps/coding-agent/tests/test_agent014_assets.py) |
| [AG-20](03-requirements.md#ag-20) | Implemented; qualification remaining | [test_agent014_trust.py](../../apps/coding-agent/tests/test_agent014_trust.py) |
| [AG-21](03-requirements.md#ag-21) | Implemented; qualification remaining | [test_adapters.py](../../apps/coding-agent/tests/test_adapters.py) |
| [AG-22](03-requirements.md#ag-22) | Implemented; qualification remaining | [test_agent014_operations.py](../../apps/coding-agent/tests/test_agent014_operations.py) |
| [AG-23](03-requirements.md#ag-23) | Implemented; representative tests pass | [test_agent014_operations.py](../../apps/coding-agent/tests/test_agent014_operations.py) |
| [AG-24](03-requirements.md#ag-24) | Implemented; qualification remaining | [test_agent014_operations.py](../../apps/coding-agent/tests/test_agent014_operations.py) |
| [AG-25](03-requirements.md#ag-25) | Implemented; representative tests pass | [test_agent014_operations.py](../../apps/coding-agent/tests/test_agent014_operations.py) |
| [AG-26](03-requirements.md#ag-26) | Implemented; representative tests pass | [test_agent014_operations.py](../../apps/coding-agent/tests/test_agent014_operations.py) |
| [AG-27](03-requirements.md#ag-27) | Implemented; representative tests pass | [test_agent014_operations.py](../../apps/coding-agent/tests/test_agent014_operations.py) |
| [AG-50](03-requirements.md#ag-50) | Implemented; representative tests pass | [test_agent014_operations.py](../../apps/coding-agent/tests/test_agent014_operations.py) |
| [AG-51](03-requirements.md#ag-51) | Implemented; representative tests pass | [test_agent014_trust.py](../../apps/coding-agent/tests/test_agent014_trust.py) |
| [AG-52](03-requirements.md#ag-52) | Implemented; representative tests pass | [test_agent014_operations.py](../../apps/coding-agent/tests/test_agent014_operations.py) |
| [AG-53](03-requirements.md#ag-53) | Implemented; representative tests pass | [test_agent014_operations.py](../../apps/coding-agent/tests/test_agent014_operations.py) |
| [AG-54](03-requirements.md#ag-54) | Partial | [test_agent014_trust.py](../../apps/coding-agent/tests/test_agent014_trust.py) |
| [AG-55](03-requirements.md#ag-55) | Implemented; qualification remaining | [validate_graders.py](../../exams/validate_graders.py) |
| [AG-56](03-requirements.md#ag-56) | Implemented; representative tests pass | [test_agent014_trust.py](../../apps/coding-agent/tests/test_agent014_trust.py) |
| [AG-57](03-requirements.md#ag-57) | Implemented; representative tests pass | [test_agent014_trust.py](../../apps/coding-agent/tests/test_agent014_trust.py) |
| [AG-58](03-requirements.md#ag-58) | Implemented; representative tests pass | [test_agent014_budget.py](../../apps/coding-agent/tests/test_agent014_budget.py) |
| [AG-40](03-requirements.md#ag-40) | Implemented; qualification remaining | [test_adapters.py](../../apps/coding-agent/tests/test_adapters.py) |
| [AG-41](03-requirements.md#ag-41) | Implemented; representative tests pass | [test_agent014_trust.py](../../apps/coding-agent/tests/test_agent014_trust.py) |
| [AG-42](03-requirements.md#ag-42) | Implemented; representative tests pass | [test_agent014_trust.py](../../apps/coding-agent/tests/test_agent014_trust.py) |
| [AG-43](03-requirements.md#ag-43) | Implemented; qualification remaining | [test_agent014_parity.py](../../apps/coding-agent/tests/test_agent014_parity.py) |
| [AG-44](03-requirements.md#ag-44) | Implemented; qualification remaining | [test_long_running.py](../../apps/coding-agent/tests/test_long_running.py) |
| [AG-45](03-requirements.md#ag-45) | Implemented; qualification remaining | [commands.test.ts](../../apps/coding-agent/web/src/domain/commands.test.ts) |
| [AG-46](03-requirements.md#ag-46) | Implemented; qualification remaining | [test_agent014_assets.py](../../apps/coding-agent/tests/test_agent014_assets.py) |
| [AG-47](03-requirements.md#ag-47) | Implemented; representative tests pass | [test_agent014_trust.py](../../apps/coding-agent/tests/test_agent014_trust.py) |
| [AG-60](03-requirements.md#ag-60) | Implemented; qualification remaining | [test_agent014_operations.py](../../apps/coding-agent/tests/test_agent014_operations.py) |
| [AG-61](03-requirements.md#ag-61) | Implemented; representative tests pass | [test_agent014_operations.py](../../apps/coding-agent/tests/test_agent014_operations.py) |
| [AG-62](03-requirements.md#ag-62) | Implemented; representative tests pass | [test_agent014_scale.py](../../apps/coding-agent/tests/test_agent014_scale.py) |
| [AG-63](03-requirements.md#ag-63) | Implemented; representative tests pass | [test_long_running.py](../../apps/coding-agent/tests/test_long_running.py) |
| [AG-64](03-requirements.md#ag-64) | Implemented; representative tests pass | [test_agent014_assets.py](../../apps/coding-agent/tests/test_agent014_assets.py) |
| [AG-65](03-requirements.md#ag-65) | Implemented; representative tests pass | [test_agent014_operations.py](../../apps/coding-agent/tests/test_agent014_operations.py) |
| [AG-66](03-requirements.md#ag-66) | Implemented; qualification remaining | [agent-scale-e2e.mjs](../../apps/coding-agent/web/scripts/agent-scale-e2e.mjs) |
| [AG-67](03-requirements.md#ag-67) | Implemented; representative tests pass | [test_agent014_scale.py](../../apps/coding-agent/tests/test_agent014_scale.py) |
| [AG-70](03-requirements.md#ag-70) | Implemented; qualification remaining | [test_agent014_parity.py](../../apps/coding-agent/tests/test_agent014_parity.py) |
| [AG-71](03-requirements.md#ag-71) | Implemented; qualification remaining | [test_agent014_parity.py](../../apps/coding-agent/tests/test_agent014_parity.py) |
| [AG-80](03-requirements.md#ag-80) | Implemented; qualification remaining | [sync-app-source.sh](../../apps/coding-agent/scripts/sync-app-source.sh) |
| [AG-81](03-requirements.md#ag-81) | Implemented; representative tests pass | [test_agent014_trust.py](../../apps/coding-agent/tests/test_agent014_trust.py) |
| [AG-82](03-requirements.md#ag-82) | Partial | [test_agent014_traceability.py](../../apps/coding-agent/tests/test_agent014_traceability.py) |


Latest reassessment: [17 · First-principles gap closure](17-first-principles-closure.md) supersedes the
earlier log-authentication diagnosis and records additional protocol, liveness and benchmark fixes.
