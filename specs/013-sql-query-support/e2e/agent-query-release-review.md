# AI query integration release review

Final app revision: `7f104c78d859f42a8ef0ab764fc4adf1907e89fe`, version 1.2.0-rc.3. Scope: 31 app code/config/test files. Public push and necessary tested dev fixes are authorized in this conversation. Credentials, documents, screenshots, node_modules and unrelated user changes are excluded.

Validation: 1,994 backend tests passed (4 skipped), 1,233 frontend tests passed, production build passed, 16 local SQL E2E checks passed. Actual-model qualification is recorded separately in [AI report](agent-report.json). Final refinements reconcile pending submissions with matching authoritative terminal observations, preserve SQL notifications during delayed session hydration and avoid treating an honored prohibition as missing positive tool evidence.

Exact payload relative to deployed rc.2: [patch](agent-query-release.patch). SHA-256: `5b78e09b6d821cd86e009c8fc89ce2b8df5b6b7a08ef3b7b42c74929e5b4b8a2`. Added-line credential-pattern scan: no matches.

- `apps/coding-agent/VERSION`
- `apps/coding-agent/api/adapters/acp/agent_config.py`
- `apps/coding-agent/api/adapters/acp/mapper.py`
- `apps/coding-agent/api/domain/events.py`
- `apps/coding-agent/api/domain/evidence.py`
- `apps/coding-agent/api/domain/evidence_map.py`
- `apps/coding-agent/api/domain/query_intent.py`
- `apps/coding-agent/api/domain/supervisor.py`
- `apps/coding-agent/api/main.py`
- `apps/coding-agent/api/routers/sql.py`
- `apps/coding-agent/api/routers/sql_agent.py`
- `apps/coding-agent/api/services/context.py`
- `apps/coding-agent/api/services/orchestrator.py`
- `apps/coding-agent/api/services/run_bridge.py`
- `apps/coding-agent/pyproject.toml`
- `apps/coding-agent/tests/test_sql_agent.py`
- `apps/coding-agent/tests/test_tools_fence.py`
- `apps/coding-agent/tests/test_version.py`
- `apps/coding-agent/tools/databricks_notebook_mcp.py`
- `apps/coding-agent/tools/skills/sql-queries.md`
- `apps/coding-agent/web/package-lock.json`
- `apps/coding-agent/web/package.json`
- `apps/coding-agent/web/src/App.tsx`
- `apps/coding-agent/web/src/components/QueryEditor.tsx`
- `apps/coding-agent/web/src/domain/event-parity.json`
- `apps/coding-agent/web/src/domain/events.ts`
- `apps/coding-agent/web/src/domain/query-agent.test.ts`
- `apps/coding-agent/web/src/domain/query.ts`
- `apps/coding-agent/web/src/hooks/useSessionStream.test.ts`
- `apps/coding-agent/web/src/hooks/useSessionStream.ts`
- `apps/coding-agent/web/src/sql.css`
