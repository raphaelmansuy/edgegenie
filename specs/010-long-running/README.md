# Five WHYs: long-running OpenGenie sessions

1. **Why do people lose a coding mission when they leave?** The visible connection is often mistaken for ownership of the work. This repository already starts agent tasks on the server; its session state and event log were nevertheless volatile.
2. **Why is server execution alone insufficient?** A server restart loses accepted prompts, retry receipts, progress, and the association with the agent conversation. A browser reconnect cannot reconstruct missing server state.
3. **Why retain an execution journal?** Acceptance, progress, permission decisions, and outcomes must remain reviewable without a connected viewer. A successful HTTP response must refer to a committed task.
4. **Why separate recovery from retry?** A Databricks write may have succeeded before its response was saved. Repeating the prompt after a crash could duplicate tables, jobs, or external effects. Recovery restores context; the user then reconciles uncertain work.
5. **Why make this visible in the product?** Users need to know whether execution is running, observation is disconnected, a decision is required, or work is ready for review. A spinner cannot express that contract.

## First principles

Execution belongs to the server. The browser observes and steers. A durable journal is the record of accepted work. A transport connection is neither authorization nor a lease on the user’s attention. No system can atomically commit both an arbitrary external Databricks operation and its local transcript; recovery must expose that uncertainty. Delegated credentials can expire even while the user is away.

## Reading map

| Document | Purpose | Depends on |
|---|---|---|
| [01 Product](01-product.md) | Outcomes, acceptance requirements, all eight expert lenses | This rationale |
| [02 OpenCode and ACP](02-opencode-acp.md) | Code investigation, protocol contracts, primary sources | Product |
| [03 Architecture](03-architecture.md) | Ownership, sequence and state diagrams, failure boundaries | Protocol |
| [04 Persistence and API](04-persistence-api.md) | E/R model, transactions, isolation, API contracts | Architecture |
| [05 UX and UI](05-ux-ui.md) | Navigation, ASCII wireframes, interaction and accessibility | Product, API |
| [06 Implementation](06-implementation-plan.md) | Concrete code changes, DRY/SOLID, delivery gates | All preceding |
| [07 Edge cases and tests](07-edge-cases-tests.md) | Requirement-to-test traceability and residual risks | Architecture, implementation |
| [08 Operations](08-operations.md) | Configuration, recovery, storage, limits, rollout | Persistence, tests |
| [E2E evidence](e2e/README.md) | Reproduction, screenshots and visual inspection | Tests |

## Delivery boundary

Implemented: browser-independent execution, durable journals in SQLite and Postgres/Lakebase, owner-scoped routes, idempotent message acceptance, ordered replay, bounded execution, pending approval handling, restart recovery, and a shared status UI. A server restart interrupts uncertain operations rather than automatically repeating them. This is one active application worker per journal, enforced by storage ownership locks; it is not a horizontally distributed scheduler.

The user’s Genie Code disconnect behavior is the motivation, not a verified competitive benchmark. No claim of overall model quality superiority follows from this feature. Live Databricks identity/warehouse tools are unavailable in the authoring session; see [validation limits](08-operations.md#validation-boundaries).
