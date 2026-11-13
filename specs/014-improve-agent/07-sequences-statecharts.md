# 07 · Sequences and state charts

[Map](README.md) · architecture: [05](05-architecture.md) · data: [06](06-data-model.md) · edge cases: [09](09-edge-cases.md) · tests: [11](11-test-e2e-plan.md)

Every state below is a stored value. Every transition names what causes it. A state chart is complete
when each edge case in [09](09-edge-cases.md) lands on a state drawn here; the last column of that
matrix says which.

Colour key, the same in every chart: blue is in progress, green is a good end, amber is waiting for a
person or for the workspace, red is an end that needs attention.

## Sequence 1 Session start and capability probe

The agent process is not started until the first prompt ([AG-67](03-requirements.md#ag-67)). The probe
runs first, because it decides which tools exist ([AG-31](03-requirements.md#ag-31)).

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#E4EAFE','primaryTextColor':'#263449','primaryBorderColor':'#8292AD','lineColor':'#7B8798','secondaryColor':'#E2F2EA','tertiaryColor':'#FFF1D6','actorBkg':'#E4EAFE','actorBorder':'#8292AD','noteBkgColor':'#FFF1D6','noteBorderColor':'#AA9773','activationBkgColor':'#E2F2EA','activationBorderColor':'#7F9A8C','labelBoxBkgColor':'#E2F2EA','labelBoxBorderColor':'#7F9A8C'}}}%%
sequenceDiagram
    autonumber
    actor U as User
    participant W as Web app
    participant S as SessionService
    participant C as CapabilityService
    participant H as Handlers
    participant D as Databricks
    participant T as TurnService
    participant A as Agent process

    U->>W: New conversation, folder and schema
    W->>S: POST /sessions
    S->>S: Validate folder with policy.paths, store session row
    S->>C: probe(session, user token)
    par one cheap read per asset kind
        C->>H: describe or list, limit 1
        H->>D: GET as the user
        D-->>H: 200 or 403
    end
    C-->>S: Matrix with reasons
    S-->>W: 201, capabilities.reported
    W-->>U: Capability strip, composer ready
    Note over S,A: No agent process exists yet

    U->>W: First message
    W->>T: POST /messages with retry key
    T->>T: Commit turn, respond 202
    T->>A: Spawn with minimal environment, pinned version checked
    T->>A: initialize, read capabilities
    alt agent lacks a required capability
        T-->>W: session.degraded with the stated reason
    else negotiated
        T->>A: session/new with the facade as MCP server
        T->>A: session/prompt
    end
```

## Sequence 2 Change with review

The server channel ([05](05-architecture.md#how-the-humans-answer-is-collected)), used when the need for
a review depends on the arguments, and by any agent that does not ask in the protocol. The tool never
blocks longer than the bound; the turn pauses instead of timing out. In Review mode with the pinned
agent the ordinary path is [sequence 4](#sequence-4-permission-as-the-protocol-defines-it), which
reaches the same ChangeService.

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#E4EAFE','primaryTextColor':'#263449','primaryBorderColor':'#8292AD','lineColor':'#7B8798','secondaryColor':'#E2F2EA','tertiaryColor':'#FFF1D6','actorBkg':'#E4EAFE','actorBorder':'#8292AD','noteBkgColor':'#FFF1D6','noteBorderColor':'#AA9773','activationBkgColor':'#E2F2EA','activationBorderColor':'#7F9A8C','labelBoxBkgColor':'#E2F2EA','labelBoxBorderColor':'#7F9A8C'}}}%%
sequenceDiagram
    autonumber
    actor U as User
    participant W as Web app
    participant A as Agent
    participant F as MCP facade
    participant X as Toolbox
    participant G as ChangeService
    participant H as Notebook handler
    participant D as Databricks
    participant J as Stores

    A->>F: dbx_edit(notebook, base r41, replace cell 4, insert cell 5)
    F->>X: POST /internal/tools/dbx_edit with session key
    X->>G: propose
    G->>H: plan(ref, r41, ops)
    H->>D: Read current revision and content as the user
    D-->>H: r41, source
    H-->>G: Plan with diff, digests, class change
    G->>G: verdict(review, inside fence, change) is ask
    G->>J: invocation, change awaiting_review, approval pending
    G-->>X: awaiting_review, change c_7f2a
    X-->>F: Reply within the bound
    F-->>A: Waiting for the user, change c_7f2a
    J-->>W: change.proposed
    W-->>U: Change card with diff

    alt user decides while the agent waits
        A->>F: dbx_change(c_7f2a, wait 25)
        U->>W: Apply
        W->>G: POST decision apply, idempotency key
        G->>J: change applying
        G->>H: apply(plan)
        H->>D: Check revision is still r41, then import
        alt revision still r41
            D-->>H: r42
            G->>J: previous content, change applied r42, change.applied
            G-->>F: applied r42
            F-->>A: Applied, new revision r42
        else notebook moved
            D-->>H: r43 found
            G->>J: change conflicted
            G-->>F: conflicted, current is r43
            F-->>A: Not written, read again and re-plan
        end
    else no decision within two waits
        F-->>A: End your turn and report what is waiting
        A-->>W: Final report
        Note over W,J: Turn is paused, not blocked
        U->>W: Apply, later
        W->>G: POST decision apply
        G->>J: change applied, wake-up fired, turn queued
        Note over A,J: The queued turn carries the outcome as context
    end
```

Reject is the mirror image: the change becomes `rejected`, nothing is read or written again, and the
agent is told once.

## Sequence 3 Long run with continuation

Drawn at tier 1, where the session's identity may call the Jobs API (a local token). On an app
deployment the agent cannot start the run ([identity tiers](05-architecture.md#identity-tiers)); the
observation loop is the same with one substitution: the handler reads `system.lakeflow` through the
warehouse instead of `runs/get`, and the card shows the refresh time.

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#E4EAFE','primaryTextColor':'#263449','primaryBorderColor':'#8292AD','lineColor':'#7B8798','secondaryColor':'#E2F2EA','tertiaryColor':'#FFF1D6','actorBkg':'#E4EAFE','actorBorder':'#8292AD','noteBkgColor':'#FFF1D6','noteBorderColor':'#AA9773','activationBkgColor':'#E2F2EA','activationBorderColor':'#7F9A8C','labelBoxBkgColor':'#E2F2EA','labelBoxBorderColor':'#7F9A8C'}}}%%
sequenceDiagram
    autonumber
    actor U as User
    participant W as Web app
    participant A as Agent
    participant X as Toolbox
    participant O as OperationService
    participant H as Job handler
    participant D as Databricks
    participant J as Stores
    participant T as TurnService

    A->>X: dbx_run(job, agent_3fa9_nightly)
    X->>O: start
    O->>J: operation submitting
    O->>H: submit as the user
    H->>D: run-now
    D-->>H: run 88213
    O->>J: operation running, native id 88213, wake-up armed continue
    O-->>X: operation op_91c, running
    X-->>A: Handle op_91c, poll with dbx_operation
    J-->>W: operation.started
    W-->>U: Operation card

    A->>X: dbx_operation(op_91c, wait 25)
    X-->>A: Still running, 1 of 3 tasks done
    A-->>W: Report, the run continues
    Note over A,T: Turn paused on op_91c. The agent process may be released.

    loop poll with backoff while the delegated credential is valid
        O->>H: observe(88213)
        H->>D: runs/get as the user
        D-->>H: state and tasks
        O->>J: operation.progress when the state version advances
    end

    alt credential expires before the run ends
        O->>J: operation unobserved, last seen time
        W-->>U: Last seen running, sign in to refresh
        U->>W: Returns, any authenticated request
        W->>O: keepalive refreshes the credential, observation resumes
    end

    D-->>H: TERMINATED, silver FAILED
    O->>J: operation failed, result digest, wake-up fired
    O->>T: Queue system turn, retry key is the operation id
    J-->>W: operation.settled
    T->>A: session/prompt with the failed task and its error as context
    Note over A,D: The mission continues without the tab having stayed open
```

## Sequence 4 Permission as the protocol defines it

The frames are the ones the pinned agent sent (A-09, A-10 in
[14](14-live-investigation.md#agent-facts)). Two details decide the design: the request's own input is
empty and the arguments come on the tool-call update for the same id; and after a rejection the agent
ends the turn without a word.

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#E4EAFE','primaryTextColor':'#263449','primaryBorderColor':'#8292AD','lineColor':'#7B8798','secondaryColor':'#E2F2EA','tertiaryColor':'#FFF1D6','actorBkg':'#E4EAFE','actorBorder':'#8292AD','noteBkgColor':'#FFF1D6','noteBorderColor':'#AA9773','activationBkgColor':'#E2F2EA','activationBorderColor':'#7F9A8C','labelBoxBkgColor':'#E2F2EA','labelBoxBorderColor':'#7F9A8C'}}}%%
sequenceDiagram
    autonumber
    actor U as User
    participant W as Web app
    participant P as ACP client
    participant A as Agent
    participant G as ChangeService
    participant T as TurnService

    A->>P: tool_call, status pending, input empty
    A->>P: session/request_permission with toolCallId and options once, always, reject
    A->>P: tool_call_update for the same id, in_progress, with the arguments
    P->>G: Plan from the arguments on the update, not from the request
    G-->>P: Asset, base revision, class, verdict, diff
    P->>W: approval.requested with the plan and the agent's title shown as its words
    Note over A,P: The agent waits. No tokens are spent while a person decides.
    alt user allows once
        U->>W: Apply
        W->>P: decision allow_once
        P->>G: Record a grant for session, tool, argument digest
        P-->>A: outcome selected, optionId once
        A->>G: The tool call arrives through the facade, the grant matches, the change is applied
        A->>P: tool_call_update completed, without title, kind or input
    else user rejects
        U->>W: Reject
        W->>P: decision deny
        P-->>A: outcome selected, optionId reject
        A->>P: tool_call_update failed, the user rejected permission
        A-->>P: session/prompt response, end_turn, no text
        P->>T: Turn ended after a rejection
        T->>T: Outcome declined. No continue prompt, no audit.
    else user stops the turn
        U->>W: Stop
        P->>A: session/cancel
        P-->>A: outcome cancelled for every pending request
        A-->>P: session/prompt response, stopReason cancelled
    else the tool call arrives with no grant
        A->>G: Mutating call, verdict ask, no matching grant
        G-->>A: Not applied. Sequence 2 takes over.
    else server restarts while pending
        Note over P,A: The request died with the process. Approval is expired, never assumed.
    end
```

## Sequence 5 Settling a turn

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#E4EAFE','primaryTextColor':'#263449','primaryBorderColor':'#8292AD','lineColor':'#7B8798','secondaryColor':'#E2F2EA','tertiaryColor':'#FFF1D6','actorBkg':'#E4EAFE','actorBorder':'#8292AD','noteBkgColor':'#FFF1D6','noteBorderColor':'#AA9773','activationBkgColor':'#E2F2EA','activationBorderColor':'#7F9A8C','labelBoxBkgColor':'#E2F2EA','labelBoxBorderColor':'#7F9A8C'}}}%%
sequenceDiagram
    autonumber
    participant A as Agent
    participant T as TurnService
    participant V as Supervisor, pure
    participant J as Stores
    participant W as Web app

    A-->>T: session/prompt response, stopReason and usage
    T->>J: usage_pass row for this pass
    alt stopReason is refusal, max_tokens or max_turn_requests
        T->>J: Turn ends with that outcome, no audit
    else end_turn
        T->>J: Read invocations, changes, operations of the turn
        T->>V: decide(prompt, answer, ledgers, passes, budget left)
        alt a change or operation is still waiting
            V-->>T: PAUSE
            T->>J: turn.paused with the ids
        else every mutation has a later successful observation and quoted values match
            V-->>T: DONE with grades
            T->>J: evidence rows, turn.completed
        else a quoted value contradicts the recorded result
            V-->>T: BLOCKED, contradicted
            T->>J: evidence rows, turn.blocked with both values
        else something is unproven and passes and budget remain
            V-->>T: AUDIT
            T->>A: session/prompt with the audit instruction
        else budget would be exceeded
            V-->>T: BLOCKED, budget
            T->>J: budget.reached
        end
    end
    J-->>W: Events
```

## Session and agent process states

The session outlives its agent process. Two charts, because conflating them is what made idle sessions
hold processes ([reaper.py](../../apps/coding-agent/api/domain/reaper.py)).

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#E4EAFE','primaryTextColor':'#263449','primaryBorderColor':'#8292AD','lineColor':'#7B8798','secondaryColor':'#E2F2EA','tertiaryColor':'#FFF1D6'}}}%%
stateDiagram-v2
    direction LR
    [*] --> Open: created, probed
    Open --> Working: turn accepted
    Working --> Open: turn settled
    Working --> Waiting: turn paused on a change or an operation
    Waiting --> Working: decision or wake-up queues a turn
    Waiting --> Open: user dismisses what was waiting
    Working --> NeedsRestore: agent failed, restart, credential expired
    Waiting --> NeedsRestore: restart with nothing recoverable in memory
    NeedsRestore --> Open: user restores
    Open --> Archived: user closes, resources acknowledged
    Waiting --> Archived: user closes, chooses what to cancel
    NeedsRestore --> Archived: user closes
    Archived --> [*]

    classDef progress fill:#E4EAFE,stroke:#8292AD,color:#263449
    classDef good fill:#E2F2EA,stroke:#7F9A8C,color:#263449
    classDef wait fill:#FFF1D6,stroke:#AA9773,color:#263449
    classDef bad fill:#FFE3E0,stroke:#B98A84,color:#263449
    class Working progress
    class Open,Archived good
    class Waiting wait
    class NeedsRestore bad
```

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#E4EAFE','primaryTextColor':'#263449','primaryBorderColor':'#8292AD','lineColor':'#7B8798','secondaryColor':'#E2F2EA','tertiaryColor':'#FFF1D6'}}}%%
stateDiagram-v2
    direction LR
    [*] --> Absent
    Absent --> Starting: first prompt, or restore
    Starting --> Refused: version not supported, or capability missing
    Starting --> Ready: initialize and session/new or resume
    Ready --> Prompting: session/prompt
    Prompting --> Ready: response with a stop reason
    Prompting --> Silent: no update within the applicable limit
    Silent --> Prompting: update arrives before the limit
    Silent --> Dead: limit exceeded, stderr line captured
    Prompting --> Dead: process exit, or pipe closed
    Ready --> Absent: idle release, state freed
    Dead --> Absent: bookkeeping removed
    Refused --> Absent

    classDef progress fill:#E4EAFE,stroke:#8292AD,color:#263449
    classDef good fill:#E2F2EA,stroke:#7F9A8C,color:#263449
    classDef wait fill:#FFF1D6,stroke:#AA9773,color:#263449
    classDef bad fill:#FFE3E0,stroke:#B98A84,color:#263449
    class Starting,Prompting progress
    class Ready,Absent good
    class Silent wait
    class Refused,Dead bad
```

"The applicable limit" is the tool limit while a tool call is in progress, the model limit otherwise,
and unlimited while a human decision is pending ([AG-21](03-requirements.md#ag-21)).

## Turn states

Three additions to today's machine in [session.py](../../apps/coding-agent/api/domain/session.py):
`Paused`, stop reasons as distinct ends, and `Declined` for a turn the owner ended by rejecting a change.

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#E4EAFE','primaryTextColor':'#263449','primaryBorderColor':'#8292AD','lineColor':'#7B8798','secondaryColor':'#E2F2EA','tertiaryColor':'#FFF1D6'}}}%%
stateDiagram-v2
    [*] --> Queued: accepted, committed with its retry key
    Queued --> Running: slot and budget available
    Queued --> Cancelled: stop
    Queued --> Interrupted: preceding turn failed or restart
    Running --> Auditing: answer given, something unproven
    Auditing --> Running: audit pass prompts again
    Running --> Paused: waiting on a change or an operation
    Auditing --> Paused: same
    Running --> Completed: proven, or nothing to prove
    Auditing --> Completed: proven
    Running --> Blocked: unproven after passes, contradicted, or budget
    Auditing --> Blocked: same
    Running --> Refused: stop reason refusal
    Running --> Declined: the owner rejected a change and the agent ended the turn
    Running --> Truncated: stop reason max_tokens or max_turn_requests
    Running --> Cancelled: stop
    Running --> Failed: agent or model error
    Running --> Interrupted: restart, or credential expired
    Paused --> Completed: what it waited for settled and was acknowledged
    Paused --> Cancelled: stop, or session closed
    Completed --> [*]
    Blocked --> [*]
    Refused --> [*]
    Declined --> [*]
    Truncated --> [*]
    Cancelled --> [*]
    Failed --> [*]
    Interrupted --> [*]

    classDef progress fill:#E4EAFE,stroke:#8292AD,color:#263449
    classDef good fill:#E2F2EA,stroke:#7F9A8C,color:#263449
    classDef wait fill:#FFF1D6,stroke:#AA9773,color:#263449
    classDef bad fill:#FFE3E0,stroke:#B98A84,color:#263449
    class Queued,Running,Auditing progress
    class Completed,Declined good
    class Paused wait
    class Blocked,Refused,Truncated,Cancelled,Failed,Interrupted bad
```

A wake-up does not resume a paused turn; it creates the next one, whose `origin` is the change or
operation. The paused turn completes when that next turn is accepted. This keeps "one prompt, one turn"
and the retry-key rule intact.

## Change states

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#E4EAFE','primaryTextColor':'#263449','primaryBorderColor':'#8292AD','lineColor':'#7B8798','secondaryColor':'#E2F2EA','tertiaryColor':'#FFF1D6'}}}%%
stateDiagram-v2
    [*] --> Planned: handler.plan succeeded
    Planned --> Refused: verdict deny
    Planned --> AwaitingReview: verdict ask
    Planned --> Applying: verdict allow
    AwaitingReview --> Applying: user applies, or a matching grant exists
    AwaitingReview --> Rejected: user rejects
    AwaitingReview --> Expired: turn cancelled, session closed, or restart
    Applying --> Applied: write confirmed, new revision stored
    Applying --> Conflicted: base revision moved
    Applying --> Failed: workspace refused
    Applying --> Unknown: response lost, or crash before confirmation
    Unknown --> Applied: lookup finds the planned content
    Unknown --> Failed: lookup finds the base content
    Unknown --> Conflicted: lookup finds neither
    Applied --> Verified: later successful observation of the asset
    Applied --> Reverted: undo, asset still at the new revision
    Verified --> Reverted: undo, asset still at the new revision
    Applied --> Superseded: a later change to the same asset applied
    Verified --> Superseded: same
    Refused --> [*]
    Rejected --> [*]
    Expired --> [*]
    Failed --> [*]
    Conflicted --> [*]
    Reverted --> [*]
    Superseded --> [*]
    Verified --> [*]

    classDef progress fill:#E4EAFE,stroke:#8292AD,color:#263449
    classDef good fill:#E2F2EA,stroke:#7F9A8C,color:#263449
    classDef wait fill:#FFF1D6,stroke:#AA9773,color:#263449
    classDef bad fill:#FFE3E0,stroke:#B98A84,color:#263449
    class Planned,Applying progress
    class Applied,Verified,Reverted,Superseded good
    class AwaitingReview,Unknown wait
    class Refused,Rejected,Expired,Failed,Conflicted bad
```

Invariants, each a test:

- Nothing is written in `Planned`, `AwaitingReview`, `Refused`, `Rejected` or `Expired`.
- `Applying` is entered at most once per change.
- `Unknown` is left only by a read, never by a second write.
- Undo from `Superseded` is refused: the asset is no longer at this change's revision.

## Operation states

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#E4EAFE','primaryTextColor':'#263449','primaryBorderColor':'#8292AD','lineColor':'#7B8798','secondaryColor':'#E2F2EA','tertiaryColor':'#FFF1D6'}}}%%
stateDiagram-v2
    [*] --> Submitting: row written before the remote call
    Submitting --> Running: native id stored
    Submitting --> Rejected: workspace refused
    Submitting --> Unknown: response lost, or crash
    Unknown --> Running: lookup by run name or statement tag finds it
    Unknown --> NotStarted: lookup finds nothing after the grace period
    Running --> Running: newer observation, state version advances
    Running --> Unobserved: delegated credential expired, or workspace unreachable
    Unobserved --> Running: credential refreshed, observation resumes
    Unobserved --> Succeeded: observed terminal on return
    Unobserved --> Failed: observed terminal on return
    Running --> Succeeded: terminal success
    Running --> Failed: terminal failure, per-task errors stored
    Running --> Cancelling: user or stop
    Cancelling --> Cancelled: workspace confirms
    Cancelling --> Succeeded: finished before the cancel landed
    Cancelling --> Failed: same
    Succeeded --> [*]
    Failed --> [*]
    Cancelled --> [*]
    Rejected --> [*]
    NotStarted --> [*]

    classDef progress fill:#E4EAFE,stroke:#8292AD,color:#263449
    classDef good fill:#E2F2EA,stroke:#7F9A8C,color:#263449
    classDef wait fill:#FFF1D6,stroke:#AA9773,color:#263449
    classDef bad fill:#FFE3E0,stroke:#B98A84,color:#263449
    class Submitting,Running,Cancelling progress
    class Succeeded good
    class Unknown,Unobserved wait
    class Failed,Cancelled,Rejected,NotStarted bad
```

Invariants:

- A row never returns to `Submitting`. There is no automatic resubmission from any state.
- `Unobserved` is not an outcome. The interface shows the last seen state and time.
- A wake-up fires on entry to `Succeeded`, `Failed` or `Cancelled`, once.
- An observation with a lower `state_version` is dropped.

## Approval states

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#E4EAFE','primaryTextColor':'#263449','primaryBorderColor':'#8292AD','lineColor':'#7B8798','secondaryColor':'#E2F2EA','tertiaryColor':'#FFF1D6'}}}%%
stateDiagram-v2
    direction LR
    [*] --> Pending: change needs a person, or the agent asked
    Pending --> Allowed: owner allows once or for the session
    Pending --> Denied: owner denies
    Pending --> Cancelled: turn stopped
    Pending --> Expired: restart, session closed, or credential expired
    Allowed --> [*]
    Denied --> [*]
    Cancelled --> [*]
    Expired --> [*]

    classDef good fill:#E2F2EA,stroke:#7F9A8C,color:#263449
    classDef wait fill:#FFF1D6,stroke:#AA9773,color:#263449
    classDef bad fill:#FFE3E0,stroke:#B98A84,color:#263449
    class Pending wait
    class Allowed good
    class Denied,Cancelled,Expired bad
```

A second decision on a decided approval is a 409, as today. "For the session" is stored as a grant with
a scope the user can read (tool and asset), and it never covers the irreversible class.

## Mode and budget

| From | To | When | Effect |
|---|---|---|---|
| new session | Review | At creation | The default (D19). Sessions created before this change keep Auto, which is what they do today. |
| any mode | any mode | Between tool calls, by the owner | Tool catalogue recomputed; the agent's permission configuration regenerated and, for Plan, its own `mode` option set; the agent is told in the next tool reply; `mode.changed` recorded |
| Auto | Review | Automatically, when a change conflicts twice on the same asset in one turn | The agent is fighting a human edit; stop applying and show both |
| within budget | reached | The next pass would exceed the limit | No new pass starts; turn ends `Blocked` with reason budget; waiting changes and running operations are untouched |
| reached | within budget | Owner raises the limit | A continuation may be sent |
