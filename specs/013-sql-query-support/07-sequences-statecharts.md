# Sequences, states and transition invariants

[Index](README.md) · [API](05-architecture-api.md) · [Data](06-data-persistence.md) · [Edges](09-edge-cases.md) · [Transition tests](11-test-e2e-plan.md)

Pastel fills use dark text and muted borders. Color is redundant with labels. Each chart describes a separate state dimension; do not encode document state, execution and result availability in one exponential enum.

## Sequence A — author, create copy and reopen

```mermaid
%%{init: {'theme':'base','themeVariables':{'actorBkg':'#E4EAFE','actorBorder':'#8292AD','actorTextColor':'#263449','signalColor':'#687B92','signalTextColor':'#263449','noteBkgColor':'#FFF1D6','noteTextColor':'#263449','activationBkgColor':'#E2F2EA','activationBorderColor':'#7C9A89'}}}%%
sequenceDiagram
  actor U as User
  participant E as Query editor
  participant S as QueryService
  participant J as App store
  participant D as Databricks Query API
  U->>E: Edit local buffer and choose Create Query or Save copy
  E->>S: Own draft revision, destination, operation key
  S->>S: Authenticate, validate destination and supported fields
  S->>J: Reserve create operation and immutable snapshot
  J-->>S: Reservation committed
  S->>D: Create once as user
  alt Native ID returned
    D-->>S: Native Query ID
    S->>J: Persist created_unverified and ID
    S->>D: GET by returned ID
    D-->>S: Authorized saved asset
    S->>J: Mark created and link asset
    S-->>E: Native ref plus persistence evidence
    E->>E: Alias draft tab, retain caret, add recent
  else Request outcome unknown
    S->>J: Persist create_unknown
    S-->>E: Preserve buffer and offer operation reconciliation
    Note over E,D: No second create POST and no delete compensation
  end
```

If the user edits again while create is in flight, only the submitted revision becomes saved. The newer buffer stays dirty against the returned native ref and offers another Save copy. Native external changes never overwrite a dirty app buffer.

## Sequence B — run, poll and reconnect

```mermaid
%%{init: {'theme':'base','themeVariables':{'actorBkg':'#E4EAFE','actorBorder':'#8292AD','actorTextColor':'#263449','signalColor':'#687B92','signalTextColor':'#263449','noteBkgColor':'#FFF1D6','noteTextColor':'#263449','activationBkgColor':'#E2F2EA','activationBorderColor':'#7C9A89'}}}%%
sequenceDiagram
  actor U as User
  participant E as Editor
  participant S as SqlRunService
  participant J as Durable run store
  participant D as Statement API
  U->>E: Run query or selection
  E->>S: Snapshot ref, scope, bindings, warehouse, operation key
  S->>S: Validate source access, SQL policy and context
  S->>J: Transactionally reserve attempt and immutable input
  S->>J: Mark submitting before external request
  S->>D: Submit once, wait_timeout 0s, bounded INLINE
  D-->>S: Statement ID and initial observed state
  S->>J: Persist handle and observation version
  S-->>E: 202 run handle
  loop While visible and nonterminal, within poll budgets
    E->>S: GET own run status
    S->>D: Poll known ID as current user
    D-->>S: Current observation
    S->>J: Apply monotonic versioned observation
    S-->>E: State and result availability
  end
  Note over E,J: Browser close detaches observation and does not cancel execution
  U->>E: Reload or open own history
  E->>S: GET own run by durable handle
  S->>D: Reconcile known ID with renewed same-user token
  S-->>E: Terminal fact or continuing state
```

If a token expires, stop upstream polling and show Reconnect. An idle background owner cannot invent a fresh forwarded token. If submission response/handle persistence is lost, follow the unknown-outcome state below. A known statement continues remotely even if the server stops; durable provenance does not imply continuous server observation.

## State A — editor and persistence

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#E4EAFE','primaryTextColor':'#263449','primaryBorderColor':'#8292AD','lineColor':'#7B8798','tertiaryColor':'#FFF1D6'}}}%%
stateDiagram-v2
  [*] --> Loading
  Loading --> Clean: permitted source read
  Loading --> Unavailable: denied or missing
  Clean --> Dirty: local edit
  Dirty --> CreatingCopy: explicit create or save copy
  CreatingCopy --> Clean: exact submitted revision verified
  CreatingCopy --> Dirty: verified but newer local edits exist
  CreatingCopy --> CreateUnknown: lost outcome
  CreatingCopy --> Dirty: known failure
  CreateUnknown --> Clean: reconcile verified ID and unchanged buffer
  CreateUnknown --> Dirty: reconcile verified ID and newer edits
  CreateUnknown --> Dirty: user acknowledges unresolved outcome
  Dirty --> Conflict: app draft revision changed
  Conflict --> Dirty: explicit merge or recover separate draft
  Dirty --> Clean: explicit discard to authorized base
  Clean --> Clean: external refresh
  Dirty --> Conflict: external source changed
  Clean --> Unavailable: access lost
  Dirty --> Unavailable: access lost, isolate own draft
  classDef safe fill:#E2F2EA,stroke:#7F9A8C,color:#263449;
  classDef work fill:#E4EAFE,stroke:#8292AD,color:#263449;
  classDef attention fill:#FFF1D6,stroke:#AA9773,color:#263449;
  class Clean safe;
  class Loading,Dirty,CreatingCopy work;
  class Unavailable,CreateUnknown,Conflict attention;
```

Access loss removes cached remote content from the active view. An already-owned private draft may be exported only under app policy; it does not retain permission to rerun its origin. Unavailable is a view state, not permission to delete unsaved work silently.

## State B — execution attempt

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#E4EAFE','primaryTextColor':'#263449','primaryBorderColor':'#8292AD','lineColor':'#7B8798','tertiaryColor':'#FFF1D6'}}}%%
stateDiagram-v2
  [*] --> Validating
  Validating --> Refused: policy, access or input rejected
  Validating --> Reserved: durable reservation
  Reserved --> Submitting: dispatch claimed and persisted
  Submitting --> Pending: known ID, upstream pending
  Submitting --> Running: known ID, upstream running
  Submitting --> Succeeded: immediate success
  Submitting --> Failed: definitive upstream failure
  Submitting --> Canceled: upstream already canceled
  Submitting --> SubmissionUnknown: response or commit lost
  Pending --> Running: upstream observation
  Pending --> Succeeded: fast completion
  Pending --> Failed: upstream failure
  Pending --> Canceled: external cancellation confirmed
  Pending --> CancelRequested: explicit cancel or app deadline
  Running --> CancelRequested: explicit cancel or app deadline
  Running --> Succeeded: upstream success
  Running --> Failed: upstream failure
  Running --> Canceled: external cancellation confirmed
  CancelRequested --> Canceled: upstream confirms
  CancelRequested --> Succeeded: completion won race
  CancelRequested --> Failed: upstream failure won race
  Pending --> Reconciling: transport, auth or owner lost
  Running --> Reconciling: transport, auth or owner lost
  CancelRequested --> Reconciling: cancel result unknown
  Reconciling --> Pending: known ID still pending
  Reconciling --> Running: known ID still running
  Reconciling --> CancelRequested: still active with cancel intent
  Reconciling --> Succeeded: confirmed success or CLOSED
  Reconciling --> Failed: confirmed failure
  Reconciling --> Canceled: confirmed cancellation
  SubmissionUnknown --> Reconciling: authoritative ID recovered
  SubmissionUnknown --> OutcomeUnknown: unresolved and acknowledged
  classDef safe fill:#E2F2EA,stroke:#7F9A8C,color:#263449;
  classDef active fill:#E4EAFE,stroke:#8292AD,color:#263449;
  classDef caution fill:#FFF1D6,stroke:#AA9773,color:#263449;
  classDef stopped fill:#F7E2E8,stroke:#B38A96,color:#263449;
  class Succeeded safe;
  class Validating,Reserved,Submitting,Pending,Running active;
  class SubmissionUnknown,OutcomeUnknown,Reconciling,CancelRequested caution;
  class Refused,Failed,Canceled stopped;
```

`CLOSED` maps to execution succeeded with results expired. Unrecognized upstream state goes to Reconciling/protocol-error display; it is never coerced to success. There is no transition from SubmissionUnknown or OutcomeUnknown back to Submitting for the same operation. A deliberate new run is a new attempt/key after explicit acknowledgement. Local cancellation before dispatch can mark an attempt Canceled without calling Databricks; the reservation transaction must prove dispatch has not been claimed.

## State C — result availability

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#E4EAFE','primaryTextColor':'#263449','primaryBorderColor':'#8292AD','lineColor':'#7B8798','tertiaryColor':'#FFF1D6'}}}%%
stateDiagram-v2
  [*] --> NotReady
  NotReady --> Fetching: successful execution with result
  NotReady --> Empty: success without rows
  NotReady --> Expired: CLOSED observation
  Fetching --> Available: validated chunk
  Fetching --> FetchError: transient or protocol error
  FetchError --> Fetching: explicit safe fetch retry
  Fetching --> Expired: result no longer available
  Available --> Fetching: next bounded chunk
  Available --> Available: input changed, mark stale
  Available --> Expired: upstream expiry
  Available --> Denied: access lost, clear cache
  classDef ready fill:#E2F2EA,stroke:#7F9A8C,color:#263449;
  classDef work fill:#E4EAFE,stroke:#8292AD,color:#263449;
  classDef caution fill:#FFF1D6,stroke:#AA9773,color:#263449;
  class Empty,Available ready;
  class Fetching,NotReady work;
  class FetchError,Expired,Denied caution;
```

Staleness is a derived comparison of pinned inputs and current buffer/context, not a new execution state. A chunk-fetch failure does not turn a successful execution into Failed. An explicit rerun from Expired creates a fresh attempt after validation and may produce different data.

## Transition invariants

1. Every dispatch has a durable reservation and an immutable snapshot; every remote result attaches to its statement ID.
2. Same operation key/body returns the same attempt; changed body is a conflict.
3. At most one nonterminal active attempt per document/principal in R1; own history remains available independently of tabs.
4. Cancel intent never manufactures Canceled; terminal execution facts cannot regress under reordered polls.
5. Saving, executing, inspecting results and sending AI context are separate actions.
6. Closing/reloading/swapping tabs changes observation, not remote execution.
7. Unknown submission is never automatically replayed, even for apparently read-only SQL.
8. Source/result expiry and loss of authorization are independently visible.

Test these as reducer properties and fault-injection traces, then verify the observable paths through [T03–T15](11-test-e2e-plan.md).
