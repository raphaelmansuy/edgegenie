# Implementation and verification plan

Start with [first principles](README.md), [requirements](01-product.md), [code investigation](02-opencode-acp.md), [architecture](03-architecture.md), [storage/API](04-persistence-api.md), and [UX](05-ux-ui.md). Tests and operating limits are in [07](07-edge-cases-tests.md) and [08](08-operations.md).

## Delivery slices

| Slice | Concrete implementation | Verification gate |
|---|---|---|
| 1. Journal seam | Extend EventStore with atomic `commit` and `snapshots`; share Broadcast wakeups; retain MemoryEventStore for isolated demos/tests | Contract tests for ordering, paging, overflow and checkpoint |
| 2. Durable adapters | SQLite journal with WAL/FULL and process lock; Postgres/Lakebase journal with transaction and exclusive advisory ownership; common migration 004 | Actual SQLite reopen; actual Postgres commit/reopen/second-owner refusal |
| 3. Lifecycle | Whitelisted checkpoints, restore before serving, unfinished-turn interruption, fresh credential restore, orderly runner shutdown | HTTP restart and idempotency tests; no implicit prompt replay |
| 4. ACP correctness | Capability-gated `session/load`; consume historical replay; refuse incompatible protocol; durable permission notification; no dropped updates | Real subprocess protocol tests including missing capability/history |
| 5. Acceptance and controls | Per-session submission lock, body-bound retry receipt, owner boundary, bounded execution slots and runtime, stop accepted queue | Concurrent retry, foreign-user, expiry, queue cancellation and storage failure tests |
| 6. Product UI | One RunStatus in dock/full view; connection-aware copy; return link; restore; history state/filter/polling | TypeScript, component tests, reducer parity, browser journeys |
| 7. Evidence | Actual page close and offline/reconnect, server restart/restore, approval while away, narrow/wide themes | All screenshots under `e2e/screenshots`, visually inspect every image, fix observed defects and recapture |

## DRY and SOLID

- **Single responsibility:** journals commit and read durable state; Broadcast handles subscriptions; the orchestrator owns lifecycle; the ACP adapter owns wire capabilities; mission.ts derives user-visible state; RunStatus renders it.
- **Open/closed:** a journal adapter satisfies the same commit/replay contract. Adding another store must not fork the runner or browser protocol.
- **Liskov:** memory and durable journals are exercised by shared ordering/replay checks. The durable flag makes persistence guarantees explicit; memory does not masquerade as durable storage.
- **Interface segregation:** the browser receives execution facts, not provider secrets or database rows. ACP SessionSpec carries the saved agent ID without exposing transport objects to the domain.
- **Dependency inversion:** orchestration consumes store/runtime interfaces; main.py alone selects implementations. Lakebase reuses the existing credential source and migration runner.
- **DRY:** reuse the supervisor, model resolver, scoped tool registry, event reducer, transcript, existing deep-link formatter, composer and semantic theme tokens. Do not build a second agent execution loop or duplicate mission screens.

## Migration and release ordering

Deploy compatible code and migration together. The schema version advances to 4; older builds refuse a newer schema rather than mutating it. Configure the durable journal before enabling production. Run a disposable local Postgres test and deterministic ACP/browser suite, then perform the separate live Databricks smoke checks in [operations](08-operations.md). Preserve the ACP data directory before testing recovery across a replacement host.

## Completion criteria

The implementation is complete within the [delivery boundary](README.md#delivery-boundary) when all LR requirements have local evidence or an explicit live-environment validation boundary, the build and regression suites pass, documentation links and diagrams validate, and every E2E screenshot is inspected. Results must record actual outcomes, not assume a green screenshot proves a live Databricks mutation.
