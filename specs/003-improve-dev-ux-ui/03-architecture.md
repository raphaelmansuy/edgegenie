# 03 · Architecture

[Index](README.md) · prev: [02 Requirements](02-requirements.md) · next: [04 Lenses](04-lenses.md)

The design in one sentence: **the document is pure data, the editor is an uncontolled view of that
data that owns its own state, and every write — human or agent — passes one policy function before
touching the workspace.**

---

## Screen wireframe

The editing surface lives in the **centre zone** as a second work surface beside the transcript.
No new zone is added: [001-perfect-shell](../001-perfect-shell/03-architecture.md#zone-model)
established four zones, and a fifth would multiply states without adding capability.

```
┌─ CHROME ─────────────────────────────────────────────────────────────────────────────────────────┐
│ ◧ Databricks Coding Agents    [▣] [▤] [sys|light|dark]   ⌘K   ⌘   ⟳                              │
├─ WORKBENCH ──────────────────────────────────────────────────────────────────────────────────────┤
│┌────────────────────────┐ ┌─ DOC TABS ───────────────────────────────┐ ┌────────────────────────┐│
││ Sess Files Catalog     │ │ ◆ Chat │ ▪ taxi_hours × │ ▪ notes × │+2  │ │ Context  Audit         ││
││                        │ └──────────────────────────────────────────┘ │                        ││
││ + New        RECENT    │ ┌─ EDITOR BAR ─────────────────────────────┐ │ CELL 3 / 9             ││
││                        │ │ taxi_hours.py  py  ⌂ fence ✓             │ │ ────────────────────── ││
││ ▾ samples              │ │                   [Run] [Diff] [Save]    │ │ what it does           ││
││     ▸ nyctaxi          │ └──────────────────────────────────────────┘ │ reads 1 table          ││
││     ▸ tpcds            │ ┌─ CODE ───────────────────────────────────┐ │ ran ✓ 4.2s · 24 rows   ││
││ ▸ /Users/raph…         │ │ 1 │ %python                              │ │ agent wrote this cell  ││
││                        │ │ 2 │ import pandas as pd                  │ │                        ││
││ ◆ revenue    12m       │ │ 3 │ df = spark.table("samples.ny         │ │ FENCE                  ││
││ ◆ hello       3d       │ │ 4 │ df.groupBy("pickup_hour").av         │ │ ✓ inside               ││
││ ◆ debug job    1h      │ │ 5 │                                      │ │   /agent_scratch/      ││
│└────────────────────────┘ └──────────────────────────────────────────┘ │                        ││
│                           ┌─ COMPOSER ───────────────────────────────┐ │ ⌘S   save              ││
│                           │ Ask, or ⇧⌘K to edit this cell...    ⌘↵   │ │ ⌘↵   run cell          ││
│                           └──────────────────────────────────────────┘ │ ⌘/   shortcuts         ││
│                                                                        └────────────────────────┘│
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

┌─ DOC TABS ───────────────────────────────────────────────────────────────────────────────────────┐
│  ◆ Chat │ ▪ taxi_hours  ● ×  │ ▪ notes.md × │ +3                                                 │
├─ EDITOR BAR ─────────────────────────────────────────────────────────────────────────────────────┤
│  taxi_hours   notebook   py   9 cells   ⌂ in fence ✓    [Run all] [Diff] [Save]                  │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ┌──────────────────────────────────────────────────────────────────────────────────────────────┐ │
│ │ [md]                                        [⋯] [🗑]                                          │ │
│ │ # Revenue by pickup hour                                                                     │ │
│ │ Renders as prose when unfocused; click to edit.                                              │ │
│ └──────────────────────────────────────────────────────────────────────────────────────────────┘ │
│ ┌──────────────────────────────────────────────────────────────────────────────────────────────┐ │
│ │ ▶ [py]                                      [⋯] [🗑]                                          │ │
│ │ 1 │ df = spark.table("samples.nyctaxi.trips")                                                │ │
│ │ 2 │ df.groupBy("pickup_hour").avg("fare").show()                                             │ │
│ │ ── agent wrote this cell · ran 4.2s · 24 rows ──                                             │ │
│ └──────────────────────────────────────────────────────────────────────────────────────────────┘ │
│ ┌──────────────────────────────────────────────────────────────────────────────────────────────┐ │
│ │ ▶ [py]                                   ┌ caret ┐                                           │ │
│ │ 3 │ ▏                                                                                        │ │
│ └──────────────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                                  │
│                                   [ + code ]        [ + markdown ]                               │
│                                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Reading the fence before you type

WR-5 requires the fence to be visible **before** the first keystroke, not at save time. It is a
chip in the editor bar, and it has three states:

```
  ⌂ in fence ✓          →  writable, save enabled
  ⚠ outside fence       →  save asks for approval (and says which folder you are in)
  ◼ read-only           →  no save at all: too large, or the object is not writable
```

---

## Component model

```mermaid
classDiagram
    direction TB
    class Doc {
        +string id
        +DocKind kind
        +string ref
        +string name
        +number rev
    }
    class DocumentModel {
        <<pure>>
        +parseSource(text, lang) Cell[]
        +serialize(cells, lang) string
        +normalize(cells) Cell[]
    }
    class Cell {
        +string id
        +CellKind kind
        +string language
        +string source
    }
    class EditSession {
        +string docId
        +string version
        +boolean dirty
        +number caret
        +draft()
        +revert()
    }
    class Fence {
        <<pure>>
        +checkPath(scope, path) Decision
        +checkSql(scope, sql) Decision
    }
    class EditorHost {
        +mount(el)
        +getValue() string
        +setValue(s)
        +onChange(cb)
        +onCellMeta(cb)
    }
    class SaveClient {
        +save(doc, text, version) Result
        +conflict(a, b) Diff
    }

    Doc --> DocumentModel : parsed by
    DocumentModel --> Cell : produces
    EditSession --> Doc : tracks
    EditSession --> EditorHost : owns
    SaveClient --> Fence : asks
    SaveClient --> EditSession : reads
```

**Why `EditorHost` is an interface, not the CodeMirror type.** The rest of the app must not import
CodeMirror. Everything it needs is this five-method surface, so the editor can be swapped (or
mocked in a unit test) without touching a single component. This is the Dependency Inversion in
[04](04-lenses.md#2-full-stack-developer).

---

## The document model

`Cell` already exists and is pure (`api/domain/notebook.py`). It gains an `id`, which is what makes
A5 possible:

```ts
// web/src/domain/notebook.ts — the pure core, no React, no CodeMirror

export type CellKind = "code" | "markdown";
export interface Cell {
  id: string;          // stable across reorder; derived at parse, kept afterwards
  kind: CellKind;
  language: string;    // "python" | "sql" | "scala" | "r" | "markdown" | "shell" | ...
  source: string;
}

export function parseCells(text: string, language: string): Cell[];
export function serializeCells(cells: readonly Cell[]): string;
export function moveCell(cells: readonly Cell[], from: number, to: number): Cell[];
export function setCellKind(cells: readonly Cell[], id: string, kind: CellKind): Cell[];
export function insertCell(cells: readonly Cell[], at: number, cell: Cell): Cell[];
export function removeCell(cells: readonly Cell[], id: string): Cell[];
```

The round trip is the contract:

```
serializeCells(parseCells(t)) ≡ t        for every SOURCE document t we can read
parseCells(serializeCells(c)) ≡ c        up to id regeneration, for every cell list c we can build
```

The first is a property test over real notebooks from the workspace; the second is a property test
over generated cell lists. Both must hold, because a violation means opening and saving a notebook
silently rewrites it — the worst possible bug in an editor.

### Why `id` cannot be the index

A move changes every index in the tail. If `id` were the index, then:

```
move(5 → 1)  ⇒  cells 5,4,3,2 all appear "changed"  ⇒  diff says 4 edits, not 1 move
```

With a content+position key at parse and a preserved key thereafter, a move is one operation and the
diff can say "moved". This is A5, and it is why `parseCells` attaches ids in a second pass rather
than treating them as data.

---

## The edit path (no React in the keystroke)

This is the single most important diagram in the spec. A3 says a keystroke must not re-render
anything but the editor.

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant CM as EditorHost (CodeMirror)
    participant ES as EditSession
    participant LS as localStorage
    participant API as FastAPI
    participant SC as SaveClient
    participant F as Fence (scope.py)

    U->>CM: keystroke
    CM->>CM: update EditorState (its own document)
    CM-->>ES: onChange(value) debounced 150ms
    ES->>ES: dirty = true
    ES->>LS: write draft(docId, value, version)
    Note over CM,ES: React is NOT in this loop.<br/>No component re-renders per keystroke.

    U->>SC: ⌘S
    SC->>ES: current value + held version
    SC->>F: checkPath(scope, path)
    alt inside fence
        F-->>SC: ALLOW
        SC->>API: POST /api/workspace/save {path, text, version}
        API->>F: checkPath (authority, again)
        API->>API: compare version
        API-->>SC: 200 {version}
        SC->>ES: clean, new version
    else outside fence
        F-->>SC: ASK
        SC->>U: approval sheet (path + reason)
        U->>SC: allow once
        SC->>API: POST with approval token
    end
```

### Why the client check exists at all

WR-1 makes the server authoritative. So why duplicate? Because the fence has to **explain itself**
before a round trip: "this path is outside `/agent_scratch/`, saving will ask for approval" is useful
information at the moment of typing, and useless as a `403` after a 300 ms pause. The client check is
a **preview of a decision it cannot make**. If they ever disagree, the server wins — and that
disagreement is a logged defect, not a tolerated case.

---

## The write path

Three callers, one policy function. This is the whole point of the spec.

```mermaid
flowchart LR
    subgraph callers["three callers"]
        A1["agent tool<br/>dbx_write_notebook"]
        A2["agent tool<br/>dbx_write_file"]
        H1["human save<br/>POST /api/workspace/save"]
    end

    subgraph policy["one policy (pure, tested)"]
        CP["scope.check_path"]
        CS["scope.check_sql"]
    end

    subgraph outcome["one outcome vocabulary"]
        AL["ALLOW"]
        AS["ASK → approval"]
        DN["DENY"]
    end

    WS[("Databricks<br/>workspace API<br/>import / export")]

    A1 --> CP
    A2 --> CP
    H1 --> CP
    CP --> AL
    CP --> AS
    CP --> DN
    AL --> WS
    AS -->|"human approves"| WS
    DN -.->|"refused"| X["403 to caller"]

    A1 -.->|"read-only SQL path"| CS
```

The rule that makes this safe: **`H1` must be indistinguishable from `A1`/`A2` from the policy's point
of view.** Same function, same `Scope`, same `Decision` type, same event recorded. A test asserts
this by calling all three with the same path and requiring identical verdicts.

### The save route

```python
# api/routers/api.py — sketch, not final
class SaveObject(BaseModel):
    path: str = Field(min_length=1, max_length=1024)
    text: str
    format: Literal["SOURCE", "AUTO"] = "SOURCE"
    version: str | None = None          # CX-1: the token the client held
    approval_id: str | None = None      # WR-3: present when the fence said ASK

@router.post("/workspace/save")
async def workspace_save(request: Request, body: SaveObject) -> dict:
    scope = _scope(request)
    decision = scope_mod.check_path(scope, body.path)      # WR-1: the same function
    if decision.verdict is Verdict.ASK and not _approval_valid(request, body.approval_id, body.path):
        raise HTTPException(403, f"{decision.reason} — approval required")
    current = await _browser(request).status(body.path, _user_token(request))
    if body.version and body.version != _version_of(current):   # CX-2
        raise HTTPException(409, {"current": _version_of(current), "yours": body.version})
    await _browser(request).import_source(body.path, body.text, _user_token(request), overwrite=True)
    await _record_human_write(request, body.path, len(body.text))  # WR-4
    return {"version": _version_of(await _browser(request).status(body.path, _user_token(request)))}
```

Every line here is a requirement: `check_path` (WR-1), the approval gate (WR-3), the version
comparison (CX-2), the event record (WR-4). The route contains no path logic of its own.

---

## Concurrency: what we can and cannot promise

The workspace API has **no conditional write** ([01](01-current-state-audit.md#what-the-databricks-workspace-api-gives-us)).
So:

```
time ──────────────────────────────────────────────────────────────────►
  get-status ──── compare ──── import          ← our window: TOCTOU, unavoidable
                   ▲
                   └── another writer can land here, between our check and our write
```

We therefore make three honest promises and no fourth:

| Promise | How | Test |
|---|---|---|
| A conflicting save is **detected** in the overwhelming majority of cases | version compare immediately before import | CX-2 |
| A detected conflict is **never auto-resolved** | 409 → user chooses | CX-3 |
| An undetected conflict is **always recoverable** | local draft of every buffer, plus the pre-save snapshot | CX-5 |

We explicitly **do not** promise "no lost writes", because we cannot keep it. Saying so in the UI —
"your version was saved locally" — is more honest than a lock that does not hold.

```mermaid
stateDiagram-v2
    [*] --> Clean
    Clean --> Dirty: keystroke
    Dirty --> Saving: ⌘S
    Saving --> Clean: 200 (new version)
    Saving --> Conflict: 409
    Saving --> Dirty: network error (draft kept)
    Conflict --> Dirty: keep mine
    Conflict --> Clean: take theirs
    Conflict --> Reviewing: see diff
    Reviewing --> Dirty: accept some hunks
    Reviewing --> Clean: accept all
    Dirty --> DraftOnly: tab closed
    DraftOnly --> Dirty: reopened, restored
```

---

## Both writers, one model

A6 says the agent is a client of the document, not a privileged writer. Concretely:

```mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant ED as Editor (buffer v1)
    participant AG as Agent turn
    participant SRV as Server
    actor AP as Approval

    U->>ED: edits (dirty)
    Note over ED: buffer diverges from v1
    AG->>SRV: dbx_write_notebook(path, cells) → proposes
    SRV->>SRV: check_path → ALLOW (inside fence)
    SRV-->>U: proposal event: diff(v1 → v2), NOT applied
    U->>ED: review diff
    alt user accepts
        U->>ED: apply hunks (buffer = merge(buf, v2))
        U->>SRV: save (with version)
    else user rejects
        U->>ED: dismiss
        Note over ED: buffer unchanged, byte-identical
    end
```

The key decision: **an agent write inside the fence that targets a document the user has open
becomes a proposal rather than a silent write.** Outside that case it writes as it does today.
That is a change in agent behaviour, scoped narrowly, and it is what makes DF-1 true without
weakening the agent.

> Trade-off, stated: this makes the agent slightly less autonomous for open documents. It is worth
> it — "the agent changed the file while I was editing it and I lost my work" is the single failure
> users forgive least.

---

## Where each piece lives

| Piece | Path | Kind | Responsibility |
|---|---|---|---|
| Document model | `web/src/domain/notebook.ts` | pure | parse / serialize / cell ops |
| Fence preview | `web/src/domain/fence.ts` | pure | mirror of `scope.check_path` for display only |
| Version token | `web/src/domain/version.ts` | pure | derive + compare tokens |
| Diff algorithm | `web/src/domain/diff.ts` | pure | line + cell diffs, hunk apply/reject |
| Draft store | `web/src/domain/drafts.ts` | pure | key scheme, TTL, recovery |
| Editor host | `web/src/editor/host.ts` | adapter | the 5-method `EditorHost` over CodeMirror |
| Editor mount | `web/src/editor/Editor.tsx` | React | mounts the host, no per-keystroke state |
| Notebook surface | `web/src/components/NotebookEditor.tsx` | React | cell stack, focus model |
| Diff surface | `web/src/components/DiffView.tsx` | React | hunks, accept/reject |
| Save client | `web/src/api/save.ts` | adapter | talks to the route, maps 409 |
| Save route | `api/routers/api.py` | FastAPI | fence + version + import |
| Serialization | `api/domain/notebook.py` | pure | add `serialize_source` next to `parse_source` |
| Workspace write | `api/adapters/databricks/workspace.py` | adapter | `import_source`, `status` |

Three rules keep this DRY and SOLID ([04](04-lenses.md#solid-applied)):

1. **`domain/` never imports React or CodeMirror.** All of it is unit-testable without a DOM.
2. **One adapter per external system.** CodeMirror behind `EditorHost`; the workspace API behind
   `WorkspaceBrowser`. Swapping either touches exactly one file.
3. **The fence is never re-implemented.** `domain/fence.ts` is a *display* mirror, and a test asserts
   it agrees with the Python for a corpus of paths — if it drifts, the test fails, not the user.

---

## Sequence: opening a document

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant P as Palette (⌘P)
    participant APP as App
    participant API as FastAPI
    participant WS as Workspace API
    participant ED as EditorHost

    U->>P: type "taxi"
    P->>APP: open(notebook, /agent_scratch/taxi_hours)
    APP->>APP: doc tab created (immediate, no spinner)
    APP->>API: GET /workspace/object?path=…
    API->>WS: get-status + export
    WS-->>API: source text + objectId + language
    API-->>APP: {cells, text, version}
    APP->>ED: lazy import editor + mount (code-split)
    ED-->>U: caret placed, fence chip shown
    Note over ED: CLS must stay 0 — the pane is<br/>reserved before the editor mounts (UX-3)
```

---

## Mermaid: the state of a document as the app sees it

```mermaid
stateDiagram-v2
    [*] --> Closed
    Closed --> Loading: open(ref)
    Loading --> Ready: 200
    Loading --> Failed: 4xx/5xx (shows the error, keeps the tab)
    Ready --> Editable: inside fence
    Ready --> ReadOnly: outside fence, or too large
    Editable --> Dirty: keystroke
    Dirty --> Saving: ⌘S
    Saving --> Editable: saved
    Saving --> Conflict: 409
    Conflict --> Dirty: keep mine
    Conflict --> Editable: take theirs
    Editable --> Stale: agent proposes (diff available)
    Stale --> Editable: accept / reject
    Ready --> Closed: tab closed (draft kept)
    Dirty --> Closed: tab closed (draft kept)
```

[Next: the eight lenses →](04-lenses.md)
