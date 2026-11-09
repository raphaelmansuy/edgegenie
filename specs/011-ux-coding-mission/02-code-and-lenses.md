# Code grounding and professional lenses

[Product requirements](01-product.md) drive these decisions. The [implementation plan](05-implementation-plan.md) maps them to changes.

## Baseline implementation observed before this change

Paths below are relative to `apps/coding-agent/` and link to the real files. Claims about the large App/router files apply to the named integration points only.

| Source | Observed contract | Decision |
|---|---|---|
| [events.ts](../../apps/coding-agent/web/src/domain/events.ts) | SessionView embeds Turn; plan.updated and evidence.proposed are snapshots; turn status is explicit | Derive mission state from the same reducer |
| [mission.ts](../../apps/coding-agent/web/src/domain/mission.ts) | missionLabel and missionStatus distinguish execution/connection/recovery | Extend pure mission domain; retain existing operational language |
| [App.tsx](../../apps/coding-agent/web/src/App.tsx) `SessionHome`, `viewDoc`, write-refresh effect | Centre currently alternates document, transcript and artifact home; verified writes can auto-open | Replace active-session centre with mission screen; retain document refresh, make opening explicit |
| [Chrome.tsx](../../apps/coding-agent/web/src/components/Chrome.tsx) `SessionHome` | Title and session-wide artifact list | Remove superseded component rather than retaining dead implementation |
| [useSessionStream.ts](../../apps/coding-agent/web/src/hooks/useSessionStream.ts) | Metadata hydration plus journal replay; dedup by seq; 40ms batches | No parallel stream/store or new network endpoint; preserve streamed plan, duration, blockers and audit fields when late metadata merges |
| [RunStatus.tsx](../../apps/coding-agent/web/src/components/RunStatus.tsx) | Connection-aware stop, restore and return link with error feedback | Reuse when dock is absent, keep dock as operational surface when present |
| [Transcript.tsx](../../apps/coding-agent/web/src/components/Transcript.tsx) | ToolCard and TurnView already provide full result/answer/evidence inspection | Reuse these for Activity and evidence source disclosure |
| [artifacts.ts](../../apps/coding-agent/web/src/domain/artifacts.ts) | Deduplicates completed read/write artifacts | Reuse with one selected turn, not all session turns |
| [api.py](../../apps/coding-agent/api/routers/api.py) `get_session`, stream and messages routes | Metadata includes turn checkpoints; full content is reconstructed from events | No new API or SQL required |
| [session.py](../../apps/coding-agent/api/domain/session.py) | Immutable turn states and accepted queue | UI never becomes a scheduler |
| [004 migration](../../apps/coding-agent/api/adapters/llm/store/migrations/004_session_journal.sql) | One session_snapshot per session; one session_event per session/seq | No migration: mission is an existing embedded turn |

## Six lenses

| Lens | Decision and reason | Guardrail and test |
|---|---|---|
| Product Owner | Mission means an accepted instruction; current and last achieved are distinct entry points | M-01–04; queue/history/review-state tests |
| Full Stack Developer | Pure projection + small presentation sections; App supplies actions; existing API owns lifecycle | No duplicate send/stop/approval implementations; real server E2E |
| Database Expert | Grain: one mission per turn, one journal event per session/seq; counts never join across turns | No new write model or SQL; per-turn proof/artifacts tests |
| UX and UI Designer | Objective first, textual state, progressive disclosure, quiet default, visible return path | Small-screen, keyboard, long-content and visual inspection |
| Front Designer | Existing tokens and icons, constrained measure, container-based layout, limited motion | Both themes; AA contrast checks; scroll/overflow checks |
| AI Engineer expert | Plan is reported intention; evidence is separate adjudicated proof; never expose hidden reasoning as progress | Evidence must resolve to successful matching tool call; missing proof remains reviewable, never achieved |

## DRY and SOLID

**Single responsibility:** domain selects and classifies; screen composes; ToolCard inspects tools; RunStatus owns operational actions; App navigates. **Open/closed:** the state presentation map is declarative and unknown plan states have a neutral fallback. **Liskov:** the existing SessionView/Turn contracts work for replay, live SSE and fixtures. **Interface segregation:** screen accepts only session, connection, lifecycle callbacks and document navigation. **Dependency inversion:** presentation consumes typed state/callbacks rather than fetching or importing an orchestrator.

Reuse `artifactsOf`, `toolState`, `toolLabel`, `subject`, `stripEvidence`, `ToolCard`, `Markdown`, `CopyButton`, `RunStatus` and shared tokens. No UI-only mission database, second stream or copied evidence/tool renderer. [Architecture](04-architecture.md) and [tests](06-edge-cases-tests.md) make these constraints reviewable.
