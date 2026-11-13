# Specification validation record

[Index](README.md) · [Grounding](02-code-grounding.md) · [Implementation plan](10-implementation-plan.md) · [Planned product tests](11-test-e2e-plan.md)

## Scope of this record

The original checks below cover specification authoring on 2026-11-12. Subsequent product implementation/testing is recorded separately in [14](14-implementation-outcome.md) and the [E2E evidence](e2e/README.md). Native workspace verification and measured performance qualification remain outstanding.

Sources reviewed: official Databricks pages linked in [the evidence ledger](01-databricks-assessment.md), supplied screenshots, repository files/regions stated in [the code audit](02-code-grounding.md), and existing documentation validation scripts. Search snippets were checked against directly opened current pages.

## Checks

| Check | Result |
|---|---|
| Document graph | 15 Markdown documents; 153 internal links resolve, including code-file and screenshot references. |
| Mermaid syntax | All 8 diagrams parse using the repository validator and an already available Mermaid runtime. Includes architecture, ER, two sequences, three state charts and delivery dependencies. |
| ASCII layout | All 5 navigation/screen grids contain ASCII only and have consistent widths, aligned dividers and matching borders. |
| Requirement traceability | All 24 SQ requirements map to planned scenarios. |
| Edge traceability | All 64 EC rows reference valid scenarios among T01–T18. This verifies references, not execution of those tests. |
| Pastel styling | All 8 Mermaid blocks include explicit theme variables; dark text and labeled states accompany pastel fills. |
| Reference preservation | Two supplied screenshots copied unchanged into `assets/`; they remain untrusted UI references. |
| Working-tree whitespace | `git diff --check` passed; the spec-specific checker additionally checks new untracked Markdown whitespace. |

Reproduce from the repository root:

```bash
python3 specs/013-sql-query-support/tools/verify_spec.py
node apps/coding-agent/web/scripts/verify-spec-links.mjs specs/013-sql-query-support
JSDOM_PATH=/private/tmp/mmd/node_modules/jsdom/lib/api.js \
MERMAID_PATH=/private/tmp/mmd/node_modules/mermaid/dist/mermaid.core.mjs \
node apps/coding-agent/web/scripts/verify-spec-mermaid.mjs specs/013-sql-query-support
git diff --check
```

The temporary runtime paths above existed in this session and are not portable project dependencies. Use an already available compatible Mermaid/jsdom runtime and adjust those paths in another environment. No package installation was performed for the original documentation checks. SQLGlot was subsequently installed in the project environment for implementation tests. The custom checker validates simple ASCII `+---+` grids because the existing repository ASCII checker validates Unicode box-drawing grids.

One sequence note initially used a semicolon that Mermaid interpreted as a statement separator; it was corrected and all diagrams then passed. A wireframe generation width assertion was also corrected before file output. Final consistency review clarified cache eviction/search scope, draft-head versus immutable-snapshot grain, source-history index ordering and externally canceled run transitions.

Mermaid validation is parser validation; diagrams were not browser-rendered or visually tested. ASCII geometry was mechanically checked. These original documentation checks alone establish no product behavior. Subsequent product tests are reported in [14](14-implementation-outcome.md); performance targets and live Databricks interoperability remain unverified.

## Limitations

- Databricks identity/warehouse/server tools were not exposed in this session; no workspace or warehouse was assumed from screenshots or environment.
- Native create/update semantics and effective permissions lookup still need live qualification. Parser selection and local full-stack E2E now have implementation evidence in [14](14-implementation-outcome.md).
- The code audit explicitly scopes partial reads. No claims are made about unread notebook content or live data.
- Existing unrelated working-tree changes were preserved. Product code and dependency manifests were subsequently edited under the user’s implementation instruction.


## Implementation follow-up validation

After implementation, the root document graph has 16 Markdown files and 212 resolving internal links. Including the nested E2E overview and visual ledger, all 18 Markdown files and 244 internal links resolve. All eight pastel Mermaid blocks still parse; all five ASCII grids still align. The checker validates 24 requirement references and 64 edge references against the 18 target scenarios.

The evidence checker now verifies that all 18 screenshot files match the hashes in the manual inspection manifest and that the browser report records 16 passing checks without runtime errors. A hash match validates evidence consistency; it does not perform visual review. The images were separately opened and inspected as recorded in the ledger. Final functional reruns can retain those image bytes explicitly rather than replace reviewed evidence.

Product checks, actual implementation scope, native gates and unimplemented target clauses are recorded in document 14. The original documentation-only observations above remain historical, rather than claims that implementation has not happened.

## Versioned dev follow-up

[v1.2.0-rc.1](https://github.com/raphaelmansuy/opengenie/releases/tag/v1.2.0-rc.1) was published and deployed to the verified dev workspace. Identity, warehouse inventory and native Query metadata reads now have live evidence; native create/update/run interoperability and performance qualification remain open. All eight Mermaid diagrams parse, all five ASCII grids align, and the 24-requirement/64-edge planned traceability checks pass. The checker also verifies the 18 local and four live screenshot hashes, manual review flags, and final live source/deployment agreement. Actual test results and remaining target gaps are in [14](14-implementation-outcome.md), not inferred from documentation checks.

Final link validation: 16 root documents with 224 internal links and seven E2E documents with 65 internal links; zero link problems in either group.

## SQL-enabled rc.2 validation

[Release qualification](15-sql-enabled-release.md) records 1,959 backend passes (4 skips) with real Postgres suites, 1,231 frontend passes, 16 local and 17 native E2E checks. Screenshot validation now covers 18 local, four historical rc.1 and eleven current rc.2 reviewed images. Actual cold serverless start and app-replacement recovery are verified; the remaining release gates remain explicit.

Final rc.2 link checks: 17 root documents / 258 internal links and eight E2E documents / 88 internal links, zero problems. Five ASCII grids and all eight themed Mermaid blocks remain valid. All 33 screenshot hashes match individual review records.

## AI query integration rc.3 validation

[Assessment and evaluation](16-ai-query-integration.md) records 1,994 backend passes / 4 skips / 7 warnings with real local Postgres enabled, 1,233 frontend passes, production build, 16 local SQL E2E checks and seven live checks over four actual-model missions. A full backend iteration hit an intermittent existing kernel stdout-capture failure; the 70-test query/kernel serial recheck passed without weakening the test, then the full suite passed. The final authoritative-receipt guard additionally passed all 35 query-agent contract cases.

The document graph now includes six aligned ASCII screens/navigation grids and ten parsing pastel Mermaid diagrams. The evidence validator checks current rc.3 source/deployment agreement plus all nine individually reviewed image hashes; historical rc.2 and rc.1 evidence retains its separate provenance. All 42 numbered screenshot files have individual review records. These results qualify the stated workflow, not every target edge or arbitrary model interpretation.

Final rc.3 documentation checks: 18 root Markdown documents / 288 resolving internal links; nine E2E documents / 109 resolving internal links; zero link problems. All ten Mermaid diagrams parse, six ASCII grids align, 24 requirements and 64 edges retain planned traceability, and all 42 reviewed image hashes agree with their manifests. Release tag, published prerelease and active dev deployment resolve to `7f104c7`. The task-owned local test database server was stopped after validation; its files were retained.

## CTE policy correction rc.4 validation

[Explanation and scope](17-cte-policy-correction.md) records 2,061 backend passes / 4 skips / 7 warnings (67 new policy cases), 1,233 frontend passes, build success, 16 local browser checks and eight authenticated native/actual-model CTE checks. Initial local Postgres socket configuration was corrected to use the verified task-owned TCP endpoint. The existing intermittent notebook stdout-capture case passed in isolation and in the final full suite without test changes. Seven new screenshot files were individually opened; their hashes and actual source/deployment IDs are pinned in [the manifest](e2e/cte-screenshots-manifest.json). The original user draft remained unchanged, and phone panning reached the last result column without resubmission. Historical rc.3 evidence now resolves to its archived deployment record.

Final rc.4 consistency checks: 19 root Markdown documents / 314 resolving internal links and ten E2E documents / 128 resolving links, zero link problems. Six ASCII grids align and all eleven pastel Mermaid diagrams parse. All 49 retained numbered screenshots match individual-review manifests. The release tag, published prerelease and active dev deployment agree on `717c621`. The task-owned test database server was stopped with its files retained.
