[Index](README.md) · [07 Back end](07-backend.md) · **08 Data** · [09 Security](09-security-security.md) · [12 Ops](12-operations.md)

# 08 · Data model (Lakebase Postgres)

## Entities

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#E8F0FE','primaryTextColor':'#1F2937','primaryBorderColor':'#A8C0E8','lineColor':'#94A3B8'}}}%%
erDiagram
    APP_USER ||--o{ SESSION : owns
    SESSION ||--o{ TURN : contains
    SESSION ||--o{ EVENT : emits
    SESSION ||--o{ ARTEFACT : touches
    SESSION ||--o{ APPROVAL : requests
    TURN ||--o{ EVENT : groups
    TURN ||--o{ EVIDENCE_ITEM : proves
    EVENT }o--|| TURN : "belongs to (nullable)"
    APPROVAL ||--|| EVENT : "decided by"
    ARTEFACT }o--|| SESSION : "created in"

    APP_USER {
        text user_id PK "from Databricks identity"
        text email
        timestamptz first_seen
    }
    SESSION {
        uuid id PK
        text user_id FK
        text title
        text workspace_folder "the fence"
        text allow_schemas "csv, null = derive from folder"
        text model_id
        text agent_name
        text agent_version
        text status "provisioning|ready|streaming|blocked|archived|failed"
        int  max_tools
        bigint token_total
        numeric cost_estimate
        timestamptz created_at
        timestamptz last_active_at
    }
    TURN {
        uuid id PK
        uuid session_id FK
        int  index "1..n"
        text prompt
        text stop_reason
        text status "running|auditing|completed|blocked|cancelled|interrupted|failed"
        int  tool_calls
        int  input_tokens
        int  output_tokens
        int  cached_tokens
        timestamptz started_at
        timestamptz ended_at
    }
    EVENT {
        bigint seq PK "per session, monotonic"
        uuid session_id FK
        uuid turn_id FK "nullable"
        text type
        text actor
        jsonb payload
        timestamptz at
    }
    ARTEFACT {
        uuid id PK
        uuid session_id FK
        text kind "notebook|file|table|job|app|lakebase"
        text path_or_name
        text change "created|modified|deleted"
        text before_hash
        text after_hash
        int  lines_changed
        timestamptz at
    }
    EVIDENCE_ITEM {
        uuid id PK
        uuid turn_id FK
        text requirement
        text tool_call_id
        text tool_name
        text result_summary
        bool verified "cited call actually happened"
    }
    APPROVAL {
        uuid id PK
        uuid session_id FK
        uuid turn_id FK
        text tool_call_id
        text action "create|write|delete|run"
        text target
        text reason
        text blast_radius
        text outcome "allow_once|allow_session|deny|expired"
        text decided_by
        timestamptz requested_at
        timestamptz decided_at
    }
```

## Event sourcing, but pragmatic

The `EVENT` table is the source of truth for a transcript; `TURN` is a **projection** kept for fast listing and for
cost reporting. We do not re-derive turns on every read (too slow for a session list), and we do not pretend the projection
is authoritative: a repair job re-derives `TURN` from `EVENT` if they disagree.

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#E8F0FE','primaryTextColor':'#1F2937','primaryBorderColor':'#A8C0E8','lineColor':'#94A3B8'}}}%%
stateDiagram-v2
    [*] --> running: turn.started
    running --> auditing: stopReason end_turn
    auditing --> running: gaps found (audit pass)
    auditing --> completed: evidence verified
    running --> cancelled: user cancel
    running --> interrupted: process died
    running --> failed: unrecoverable error
    interrupted --> running: resumed
    completed --> [*]
    cancelled --> [*]
    blocked --> [*]
    running --> blocked: agent reports it cannot proceed
```

## Indexes and access patterns

| Query | Frequency | Index |
|---|---|---|
| Session list for a user, newest first | every page load | `(user_id, last_active_at desc)` |
| Events for a session after seq N | every SSE connect/reconnect | PK `(session_id, seq)` |
| Turn list for a session | on open | `(session_id, index)` |
| Artefacts for a session | inspector tab | `(session_id, at)` |
| Audit: who wrote object X | incident | `(path_or_name)` + GIN on `payload` |
| Cleanup: idle sessions | hourly job | `(last_active_at)` |
| Approvals pending | the UI polls the stream, not a table scan | `(session_id) WHERE outcome IS NULL` (partial) |

## Retention and privacy

| Data | Retention | Reason |
|---|---|---|
| `EVENT` payloads | 30 days (configurable) | Debugging; then only `type`, `at`, counts remain |
| `TURN.prompt` | 90 days | "what did I ask" |
| `APPROVAL` | 1 year | Governance evidence |
| `ARTEFACT` | session lifetime | Diffs are regenerated from events, not stored |
| SQL result rows | **never stored** | Avoids creating a second copy of governed data outside Unity Catalog |
| Tokens | **never stored** | Passed through per request ([09](09-security-security.md)) |

That last row is a deliberate design decision: **the app stores what happened, not the data itself.** It keeps the app
outside the data-governance blast radius.

## Migration strategy

- Alembic, forward-only, one migration per PR.
- Every migration is additive for one release (add column → backfill → drop old in the next release).
- `events` is partitioned monthly (`PARTITION BY RANGE (at)`) from day one: a chat app accumulates rows fast.
- A `_schema_version` row is checked at boot; a mismatch refuses to start (never run half a schema).

## Capacity estimate (\[proposal], to be confirmed by the load test)

| Item | Per turn | Per session (10 turns) | 100 users × 5 sessions/month |
|---|---|---|---|
| Events | 40–120 | 400–1,200 | 0.6–1.8 M rows/month |
| Event bytes | 2–8 KB | 20–100 KB | 50–250 MB/month (90% in payloads) |
| Turns | 1 | 10 | 5,000/month |

At those volumes a CU_1 Lakebase instance is comfortable; the first real constraint will be the 30-day payload window,
which keeps the table small.

## Edge cases in the data layer

| Edge case | Handling |
|---|---|
| E-13 deep pagination with new rows appearing | keyset pagination on `(last_active_at, id)`, never OFFSET |
| E-14 two workers appending the same turn | `turn_id` + unique `(session_id, seq)`; sequence from a Postgres sequence, not the app |
| E-16 session deleted while streaming | soft delete + `archived_at`; stream sends `session.archived` and closes |
| E-17 event payload with a secret | the writer redacts known patterns before insert (token regex, `Bearer `), with a unit test |
| E-18 clock skew between workers | all timestamps `now()` from the database, never `datetime.now()` in Python |
| E-19 GDPR-style deletion request | delete rows for a user in one transaction, then vacuum; audit rows keep a pseudonymous actor id |

Next: [09 Security and governance](09-security-security.md).
