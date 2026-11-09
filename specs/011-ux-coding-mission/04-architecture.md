# Architecture and data contract

[Code evidence](02-code-and-lenses.md), [requirements](01-product.md), [design](03-ux-ui.md), [implementation](05-implementation-plan.md), [test risks](06-edge-cases-tests.md).

## Pure read model

`currentMission(session)` selects the running/auditing turn first, then the earliest queued turn if there is no foreground, otherwise the latest terminal turn. `missionView(session, selectedTurn, conn)` returns state, title, plan counts, successful/failed tool counts, verified evidence/source resolution and per-turn artifacts. An explicitly selected historical turn ignores current approvals/recovery. No view method mutates a turn.

Achievement requires `turn.status === completed`, at least one evidence row and every row both server-verified and resolved to a completed call of the reported tool name. A plan of all completed entries alone is insufficient. Failure of an earlier tool remains visible even when later successful calls prove all requirements. All counts have **one selected turn** as grain.

## Sequence

```mermaid
sequenceDiagram
    actor User
    participant App
    participant Mission as Mission screen
    participant Stream as useSessionStream
    participant API
    participant Journal
    participant ACP
    User->>App: Open session or submit instruction
    App->>API: Existing message endpoint (when submitting)
    API->>Journal: Commit accepted turn
    API->>ACP: Execute accepted work
    App->>Stream: Select session ID
    Stream->>API: Detail + SSE after cursor
    API->>Journal: Read ordered replay
    Journal-->>Stream: Normalized events
    Stream-->>Mission: Reduced SessionView
    Mission->>Mission: Select foreground and derive facts
    ACP-->>API: Plan / tools / answer
    API->>Journal: Commit events and evidence verdicts
    Journal-->>Stream: Replay and live catch-up
    Stream-->>Mission: Updated immutable view
    User->>Mission: Inspect source / open output
    Mission->>App: Existing document navigation callback
    Note over Mission,Journal: No mission-specific database or polling
```

## E/R and grain

Physical schema has two tables. `TURN`, `TOOL_CALL`, `PLAN_ENTRY` and `EVIDENCE` below are logical embedded/replayed structures, not new SQL tables. One snapshot is one session; one event is one `(session_id, seq)`; one mission is one turn. Evidence references a call within that turn; no cross-turn proof joins.

```mermaid
erDiagram
    SESSION_SNAPSHOT ||--o{ SESSION_EVENT : journals
    SESSION_SNAPSHOT ||--o{ TURN : embeds
    TURN ||--o{ PLAN_ENTRY : reports
    TURN ||--o{ TOOL_CALL : executes
    TURN ||--o{ EVIDENCE : proposes
    TOOL_CALL ||--o{ EVIDENCE : supports
    SESSION_SNAPSHOT {
        text session_id PK
        jsonb body
        bigint latest_seq
    }
    SESSION_EVENT {
        text session_id PK,FK
        bigint seq PK
        jsonb body
    }
    TURN {
        string id
        int index
        string prompt
        string status
        string model
    }
    PLAN_ENTRY {
        string content
        string status
    }
    TOOL_CALL {
        string callId
        string name
        string status
    }
    EVIDENCE {
        string requirement
        string toolCallId
        string tool
        boolean verified
    }
```

No SQL is issued and no columns are guessed. Existing owner and Unity Catalog boundaries remain server-controlled. The UI cannot bypass a 403/404 by probing alternate sources.

## Execution state

```mermaid
stateDiagram-v2
    [*] --> Starting
    Starting --> Queued: accepted
    Queued --> Running: foreground claimed
    Running --> Waiting: approval requested
    Waiting --> Running: explicit decision
    Running --> Checking: audit begins
    Checking --> Running: supervisor retry
    Checking --> Completed: turn completed
    Running --> Completed: turn completed
    Completed --> Achieved: all evidence resolves and verifies
    Completed --> Review: absent or incomplete proof
    Running --> Blocked: missing requirement or permission
    Running --> Failed: execution failure
    Running --> Stopped: user cancels
    Running --> Interrupted: server restart
    Interrupted --> Review: explicit restore loads context
    Review --> [*]
    Achieved --> [*]
    Blocked --> [*]
    Failed --> [*]
    Stopped --> [*]
```

`Achieved` and `Review` are presentation substates of completed, not new server enum values. Restore does not actually change an interrupted turn into completed: Review in the diagram means the user reviews saved work, while the turn retains interrupted status.

## Observation state

```mermaid
stateDiagram-v2
    [*] --> Connecting
    Connecting --> Live: SSE open
    Live --> Reconnecting: transport error
    Live --> Offline: browser offline
    Offline --> Connecting: online
    Reconnecting --> Live: resumed SSE
    Connecting --> Offline: offline
    Reconnecting --> Offline: offline
    Offline --> Offline: execution may continue
```

Observation wraps the current state with last-known wording; it never rewrites execution. Snapshot hydration can precede full replay, so absent plan/proof is represented as unavailable until events arrive. The existing stream batches at 40ms and deduplicates seq. Projection is linear in selected-turn entries/calls/evidence and uses a call-ID map for evidence lookup; no expensive cross-session work.
