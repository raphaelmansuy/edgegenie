# Warehouse response transport fix

The compatible SQL deployment is running, but live draft-editor initialization fails because the shared bounded HTTP adapter decompresses warehouse JSON twice. This patch removes transport encoding headers after decoding; the decoded response size remains bounded.

- Commit: `0f63b194216f5ef0b653ed94961451d11965e877`.
- Parent: approved and deployed `345d1828d1ed158a74276b3008c09093e16fce45`.
- Public destination: [raphaelmansuy/opengenie](https://github.com/raphaelmansuy/opengenie), branch `codex/sql-query-support-dev-20261112`.
- Target: existing `coding-agent` app in dev workspace `7474647158015570` (`dbc-cb61f1e1-bd8e.cloud.databricks.com`).
- [Exact patch](transport-fix.patch); SHA-256: `f27afa62cfe95b546d97f76ca0b4529e1111f07a0cf9280b4fddd97cd8f069dd`.
- Two files: `apps/coding-agent/api/adapters/databricks/http.py` and `apps/coding-agent/tests/test_sqlquery.py`; 49 additions, 1 deletion.
- No credentials, specification documents or screenshots in this public commit.

Validation: regression reproduced before fix; 53 SQL tests pass after fix; full backend 1,936 passed, 18 skipped, 7 warnings. Previous compatible frontend (1,231 tests), production build and 16 local full-stack E2E checks remain valid because this patch changes only backend transport and its tests. Live UI validation must be repeated after deployment.

Publication pending explicit approval. The previous approval named the compatible merge commit. If approved, publish the exact fix and deploy by SHA, verify the running revision, rerun the live API/UI checks, and individually inspect all four deployed screenshots.

## Recorded outcome

The publication approval and deployment steps above are historical. The user approved publication and necessary tested dev fixes, then requested a version cut. Final [v1.2.0-rc.1](https://github.com/raphaelmansuy/opengenie/releases/tag/v1.2.0-rc.1) (`8e9e520`) is published and running in dev; 10 live checks pass and all four final live images were individually inspected. See [deployment record](deployment.json) and [visual ledger](visual-inspection.md).
