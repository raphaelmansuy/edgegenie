# 05 — Architecture, entities, and sequences

[Index](README.md) · Contracts: [03](03-requirements.md) · States: [06](06-statecharts.md)
· Security: [07](07-rendering-security.md) · Plan: [10](10-implementation-plan.md)

## Component boundaries

Proposed modules below are new unless identified as existing. Names are implementation targets,
not a claim that those files already exist. Keep `Markdown.tsx` as the public compatibility adapter
while moving grammar and React node construction behind explicit interfaces.

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#E7EEFF","primaryTextColor":"#243247","primaryBorderColor":"#879AB8","lineColor":"#7C899A","secondaryColor":"#E4F3EA","tertiaryColor":"#F1E9F8"}}}%%
flowchart LR
  Source[Cell source + revision] --> Parser[Markdown parser adapter]
  Parser --> AST[Typed render model]
  AST --> View[Markdown document view]
  Policy[Link and media policy] --> View
  Profile[Notebook surface profile] --> View
  Host[Existing EditorHost] --> Source
  Save[Existing document save] --> Source
  View --> DOM[Semantic React DOM]
  classDef mint fill:#E4F3EA,stroke:#829F8B,color:#243247
  classDef lavender fill:#F1E9F8,stroke:#A18AB5,color:#243247
  class Parser,AST mint
  class Policy,Profile lavender
```

| Boundary | Responsibility | Explicitly excludes |
|---|---|---|
| `domain/markdown/parse.ts` | Source to bounded typed AST, positions, headings and diagnostics | DOM, React, storage, requests |
| `domain/markdown/policy.ts` | Pure URL/media classification and canonicalization | Fetching, app permissions decisions |
| `components/MarkdownDocument.tsx` | AST to allowlisted React nodes using a surface profile | Saving, running tools, HTML injection |
| `components/NotebookMarkdown.tsx` | Notebook reading surface, mode controls, empty/failure states | Alternate parser or serializer |
| `domain/markdown/format.ts` | Selected source + command to bounded edit operations | Direct DOM selection mutation |
| `editor/host.ts` / `codemirror.ts` | One atomic formatting transaction and undo/selection mapping | Markdown interpretation or network |
| `hooks/useMarkdownModel.ts` | Revision-scoped parsing cache/cancellation and diagnostics | Durable content storage |
| P1 `MarkdownImage` + resolver adapter | Request lifecycle under policy and caller identity | Privileged generic URL proxy |
| Existing `EditorSurface` and save service | Draft, dirty state, version token, fence, conflict, write | Preview rendering as persistence |

## Logical ER model

This is an **in-memory logical model**, not a proposed SQL schema. `NotebookDocument` and cell
source already exist conceptually. The render model, heading entries and view state are derived.
Do not add a Lakebase table, migration, full-text index or saved HTML column for this feature.

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#E7EEFF","primaryTextColor":"#243247","primaryBorderColor":"#879AB8","lineColor":"#7C899A","tertiaryColor":"#E4F3EA"}}}%%
erDiagram
  NOTEBOOK_DOCUMENT ||--o{ CELL_SOURCE : orders
  CELL_SOURCE ||--o| RENDER_MODEL : derives
  CELL_SOURCE ||--o| CELL_VIEW_STATE : displays
  RENDER_MODEL ||--o{ HEADING_ENTRY : indexes
  RENDER_MODEL ||--o{ MEDIA_REFERENCE : describes
  NOTEBOOK_DOCUMENT ||--o| DRAFT_SNAPSHOT : recovers
  NOTEBOOK_DOCUMENT {
    string path PK
    string workspaceIdentity
    string versionToken
    boolean partialRead
  }
  CELL_SOURCE {
    string sessionCellId PK
    string kind
    string language
    string source
    int sourceRevision
    boolean truncated
  }
  RENDER_MODEL {
    string cacheKey PK
    string parserVersion
    int sourceRevision
    int nodeCount
  }
  CELL_VIEW_STATE {
    string sessionCellId FK
    string mode
    int selectionStart
    int selectionEnd
    boolean collapsed
  }
  HEADING_ENTRY {
    string anchorId PK
    int sourceDepth
    int sourceOffset
    string plainLabel
  }
  MEDIA_REFERENCE {
    string referenceId PK
    string rawDestination
    string altText
    string classification
  }
  DRAFT_SNAPSHOT {
    string documentKey PK
    string sourceText
    string basedOnVersion
  }
```

IDs are session-stable cell identities, not new durable metadata. The SOURCE format does not
persist a cell ID. Reopening reparses and reconciles; anchors use a document namespace plus
cell identity and source heading ordinal during the current session. Duplicate heading text
does not become a DOM-ID collision. External links remain the existing cell-index route until
a durable anchor scheme is separately specified. Outline requests map to the current revision.

Cache key: `(workspace identity, document key, cell id, source revision, parser profile/version)`.
Store the source reference or a checked revision too; an unchecked hash alone cannot prove equality.
Discard derived state on workspace/user change, cell deletion/conversion and document close.
The existing draft store is reused, with its current security scope audited in [phase P1](10-implementation-plan.md#phases).

## Reading and editing sequence

```mermaid
%%{init: {"theme":"base","themeVariables":{"actorBkg":"#E7EEFF","actorBorder":"#879AB8","actorTextColor":"#243247","signalColor":"#52647B","signalTextColor":"#243247","noteBkgColor":"#FFF1D9","noteTextColor":"#243247"}}}%%
sequenceDiagram
  actor Reader
  participant Cell as NotebookMarkdown
  participant Host as EditorHost
  participant Model as Markdown model
  rect rgb(228,243,234)
    Model-->>Cell: Latest bounded AST + source revision
    Cell-->>Reader: Styled preview by default
  end
  Reader->>Cell: Explicit Edit / Enter
  Cell->>Host: Restore source and selection
  Reader->>Host: Type or format source
  Host-->>Cell: Source transaction + revision
  Reader->>Cell: Show preview / Esc
  rect rgb(241,233,248)
    Cell->>Host: Flush/read latest source before transition
    Cell->>Model: Parse latest revision
    Model-->>Cell: Model or bounded fallback
    Cell-->>Reader: Styled content, preserve focus and scroll anchor
  end
```

No server request is required to switch modes. Preserve the active editor state/history in a
document-scoped host/state cache while previewing; do not keep hundreds of hidden live editors.
The adapter chooses remount-with-restored-state versus retained active host in [phase P3](10-implementation-plan.md#phases).
Either must meet the same undo/selection/history tests and memory budget.

## Save and external edit sequence

```mermaid
%%{init: {"theme":"base","themeVariables":{"actorBkg":"#E7EEFF","actorTextColor":"#243247","actorBorder":"#879AB8","signalColor":"#52647B","signalTextColor":"#243247","noteBkgColor":"#FFF1D9","noteTextColor":"#243247"}}}%%
sequenceDiagram
  actor Author
  participant Cell as Cell source model
  participant Surface as Existing EditorSurface
  participant API as Existing save API
  participant Workspace
  Author->>Cell: Preview content
  Note over Cell,Surface: Preview changes no dirty/save state
  Author->>Surface: Save / Cmd-S
  Surface->>Cell: Flush active transaction and snapshot all cell sources
  Surface->>Surface: Check original completeness + round-trip
  Surface->>API: SOURCE + opaque version + existing fence context
  API->>Workspace: Existing permission/version-checked write
  alt Accepted
    Workspace-->>Surface: Saved version
    Surface-->>Author: Saved, newer edits remain dirty
  else Conflict or permission denial
    Workspace-->>Surface: Existing conflict/error outcome
    Surface-->>Author: Preserve local source, offer existing resolution
  end
```

An agent write on a clean document follows existing adoption/reconciliation. A dirty document
retains local source and shows incoming changes. Parsing or media completion never settles a
write conflict. See [state dimensions](06-statecharts.md#state-vector) and [T11](11-tests-traceability.md#test-groups).

## DRY and SOLID contracts

- **Single responsibility:** parsing, policy, rendering, source transactions and persistence have
  separate owners. `CellBlock` orchestrates rather than implementing grammar.
- **Open/closed:** typed node handlers and surface profiles extend behavior; avoid forked parsers
  for notebook/chat/read-only/file surfaces.
- **Liskov:** legacy `Markdown({text,streaming})` callers retain source escaping, workspace paths,
  code Copy and streaming fallbacks. Contract tests cover every adapter.
- **Interface segregation:** add an optional `MarkdownEditHost` capability for formatting/state
  snapshots; plain code-editor consumers do not implement irrelevant toolbar APIs.
- **Dependency inversion:** formatting and rendering depend on small editor/media interfaces,
  not CodeMirror internals, Fetch globals, workspace SDKs or database credentials.
- **DRY:** one heading traversal feeds DOM IDs and P1 outline; one URL policy handles all rich
  destinations; one SOURCE authority with a checked client mirror. Existing helpers are reused
  where their contracts match; a navigation URL helper is not repurposed as an image API.

