[Index](README.md) · prev: [03 Requirements](03-requirements.md) · next: [05 Diagrams](05-diagrams.md)

# 04 · Wireframes (ASCII)

Eight screens. Each is annotated with the requirement it satisfies, so a wrong wireframe is a wrong
requirement rather than a matter of taste.

**These are generated, not typed.** `e2e/wireframes.py` draws each frame on a character canvas where
`RAIL_W + MAIN_W + DOCK_W` *produce* the separator columns, so a border cannot be off by one, and every
write is clipped to its pane's own columns. The script also refuses to be quiet about copy that does
not fit: a clipped line is printed as a warning, and the fix is shorter copy, not a wider box.

```bash
python3 specs/013-improve-coding/e2e/wireframes.py            # print every frame
node apps/coding-agent/web/scripts/verify-spec-ascii.mjs \
     specs/013-improve-coding                                 # parse every box: 0 problems
```

Dimensions are the measured ones from [006] and [012]: chrome 52 px, rail 276, main 822, dock 380 at
1480×900. In the frames one character is ~14 px, so the panes read as 30 / 45 / 27 columns.

---

## What the geometry means

```text
  chrome 52 px   identity · model · state              ⌘K search           account
  --------------- ------------------------------------------------------ --------------
  rail 276 px    the navigator: Sessions, Files,        dock 380 px        the conversation
                 Catalog, and Data (new)                                  and the plan
  --------------- ------------------------------------------------------ --------------
                 main 822 px: the document, the mission, or the start screen

The fourth rail tab is new [UI-2]. The dock is unchanged [012]: a state word, a binding,
a composer that is always writable.
```

Every frame below keeps that skeleton. What changes between them is what the main pane and the dock
say, and which of them has the user's attention.

---

#### S1 — The shell, with the new `Data` rail tab

```text
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ ⌘ OpenGenie   ▸ gemini-3.8-flash  ● ready                     [ ⌘K   search or run a command ]  RM ▾   │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ Sessions Files Catalog Data  │ pg_tickets                                  │ ● ready                   │
│──────────────────────────────│─────────────────────────────────────────────│ in context: pg_tickets    │
│ ▾ Lakebase                   │ Lakebase project · projects/pg-tickets      │───────────────────────────│
│   ● pg_tickets      project  │ postgres 17 · production · scale to zero    │ ╭─ created a database ─╮  │
│   ○ pg_orders       project  │                                             │ │ pg_tickets        ✓  │  │
│ ▾ Databricks Apps            │ COMPUTE                                     │ ╰──────────────────────╯  │
│   ▲ tickets_app         app  │   primary  READ_WRITE  0.5–4 CU   ready     │ ╭─ created an app ─────╮  │
│   △ orders_api          app  │   host     ep-cool-butterfly-9f2            │ │ tickets_app       ✓  │  │
│ ▾ Unity Catalog              │                                             │ │ running · /logz      │  │
│   samples.nyctaxi.trips      │ BRANCHES                                    │ ╰──────────────────────╯  │
│                              │   production          default               │                           │
│                              │   agent-4ff4405d      from production       │ Both exist. The app       │
│                              │                                             │ reads the table you       │
│                              │ DATABASES                                   │ seeded.                   │
│                              │   databricks_postgres 3 tables 12 rows      │                           │
│                              │                                             │                           │
│                              │ USED BY                                     │───────────────────────────│
│                              │   tickets_app        CAN_CONNECT_AND_CREATE │ +  @  /   model ▾  Send   │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

The rail's fourth tab is new `[UI-2]`. Every node kind in it opens a document `[UI-1]`. The dock still answers the [012] rule: a state word, the binding it is about, and a composer that never refuses a keystroke.

#### S2 — A Lakebase project, opened as a document

```text
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ ⌘ OpenGenie   ▸ gemini-3.8-flash  ● ready                     [ ⌘K   search or run a command ]  RM ▾   │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ Sessions Files Catalog Data  │ pg_tickets · branch agent-4ff4405d          │ ● ready                   │
│──────────────────────────────│─────────────────────────────────────────────│ in branch agent-4f…       │
│ ▾ Lakebase                   │ COMPUTE  primary  READ_WRITE                │───────────────────────────│
│   ● pg_tickets               │   0.5–4 CU    max − min = 3.5  ✓ (≤ 16)     │ ╭─ ran SQL ────────────╮  │
│   ○ pg_orders                │   scale to zero  24 h idle                  │ │ 12 rows · 0.4 s   ✓  │  │
│ ▾ Databricks Apps            │   218 connections at 1 CU                   │ ╰──────────────────────╯  │
│   ▲ tickets_app              │                                             │                           │
│   △ orders_api               │ TABLES IN databricks_postgres / app         │ The table is in the       │
│                              │   name        rows     size                 │ branch, not in            │
│                              │   tickets       12     8 kB                 │ production.               │
│                              │   agents         3     8 kB                 │                           │
│                              │                                             │                           │
│                              │ SQL RUNS ON THIS BRANCH ONLY                │                           │
│                              │   production was never written to           │                           │
│                              │                                             │                           │
│                              │                                             │                           │
│                              │                                             │───────────────────────────│
│                              │                                             │ +  @  /   model ▾  Send   │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

Every value is a fact from a call, never a paraphrase `[UI-3]`. The autoscaling range shows the rule being evaluated (`max − min = 3.5 ✓ (≤ 16)`) because that is the number a user gets wrong `[LB-4]`. The branch line exists because SQL now runs on a named branch `[LB-3]`.

#### S3 — A Databricks App, opened as a document

```text
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ ⌘ OpenGenie   ▸ gemini-3.8-flash  ● ready                     [ ⌘K   search or run a command ]  RM ▾   │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ Sessions Files Catalog Data  │ tickets_app                                 │ ● ready                   │
│──────────────────────────────│─────────────────────────────────────────────│ in context: tickets_app   │
│ ▾ Lakebase                   │ RUNNING  ·  deployment SUCCEEDED            │───────────────────────────│
│   ● pg_tickets               │ URL      tickets-app-1.aws.datab…           │ ╭─ verified the app ───╮  │
│ ▾ Databricks Apps            │ COMPUTE  MEDIUM · 1 instance · scale to 0   │ │ HTTP 200          ✓  │  │
│   ▲ tickets_app              │                                             │ │ 12 rows returned  ✓  │  │
│   △ orders_api               │ RESOURCES                                   │ ╰──────────────────────╯  │
│                              │   postgres   …/branches/agent-4ff4405d      │                           │
│                              │              CAN_CONNECT_AND_CREATE         │ Proven, not claimed:      │
│                              │                                             │ the URL answered.         │
│                              │ HEALTH                                      │                           │
│                              │   GET /           200   41 ms               │                           │
│                              │   GET /api/rows   200   63 ms  12 rows      │                           │
│                              │                                             │                           │
│                              │ LOGS (tail)   /logz                         │                           │
│                              │   10:42:01 uvicorn running on :8000         │                           │
│                              │                                             │───────────────────────────│
│                              │                                             │ +  @  /   model ▾  Send   │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

The health block is the answer to "is it working" `[UI-4]`, backed by one HTTP call `[AP-4]`. `/logz` is a link, not a promise: logs are lost when compute stops `[E-14]`.

#### S4 — The approval moment: a deploy outside the folder

```text
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ ⌘ OpenGenie   ▸ gemini-3.8-flash  ● working                   [ ⌘K   search or run a command ]  RM ▾   │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ Sessions Files Catalog Data  │ tickets_app                                 │ ● decide                  │
│──────────────────────────────│─────────────────────────────────────────────│                           │
│ ▾ Databricks Apps            │ A deployment is waiting for you.            │───────────────────────────│
│   ▲ tickets_app              │                                             │ ╭─ needs your decision ╮  │
│                              │ The agent wrote the files and asks before   │ │ deploy an app outside│  │
│                              │ deploying: an app is visible to the whole   │ │ your working folder  │  │
│                              │ workspace.                                  │ ╰──────────────────────╯  │
│                              │                                             │ /Users/you/agent_scra…    │
│                              │ Nothing has been deployed yet.              │   tickets_app             │
│                              │                                             │                           │
│                              │                                             │ why: an app is            │
│                              │                                             │ workspace-wide, so it     │
│                              │                                             │ is named after this       │
│                              │                                             │ session                   │
│                              │                                             │ [Allow once] [Session]    │
│                              │                                             │ [        Deny        ]    │
│                              │                                             │───────────────────────────│
│                              │                                             │ readOnly · decide above   │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

Creating an app outside the working folder is a decision, not a background effect `[SCF-4]`. The three outcomes are one click each and none of them is dismissible with Escape, which is the [012] rule for a decision that must be made rather than escaped.

#### S5 — A refusal, in the platform's own words

```text
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ ⌘ OpenGenie   ▸ gemini-3.8-flash  ● blocked                   [ ⌘K   search or run a command ]  RM ▾   │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ Sessions Files Catalog Data  │ Cannot create a Lakebase project            │ ● blocked                 │
│──────────────────────────────│─────────────────────────────────────────────│                           │
│ ▾ Lakebase                   │ The workspace refused:                      │───────────────────────────│
│   (nothing yet)              │                                             │ The agent stopped.        │
│                              │   PERMISSION_DENIED: you need CAN MANAGE    │                           │
│                              │   on project pg-tickets                     │ Nothing was created.      │
│                              │                                             │                           │
│                              │ That is your access, not the app's.         │ The platform's own words  │
│                              │ Ask the owner, or pick a project you own.   │ are in the centre,        │
│                              │                                             │ verbatim.                 │
│                              │   [ Choose another project ]   [ Copy ]     │                           │
│                              │                                             │                           │
│                              │                                             │                           │
│                              │                                             │                           │
│                              │                                             │                           │
│                              │                                             │                           │
│                              │                                             │───────────────────────────│
│                              │                                             │ +  @  /   model ▾  Send   │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

The platform's sentence, verbatim, then who can fix it, then one action `[UI-6]`. No retry: a missing `CAN MANAGE` does not change on the second try `[E-8]`.

#### S6 — A scaffold in progress: seven proven steps

```text
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ ⌘ OpenGenie   ▸ gemini-3.8-flash  ● working                   [ ⌘K   search or run a command ]  RM ▾   │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ Sessions Files Catalog Data  │ New app · from a Lakebase table             │ ● working                 │
│──────────────────────────────│─────────────────────────────────────────────│                           │
│                              │ 1  ✓  project     pg_tickets                │───────────────────────────│
│                              │ 2  ✓  branch      agent-4ff4405d            │ ╭─ plan ───────────────╮  │
│                              │ 3  ✓  table       app.tickets · 12 rows     │ │ create database    ✓ │  │
│                              │ 4  ✓  resource    postgres CAN_CONNECT      │ │ seed a table       ✓ │  │
│                              │ 5  ▸  files       app.yaml · main.py        │ │ scaffold the app   ▸ │  │
│                              │ 6  ·  deploy      —                         │ │ deploy             · │  │
│                              │ 7  ·  verify      —                         │ │ verify HTTP 200    · │  │
│                              │                                             │ ╰──────────────────────╯  │
│                              │ A step is drawn done only when a call proved│                           │
│                              │ it. Unproven steps stay empty.              │───────────────────────────│
│                              │                                             │ [ Stop ]                  │
│                              │                                             │                           │
│                              │                                             │                           │
│                              │                                             │                           │
│                              │                                             │                           │
│                              │                                             │                           │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

Seven steps, and a step is `✓` only when a call proved it `[SCF-1]`. Step 5 is `▸` because it is running; 6 and 7 are `·` because nothing has been attempted `[SCF-2]`. A failure at step 3 leaves 4–7 empty rather than creating an app over a missing table.

#### S7 — At 900 px: the rail keeps a column, the dock yields (see the note)

```text
┌────────────────────────────────────────────────────────┐
│ ⌘ OpenGenie  ▸ gemini-3.8-flash          ☰   ⌘K   RM ▾ │
└────────────────────────────────────────────────────────┘
┌────────────────────────────────────────────────────────┐
│ tickets_app                    │ ● ready               │
│────────────────────────────────│ in context:           │
│ RUNNING · deployment SUCCEEDED │ tickets_app           │
│ GET /           200  41 ms     │───────────────────────│
│ GET /api/rows   200  63 ms     │ The app answers       │
│                                │ on the URL above.     │
│ ☰ opens the navigator:         │                       │
│    Data → Lakebase             │ Under 1180 px the     │
│                                │ rail is a drawer.     │
│                                │                       │
│                                │───────────────────────│
│                                │ + @ /  model  Send    │
└────────────────────────────────────────────────────────┘
```

**Corrected after the E2E run.** This frame was drawn assuming a drawer at 900 px. `modeFor` in `domain/layout.ts` puts `narrow` at ≤ 820, so 900 px is `mid`: the rail keeps a column and the DOCK yields to an edge tab. The scene asserts the code's rule, not this drawing — the frames are illustrative, `layout.ts` is the authority `[UI-2]`.

#### S8 — The palette, with the new objects in it

```text
┌────────────────────────────────────────────────────────────────┐
│ ⌘K   search or run a command                                   │
│────────────────────────────────────────────────────────────────│
│ › lakeb                                                        │
│────────────────────────────────────────────────────────────────│
│ Lakebase   pg_tickets          project                         │
│ Lakebase   pg_orders           project                         │
│ Apps       tickets_app          running                        │
│ Apps       orders_api           stopped                        │
│ Action     Create a Lakebase project                           │
│ Action     Scaffold an app from a table                        │
│ Table      samples.nyctaxi.trips                               │
└────────────────────────────────────────────────────────────────┘
```

Search finds the two new kinds by name, beside notebooks and tables `[UI-5]`. A project is matched on its id and an app on its name, which are the two identities `[LB-5]` and `[AP-1]` assign.

---

## The state table these frames cover

Every screen here is reachable, and every one has a way out. `[E-*]` refers to
[09 Edge cases](09-edge-cases.md).

| Screen | Entered when | The way out it offers |
|---|---|---|
| S1 the shell | any load, Data tab selected | ⌘4, or a click on a node |
| S2 a project | a node, a tool row's *Open*, or `#/lakebase/…` | the tab strip; *Open in Databricks* |
| S3 an app | a node, a tool row's *Open*, or `#/app/…` | the tab strip; the `/logz` link |
| S4 the approval | the agent asks to create outside the folder | Allow once / This session / Deny `[E-5]` |
| S5 a refusal | a 403, a git-only workspace, a bad name | the platform's sentence + one action `[E-7..9]` |
| S6 a scaffold running | a plan with ≥ 1 step | Stop; and every step names its proof |
| S7 narrow | viewport < 1180 px | ⌘B / ☰ opens the navigator; ⌘J closes the dock |
| S8 the palette | ⌘K | Escape, or pick a row |

The rule every frame obeys, from [012] and restated because it is easy to break in a new screen:
**a state that can persist must name its exit, in the same place it is announced.**
