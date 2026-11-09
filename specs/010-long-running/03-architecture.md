# Execution ownership and lifecycle

Context: [five WHYs](README.md), [protocol facts](02-opencode-acp.md). Contracts: [storage/API](04-persistence-api.md), [edge cases](07-edge-cases-tests.md).

The application server owns active tasks and ACP permission futures. The journal owns accepted work and replayable observations. The browser owns neither. One application worker per journal is an explicit invariant enforced by a SQLite process lock or a Postgres advisory lock. Global execution slots bound concurrent active turns; each session serializes submissions and permission decisions.

```mermaid
sequenceDiagram
    actor User
    participant Browser
    participant API
    participant Journal
    participant Runner
    participant ACP as OpenCode ACP v1
    participant DBX as Databricks tools
    User->>Browser: Submit mission
    Browser->>API: POST message + retry key
    API->>API: Verify owner, validate context
    API->>Journal: Commit turn + receipt + start event
    Journal-->>API: Commit acknowledged
    API->>Runner: Schedule retained task
    API-->>Browser: 202 + turn ID
    Runner->>ACP: session/prompt
    ACP->>DBX: Governed tool call
    User->>Browser: Close tab / lose connection
    Browser--xAPI: SSE disconnect
    Note over Runner,DBX: Execution continues without subscribers
    DBX-->>ACP: Tool result
    ACP-->>Runner: session/update
    Runner->>Journal: Commit progress
    ACP-->>Runner: Prompt response / stop reason
    Runner->>Journal: Commit verified outcome
    User->>Browser: Open return link
    Browser->>API: Same authenticated owner, replay after 0
    API->>Journal: Read ordered pages
    API-->>Browser: Saved transcript and outcome
```

```mermaid
stateDiagram-v2
    [*] --> Provisioning
    Provisioning --> Ready: initialize + new/load
    Ready --> Queued: accepted and committed
    Queued --> Running: execution slot available
    Running --> WaitingApproval: permission request committed
    WaitingApproval --> Running: offered option selected
    Running --> Auditing: existing supervisor
    Auditing --> Running: bounded continuation
    Auditing --> Completed: tool-backed evidence
    Running --> Completed: verified end
    Running --> Stopped: user cancellation
    WaitingApproval --> Stopped: cancellation
    Queued --> Stopped: stop accepted queue
    Running --> NeedsAttention: crash / expiry / limit / failure
    WaitingApproval --> NeedsAttention: worker restarted
    Queued --> NeedsAttention: worker restarted
    Completed --> NeedsAttention: runtime unloaded
    NeedsAttention --> Ready: explicit capability-gated restore
    Ready --> Archived: user archives
    Stopped --> Archived: user archives
    Completed --> Archived: user archives
    Archived --> [*]
```

This is the conceptual mission state machine. Existing `SessionStatus` and `TurnStatus` remain the source enums; `requires_resume` distinguishes recovery from a normal blocked tool turn. `execution.state` provides the history summary. Connection state is separate: connecting/live/reconnecting/offline never transitions a mission into stopped.

```mermaid
sequenceDiagram
    participant Old as Worker A
    participant Store as Durable journal
    participant New as Worker B
    participant User
    participant ACP
    Old->>Store: Snapshot and event commits
    Note over Old: Process ends
    New->>Store: Acquire exclusive execution ownership
    New->>Store: Restore projections
    New->>Store: Interrupt unfinished turns and expire approvals
    User->>New: Open saved conversation
    New-->>User: Progress + Restore agent
    User->>New: Restore with current identity/token
    New->>ACP: initialize (v1)
    ACP-->>New: loadSession capability
    New->>ACP: session/load(saved ID, cwd, current MCP)
    ACP-->>New: Historical replay, then result
    Note over New: Consume agent replay without duplicating journal
    New->>Store: session.ready checkpoint
    New-->>User: Ready to reconcile and continue
```

## Failure boundaries

- Disconnecting a viewer unsubscribes only that viewer.
- Losing a worker interrupts uncertain active and queued work. It cannot prove an external operation did not complete.
- Losing journal writes closes the agent; there is no volatile fallback for accepted durable work.
- Losing the Postgres owner connection fences further commits. A new owner may start only after the database releases the old advisory lock.
- Expired permissions are never replayed as approvals. New requests must use new random IDs.
- Loading an agent does not rerun the interrupted prompt. Follow-up instructions are explicit user actions.
- An already-submitted Databricks job or SQL request can outlive the ACP process. Recovery requires checking its actual state.

The deployment remains a single execution owner. Distributed worker leases, an outbox and automatic reconciliation of every Databricks operation would be a different scheduler architecture; they are not implied by using Postgres. See [rollout limits](08-operations.md).
