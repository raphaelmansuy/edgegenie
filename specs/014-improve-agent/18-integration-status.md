# Integration and deployment status — 2026-11-13

The implementation checkpoint is commit `1f1d86b`. It was developed from
`824158d`, while upstream main is now `d2d4754e05f15dc06f41d57fdeaaa8b9ae6415e8` (44 additional commits).

## Merge qualification

A normal three-way merge was attempted without committing. It produced 50
conflicted paths, listed below. The attempt was then aborted, leaving the
implementation commit intact. No upstream commits were discarded and main was
not changed.

This is a semantic integration task, not just a conflict-marker cleanup. For
example, upstream `api/main.py` wires kernels, SQL runs, infrastructure browsers,
and jobs/pipelines routers absent from the implementation checkpoint's composition.
It also provides the app service principal to the agent, while this specification
requires a qualified execution identity and otherwise refuses that route.
The merged implementation must preserve the upstream product surfaces while
retaining the new agent identity boundary, then rerun both test suites and browser
flows. This qualification has **not** been completed. Prior local E2E and screenshot
results describe the implementation checkpoint, not an integrated main build.

## Deployment preflight

The Databricks CLI authenticated as `raphael.mansuy@gmail.com` (user
`78760067054768`) against the requested workspace. The required MCP identity and
warehouse tools were unavailable, so the CLI was used. Warehouse
`50b601f08d1a858d` (`Serverless Starter Warehouse`) reports `STOPPED`.

The target `coding-agent` reports:

- Compute: `STOPPED`
- Compute message: “App compute was stopped due to workspace or account status.”
- App: `UNAVAILABLE`
- Active deployment: none

No workspace source upload, deployment, account change, or permission change was
performed. Deployment remains pending both a qualified merge and restored platform
availability. The optional phase flags remain at their existing defaults.

## Conflicted paths

```text
.gitignore
apps/coding-agent/Makefile
apps/coding-agent/api/adapters/acp/agent_config.py
apps/coding-agent/api/adapters/acp/mapper.py
apps/coding-agent/api/adapters/databricks/catalog.py
apps/coding-agent/api/adapters/databricks/http.py
apps/coding-agent/api/adapters/databricks/queries.py
apps/coding-agent/api/adapters/durable/postgres.py
apps/coding-agent/api/adapters/durable/query_sqlite.py
apps/coding-agent/api/adapters/durable/sqlite.py
apps/coding-agent/api/adapters/mcp/registry.py
apps/coding-agent/api/adapters/memory/store.py
apps/coding-agent/api/domain/context.py
apps/coding-agent/api/domain/events.py
apps/coding-agent/api/domain/scope.py
apps/coding-agent/api/domain/sqlpolicy.py
apps/coding-agent/api/domain/sqlquery.py
apps/coding-agent/api/domain/supervisor.py
apps/coding-agent/api/main.py
apps/coding-agent/api/routers/api.py
apps/coding-agent/api/routers/sql.py
apps/coding-agent/api/services/blobs.py
apps/coding-agent/api/services/context.py
apps/coding-agent/api/services/orchestrator.py
apps/coding-agent/api/services/run_bridge.py
apps/coding-agent/api/services/sql_service.py
apps/coding-agent/scripts/verify-deployed.sh
apps/coding-agent/tests/test_sqlquery.py
apps/coding-agent/tools/databricks_notebook_mcp.py
apps/coding-agent/tools/skills/databricks-apps.md
apps/coding-agent/tools/skills/lakebase-postgres.md
apps/coding-agent/web/package.json
apps/coding-agent/web/scripts/sql-query-e2e.mjs
apps/coding-agent/web/src/App.tsx
apps/coding-agent/web/src/api/client.ts
apps/coding-agent/web/src/components/AssistantDock.tsx
apps/coding-agent/web/src/components/Chrome.tsx
apps/coding-agent/web/src/components/Composer.tsx
apps/coding-agent/web/src/components/QueryEditor.tsx
apps/coding-agent/web/src/domain/docs.ts
apps/coding-agent/web/src/domain/event-parity.json
apps/coding-agent/web/src/domain/events.ts
apps/coding-agent/web/src/domain/links.ts
apps/coding-agent/web/src/domain/query.ts
apps/coding-agent/web/src/domain/recent.ts
apps/coding-agent/web/src/domain/route.ts
apps/coding-agent/web/src/domain/workingset.ts
apps/coding-agent/web/src/sql.css
apps/coding-agent/web/src/styles.css
mcp/databricks_notebook_mcp.py
```
