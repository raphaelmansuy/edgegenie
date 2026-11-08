# 05 — Diagrams (Mermaid)

Part of [007](README.md). Requirements: [03](03-requirements.md). Wireframes: [04](04-wireframes.md).

---

## 1. A focus-returning dialog, as a sequence

The behaviour `KB-1` requires, drawn once. Every dialog in the app (`Palette`, `ShortcutSheet`,
`ProviderSettings`, `ApprovalSheet`, `FolderPicker`) must follow the same shape — which is why the
implementation is one hook, not five effects.

```mermaid
sequenceDiagram
  autonumber
  actor U as User
  participant T as Trigger (a button)
  participant D as Dialog
  participant F as FocusStore (a ref)
  participant Next as Named successor

  U->>T: press ⌘K (or click)
  T->>F: remember(activeElement)
  Note over F: the element the user was on —<br/>not necessarily the trigger itself
  T->>D: open
  D->>D: focus the first field
  U->>D: Escape
  D->>F: where was I?
  alt the opener is still in the document
    F-->>D: the element
    D->>U: .focus() → focus is back where it was
  else the opener was removed (a tab closed, a row re-rendered)
    F-->>D: gone
    D->>Next: next tab → the composer → the centre pane
    Next->>U: focus lands on a named region, never body
  end
```

## 2. Chord arbitration — one owner, decided by context

`KB-2` + `[D3]`. The registry is data; the resolver is pure; the hook only dispatches.

```mermaid
stateDiagram-v2
  [*] --> Idle
  Idle --> Typing: focus is in a text field
  Idle --> Command: focus is on a cell / a region
  Typing --> Idle: blur

  state Typing {
    [*] --> Text
    Text: bare letters are text, never commands
    Text: modified chords still resolve (⌘K, ⌘I, ⌘S)
    Text --> Text: ⇥ leaves for the next control
  }

  state Command {
    [*] --> Cell
    Cell: ⌘I = inspector   (KB-9)
    Cell: ⌘⇧I = cell prompt (KB-10)
    Cell: ↵ = edit, ⇥ = leave the cell (KB-4)
  }

  Idle --> Dialog: a dialog opens
  Command --> Dialog: ⌘K / ⌘/ / ⌘,
  state Dialog {
    [*] --> Modal
    Modal: every chord except Esc is the dialog's
    Modal --> [*]: Esc → close → restore focus (KB-1)
  }

  Dialog --> Idle: focus restored
```

## 3. Escape: one ordered meaning (`KB-8`)

```mermaid
flowchart TD
  A[Escape pressed] --> B{settings or keys sheet open?}
  B -- yes --> B1[close it → restore focus] --> Z[handled]
  B -- no --> C{palette open?}
  C -- yes --> C1[close it → restore focus] --> Z
  C -- no --> D{popover open? folder picker, model picker, menu}
  D -- yes --> D1[close it → restore focus] --> Z
  D -- no --> E{drawer open?}
  E -- yes --> E1[close the drawer] --> Z
  E -- no --> F{editing a cell or markdown?}
  F -- yes --> F1[leave edit mode, keep the cell selected] --> Z
  F -- no --> G{agent running AND focus in the composer?}
  G -- yes --> G1[stop the agent — the visible Stop affordance] --> Z
  G -- no --> H[nothing: never swallow Escape]
```

The last branch is the important one: Escape is how a user leaves a full-screen mode, so the app
must not consume it when it has nothing to close. Today `Composer.tsx:241` stops the agent on
Escape from anywhere in the field; `KB-8` keeps that (it is the documented affordance next to the
Stop button) but makes the order explicit and testable.

## 4. Scrolling: who owns the wheel

`SC-2`, `SC-3`. One scroller per region; `overscroll-behavior: contain` stops the chain at the
region boundary so a trackpad flick cannot navigate the browser.

```mermaid
flowchart LR
  subgraph page["the page (overflow: clip — never scrolls)"]
    subgraph centre["main → .doc-panel → .cells (the ONE scroller)"]
      cell1["cell 1"]
      cell2["cell 2 … the cell grows, it never scrolls"]
    end
    subgraph dock["complementary → .dock-body (its own scroller)"]
      turns["turns stream here, pinned to the bottom while pinned"]
    end
  end
  wheel((wheel / trackpad)) -->|pointer over cells| centre
  wheel -->|pointer over dock| dock
  centre -.->|at the end: contained, no chain| x1[no browser back/forward]
  dock -.->|at the end: contained| x2[no page scroll]
  centre -->|"Show / open at cell N (the user asked)"| smooth[smooth scroll allowed — SC-1]
```

## 5. A view's state, and where it is remembered

The data model behind "never lose my place" — `KB-1`, plus the view state from round 3.

```mermaid
erDiagram
  DOCUMENT ||--o{ CELL : contains
  DOCUMENT {
    string ref PK "canonical path (/Workspace stripped)"
    string kind "notebook | file | table"
    string version "modified_at hash, from the server"
    int rev "bumped when the agent writes"
  }
  CELL {
    string id PK "stable across a reload (reconcile)"
    int index
    string kind "code | markdown"
    string source
  }
  VIEW_STATE ||--|| DOCUMENT : "one per path, in sessionStorage"
  VIEW_STATE {
    string path FK
    int cell "1-based, 0 = none"
    int caret "character offset"
    string mode "edit | command"
    int scroll "scrollTop px"
  }
  FOCUS_RETURN {
    string opener "a ref to the element that opened a dialog"
    string fallback "next tab → composer → centre"
  }
  KEY_REGISTRY ||--o{ KEY_BINDING : declares
  KEY_REGISTRY {
    string version
  }
  KEY_BINDING {
    string combo PK "mod+i"
    string id FK "inspector"
    string owner "shell | notebook | composer"
    string when "always | !dialog"
    string scope "global | cell | composer"
  }
```

`FOCUS_RETURN` is not persisted — it is a ref for the life of an open dialog. `KEY_REGISTRY` is a
module constant; putting it here is the point of `KB-5`: the set is *a thing*, and a test can read it.

## 6. Opening and closing a document, with focus

How `KB-1` and `KB-4` interact with the tab strip (already implemented; drawn to show the seam).

```mermaid
sequenceDiagram
  autonumber
  actor U as User
  participant Tabs as Tab strip
  participant App as App
  participant Doc as Document
  U->>Tabs: ⌘W on tab 2
  Tabs->>App: onClose(id)
  App->>App: pick the successor tab (next, else previous)
  App->>Doc: render the successor
  App->>Tabs: focus the successor tab (role=tab, tabIndex 0)
  Note over Tabs: never focus body — the strip is a widget<br/>and it keeps one roving tab stop
```
