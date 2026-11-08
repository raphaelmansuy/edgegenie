# 04 — Wireframes (ASCII)

Part of [007](README.md). Requirements: [03](03-requirements.md). The widths below are the real ones
from `layout.ts` at the stated viewport, not decorative.

---

## 1. The shell, 1440 px, nothing open

```
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ [◕] OpenGenie   [model ▾]  [⌘K Search or run a command]        [◐][◑][●] [▤] [?] [RM]  52px │  banner
├───────────────┬──────────────────────────────────────────────────┬────────────────────────────┤
│ ▸ rail 276    │ ▸ main  782                                      │ ▸ complementary 380        │
│               │                                                  │                            │
│ ┌Sessions┐    │   Skip to the work ────────────────────────────┐ │  NEW · in context: —       │
│ │ Files  │    │   (skip link, visible only on focus)           │ │  ─────────────────────────  │
│ │Catalog │    │                                                │ │  What can you do here?     │
│ └────────┘    │              ◕  (hero mark, 40px)              │ │  Open something from Files │
│               │     What should we build today?                │ │  Start a scratch notebook  │
│  RECENT   +   │  A coding agent that works in your workspace…  │ │                            │
│  ──────────   │                                                │ │                            │
│  · Hello      │  ┌ WORKING FOLDER ──────────────────────────┐  │ │  ┌──────────────────────┐  │
│  · Add a KPI  │  │ [◲] agent_scratch                     ▸  │  │ │  │ Ask anything…        │  │
│  · Hello      │  │     /Users/…/agent_scratch               │  │ │  │                      │  │
│               │  └──────────────────────────────────────────┘  │ │  │ @  /   model    Send │  │
│               │  Everything under it, nothing outside it.      │ │  └──────────────────────┘  │
│               │                                                │ │                            │
│               │  ┌──────────┐┌──────────┐┌──────────┐         │ │                            │
│               │  │Build a   ││Investigate││Create a  │        │ │                            │
│               │  │notebook  ││a number  ││job       │         │ │                            │
│               │  └──────────┘└──────────┘└──────────┘         │ │                            │
│               │  ┌──────────┐┌──────────┐┌──────────┐         │ │                            │
│               │  │Lakebase  ││Document  ││Debug a   │         │ │                            │
│               │  │and an app││tables    ││failing job│        │ │                            │
│               │  └──────────┘└──────────┘└──────────┘         │ │                            │
│               │                                                │ │                            │
│               │  ┌ OPEN SOMETHING ─────┐┌ THIS WORKSPACE ─────┐│ │                            │
│               │  │ ⌕ Search…       ⌘K  ││ signed in raphael…  ││ │                            │
│               │  │ ▤ Browse catalog    ││ writes   /Users/…   ││ │                            │
│               │  │ · rf_target      ↗  ││ model    gemini-3.8 ││ │                            │
│               │  └─────────────────────┘└─────────────────────┘│ │                            │
├───────────────┴──────────────────────────────────────────────────┴────────────────────────────┤
```

**Tab stops in this state (target ≤ 8 to the composer, ≤ 12 to the work):**

```
1  Skip to the work        ← KB-7 (new)
2  Skip to the conversation← KB-7 (new)
3  model chip
4  search / palette
5  rail tab: Sessions
6  working folder picker
7  the first start card
…  composer (via skip link or the budget)
```

## 2. The shell, 1440 px, a notebook open

```
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ [◕] OpenGenie  [model ▾]  [⌘K …]                                   [◐][◑][●] [▤] [?] [RM]     │
├───────────────┬──────────────────────────────────────────────────┬────────────────────────────┤
│ rail 276      │ main 782                                         │ complementary 380          │
│               │ ┌ tabs ─────────────────────────────────────────┐ │                            │
│ Sessions      │ │▸tall_demo ✕│▸rf_target ✕│              +2 │ │  READY · tall_demo         │
│ Files         │ ├───────────────────────────────────────────────┤ │  ────────────────────────  │
│ Catalog       │ │ tall_demo  PYTHON   [Ask ▾] [Run all] [Save] │ │  ▸ wrote a notebook  Open ↗│
│               │ ├───────────────────────────────────────────────┤ │  ▸ ran SQL       table    │
│ · Hello       │ │ ┌ agent banner (only after a write) ────────┐ │ │  ▸ Done …                  │
│ · Add a KPI   │ │ │ This notebook was updated · 1 cell added  │ │ │                            │
│ · Calculate π │ │ │                        [Show] [Undo] [✕]   │ │ │                            │
│               │ │ └───────────────────────────────────────────┘ │ │                            │
│               │ │ ┌ cell 1 ───────────────────────────────────┐ │ │  ┌──────────────────────┐  │
│               │ │ │ 1  md  [md][Ask][link][Run][+][✕]         │ │ │  │ Ask about tall_demo… │  │
│               │ │ │    # Tall demo                            │ │ │  │ @  /   model    Send │  │
│               │ │ └───────────────────────────────────────────┘ │ │  └──────────────────────┘  │
│               │ │ ┌ cell 2 ───────────────────────────────────┐ │ │                            │
│               │ │ │ 2  pyth [md][Ask][link][Run][+][✕]        │ │ │                            │
│               │ │ │   1  import pandas as pd                  │ │ │                            │
│               │ │ │   2  df = spark.table("samples…")         │ │ │                            │
│               │ │ │  ┌ result ─────────────────────────────┐   │ │ │                            │
│               │ │ │  │  pickup_hour | trips | avg_fare     │   │ │ │                            │
│               │ │ │  └─────────────────────────────────────┘   │ │ │                            │
│               │ │ └───────────────────────────────────────────┘ │ │                            │
│               │ │ …  the .cells region is the ONE scroller       │ │                            │
│               │ │                                                │ │                            │
│               │ │ [+ Code] [+ Text] [✨ Generate]                 │ │                            │
└───────────────┴──────────────────────────────────────────────────┴────────────────────────────┘
```

**The cell as one Tab stop (KB-4):**

```
   Tab ──▶ ┌ cell 2 (focused, COMMAND mode) ┐
           │  ←→  move between the cell's controls
           │  ↵   edit the source
           │  ⇥   leave the cell for the next one
           └─────────────────────────────────┘
```

## 3. 1024 px — the inspector yields first, the dock stays a column

```
┌────────────────────────────────────────────────────────────────────┐
│ [◕] OpenGenie  [model]  [⌘K]                     [▤] [?] [RM]      │
├───────────┬──────────────────────────────────────┬─────────────────┤
│ rail 276  │ main 368                             │ dock 380        │
│           │  ← CENTRE_MIN 480 is violated here   │                 │
│           │                                      │                 │
│  (the rail yields to a drawer at < 1136 when the dock opens)        │
└───────────┴──────────────────────────────────────┴─────────────────┘
```

Actual behaviour at 1024 with the dock open: `takesColumn("dock")` is false (`1136`), `focus` mode
is on (`DOCK_FOCUS_MIN 860 ≤ 1024 < 1136`), so **the rail becomes a drawer and the centre keeps
480**: `480 + 380 = 860 ≤ 1024`. The frame above is the *pre-focus* layout, kept here because it is
the one that must not happen.

```
┌────────────────────────────────────────────────────────────────────┐
│ [◕] OpenGenie  …                                                   │
├───────────────────────────────────────────┬────────────────────────┤
│ main 644                                  │ dock 380               │
│   (rail is a drawer: ⌘B brings it back)   │                        │
└───────────────────────────────────────────┴────────────────────────┘
```

## 4. The skip links, on focus

```
┌────────────────────────────────────────────────────────────────────┐
│ ┏━━━━━━━━━━━━━━━━━━━┓ ┏━━━━━━━━━━━━━━━━━━━━━━━━━┓                  │
│ ┃ Skip to the work ┃ ┃ Skip to the conversation┃   (ink on accent,  │
│ ┗━━━━━━━━━━━━━━━━━━━┛ ┗━━━━━━━━━━━━━━━━━━━━━━━━━┛   6px radius,    │
│                                                       2px offset)    │
├────────────────────────────────────────────────────────────────────┤
```

They sit in the top bar's normal flow, `position: absolute; transform: translateY(-120%)` at rest,
and slide in on `:focus-visible`. They are the first two Tab stops and they call `.focus()` on the
target, so the next Tab continues *inside* the region (P5).

## 5. The folder picker (from round 4, unchanged shape)

```
        ┌ Choose the working folder ───────────────────┐
        │ ⌕ Find a folder…                        ⟳     │
        │ The agent can write only here.               │
        ├──────────────────────────────────────────────┤
        │ ▾ My home                                    │
        │   ▸ agent_scratch           [current]        │
        │   ▸ coding-agent                             │
        │ ▸ Shared                        [Use]        │
        │ ▸ Repos                         [Use]        │
        ├──────────────────────────────────────────────┤
        │ Everything under it, nothing outside it.     │
        │                          [Type a path…]      │
        └──────────────────────────────────────────────┘
```

## 6. Focus return: the contract, drawn

```
  [⌘K]──open──▶ palette ──Esc──▶ ✗ body
        │                        ▲
        └────────────────────────┘  TODAY (KB-1 fails)

  [⌘K]──open──▶ palette ──Esc──▶ [⌘K]   ← AFTER: the opener, by ref
        │                        ▲
        └── (opener removed by a re-render?) ──▶ named successor:
                next tab → the composer → the centre pane
```
