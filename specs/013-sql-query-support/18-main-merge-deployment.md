# Merged main deployment

[Specification index](README.md) · [CTE correction](17-cte-policy-correction.md) · [AI integration](16-ai-query-integration.md) · [Acceptance limits](14-implementation-outcome.md)

The SQL feature and its fixes are committed and [PR #17](https://github.com/raphaelmansuy/opengenie/pull/17) is merged. Databricks dev runs exact main commit `d2d4754e05f15dc06f41d57fdeaaa8b9ae6415e8`, deployment `01f1de70fb671ee4b550c1f685eb3a56`. The app reports `1.2.0-rc.4`. The immutable [rc.4 tag](https://github.com/raphaelmansuy/opengenie/releases/tag/v1.2.0-rc.4) still points to `717c621`; a Git diff confirms that the merged app tree is identical to that tested release tree.

The final integration commit `4aa71b7` corrects the existing public architecture/data-model documentation and code-backed count checks. The checks now include 45 tools, the 32-tool core profile and migration 005's SQL journal tables. They also verify the exact agent table inventory. No private spec or screenshot artifacts were published. The original user's working checkout and index were preserved; Git integration used the isolated release worktree.

## Validation and deployment

- App validation: 2,061 backend passes, four skips and seven warnings, including real Postgres tests; 1,233 frontend passes across 84 files; production build and 16 local SQL E2E checks passed. These results apply to the identical merged app tree.
- Integration validation: 14 public claim checks and 11 code-backed count checks, site build/link checks, no-Pillow build/check and generated-wireframe checks passed. The architecture and data-model pages passed all 12 viewport/theme combinations; the final data-model wording was rechecked in six combinations.
- Main CI: [workflow 43181131344](https://github.com/raphaelmansuy/opengenie/actions/runs/43181131344) passed build/check and publishing. All 180 browser views passed and 69 internal links resolved. [CI evidence](e2e/merge-ci-report.json).
- Deployment: the SDK verified the requested host and signed-in identity, exact active source revision and RUNNING app state. Resources and user API scopes match the pre-deployment snapshot.
- Live SQL: the warehouse began STOPPED and started on demand. The exact reported CTE returned 60 unique ordered daily rows. Reload reused the same native statement; unsupported function and mutation attempts created no execution.
- Live AI: the actual configured model inspected the table schema before editing, stated the grain, updated the attached draft and executed that source. Its terminal receipt matches the editor source hash and native statement. The original user draft's version and text are unchanged.
- Visual evidence: all seven new screenshots 50–56 were individually opened and reviewed. Earlier 49 reviewed images retain their bytes and provenance.

The input grain is one row per trip; the query groups to one row per pickup date. Results are bounded previews. Native saved-Query writes/origin execution remain gated. This delivery does not claim completion of every target requirement or arbitrary SQL/function/model correctness; see [remaining acceptance](14-implementation-outcome.md).

[Current deployment record](e2e/deployment.json) · [Eight-check main report](e2e/merge-report.json) · [Seven-image review manifest](e2e/merge-screenshots-manifest.json) · [Visual ledger](e2e/visual-inspection.md) · [Archived release deployment](e2e/releases/v1.2.0-rc.4-deployment.json)

## Repeat without replacing release evidence

```bash
CTE_REPORT=merge-report.json CTE_SCREENSHOT_OFFSET=7 \
node specs/013-sql-query-support/e2e/tools/cte-policy-smoke.mjs
python3 specs/013-sql-query-support/tools/verify_spec.py
```

The [shared harness](e2e/tools/cte-policy-smoke.mjs) accepts a report filename and screenshot offset to reuse the same checks across deployments. A reproduction input and authorized profile are required as described in the [E2E guide](e2e/README.md). Every replacement image requires a fresh individual visual review before updating its manifest.
