# 06 — Statecharts and transition guards

[Index](README.md) · Requirements: [03](03-requirements.md) · Screens: [04](04-ux-wireframes.md)
· Risks: [09](09-edge-cases.md) · Tests: [11](11-tests-traceability.md)

## State vector

Do not replace the current local boolean with a larger boolean soup. Use a pure transition
function over an explicit view state, and keep independent facts separate:

`{cellId, documentKey, sourceRevision, mode, editorStatus, permission, composition, renderRevision}`.

`mode = read | edit`; collapse is orthogonal. Dirty/saving/conflict belongs to `EditorSurface`.
Media has its own request state. Focus identifies a target/control; it is not equivalent to mode.
All async messages carry document key + cell ID + source revision + request generation.
Accept a result only if its complete identity tuple still matches the live model.

## Interaction state

Outside Edit, the surface always interprets and styles Markdown. A short loading surface reserves
space while parsing; raw source is shown only in the labeled fallback after a render/load failure.
That fallback does not pretend to be a successful preview. Empty source is a styled empty state.

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#E7EEFF","primaryTextColor":"#243247","primaryBorderColor":"#879AB8","lineColor":"#7C899A","tertiaryColor":"#F1E9F8"}}}%%
stateDiagram-v2
  [*] --> ReadPending
  ReadPending --> ReadStyled: current revision parsed
  ReadPending --> ReadFallback: parser fails or limit reached
  ReadStyled --> EditLoading: explicit Edit and writable
  ReadFallback --> EditLoading: explicit Edit and writable
  EditLoading --> Editing: host ready and request current
  EditLoading --> ReadFallback: host load fails
  Editing --> Composing: IME composition starts
  Composing --> Editing: composition ends and flushes
  Editing --> ReadPending: Show preview or resolved Esc or eligible blur
  Editing --> ReadPending: permission revoked after source snapshot
  ReadStyled --> ReadPending: source revision changes
  classDef mint fill:#E4F3EA,stroke:#829F8B,color:#243247
  classDef lavender fill:#F1E9F8,stroke:#A18AB5,color:#243247
  classDef amber fill:#FFF1D9,stroke:#B49A6F,color:#243247
  class ReadStyled mint
  class Editing,Composing lavender
  class ReadFallback amber
```

The diagram is the primary lifecycle. Structural deletion/navigation disposes every state;
reopening begins a new generation. Conversion to code exits this machine and uses the code-cell
surface. A newly inserted writable + Text cell may take the explicit Edit transition immediately.

| Event/guard | Required behavior | Risks/tests |
|---|---|---|
| Enter on command-focused writable cell | Edit, restore last caret; consume no run request | E01, E05 / T01, T09 |
| Enter on child link/button, or modified shortcut | Let that control handle it; no parent edit | E05, E08 / T06, T09 |
| Double-click preview | Optional Edit shortcut only outside interactive children and active text selection | E05 / T01 |
| Show preview | Flush latest source once, snapshot selection/history, then parse | E04 / T02 |
| Esc with completion/search/dialog open | Close the innermost overlay first; remain Edit | E06 / T09 |
| Esc/preview during IME | Defer mode change until compositionend; never commit partial composition | E06 / T02 |
| Focus moves to formatting toolbar | Keep Edit and saved selection; never let blur discard host state | E03 / T02 |
| Focus moves outside the entire cell while document has focus | After composition/transaction settles, transition to read mode; do not save | E04 / T01 |
| Browser/window loses focus | Preserve Edit/selection; no synthetic preview or save | E07 / T12 |
| Read-only or permission revoked | Disable mutation commands at invocation time; retain unsaved source and offer Copy | E02, E35 / T10, T14 |
| Collapse current edit cell | Flush source first, keep undo state; next Expand opens styled read mode | E23 / T12 |
| Delete/reorder/external change while loading | Match identity, not array index; cancel obsolete work | E24, E25, E36 / T11, T12 |

## Save state

This is a model of the **existing document save owner**, not a second save implementation.
Source changes, not display transitions, mark Dirty. The representation checks run against the
original completeness metadata before serialization and then against the snapshot's round-trip.

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#E7EEFF","primaryTextColor":"#243247","primaryBorderColor":"#879AB8","lineColor":"#7C899A","tertiaryColor":"#FFF1D9"}}}%%
stateDiagram-v2
  [*] --> Clean
  Clean --> Dirty: source transaction
  Dirty --> Saving: Save and complete writable snapshot
  Dirty --> Blocked: truncated or unrepresentable
  Saving --> Clean: accepted and source still equals snapshot
  Saving --> Dirty: accepted but newer local edit exists
  Saving --> Conflict: version mismatch
  Saving --> SaveError: network or permission failure
  Conflict --> Dirty: user chooses a resolution
  SaveError --> Dirty: user reviews then retries
  Blocked --> Dirty: complete source explicitly reloaded
  Dirty --> Conflict: incoming agent edit requires review
  Clean --> Clean: preview or theme or link action
  classDef mint fill:#E4F3EA,stroke:#829F8B,color:#243247
  classDef rose fill:#F8E6EB,stroke:#B48D99,color:#243247
  class Clean mint
  class Conflict,SaveError,Blocked rose
```

Save error does not authorize overwriting a conflict or repeating an unknown write automatically.
Preview must not say Saved. Existing approval/fence outcomes stay with the document UI.
See [MD-12](03-requirements.md#requirements), [E26–E35](09-edge-cases.md#register).

## Media state

P0 renders the `NotLoaded` placeholder. P1 enables the guarded loading transitions. A denied
workspace read is final for that request; it is never retried under another principal.

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#E7EEFF","primaryTextColor":"#243247","primaryBorderColor":"#879AB8","lineColor":"#7C899A","tertiaryColor":"#FFF1D9"}}}%%
stateDiagram-v2
  [*] --> NotLoaded
  NotLoaded --> Loading: policy allows and user requests load
  NotLoaded --> Unsupported: scheme or type forbidden
  Loading --> Ready: decoded current bounded image
  Loading --> Denied: 401 or 403
  Loading --> Failed: offline or missing or invalid image
  Failed --> Loading: explicit Retry
  Ready --> NotLoaded: source destination changes
  Loading --> Disposed: cell deleted or view disposed
  Ready --> Disposed: view disposed
  Denied --> NotLoaded: identity or permission explicitly refreshed
  classDef mint fill:#E4F3EA,stroke:#829F8B,color:#243247
  classDef amber fill:#FFF1D9,stroke:#B49A6F,color:#243247
  class Ready mint
  class Denied,Failed,Unsupported amber
```

Every transition preserves alt text, source destination and layout bounds. Abort listeners,
disconnect observers and revoke object URLs on disposal. Test state transitions as a generated
event sequence in addition to the selected E2E stories ([T07/T12](11-tests-traceability.md#test-groups)).

