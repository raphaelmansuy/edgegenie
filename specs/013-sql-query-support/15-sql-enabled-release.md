# SQL execution enabled in dev

[Index](README.md) · [First principles](00-five-whys-first-principles.md) · [Architecture](05-architecture-api.md) · [Persistence](06-data-persistence.md) · [State charts](07-sequences-statecharts.md) · [Edge cases](09-edge-cases.md) · [Outcome](14-implementation-outcome.md) · [Payload review](e2e/sql-enabled-release-review.md)

This document records the rc.2 execution/persistence foundation. Subsequent AI follow-up: [rc.3 assessment](16-ai-query-integration.md); current [rc.4 CTE correction](17-cte-policy-correction.md) and [deployment record](e2e/deployment.json). The rc.2 deployment is [archived](e2e/releases/v1.2.0-rc.2-deployment.json).

## Why this release changes the previous boundary

The five-whys chain remains the basis of the feature: SQL needs an identity; a run needs its exact input and statement handle; reconnect must recover that handle; recovery requires persistent intent; reusing the existing Lakebase coordinator gives SQL that persistence without another authentication or connection lifecycle.

`v1.2.0-rc.2` enables independent SQL drafts to execute one validated read-only statement as the signed-in user. A stopped serverless warehouse is selectable and Run stays enabled. Submission uses the Statement Execution API with `wait_timeout=0s`; Databricks starts compute on demand, while the existing run state machine shows pending/running/terminal states. There is no manual warehouse start/stop call and no change to auto-stop settings. [Databricks warehouse behavior](https://docs.databricks.com/aws/en/compute/sql-warehouse), [Statement Execution API](https://docs.databricks.com/api/statement-execution/v1/execute-statement).

## Code and storage contract

Exact source: commit `fe4e1109a18495a1bcb0e58908655c1dea3ed908`, public branch `codex/sql-query-support-dev-20261112`.

| Responsibility | Implementation |
|---|---|
| Shared connection lifecycle | [Postgres coordinator](https://github.com/raphaelmansuy/opengenie/blob/fe4e1109a18495a1bcb0e58908655c1dea3ed908/apps/coding-agent/api/adapters/durable/postgres.py): public injected operation runner retains caller-cancellation shielding, reconnect, read-only retry and single-active-server ownership. SQL does not open a second connection or mint a second token. |
| SQL persistence | [PostgresQueryStore](https://github.com/raphaelmansuy/opengenie/blob/fe4e1109a18495a1bcb0e58908655c1dea3ed908/apps/coding-agent/api/adapters/durable/query_postgres.py): owner-scoped encrypted drafts, runs and operation reservations. Row encryption authenticates scope/kind/id. A stable SQL-specific key is derived from the existing deployment KEK, or an explicit SQL key is used; keys and tokens are not stored in the database. |
| Atomicity and bounds | Reservation and CAS writes use a database transaction and a transaction advisory lock. Existing limits remain four active runs per user, 32 globally and one unresolved run per source. Active metadata reads are capped at 33; recent history at 50. Input/output bounds remain unchanged. |
| DRY policy | [Shared domain policy](https://github.com/raphaelmansuy/opengenie/blob/fe4e1109a18495a1bcb0e58908655c1dea3ed908/apps/coding-agent/api/domain/sqlquery.py) owns operation-key conflicts/expiry and run-capacity rules for both SQLite and Postgres adapters. |
| Migration | Additive `005_sql_journal.sql` goes through the existing migration runner. One row per scoped asset/run identity in `agent.sql_item`; one row per scoped operation key in `agent.sql_operation`. SQL/source bodies are encrypted; indexed identity/state metadata is separate. |
| UI | The stopped warehouse has a neutral status dot and visible “Starts on demand” hint. Warehouse metadata refreshes as run state changes. Existing editor, results, themes and document navigation are reused. |
| Deployment | `APP_SQL_RUN=true` in the app configuration. Lakebase session deployments select the Postgres SQL store when a recovery key is available. Missing key with requested native execution fails closed. Existing identity scopes and resource bindings are preserved. |

The run service, typed parameters, provider protocol, native user-token transport, polling, cancellation, immutable source snapshots and assistant context remain the same components specified in [05](05-architecture-api.md) and [07](07-sequences-statecharts.md). No parallel SQL execution path was introduced.

## Evidence and release gates

- Full backend: 1,959 passed, 4 skipped, 7 warnings; real isolated Postgres migration, journal reconnection, SQL CAS/encryption/isolation/concurrency/restart tests enabled. [Contract tests](https://github.com/raphaelmansuy/opengenie/blob/fe4e1109a18495a1bcb0e58908655c1dea3ed908/apps/coding-agent/tests/test_sqlquery_postgres.py).
- Frontend: 1,231 tests passed; production build passed; 16 local full-stack E2E checks passed on the release source.
- Live native execution: a stopped serverless warehouse returned `1` for `SELECT 1`; typed binding and NULL, multistatement refusal, native cancellation, browser reload and own history passed. All executed SQL was table-free and read-only; no Unity Catalog data table or native Query asset was modified.
- The mobile Results button gains a checkmark after success. The live harness selector was corrected to match the scoped Results prefix, and remaining assertions were repeated without another SQL submission. This test-harness correction did not require an app change.
- [Live machine report](e2e/deployed-report.json), [deployment record](e2e/deployment.json) and [visual ledger](e2e/visual-inspection.md) record final restart/release qualification and image provenance.

Native saved-Query-origin execution still requires verified effective Query permissions. Native Query creation/update remain disabled. Broader UC fixtures, auth-expiry, additional result chunks, physical retention purge and full accessibility qualification remain in the [target checkpoint](14-implementation-outcome.md#requirement-checkpoint-against-the-full-target).

## Operation and rollback

The existing deployment KEK must remain stable across restarts; back it up according to the app’s secret/backup procedure. Key rotation must retain decryptability of existing encrypted rows. SQL source is never decrypted by a database query and external SQL always runs with the signed-in user's token.

After migration 005, rollback uses schema-5-compatible code with SQL execution disabled. The existing schema-ahead guard intentionally refuses older schema-4 builds; do not bypass it or delete migration records. No migration rollback or existing data deletion is part of this release.

Published [v1.2.0-rc.2](https://github.com/raphaelmansuy/opengenie/releases/tag/v1.2.0-rc.2) and verified 17 live checks, including actual server replacement recovery. All eleven new deployed screenshots were individually inspected; all 33 retained images remain hash-linked to their review records.
