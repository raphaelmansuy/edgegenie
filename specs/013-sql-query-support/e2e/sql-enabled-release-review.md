# Execution-enabled SQL dev release

Version `1.2.0-rc.2`, commit `fe4e1109a18495a1bcb0e58908655c1dea3ed908`, public dev branch `codex/sql-query-support-dev-20261112`.

The user requested a new deployed release that allows SQL. Prior approval also permits necessary tested app fixes on this branch. This patch adds encrypted SQL persistence over the existing cancellation-safe Lakebase coordinator, one additive migration, shared reservation policy, an on-demand warehouse hint/status refresh, execution configuration and matching version metadata. Native SQL statements use the signed-in user’s token; the app identity handles only its private encrypted journal.

- [Exact patch](sql-enabled-release.patch), SHA-256 `06f903fd00858d53742deb0df9725860fe6ae17dd63a78adb9525296f3c0e8f0`.
- Backend: 1,959 passed, 4 skipped, 7 warnings with real isolated Postgres migration/recovery tests enabled.
- Frontend: 1,231 passed; production build passed; all 16 local full-stack E2E checks passed.
- No credentials, documents, screenshots or unrelated files are in the public commit.
- Native Query creation/update and saved-Query-origin execution remain gated. Independent drafts execute a single validated read-only statement, bounded to 1,000 preview rows.
- Migration 005 is additive and uses the existing runner. Its schema-version guard means rollback must use schema-5-compatible code with SQL execution disabled; deploying schema-4 code after migration is intentionally refused.
- Publish the version tag/prerelease after real dev execution, restart recovery and visual review.

## App files

- `apps/coding-agent/VERSION`
- `apps/coding-agent/api/adapters/durable/postgres.py`
- `apps/coding-agent/api/adapters/durable/query_postgres.py`
- `apps/coding-agent/api/adapters/durable/query_sqlite.py`
- `apps/coding-agent/api/adapters/llm/store/migrate.py`
- `apps/coding-agent/api/adapters/llm/store/migrations/005_sql_journal.sql`
- `apps/coding-agent/api/domain/sqlquery.py`
- `apps/coding-agent/api/main.py`
- `apps/coding-agent/app.yaml`
- `apps/coding-agent/pyproject.toml`
- `apps/coding-agent/tests/test_sqlquery_postgres.py`
- `apps/coding-agent/tests/test_version.py`
- `apps/coding-agent/web/package-lock.json`
- `apps/coding-agent/web/package.json`
- `apps/coding-agent/web/src/components/QueryEditor.tsx`

## Recorded outcome

[Version v1.2.0-rc.2](https://github.com/raphaelmansuy/opengenie/releases/tag/v1.2.0-rc.2) is published. Exact commit `fe4e110` is running in dev after an identical-source replacement. All 17 native checks pass; stopped-warehouse startup, Canceled, browser reload and server-restart recovery were observed. All eleven new deployed screenshots were individually inspected. Existing scopes/resources are preserved.
