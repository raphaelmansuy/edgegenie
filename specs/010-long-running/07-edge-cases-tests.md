# Edge cases, mitigations and traceability

[Requirements](01-product.md), [architecture](03-architecture.md), [API contracts](04-persistence-api.md), [implementation plan](06-implementation-plan.md), [operating boundaries](08-operations.md), [browser evidence](e2e/README.md).

## Verified local cases

Primary tests: [test_long_running.py](../../apps/coding-agent/tests/test_long_running.py), [existing ACP tests](../../apps/coding-agent/tests/test_adapters.py), [mission reducer tests](../../apps/coding-agent/web/src/domain/mission.test.ts), [RunStatus component tests](../../apps/coding-agent/web/src/components/RunStatus.test.tsx), [browser suite](../../apps/coding-agent/web/scripts/long-running-e2e.mjs).

| Requirements | Edge case | Mitigation | Test/evidence |
|---|---|---|---|
| LR-01/03 | Last browser closes during a mission | Runner has server-owned task reference; SSE cleanup only unsubscribes | `test_work_finishes_without_any_browser_subscribers`; E2E close + fresh page |
| LR-01/10/11 | Offline and reconnect during progress | Show observation loss, replay committed sequence, disable remote controls offline | E2E offline/reconnect; missionStatus tests |
| LR-02/07 | HTTP response lost and client retries | Receipt stored in the same snapshot/event transaction | `test_restart_preserves_history_and_receipt_without_repeating_work` |
| LR-07 | Eight simultaneous submissions use one retry key | Per-session lock and body hash return one original turn | `test_concurrent_retry_accepts_exactly_one_turn` |
| LR-07 | Same key used for a different prompt | 409 instead of executing a second mutation | `test_reused_key_with_different_body_is_a_conflict` |
| LR-04/05 | Server restarts with active/queued work | Mark unfinished turns interrupted, preserve history, require explicit load | Restart test and E2E restore |
| LR-06 | Foreign account guesses a session ID | Central owner gate returns 404 across reads and mutations | `test_foreign_user_cannot_read_mutate_stream_restore_or_approve` |
| LR-08 | User stops while another turn is queued | Cancel accepted queue before stopping active ACP work | Stop-queue test and E2E |
| LR-09 | Agent needs permission while every browser is gone | Server holds permission future; prompt idle guard excludes human waits | Permission-without-viewer test and E2E return/approve |
| LR-09 | Invalid option, wrong permission kind or stale second decision | Validate offered option ID/kind under session lock; 409 if expired | Permission option test |
| LR-09 | Worker restarts with pending permission | Expire old transport request; never assume approval | Restart-permission test |
| LR-09 | Stop while waiting for permission | Resolve pending permission as cancelled before cancellation drain | Restart/cancel-permission test |
| LR-10 | Slow subscriber overflows 2000 wakeups | Force journal catch-up, read authoritative pages | Shared memory/SQLite overflow contract test |
| LR-10 | More than one finite event page | Ordered `nextAfter` + `hasMore` and bounded limit | Pagination test; shared journal test |
| LR-10 | Negative cursor, zero limit, future SSE cursor | Reject invalid replay input | Finite replay bounds test |
| LR-13 | Delegated JWT already expired | Interrupt before the agent can execute a tool | Known-expired-delegation test |
| LR-13 | Agent exceeds runtime budget | Close runtime, interrupt active and queued work, preserve journal | Runtime-limit test |
| LR-14 | Second SQLite worker opens same file | Exclusive owner lock refuses startup | Second-owner test |
| LR-14 | Second Postgres worker opens same database | Dedicated connection holds advisory ownership | Actual local Postgres contract test |
| LR-02/14 | Disk full while accepting a prompt | No successful acceptance and no task scheduled | Failed-commit test |
| LR-14 | Production has no durable journal | Refuse startup | Production-storage test |
| LR-06/13 | Forwarded token could leak into storage | Explicit snapshot whitelist; private journal permissions | Token-file scan test |
| LR-15 | Idle cleanup reaches a completed conversation | Release native process, retain durable history and recovery marker | Durable idle test; existing reaper policy tests |
| LR-16 | Recovery fails or user is offline | Inline actionable error; restore disabled offline | RunStatus tests; browser layout cases |
| LR-11/16 | Duplicate permission surfaces | One shared inline decision component | Browser strict selector caught modal duplication; fixed and recaptured |

## Recovery and failure analysis

An external operation can complete before the worker checkpoints its result. The local journal cannot supply an exactly-once transaction spanning arbitrary Databricks tools. The tested mitigation is **no automatic prompt replay**; recovery restores context for explicit reconciliation. This remains an operational responsibility, not an untested claim of distributed exactly-once execution.

Unrecognized ACP versions and missing `loadSession` capability fail closed. Missing native agent history leaves the application transcript readable and reports a restore failure. File/blob data and OpenCode native history need their own persistence; application journal tests cannot prove those platform mounts. Opaque access-token expiration and Unity Catalog denial remain provider/tool errors; there is no authorization workaround. Storage outage mid-execution closes the agent; external jobs already submitted may continue.

Very long transcripts are paged server-side. The browser reducer retains existing bounded message/reasoning text, and full durable events remain available through the finite API. The current feature does not introduce event-retention pruning; operators must size and back up storage. Multiple application workers are refused, not load-balanced. See [operations](08-operations.md).

## Gate discipline

Run focused lifecycle tests first, then the backend regression suite, frontend suite, TypeScript/build, local Postgres contract, document links/ASCII/Mermaid, and deterministic browser suite. Tests must inspect actual state after departure/restart, not merely count screenshots. All browser images go to [screenshots](e2e/screenshots/); [the inspection record](e2e/README.md) records improvements and remaining environment boundaries.
