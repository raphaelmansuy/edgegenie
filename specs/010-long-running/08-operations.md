# Operations, rollout and recovery

Read [architecture](03-architecture.md), [persistence/API](04-persistence-api.md) and [test matrix](07-edge-cases-tests.md) first. UI consequences are in [05](05-ux-ui.md).

## Configuration

| Setting | Behavior |
|---|---|
| `APP_SESSION_USE_LAKEBASE=true` | Production journal using the configured Lakebase endpoint and existing app SDK identity |
| `APP_LLM_PG_ENDPOINT`, `APP_LLM_PG_DATABASE`, `APP_LLM_PG_USER` | Existing Lakebase connection settings reused by the journal |
| `APP_SESSION_DATABASE_URL` | Explicit Postgres DSN; preserve as a secret, never print it |
| `APP_SESSION_DB_PATH` | SQLite journal on persistent POSIX storage; one worker; appropriate for local installs or hosts with durable disk |
| No journal configured | Explicit temporary history in development/demo; production startup fails |
| `APP_SESSION_MAX_RUN_SECONDS` | Wall-clock active-turn budget including supervisor and approval wait; default 21600 seconds, configurable 1–604800 |
| `APP_MAX_CONCURRENT_AGENTS` | Global active-turn execution slots, default 4; accepted work waits without interleaving within a session |
| `APP_DEMO_EVENT_DELAY` | Deterministic fixture delay for disconnect/reconnect E2E; no model claims |

Use one application worker. Do not start multiple uvicorn workers against the same journal: startup must fail rather than allow overlapping execution. Postgres is the preferred journal for an ephemeral Databricks App host. SQLite on container-local `/tmp` does not survive replacement; do not call it durable across redeployments.

## Storage and authorization

The session journal's service role needs its own schema, events and snapshots and access to the migration version table. End-user HTTP authorization is independently checked on every session route. This is application storage, not a new route around Unity Catalog. The tools continue to use the signed-in user's credential and scope; production Python notebook execution retains the existing explicit administrator policy.

Keep OpenCode's own data directory, the per-session working directories and file/blob storage on appropriate persistent storage if recovery across host replacement is required. Application history may survive in Lakebase while the agent's native history or an attachment is unavailable. An ACP load failure is visible; it does not create a blank session under the old conversation ID.

Forwarded access tokens remain in private temporary files/environment only. Known JWT expiry limits execution proactively, with a 15-second margin; opaque tokens rely on the provider/tool's authorization error. Reauthentication requires the actual user's fresh request. No background service-principal substitution is introduced to extend user access. Already-submitted Databricks jobs may finish independently of the agent; inspect their run IDs before asking it to repeat work.

## Recovery runbook

1. Check `/api/ready` and storage availability. A durable storage outage has no memory fallback.
2. Ensure only one server owns the journal. For Postgres, do not force-release a live owner's advisory lock; stop the old worker first.
3. Start the server with the original journal configuration. Startup restores saved projections, interrupts unfinished turns, expires transport-bound permissions, and exposes history.
4. Sign in as the owner and open the conversation link. Review partial answers and tool outcomes.
5. Choose Restore agent. The server negotiates v1 and capability-gates loading the recorded agent conversation with current tool servers and credentials.
6. Reconcile uncertain external effects through Databricks state before issuing a continuation instruction. Do not assume an interrupted tool call means the operation failed.

Stop work is cancellation, not rollback. Archive is reversible audit retention at the data level, not a hard-delete or compliance erasure API. Idle cleanup releases durable agent resources and preserves history. Retention and backups are operator responsibilities; no unrequested deletion schedule is introduced.

## Failure/availability limits

A single worker is an availability tradeoff: accepted work survives browser departure, while worker failure interrupts execution until explicit restore. There is no distributed automatic failover or exactly-once guarantee for arbitrary external writes. A runtime budget limits elapsed time, not money. The journal uses synchronous SQLite commits or a single async Postgres owner connection; very large token throughput warrants batching measurements before scaling, while preserving acceptance atomicity.

## Validation boundaries

The authoring session has no `dbxnb_dbx_whoami`, warehouse, SQL, sandbox, or Databricks documentation tools. No workspace identity or running warehouse has been assumed. Deterministic ACP subprocess tests and local Postgres verify the local lifecycle; they do not prove a live model, Unity Catalog grant, Lakebase IAM role, Databricks App mount or cross-host ACP data retention.

Before production rollout, a workspace operator must verify identity and warehouse, describe any test tables before querying them, and exercise: a real mission while all viewers disconnect; a pending permission while away; fresh credentials after expiry; an App restart using Lakebase; ACP load with retained native history; and actual run-state reconciliation. Treat a Unity Catalog permission denial as final. The [evidence report](e2e/README.md) states which checks ran locally and which need this environment.
