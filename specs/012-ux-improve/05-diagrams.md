[Index](README.md) · prev: [04 Wireframes](04-wireframes.md) · next: [06 Lenses](06-lenses.md)

# 05 · Diagrams

Mermaid only, because these are state machines, sequences and data models rather than geometry. The
wireframes are ASCII in [04](04-wireframes.md).

---

## 1. The contradiction, drawn as two state machines that disagree

This is the whole finding in one picture. The **left** machine is what the connection actually does.
The **right** machine is what the composer believes. They are different machines, and the only
coupling between them is a single boolean.

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#E8F0FE','primaryTextColor':'#1F2937','primaryBorderColor':'#A8C0E8','lineColor':'#94A3B8'}}}%%
stateDiagram-v2
    direction LR
    state "Connection (measured)" as C {
        [*] --> idle
        idle --> connecting: EventSource opened
        connecting --> live: onopen
        connecting --> reconnecting: onerror
        live --> reconnecting: onerror
        reconnecting --> live: visibilitychange / online
        reconnecting --> terminal: non-200 (404/409)
        note right of terminal
            The browser will not retry a non-200.
            The hook has no timer.
            Nothing moves this state.
        end note
    }

    state "Composer (before)" as K {
        [*] --> writable
        writable --> dead: conn ≠ live
        dead --> writable: conn = live
        note right of dead
            `disabled` → the textarea is
            UNFOCUSABLE. No keyboard, no
            screen reader, no reason shown.
        end note
    }
    terminal --> dead: the same boolean
```

**The incoherence, in one sentence:** the connection has a state the composer cannot escape, and the
composer has a state the connection cannot announce.

---

## 2. The corrected state machine

Three machines now, each with one job: the stream reports, the session stays writable, and a single
function decides what the box looks like.

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#E6F4EA','primaryTextColor':'#1F2937','primaryBorderColor':'#A8D5B5','lineColor':'#94A3B8'}}}%%
stateDiagram-v2
    [*] --> idle
    idle --> connecting: session opened
    connecting --> live: onopen
    connecting --> reconnecting: onerror (retryable)
    connecting --> closed: onerror (404/409/422)
    live --> reconnecting: stream dropped
    reconnecting --> live: onopen
    reconnecting --> closed: reason is terminal
    closed --> connecting: user clicks Retry
    note right of reconnecting
        Bounded backoff: 1,2,4,8,15 s.
        Visible "Retry now" from the first
        failure. [ST-3] [ST-4]
    end note
    note right of closed
        A stated reason plus TWO actions:
        Retry · New conversation. [ST-4]
    end note
```

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#FFF8E1','primaryTextColor':'#1F2937','primaryBorderColor':'#F2D98D','lineColor':'#94A3B8'}}}%%
stateDiagram-v2
    direction LR
    state "Composer presentation" as P {
        [*] --> writable
        writable --> blocked: archived OR requires-resume
        blocked --> writable: session reopened
        note right of blocked
            readOnly + aria-disabled
            focusable, explains itself
        end note
    }
    note left of P
        conn is NOT an input to this machine.
        It cannot disable the box. [FX-1] [P1]
    end note
```

---

## 3. Sequence: typing during `connecting` — before and after

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#FDE7EF','primaryTextColor':'#1F2937','primaryBorderColor':'#F2B5CB','lineColor':'#94A3B8'}}}%%
sequenceDiagram
    autonumber
    actor U as User
    participant D as Dock
    participant H as useSessionStream
    participant S as Server

    U->>D: page painted, composer visible
    Note over H: conn = "idle"
    D->>D: canSend = false → textarea disabled
    U->>D: click + type "chart the trips"
    Note over D: a disabled field takes no focus<br/>keystrokes go to &lt;body&gt;
    U->>D: click again, type again
    D--xU: nothing. No error, no reason. **[F1]**
    H->>S: GET /stream (still connecting)
    S-->>H: 200 text/event-stream
    H->>D: conn = live
    D->>D: canSend = true
    Note over U,D: 205 ms too late. The sentence is gone.
```

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#E6F4EA','primaryTextColor':'#1F2937','primaryBorderColor':'#A8D5B5','lineColor':'#94A3B8'}}}%%
sequenceDiagram
    autonumber
    actor U as User
    participant D as Dock
    participant H as useSessionStream
    participant S as Server

    U->>D: page painted
    Note over D: presentation = writable (conn is not an input)
    U->>D: type "chart the trips"
    D-->>U: text appears immediately
    H->>S: GET /stream
    Note over U: no window in which a keystroke is lost. **[FX-1]**
    S-->>H: 200
    H->>D: conn = live
    U->>D: ⏎
    D->>S: POST /messages (idempotency key)
    S-->>D: 202 accepted
```

---

## 4. Sequence: a refused stream, and the dead end it creates

Measured with `deadend-probe.mjs`. This is the screenshot's screen.

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#FDE7EF','primaryTextColor':'#1F2937','primaryBorderColor':'#F2B5CB','lineColor':'#94A3B8'}}}%%
sequenceDiagram
    autonumber
    actor U as User
    participant D as Dock
    participant H as useSessionStream
    participant S as Server

    U->>D: open #/session/6c2c42d4
    D->>H: subscribe
    H->>S: GET /stream?after=0
    S-->>H: 404 no such session
    H->>D: conn = reconnecting
    Note over H: EventSource readyState = CLOSED.<br/>The browser will not retry a non-200.
    D->>D: canSend = false → disabled
    D->>D: RunStatus buttons: disabled (conn ≠ live)
    U->>D: click the box
    D--xU: unfocusable. **[F1]**
    U->>D: press Esc / Retry / anything
    D--xU: no control exists. **[F3]**
    Note over U,S: "reconnecting…" is the final word.<br/>The screen recommends leaving: "Copy return link". **[F2]**
```

---

## 5. Sequence: the correction — bounded retry, then a stated exit

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#E6F4EA','primaryTextColor':'#1F2937','primaryBorderColor':'#A8D5B5','lineColor':'#94A3B8'}}}%%
sequenceDiagram
    autonumber
    actor U as User
    participant D as Dock
    participant H as useSessionStream
    participant S as Server

    H->>S: GET /stream?after=41
    S-->>H: 503 (retryable)
    H->>H: schedule retry in 1 s
    H->>D: conn = reconnecting · action = "Retry now"
    U->>D: type "keep this sentence"  (box is live)
    D-->>U: text appears
    H->>S: GET /stream?after=41 (retry 2)
    S-->>H: 200
    H->>D: conn = live · replay from seq 41
    Note over U: nothing was lost: not the sentence,<br/>not the transcript. **[ST-3] [ST-6]**

    rect rgb(253, 231, 239)
    Note over H,S: the terminal branch
    H->>S: GET /stream?after=41
    S-->>H: 404 (not retryable)
    H->>D: conn = closed · reason = "this session is gone"
    D-->>U: [Retry] [New conversation] + readOnly box that explains **[ST-4]**
    end
```

---

## 6. Sequence: Escape, as designed vs. as wired

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#FFF8E1','primaryTextColor':'#1F2937','primaryBorderColor':'#F2D98D','lineColor':'#94A3B8'}}}%%
sequenceDiagram
    autonumber
    actor U as User
    participant W as window keydown
    participant R as resolve()
    participant T as escapeTarget()
    participant A as App.stop handler

    U->>W: Esc, focus in the notebook, rail drawer open
    W->>R: comboOf = "escape", ctx.cell = true
    Note over R: SHORTCUTS has stop with owner="composer"<br/>keys.ts:236 → not a cell owner → **null**
    R--xA: never dispatched
    Note over U,A: the drawer stays open. Esc did nothing. **[F5]**

    rect rgb(230, 244, 234)
    Note over U,A: the correction
    U->>W: Esc
    W->>T: escapeTarget({dialog,popover,drawer,edit,running})
    T-->>W: "drawer"
    W->>A: close the drawer
    end
```

---

## 7. E/R: where state actually lives

The reason the fix is contained: presentation state is derived, and the only persisted facts are the
four the app already versions.

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#E8F0FE','primaryTextColor':'#1F2937','primaryBorderColor':'#A8C0E8','lineColor':'#94A3B8'}}}%%
erDiagram
    WORKSPACE_SCOPE ||--o{ DOC : "working set"
    WORKSPACE_SCOPE ||--|| LAYOUT : "geometry"
    SESSION ||--o{ TURN : "journal"
    SESSION ||--o{ APPROVAL : "pending"
    SESSION ||--|| STREAM_STATE : "derived, not stored"
    TURN ||--o{ TOOL_CALL : "evidence"

    WORKSPACE_SCOPE {
        string origin_key PK "origin|host|user"
    }
    LAYOUT {
        int railWidth
        int inspectorWidth
        int assistantWidth
        bool railVisible
        bool inspectorVisible
        bool assistantVisible
        string railTab
        int version "1|2"
    }
    SESSION {
        string id PK
        string folder
        string status "ready|streaming|archived"
        bool requiresResume
        string persistence "durable|memory"
    }
    STREAM_STATE {
        string state "idle|connecting|live|reconnecting|closed"
        string reason "optional"
        int attempt
    }
    TURN {
        string id PK
        int index
        string status
    }
    APPROVAL {
        string approvalId PK
        string outcome "null|allowed|denied"
    }
    TOOL_CALL {
        string callId PK
        string state
    }
```

`STREAM_STATE` is dashed-in on purpose: it is **derived** and must never be written to storage. The
defect began when a derived fact (the connection) was allowed to become a persisted-looking
permission (whether the box works).

---

## 8. Sequence: hard refresh with a cell deeplink

Measured PASS — recorded because it must stay passing ([LK-1], [LK-3]).

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#E8F0FE','primaryTextColor':'#1F2937','primaryBorderColor':'#A8C0E8','lineColor':'#94A3B8'}}}%%
sequenceDiagram
    autonumber
    actor U as User
    participant B as Browser
    participant A as App
    participant L as localStorage
    participant S as Server

    U->>B: paste .../#/notebook/Users/me/nb?cell=3, Enter
    B->>A: cold load, no memory
    A->>A: parseRoute(hash) → doc + cell 3
    A->>L: read layout (v2 → clamp to viewport)
    A->>S: GET /api/notebook?path=…
    S-->>A: cells
    A->>A: openDoc, setFocus(cell 3), scroll into view
    A-->>U: the notebook, at cell 3, geometry restored
    Note over A: useRoute's write is deferred until the first<br/>apply has run, so the link is not overwritten
```
