# Implementation plan

Read [principles](README.md), [code and SOLID](02-code-and-lenses.md), [design](03-ux-ui.md) and [architecture](04-architecture.md). Test IDs are in [06](06-edge-cases-tests.md); measured results belong in [07](07-validation.md).

## Ordered work

1. **Domain:** extend `domain/mission.ts` with pure foreground selection, achievement/source resolution and projection. Keep `missionLabel`/`missionStatus` public behavior. Test queue precedence, selection fallback, all lifecycle states and proof integrity before UI wiring.
2. **Presentation:** build `MissionScreen` and small plan/output/evidence sections. Reuse ToolCard, Markdown, CopyButton, RunStatus and existing vector icons. Scope selection per session and retain history selection during SSE updates. Keep unknown data explicit.
3. **Shell wiring:** replace SessionHome and the dock-dependent transcript branch with the same mission screen. Keep composers/approvals and dock unchanged. Add an always-reachable Mission overview control beside open documents. Refresh generated documents but stop automatically replacing the screen with them.
4. **Visual treatment:** use existing semantic tokens, a readable content measure and container queries. Test a narrow centre in a wide shell as well as phone viewports. Preserve full content with wrap/disclosure and internal scrolling.
5. **Verification:** run frontend suite and production build, real local HTTP/SSE/ACP E2E, targeted browser fixtures for rare lifecycle/history states, Chromium and WebKit. Test key paths through actual UI controls, not just direct state injection.
6. **Iteration:** retain first-pass screenshots, inspect every image, record concrete defects, improve and rerun relevant scenarios. Store final screenshots, reports and per-image inspection ledger under `e2e/`.
7. **Release gate:** verify internal links, ASCII grids and Mermaid parse; check git diff; document actual test counts, environment and untested live-workspace behavior. Do not label subjective perfection as a verified fact.

## Engineering constraints

- DRY: reuse event stream and reducers, artifact derivation, tool cards, operational controls and tokens. Remove superseded SessionHome rather than leave two implementations.
- SRP: state classification is pure; section components render; App owns navigation; existing server owns execution.
- OCP: state labels are declarative with conservative unknown fallbacks.
- LSP: live, replayed and fixture SessionView share one projection contract.
- ISP/DIP: pass state and typed actions; no MissionScreen API client, database access or orchestrator coupling.
- No migrations or backend behavior change is expected. If new facts are unavailable, state their absence rather than adding speculative fields.

## Completion checklist

Acceptance is complete only when [M-01–M-12](01-product.md) map to passing tests or explicit documented limits, all retained screenshots have inspection outcomes, no unexpected browser errors remain, and [validation](07-validation.md) describes the final implementation rather than the initial proposal.
