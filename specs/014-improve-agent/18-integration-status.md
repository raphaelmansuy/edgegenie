# Integration and deployment status — 2026-11-14

The 50 upstream conflicts recorded on 13 November are resolved. The integrated branch includes
upstream main `d2d4754e05f15dc06f41d57fdeaaa8b9ae6415e8` and preserves its SQL editor, notebook
sessions, jobs/pipelines, Lakebase/App browsers and deployment environment selection. The spec 014
facade, approval fence, durable work ledger and user identity boundary remain authoritative.

## Gaps closed during integration

- Repaired route composition, public compaction wiring, SQL draft event delivery and editor conflict
  preservation. Centralized the legacy tool catalogue; asynchronous wrappers enforce the same mode
  gate. Agent mutations cannot escape into the human SQL execution bridge.
- Preserved exclusive Postgres writer ownership, added bounded independent recovery reads, and made
  journal/normalized ledger/receipt updates transactional. Migration 006 upgrades the existing v5 SQL
  journal without losing its encrypted rows. Browser recovery exposed and fixed session pagination
  and import errors. Startup failure now releases child processes and credentials.
- Kept streaming deltas on one bounded coalescer with constant-size append operations. Historical
  transcript and result pages stay bounded; 200-turn fixture recovery is covered without claiming
  200 real-model turns.
- Restored upstream infrastructure styling. Retained failed screenshots and reran jobs, work and
  asset screens after the correction. Preserved pending native outcomes across recovery rather than
  inventing success or replaying mutations.
- Removed inherited app service-principal agent execution. Personal/workspace AGENTS instructions
  use bounded reads under the signed-in user; they cannot override the write fence.
- Corrected deployment CLI arguments for the qualified client and pinned Git deployments to the
  resolved remote commit. Compute preflight only starts the selected app. Verification cannot report
  success when live HTTP checks were skipped. Documentation counts now describe the integrated tree.

## Validation

The combined application gate passes 2,312 Python tests (40 skipped), 1,246 frontend tests,
TypeScript and undefined-name checks. The separate disposable real-Postgres integration run passes
93 tests (one additional session-DSN test skipped); migration v5-to-v6 and owner-scoped pagination are
included. Deployment command contracts pass for both transports. Site claim/count/build/link checks
also pass. Logs are retained in [integration-logs](e2e/integration-logs/).

Browser E2E covers review/apply/reject/undo, bundles, assets, capabilities, budgets, resources,
cleanup, native-handle cancellation/recovery, questions, protocol replay, editor conflicts, SQL
execution/history/promotion, storage failure/recovery, jobs/pipelines and Lakebase/App screens.
It uses the real SPA and app HTTP/protocol/storage paths with deterministic native/model providers;
infrastructure browser suites use recorded API fixtures. These are not deployed-model qualifications.

All 135 new integration PNGs were visually inspected, together with the earlier 346 inspected PNGs:
481 retained captures in [screenshots](e2e/screenshots/). Labeled inspection sheets and a SHA-256
inventory are saved in [screenshot-inspections.json](e2e/screenshot-inspections.json). The initial
jobs, operations and question iterations are marked superseded; their corrected reruns passed.
No claim of pixel perfection or exhaustive accessibility certification follows from these checks.

## Deployment target and remaining qualification

The authorized target is the existing `coding-agent` app in
`https://dbc-cb61f1e1-bd8e.cloud.databricks.com`, organization `7474647158015570`, authenticated as
`raphael.mansuy@gmail.com`. This workspace deploys from Git. The latest preflight reports compute
STOPPED because of workspace or account status, app UNAVAILABLE and no active deployment.
PR #18 merged as `692dc53dc1c65fbd2e6276e6d2039ef57baba83f`. A normal start request was
accepted. It brought compute ACTIVE and automatically resumed the previous deployment, which now
serves `d2d4754e05f15dc06f41d57fdeaaa8b9ae6415e8`. Two attempts to deploy the merged revision were
refused: first while compute was starting, then while the previous deployment was in progress.
No new revision was deployed by those attempts. AGENTS.md requires stopping after two failures;
an additional attempt is awaiting explicit approval. No account, billing or permission workaround
was attempted. The deployment script now waits for compute ACTIVE and any resumed deployment to
finish before submitting; both transport contracts exercise these transitions and pass (23 tests).

The eventual deployment result will be reported separately. Full two-model exam/noise,
real-agent timed fault/rotation/long-run recordings and exhaustive crash/load/WCAG gates from
[17](17-first-principles-closure.md) remain unqualified. Optional phases and a separate execution
identity stay disabled pending their required qualification. Source integration and local E2E do
not establish completion of those live release gates.
