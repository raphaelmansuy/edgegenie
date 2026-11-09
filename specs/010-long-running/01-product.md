# Product contract

Return to [five WHYs](README.md). Technical basis: [ACP](02-opencode-acp.md), [architecture](03-architecture.md), [UI](05-ux-ui.md), [tests](07-edge-cases-tests.md).

## User journey

A data engineer submits a notebook or debugging mission, sees that it runs on the server, copies a return link, and closes the page. The server continues without SSE subscribers. Returning with the same account reconstructs the conversation from the journal. If a decision is pending, the agent waits. If the application restarted, progress is available and the user explicitly restores the agent before requesting further work.

## Requirements

| ID | Observable acceptance criterion |
|---|---|
| LR-01 | Closing, navigating away from, or disconnecting every browser does not cancel an accepted turn. |
| LR-02 | Durable mode commits the turn, retry key, and start event before acknowledging acceptance. |
| LR-03 | A return link and a fresh browser restore transcript, tools, evidence, queued prompts, and outcomes. |
| LR-04 | Restart preserves history and marks unfinished work interrupted; no external operation is automatically replayed. |
| LR-05 | ACP recovery loads the recorded agent session only when v1 `loadSession` is advertised; failure is explicit. |
| LR-06 | Session reads, streams, messages, approvals, restore, model controls, and archive are owner scoped. |
| LR-07 | Concurrent retries with one key create one turn; a different body with that key is rejected. |
| LR-08 | Stop cancels accepted queued work as well as the active turn. It preserves completed effects and partial output. |
| LR-09 | A pending permission is journaled, waits without a viewer, and is validated against agent-offered options. |
| LR-10 | Reconnect replays ordered committed events without dropping overflowed progress or duplicating text. |
| LR-11 | UI distinguishes connection state from execution state and never invents a percentage or completion time. |
| LR-12 | Running sessions appear in history; history refreshes without reopening the session or reloading models. |
| LR-13 | Runtime limits and known JWT expiry interrupt work with a recovery path; failures do not grant broader identity. |
| LR-14 | Exactly one worker owns a journal; startup refuses a second owner and production refuses volatile storage. |
| LR-15 | Idle cleanup releases durable sessions’ agent resources without deleting their conversation history. |
| LR-16 | Both themes and narrow/wide layouts keep recovery controls and status readable and keyboard reachable. |

## Expert lenses and decisions

| Lens | Concern | Design decision and evidence |
|---|---|---|
| Product Owner | Users can leave with confidence and know what to review | LR-01/03/11; [return journey](05-ux-ui.md) |
| Full Stack Developer | One acceptance contract from HTTP through replay | [transactions and APIs](04-persistence-api.md); shared RunStatus and reducer |
| Database Expert | Ordering, recovery, lock ownership, outage behavior | Single writer, atomic snapshot/event commits, WAL/FULL SQLite, transactional Postgres |
| UX and UI Designer | Distinguish waiting, offline, active, completed | [wireframes](05-ux-ui.md); persistent status and inline decisions |
| Front Designer | Dense existing three-pane shell must stay usable | Existing semantic tokens; wrapping actions; same component in dock and full transcript |
| AI Engineering | Agent history, tool evidence, permissions and bounded loops | Capability-gated ACP load; evidence scoped per turn; existing supervisor retained |
| System Design Expert | Browser failure differs from worker failure | [state machine](03-architecture.md); explicit single-owner deployment and fail-closed storage |
| Databricks Expert | User identity, Unity Catalog and delegated credentials | Token never journaled, no service-principal fallback for user operations, expire rather than bypass |

## Product boundaries

A mission is an accepted user turn, including the existing bounded supervisor continuation/audit loop. Subsequent user messages are durable queued turns. There is no infinite self-directed goal engine, notification service, detached production privilege escalation, or automatic replay of ambiguous writes. A Databricks job already submitted may continue on Databricks after the agent stops; the UI does not claim rollback. Runtime budget is a wall-clock control, not a dollar-spend budget. These choices are detailed in [operations](08-operations.md).
