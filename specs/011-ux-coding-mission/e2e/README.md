# Mission browser evidence

See [requirements](../01-product.md), [risk matrix](../06-edge-cases-tests.md) and [delivery record](../07-validation.md).

**All 42 retained screenshots were opened and visually inspected.** The [visual ledger](visual-inspection.md) records findings for each image; [the manifest](visual-inspection.json) includes dimensions and SHA-256 hashes.

| Evidence | Result |
|---|---|
| [Final mission report](iteration-03.json) | 11 passing acceptance groups; 23 screenshots; Chromium and WebKit; per-image geometry and text-contrast checks |
| [Durable-session regression](regression/report.json) | 9 passing groups; 13 screenshots; disconnect, page close, accepted queue, permissions, restart, restore and responsive return |
| [Unit/build checks](verification.json) | 599 frontend tests; production build; spec links, ASCII and Mermaid checks |
| [Iteration 01](iteration-01.json) | Four presentation baselines; phone density, long-title and completed-order refinements identified |
| [Iteration 02](iteration-02.json) | Two retained images from a failed hover-contrast run; defect fixed and checked in the final run |

The final mission runner exercises the real local API, SQLite journal, SSE and deterministic ACP subprocess. Explicit presentation fixtures cover history, malformed proof, blocked/failed/archived/empty/auditing states, long paths and unicode. Fixtures use native persistent SSE and never call a connected workspace. A fixture notebook verifies editor rendering; the real local app verifies its unavailable-workspace error and navigation back to the mission.

Run `npm run build && npm run e2e:mission` from `apps/coding-agent/web`. The runner writes `iteration-03/` by default; `MISSION_ITERATION` chooses another evidence folder. Re-run the existing regression with `E2E_OUTPUT` pointing to this folder's `regression/` subdirectory. Every regenerated screenshot needs another visual inspection before its manifest hash is updated.

[Achieved desktop](iteration-03/05-achieved-desktop.png) · [Source proof](iteration-03/06-evidence-source.png) · [Phone](iteration-03/11-mobile-light.png) · [History](iteration-03/14-last-achieved.png) · [WebKit](iteration-03/23-webkit-mobile.png)
