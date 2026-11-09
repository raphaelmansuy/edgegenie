# Architecture grounded in code

Related: [requirements](01-requirements.md), [interaction](02-interaction-design.md), [plan](04-implementation-plan.md), [tests](05-test-matrix.md).

## Existing seams

- [App.tsx](../../apps/coding-agent/web/src/App.tsx): `docs`, `view`, `openDoc`, `closeDoc`, `selectTab`, route and focus binding. Agent refresh increments `rev`; ordering must preserve those objects.
- [DocTabs.tsx](../../apps/coding-agent/web/src/components/DocTabs.tsx): original active reveal and hidden badge; lacks reorder callback and resize/scroll-driven measurement.
- [docs.ts](../../apps/coding-agent/web/src/domain/docs.ts): canonical ID derives from kind plus canonical path; order is never identity.
- [EditorSurface.tsx](../../apps/coding-agent/web/src/components/EditorSurface.tsx): dirty buffer, save fence and drafts. Reorder must not change viewer keys.
- [drafts.ts](../../apps/coding-agent/web/src/domain/drafts.ts) and [viewstate.ts](../../apps/coding-agent/web/src/domain/viewstate.ts): existing local recovery and caret/scroll records; no schema change.
- [keys.ts](../../apps/coding-agent/web/src/domain/keys.ts): global command registry and shortcut sheet. Reopen belongs here; strip-specific gestures stay local.

These observations concern the named document-management sections, not every line of the entire application.

## Responsibility boundaries

The pointer lifecycle is isolated in [useTabDrag.ts](../../apps/coding-agent/web/src/hooks/useTabDrag.ts); its [lifecycle tests](../../apps/coding-agent/web/src/hooks/useTabDrag.test.ts) cover cleanup on unmount, blur and source removal. Pure [tabs.ts](../../apps/coding-agent/web/src/domain/tabs.ts) owns index movement, adjacent close selection and collision-free DOM identity. DocTabs owns geometry and transient gesture/popover state. App owns open/closed metadata, selected document and assistant context. EditorSurface owns buffer/draft lifecycle. Commands depend on callbacks rather than API or storage implementations. No service layer or third-party drag library is needed.

```mermaid
sequenceDiagram
    actor User
    participant Tabs as DocTabs
    participant Rules as tabs.ts
    participant App
    participant Editor as Existing editor
    User->>Tabs: Pointer down, cross threshold
    Tabs-->>User: Source feedback and insertion marker
    loop Pointer at edge
        Tabs->>Tabs: rAF scroll and recompute destination
    end
    User->>Tabs: Release inside strip
    Tabs->>App: onMove(documentId, targetIndex)
    App->>Rules: moveTab(currentDocs, id, index)
    Rules-->>App: New order, same document objects
    App-->>Tabs: Ordered documents
    Note over App,Editor: Active ID and keyed viewer remain unchanged
    User->>Tabs: Close active document
    Tabs->>App: onClose(id)
    App->>Rules: afterClose(docs, active, removedIds)
    App->>Editor: Unmount closed viewer and flush draft
    App-->>Tabs: Neighbor selected, focus restored
```

## Data model

The existing `Draft.docId` field stores the canonical workspace path (`Document.ref`), despite its name; it is not the kind-prefixed `Document.id`. Tables have no editable draft.

Conceptual ER only: these are existing memory/local browser records, not proposed SQL tables. One document may have zero or one draft and one view record. One ordered list contains each open ID once; recently closed metadata is bounded and excludes content.

```mermaid
erDiagram
    OPEN_LIST ||--o{ DOCUMENT : orders
    DOCUMENT ||--o| DRAFT : recovers
    DOCUMENT ||--o| VIEW_STATE : remembers
    DOCUMENT ||--o| CLOSED_ENTRY : reopens
    OPEN_LIST {
        string activeId
        string_array orderedIds
    }
    DOCUMENT {
        string id PK
        string kind
        string canonicalRef
        string name
        int rev
    }
    DRAFT {
        string docId PK
        string text
        string basedOn
        number at
    }
    VIEW_STATE {
        string canonicalRef PK
        int cell
        int caret
        number scroll
    }
    CLOSED_ENTRY {
        string id PK
        int previousIndex
    }
```

## Gesture state

```mermaid
stateDiagram-v2
    [*] --> Idle
    Idle --> Pending: Primary pointer down on tab
    Pending --> Dragging: Mouse threshold or touch hold
    Pending --> Scrolling: Touch swipe before hold
    Pending --> Idle: Release without movement
    Scrolling --> Idle: Release or cancel
    Dragging --> Dragging: Move and edge autoscroll
    Dragging --> Idle: Release inside commits
    Dragging --> Idle: Escape or cancel or outside release
    Idle --> Picker: Open documents
    Picker --> Idle: Select or Escape or outside click
    Idle --> Menu: Context menu or Shift F10
    Menu --> Idle: Action or dismissal
```

Privacy and authority: [working-set recovery](07-ux-refinement.md) stores bounded kind/reference/order/selection metadata in account/workspace-scoped sessionStorage. Closing the browser tab ends this recovery scope; document content remains in the separate existing draft mechanism. No new backend writes, SQL, analytics payloads, or credentials. Existing workspace read/save and Unity Catalog checks remain authoritative. Loading/permission errors are viewer states and must not break tab navigation.
