# Dev deployment payload ready for review

Target: `https://dbc-cb61f1e1-bd8e.cloud.databricks.com`, workspace `7474647158015570`, existing app `coding-agent`. Identity and workspace were verified through the authenticated `opengenie-dev` CLI profile. The only SQL warehouse is stopped; no SQL statement was submitted.

The workspace rejected folder-based deployment because Apps here must deploy from Git. The existing app points to the **public** repository [raphaelmansuy/opengenie](https://github.com/raphaelmansuy/opengenie). Publishing the prepared source therefore needs explicit approval. No Git push or app replacement has happened.

## Prepared immutable payload

- Branch: `codex/sql-query-support-dev-20261112`
- Commit: `9c6d7d0e20d8794ad7c31035740e16e982857de5`
- Changed files: 58, all under `apps/coding-agent/`.
- [Exact patch](deployment.patch), SHA-256 `4207af744aedeab09aebf27625a783374d24c3050827ae90adbce5afc7296681`.
- Includes SQL support and the current app/panel/packaging changes required by the tested checkout.
- Excludes the new specification documents, screenshots, local environment files, credentials, node_modules and virtual environments.
- The original working tree and index remain unchanged; the commit lives in a separate deployment worktree.
- A limited scan of added lines found 0 private-key/credential-token pattern matches. This is a limited check, not a guarantee that all information is appropriate to publish.

## Changed file manifest

| File | Added lines | Removed lines |
|---|---|---|
| `apps/coding-agent/Makefile` | 2 | 2 |
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
| `apps/coding-agent/web/package.json` | 3 | 0 |
| `apps/coding-agent/web/scripts/dock-focus-e2e.mjs` | 182 | 0 |
| `apps/coding-agent/web/scripts/dock-matrix.mjs` | 92 | 0 |
| `apps/coding-agent/web/scripts/mission-test-server.mjs` | 1 | 1 |
| `apps/coding-agent/web/scripts/sql-query-e2e.mjs` | 170 | 0 |
| `apps/coding-agent/web/src/App.tsx` | 95 | 25 |
| `apps/coding-agent/web/src/api/client.ts` | 1 | 1 |
| `apps/coding-agent/web/src/api/queries.ts` | 18 | 0 |
| `apps/coding-agent/web/src/components/AssetIcon.tsx` | 7 | 0 |
| `apps/coding-agent/web/src/components/AssistantDock.tsx` | 19 | 20 |
| `apps/coding-agent/web/src/components/Chip.tsx` | 2 | 4 |
| `apps/coding-agent/web/src/components/Chrome.tsx` | 9 | 3 |
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
| `apps/coding-agent/web/src/domain/docs.ts` | 3 | 1 |
| `apps/coding-agent/web/src/domain/events.ts` | 1 | 1 |
| `apps/coding-agent/web/src/domain/follow.test.ts` | 74 | 0 |
| `apps/coding-agent/web/src/domain/follow.ts` | 65 | 0 |
| `apps/coding-agent/web/src/domain/links.ts` | 3 | 1 |
| `apps/coding-agent/web/src/domain/panels.test.ts` | 113 | 0 |
| `apps/coding-agent/web/src/domain/panels.ts` | 76 | 0 |
| `apps/coding-agent/web/src/domain/query.test.ts` | 58 | 0 |
| `apps/coding-agent/web/src/domain/query.ts` | 90 | 0 |
| `apps/coding-agent/web/src/domain/recent.ts` | 16 | 15 |
| `apps/coding-agent/web/src/domain/route.ts` | 6 | 1 |
| `apps/coding-agent/web/src/domain/workingset.ts` | 2 | 2 |
| `apps/coding-agent/web/src/editor/Editor.tsx` | 3 | 0 |
| `apps/coding-agent/web/src/editor/codemirror.ts` | 2 | 0 |
| `apps/coding-agent/web/src/editor/host.ts` | 2 | 0 |
| `apps/coding-agent/web/src/hooks/useFollowScroll.ts` | 108 | 0 |
| `apps/coding-agent/web/src/sql.css` | 92 | 0 |
| `apps/coding-agent/web/src/styles.css` | 16 | 1 |

## Current deployment

The running dev app is still the prior deployment `01f1de3ebf311f5fb5c4c1728004ff38`. Authenticated health and identity probes return HTTP 200. The new source was uploaded to a fresh workspace folder and 11 key source files were compared byte-for-byte, but that folder was not activated. No app scopes, resources, warehouse state or existing notebooks were changed.

After public-push approval, push this exact commit, deploy its Git commit through the supported Apps deployment API, wait for SUCCEEDED and verify the live SQL API and UI. Save and visually inspect any additional deployed screenshots before claiming deployed E2E success.

## Recorded outcome

The publication approval and deployment steps above are historical. The user approved publication and necessary tested dev fixes, then requested a version cut. Final [v1.2.0-rc.1](https://github.com/raphaelmansuy/opengenie/releases/tag/v1.2.0-rc.1) (`8e9e520`) is published and running in dev; 10 live checks pass and all four final live images were individually inspected. See [deployment record](deployment.json) and [visual ledger](visual-inspection.md).
