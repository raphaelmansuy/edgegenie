# Compatible dev deployment payload

Target: existing `coding-agent` app in workspace `7474647158015570` at `https://dbc-cb61f1e1-bd8e.cloud.databricks.com`.

The first SQL deployment was incompatible with newer persisted sessions. The previous working deployment was restored and verified RUNNING. The new merge preserves the current public main baseline, including `write_mode`/session recovery and infrastructure views.

## Exact public payload

- New commit: `345d1828d1ed158a74276b3008c09093e16fce45`.
- Branch: `codex/sql-query-support-dev-20261112`.
- Public destination: [raphaelmansuy/opengenie](https://github.com/raphaelmansuy/opengenie).
- Parents: previously approved/published SQL commit `9c6d7d0e20d8794ad7c31035740e16e982857de5` and current public main `dd98164b3148753c54463128d99ba263d6bab8d5`.
- [Exact app delta from public main](compatible-deployment.patch).
- Patch SHA-256: `d1058432541c6360ebcf21824e69ccacfab3a3990aa44590f094cbad4f5993b4`.
- App files differing from current main: 58.
- Includes conflict resolutions for SQL routes, attachment kinds, shared tabs/palette, composer/assistant and deployment tooling. No credentials, new specification documents or local screenshots are added to the public branch.

## Validation

- Backend: 1,934 passed, 18 skipped.
- Frontend: 1,231 passed across 83 files.
- TypeScript/Vite production build passed.
- Local full-stack SQL E2E: 16 checks passed.
- Diff against current public main passes whitespace checks. Upstream-only EOF whitespace in three existing files was left unchanged.
- Original user working tree and index are preserved; integration is isolated in the deployment worktree.

## Files differing from current public main

| App file | Added lines | Removed lines |
|---|---|---|
| `apps/coding-agent/api/adapters/databricks/http.py` | 15 | 4 |
| `apps/coding-agent/api/adapters/databricks/queries.py` | 255 | 0 |
| `apps/coding-agent/api/adapters/durable/query_sqlite.py` | 197 | 0 |
| `apps/coding-agent/api/adapters/fake/scenarios/sqlquery.json` | 8 | 0 |
| `apps/coding-agent/api/config.py` | 5 | 0 |
| `apps/coding-agent/api/domain/context.py` | 8 | 2 |
| `apps/coding-agent/api/domain/sqlpolicy.py` | 149 | 0 |
| `apps/coding-agent/api/domain/sqlquery.py` | 90 | 0 |
| `apps/coding-agent/api/main.py` | 15 | 0 |
| `apps/coding-agent/api/routers/api.py` | 3 | 1 |
| `apps/coding-agent/api/routers/sql.py` | 223 | 0 |
| `apps/coding-agent/api/services/context.py` | 8 | 3 |
| `apps/coding-agent/api/services/sql_service.py` | 341 | 0 |
| `apps/coding-agent/pyproject.toml` | 13 | 0 |
| `apps/coding-agent/requirements.txt` | 1 | 0 |
| `apps/coding-agent/scripts/sync-app-source.sh` | 11 | 6 |
| `apps/coding-agent/tests/test_sqlquery.py` | 432 | 0 |
| `apps/coding-agent/web/package.json` | 25 | 22 |
| `apps/coding-agent/web/scripts/dock-focus-e2e.mjs` | 182 | 0 |
| `apps/coding-agent/web/scripts/dock-matrix.mjs` | 92 | 0 |
| `apps/coding-agent/web/scripts/mission-test-server.mjs` | 1 | 1 |
| `apps/coding-agent/web/scripts/sql-query-e2e.mjs` | 170 | 0 |
| `apps/coding-agent/web/src/App.tsx` | 94 | 28 |
| `apps/coding-agent/web/src/api/client.ts` | 1 | 1 |
| `apps/coding-agent/web/src/api/queries.ts` | 18 | 0 |
| `apps/coding-agent/web/src/components/AssetIcon.tsx` | 7 | 0 |
| `apps/coding-agent/web/src/components/AssistantDock.tsx` | 19 | 24 |
| `apps/coding-agent/web/src/components/Chip.tsx` | 2 | 4 |
| `apps/coding-agent/web/src/components/Chrome.tsx` | 7 | 1 |
| `apps/coding-agent/web/src/components/Composer.tsx` | 4 | 6 |
| `apps/coding-agent/web/src/components/DocContext.ts` | 3 | 0 |
| `apps/coding-agent/web/src/components/DocTabs.tsx` | 4 | 3 |
| `apps/coding-agent/web/src/components/Markdown.tsx` | 3 | 1 |
| `apps/coding-agent/web/src/components/QueryEditor.tsx` | 133 | 0 |
| `apps/coding-agent/web/src/components/QueryLibrary.tsx` | 40 | 0 |
| `apps/coding-agent/web/src/components/QuerySaveDialog.tsx` | 22 | 0 |
| `apps/coding-agent/web/src/components/SqlResults.tsx` | 58 | 0 |
| `apps/coding-agent/web/src/domain/apierror.ts` | 2 | 0 |
| `apps/coding-agent/web/src/domain/dock.ts` | 5 | 0 |
| `apps/coding-agent/web/src/domain/docs.ts` | 5 | 3 |
| `apps/coding-agent/web/src/domain/events.ts` | 1 | 1 |
| `apps/coding-agent/web/src/domain/follow.test.ts` | 74 | 0 |
| `apps/coding-agent/web/src/domain/follow.ts` | 65 | 0 |
| `apps/coding-agent/web/src/domain/kinds.test.ts` | 7 | 5 |
| `apps/coding-agent/web/src/domain/links.ts` | 3 | 1 |
| `apps/coding-agent/web/src/domain/panels.test.ts` | 113 | 0 |
| `apps/coding-agent/web/src/domain/panels.ts` | 76 | 0 |
| `apps/coding-agent/web/src/domain/query.test.ts` | 58 | 0 |
| `apps/coding-agent/web/src/domain/query.ts` | 90 | 0 |
| `apps/coding-agent/web/src/domain/recent.ts` | 15 | 16 |
| `apps/coding-agent/web/src/domain/route.ts` | 6 | 1 |
| `apps/coding-agent/web/src/domain/workingset.ts` | 2 | 2 |
| `apps/coding-agent/web/src/editor/Editor.tsx` | 3 | 0 |
| `apps/coding-agent/web/src/editor/codemirror.ts` | 2 | 0 |
| `apps/coding-agent/web/src/editor/host.ts` | 2 | 0 |
| `apps/coding-agent/web/src/hooks/useFollowScroll.ts` | 108 | 0 |
| `apps/coding-agent/web/src/sql.css` | 92 | 0 |
| `apps/coding-agent/web/src/styles.css` | 16 | 1 |

Automatic approval review requires explicit approval to publish this exact new commit; the prior consent named the original commit. After approval, push the compatible commit, deploy it by exact Git SHA, then run live API/UI smoke tests and inspect deployed screenshots.

## Recorded outcome

The publication approval and deployment steps above are historical. The user approved publication and necessary tested dev fixes, then requested a version cut. Final [v1.2.0-rc.1](https://github.com/raphaelmansuy/opengenie/releases/tag/v1.2.0-rc.1) (`8e9e520`) is published and running in dev; 10 live checks pass and all four final live images were individually inspected. See [deployment record](deployment.json) and [visual ledger](visual-inspection.md).
