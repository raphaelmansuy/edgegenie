[Index](README.md) · prev: [03 Requirements](03-requirements.md) · next: [05 Diagrams](05-diagrams.md)

# 04 · Wireframes (ASCII)

One screen per state that matters. Each is annotated with the requirement it satisfies, so a wrong
wireframe is a wrong requirement rather than a matter of taste.

Dimensions are the measured ones at 1480×900: chrome 52 px, rail 276, main 822, dock 380.

---

## 1. The shell, healthy

```
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ ⌘ OpenGenie    ▸ llama-4-maverick ●ready      [ Search or run a command        ⌘K ]   RM ▾   │ 52
├────────────┬───────────────────────────────────────────────┬─────────────────────────────────┤
│ Sessions   │ ny_taxi_kpi_dashboard                     ⟳  │ ● ready   in context: ny_taxi…  │
│ Files      │ ──────────────────────────────────────────────│                                 │
│ Catalog    │                                               │  ╭─ looked at the table ─────╮  │
│            │  ┌─────────────────────────────────────────┐  │  │ main.sales.orders    ✓    │  │
│ ● f43471fe │  │ [1] df = spark.table("main.sales…")     │  │  ╰───────────────────────────╯  │
│   ready 2m │  │     df.groupBy("pickup_hour")…          │  │                                 │
│ ● 4ff4405d │  │ ─────────────────────────────────────── │  │  I created the notebook and     │
│   ready 5m │  │ pickup_hour │ trips │ avg_fare         │  │  ran it.                        │
│ ● 6c2c42d4 │  │ ────────────┼───────┼────────────────  │  │                                 │
│  archived  │  │ 0           │  142  │  12.40           │  │  ╭─ next step ────────────────╮ │
│            │  │ 1           │   98  │  13.10           │  │  │ Chart the trips by hour     │ │
│            │  └─────────────────────────────────────────┘  │  ╰─────────────────────────────╯ │
│            │                                               │                                 │
│            │                                               ├─────────────────────────────────┤
│ + New      │                                               │ +  @  /            model ▾  Send│
└────────────┴───────────────────────────────────────────────┴─────────────────────────────────┘
   rail 276                      main 822                                  dock 380

  [FX-8] tab order follows this: chrome → rail → main → dock, left to right, top to bottom.
```

## 2. `connecting` — the first ~200 ms *(before the fix: the field was dead)*

```
                                                    dock header
                                              ┌────────────────────────┐
                                              │ ● connecting   …       │  ← [ST-4] no action:
                                              └────────────────────────┘     it resolves itself
                                                    dock body
                                              ┌────────────────────────┐
                                              │                        │
                                              │   What can I help?     │
                                              │                        │
                                              │  [Summarise the table] │
                                              │                        │
                                              ├────────────────────────┤
                                              │ Ask anything…          │  ← [FX-1] ENABLED.
                                              │ +  @  /      model ▾   │     A user who types
                                              └────────────────────────┘     now keeps the text.
```

The single change this wireframe encodes: **the box is live here.** It was `disabled`, and the
keystroke went nowhere ([02 §2](02-assessment.md#2-the-defect-in-a-timeline)).

## 3. `reconnecting` — the stream dropped, the server has the work

```
┌──────────────────────────────────────────────────────────────────────┐
│ ● reconnecting…          [ Retry now ]     in context: ny_taxi…      │  ← [ST-4] [ST-5]
├──────────────────────────────────────────────────────────────────────┤
│  ╭────────────────────────────────────────────────────────────────╮  │
│  │ Reconnecting to your session                                   │  │  ← [ST-7] one
│  │ The server runs independently. We'll catch up on saved progress │  │     role=status
│  │ when the connection returns.                                   │  │
│  │ Progress saved · Copy return link                              │  │
│  ╰────────────────────────────────────────────────────────────────╯  │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │ Ask anything…                                                  │  │  ← [FX-1] STILL LIVE
│  │ +  @  /                                       model ▾  Send    │  │     Sending is a POST
│  └────────────────────────────────────────────────────────────────┘  │     with an idempotency key.
└──────────────────────────────────────────────────────────────────────┘

  What the user gets that they did not before:
    1. a word that says what is happening        (already there)
    2. an ACTION that can change it              [ST-4]  ← new
    3. a box that still accepts what they wanted to say  [FX-1] ← new
```

## 4. `closed` — the session no longer exists (404) or the cursor is ahead (409)

```
┌──────────────────────────────────────────────────────────────────────┐
│ ⨯ session closed   [ Retry ]  [ New conversation ]   in context: —    │  ← [ST-4] two actions,
├──────────────────────────────────────────────────────────────────────┤     both named
│  ╭────────────────────────────────────────────────────────────────╮  │
│  │ This session is no longer available                            │  │  ← reason, from ST-2
│  │ It was archived or the server restarted. Your other            │  │
│  │ conversations are listed on the left.                          │  │
│  ╰────────────────────────────────────────────────────────────────╯  │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │ [readOnly] This conversation is closed. Start a new one.       │  │  ← [FX-2] focusable,
│  │ +  @  /                                       model ▾  Send    │  │     explains itself
│  └────────────────────────────────────────────────────────────────┘  │     in-place
└──────────────────────────────────────────────────────────────────────┘

  Before the fix this state did not exist: a 404 became an endless
  "reconnecting…" with every control disabled and no exit. [F2] [F3]
```

## 5. A non-writable composer, and how it differs from a writable one

```
   WRITABLE                              NON-WRITABLE  [FX-2] [FX-3]
   ┌───────────────────────────┐         ┌───────────────────────────┐
   │ Ask anything…             │         │ This conversation is      │  ← reason replaces
   │                           │         │ archived. Start a new one.│     the placeholder
   │ +  @  /     model ▾  Send │         │ +  @  /     model ▾  Send │
   └───────────────────────────┘         └───────────────────────────┘
     border: --line                        border: --line-2 (dashed)
     background: --surface                 background: --surface-2 (tinted)
     focus ring: visible                   focus ring: visible  ← STILL VISIBLE
     Tab: lands here                       Tab: lands here      ← STILL LANDS
     ⌘L: focuses, caret ready              ⌘L: focuses, and the reason is
                                               read out [FX-4]

   The difference is stated, not withheld: a user can reach the box, read why it is
   closed, and select the text they wanted to keep. `disabled` gave none of that.
```

## 6. Navigation: the three rail tabs and the drawer state

```
  railVisible, wide (≥1181)                 narrow (<821): the rail is a drawer
  ┌──────────┬──────────────┐               ┌───────────────┬──────────────┐
  │Sessions│ │              │               │               │              │
  │ Files  │ │    main      │               │     main      │   [☰ opens   │
  │Catalog │ │              │               │               │    drawer]   │
  └──────────┴──────────────┘               └───────────────┴──────────────┘
     ⌘1 ⌘2 ⌘3 switch the tab (007)            Escape closes the drawer  [KB-A]
     ⌘B toggles the rail                       (this did NOT work from the
                                                notebook before [F5])
```

## 7. Focus mode: the dock with no inspector *(860 ≤ w < 1136)*

```
  ┌──────────────┬──────────────────────────────┐
  │              │                              │
  │   main 480+  │   dock 380                   │   [008] DOCK_FOCUS_MIN
  │              │                              │   the rail yields, not the work
  │              │   ┌────────────────────────┐ │
  │              │   │ +  @  /   model ▾ Send │ │
  │              │   └────────────────────────┘ │
  └──────────────┴──────────────────────────────┘
```

## 8. Scroll hand-off, drawn

```
   pointer over a cell's output:
   ┌───────────────────────────────────────┐
   │ cell output        scrollTop=0        │  wheel ↓ → inner scrolls      [SC-2]
   │  ┌─────────────────────────────────┐  │
   │  │ row 1                           │  │
   │  │ row 2                           │  │
   │  │ row 3                           │  │
   │  └─────────────────────────────────┘  │
   │        ▲ at the bottom edge           │
   │        │ further ↓ delta              │
   │        └──────► notebook scrolls      │  [SC-1] the remaining delta is
   └───────────────────────────────────────┘         handed to the ancestor

   at the notebook's own bottom edge:
        further ↓ delta  ──►  the browser gets it (no trapping)   [SC-3]
```

## 9. The keyboard, as a user learns it

```
  Anywhere                         In the dock                 In a cell
  ─────────────────────────────    ────────────────────────    ─────────────────────────
  ⌘K   palette                     ⌘L   focus the box           ⌘⇧I  ask about this cell
  ⌘J   show/hide assistant         ⏎    send                    Esc  leave edit mode
  ⌘B   show/hide left panel        ⇧⏎   newline                 (cell chords)
  ⌘1/2/3  rail tabs                Esc  stop the agent
  ⌘,   providers                   ⌘⇧N  new conversation
  ⌘/   shortcut sheet
  Esc  close what is open, in order:  dialog → popover → drawer → edit → stop → browser
```
