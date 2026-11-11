[Index](README.md) · prev: [05 Gaps and improvements](05-gaps-and-improvements.md) · next: [07 Diagrams](07-diagrams.md)

# 06 · Wireframes

Every screen this set adds, the states each can be in, and the recovery path from each. The frames are
**generated** by [`tools/build_wireframes.py`](tools/build_wireframes.py) and checked by
`node scripts/verify-spec-ascii.mjs`, so a box cannot drift by one column without failing a command.
Edit the generator, not this file.

Two conventions, both learned from that verifier:

* **A border is a line, not a place for text.** A section title is a row inside the frame
  (`-- Last run ----`), never a label welded into `+----+`.
* **A multi-pane layout is one frame with vertical gutters**, not three boxes side by side. A second
  box's right border reads as content escaping the first.

| Frame | Screen | Phase | The question it answers |
|---|---|---|---|
| F1 | the shell as it is | — | what exists today, and the three places it falls short |
| F2 | parallel chats | 3 | can I run three things at once? |
| F3 | conversation search | 3 | where did I talk about `gold`? |
| F4 | after a restart | 2 | what survived, and what needs me? |
| F5 | write mode + approval | 2 | what may the agent change, and who decided? |
| F6 | instructions and skills | 2 | what is the agent told, and by whom? |
| F7 | accept/reject a proposal | 3 | may I see the change before it lands? |
| F8 | cost and model per turn | 2 | what did this conversation cost, on which model? |
| F9 | declarative hooks | 4 | can my platform team set the rules? |
| F10 | 820 px | — | does it survive a small window? |
| F11 | navigation | — | how do I reach any of this? |

The widths are `domain/layout.ts`'s, read rather than guessed: `CENTRE_MIN` 480 px, `ASSISTANT_MIN`
320, `ASSISTANT_DEFAULT` 380, `ASSISTANT_COLUMN_MIN` 1136, `ALL_FOUR_MIN` 1476, `modeFor` mid at
1180 and narrow at 820. F10 is drawn at 820, which is the narrowest width where the centre still has
its minimum.

---

### F1 · The shell as it is, and the three places it falls short

```text
┌────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│────────────────────────────────────────────────────────────────────────────────────────────────────────────────│
│ F1 · the shell as it exists today (measured, 1440 px)                                                          │
│────────────────────────────────────────────────────────────────────────────────────────────────────────────────│
│ rail - Sessions         │ Document tabs: mission | notebook | job         │ conversation · in context: revenue │
│                         │ ──────────────────────────────────────────────  │ ───────────────────────────────────│
│ SessionList             │ Mission overview                                │ You                                │
│  groups by day          │                                                 │  Fix the daily revenue notebook    │
│  order: RANDOM [F-6]    │  What you asked                                 │                                    │
│                         │  Fix the daily revenue notebook and prove       │ Agent                    blocked   │
│  Today                  │  the number is right.                           │  I could not verify requirement 2. │
│   Fix the revenue  ok   │                                                 │                                    │
│   Why is gold late  !   │  Plan                              2 of 4       │  v dbx_read_notebook       ok 1.2s │
│   New session      ok   │  [######----------------------]                 │  v dbx_describe_table      ok 0.9s │
│                         │   v Read the notebook                           │  x dbx_write_notebook    denied    │
│  Yesterday              │   v Check the column names                      │     outside the folder             │
│   Build a job      ok   │   > Write the corrected copy                    │                                    │
│   Lakebase app     ok   │   . Run it and quote the result                 │ ───────────────────────────────────│
│                         │                                                 │ Ask about revenue...       [model] │
│  search: title+folder   │  Evidence                                       │ ONE stream per page      [G-1]     │
│  only           [G-2]   │   v requirement 1  verified  source >           │                                    │
│                         │   ! requirement 2  NOT verified                 │                                    │
│  cmd+1 sessions         │                                                 │                                    │
│  cmd+2 files            │  Outputs & references                           │                                    │
│  cmd+3 catalog          │   notebook  /Users/me/agent_scratch/rev         │                                    │
│  cmd+4 data             │   job 812345678901                              │                                    │
│── what this frame is for ──────────────────────────────────────────────────────────────────────────────────────│
│The shell is good and the dock is the best decision in it. Three annotations mark the                           │
│gaps this spec closes: the session list order [F-6], the search scope [G-2], and the fact                       │
│that there is exactly one live conversation per page [G-1].                                                     │
└────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### F2 · Parallel chats: a tab strip of live conversations

```text
┌────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│────────────────────────────────────────────────────────────────────────────────────────────────────────────────│
│ F2 · parallel chats: a tab strip of conversations (phase 3, [R-14])                                            │
│────────────────────────────────────────────────────────────────────────────────────────────────────────────────│
│ rail - Sessions     │ [ revenue x] [ gold x] [ tickets !] [+]       │ other conversations                      │
│                     │ ────────────────────────────────────────────  │ ───────────────────                      │
│ Running   2         │ revenue                running  0:42  12k t   │ gold    running 31s                      │
│  > revenue  ...     │                                               │  task silver_agg                         │
│  > gold     ...     │ You   Fix the daily revenue notebook...       │  reading 4 tables                        │
│ Waiting   1         │                                               │                                          │
│  * tickets  !       │ Agent                                         │ tickets waiting                          │
│ Ready     3         │  Reading the notebook.                        │  needs your OK on                        │
│  . job audit        │  v dbx_read_notebook               ok 1.2s    │  CREATE TABLE                            │
│  . pipeline         │  v dbx_describe_table              ok 0.9s    │  main.gold.tickets                       │
│                     │  > dbx_write_notebook           running       │  [ Review ]                              │
│ A dot means it is   │                                               │                                          │
│ working whether or  │  Each tab keeps its OWN stream and its own    │ Never a silent                           │
│ not you are looking │  reducer state. Switching does not cancel.    │ background failure:                      │
│ at it.              │ ────────────────────────────────────────────  │ a waiting tab says                       │
│                     │ Ask in revenue...                       [m]   │ so in the strip.                         │
│ cmd+shift+[ / ]     │                                               │                                          │
│ next / prev tab     │                                               │                                          │
│── what this frame is for ──────────────────────────────────────────────────────────────────────────────────────│
│Parallel chats are the largest UX gap against Genie Code [C2] and against Cursor/Claude                         │
│Code background sessions. The journal already supports it: a stream is a cursor into                            │
│committed events, so N tabs are N cursors and nothing on the server changes.                                    │
└────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### F3 · Search inside conversations

```text
┌────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│────────────────────────────────────────────────────────────────────────────────────────────────────────────────│
│ F3 · search inside conversations (phase 3, [R-15])                                                             │
│────────────────────────────────────────────────────────────────────────────────────────────────────────────────│
│ search conversations       │ gold      in 3 conversations                                                      │
│ ─────────────────────────  │ ───────────────────────────────────────────────────                               │
│ gold late          2 hits  │ revenue   Fix the daily revenue notebook                                          │
│                            │   Today 14:02   12 hits   4 turns                                                 │
│ Today                      │   ... the gold table arrived at 06:11 but the                                     │
│  revenue  Fix the daily    │   notebook reads it at 06:00 ...                                                  │
│     ... gold is late ...   │                                                                                   │
│  gold     Why is the ...   │   Open at this turn >                                                             │
│     ... gold arrived at..  │                                                                                   │
│                            │ gold      Why is the pipeline late                                                │
│ Yesterday                  │   Today 11:20   5 hits    2 turns                                                 │
│  job audit  Check the...   │   ... silver finished 06:04, gold depends on it ...                               │
│     ... gold table ...     │                                                                                   │
│                            │ job audit Check the gold row count                                                │
│ Searches the JOURNAL, not  │   Yesterday 17:44  2 hits  1 turn                                                 │
│ the title. The rail used   │   ... gold had 0 rows on the 9th ...                                              │
│ to search titles + folder  │                                                                                   │
│ only                       │ Opens the turn, not just the conversation, and                                    │
│                            │ scrolls to the matching answer. That is the thing                                 │
│                            │ a person actually wants when they remember a word.                                │
│── what this frame is for ──────────────────────────────────────────────────────────────────────────────────────│
│Genie Code searches chats [C4]. OpenGenie searches labels. The journal makes full-text                          │
│search cheap and exact, and 'open at this turn' is only possible because events are                             │
│ordered and addressable by seq.                                                                                 │
└────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### F4 · After a restart: three sessions, three different truths

```text
┌────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│────────────────────────────────────────────────────────────────────────────────────────────────────────────────│
│ F4 · after a restart: three sessions, three different truths (phase 2, [R-10])                                 │
│────────────────────────────────────────────────────────────────────────────────────────────────────────────────│
│ a session that WAS mid-turn  │ a session that was IDLE       │ a session that was EVICTED                      │
│ ───────────────────────────  │ ────────────────────────────  │ ─────────────────────────────                   │
│ revenue        needs you     │ job audit          ready      │ pipeline audit     archived                     │
│                              │                               │                                                 │
│ Your progress is saved.      │ This conversation was idle    │ The transcript is in the                        │
│ The server restarted while   │ when the server restarted.    │ journal, so this page loads                     │
│ this turn was running, so    │ Nothing was in flight, so     │ from Postgres on demand.                        │
│ nothing was repeated.        │ nothing needs your decision.  │                                                 │
│                              │                               │ 12 turns  ·  last 6 Nov                         │
│ 4 tool calls completed       │ Type to continue. The agent   │ 3 objects created                               │
│ 1 was in flight              │ starts on your first message. │                                                 │
│                              │                               │ [ Read the transcript ]                         │
│ [ Review progress ]          │ [ Ask something ]             │ [ Start a new conversation ]                    │
│ [ Restore and continue ]     │                               │                                                 │
│                              │                               │ Today: 404 'no such session'                    │
│ requires_resume = true       │ requires_resume = FALSE       │ although the row exists.                        │
│ status = blocked             │ (today: true, which is the    │ That is [F-9], second half.                     │
│                              │  defect [F-9])                │                                                 │
│── what this frame is for ──────────────────────────────────────────────────────────────────────────────────────│
│The three states must not share a word. 'Needs you' is a fact about work in flight; 'ready'                     │
│is a fact about an idle conversation; 'archived' is the user's own delete. Today all three                      │
│render as 'needs attention', which teaches users that the app is fragile.                                       │
└────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### F5 · Write mode, and what an approval shows

```text
┌────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│────────────────────────────────────────────────────────────────────────────────────────────────────────────────│
│ F5 · write mode, and what an approval actually shows (phase 2, [R-9])                                          │
│────────────────────────────────────────────────────────────────────────────────────────────────────────────────│
│ Session setup                         │ an approval, inline in the dock                                        │
│ ────────────────────────────────────  │ ──────────────────────────────────────                                 │
│ Folder   /Users/me/agent_scratch      │ needs your decision                                                    │
│ Schema   main.agent_scratch           │                                                                        │
│                                       │ dbx_run_sql wants to write                                             │
│ Write mode                            │                                                                        │
│  ( ) read-only                        │   CREATE OR REPLACE TABLE                                              │
│      the agent may read; every write  │   main.agent_scratch.revenue_daily                                     │
│      is refused with a reason         │   AS SELECT ...                                                        │
│  (*) fenced            recommended    │                                                                        │
│      writes only inside the folder    │ Inside your fence. 1 table replaced.                                   │
│      and the schema above             │ This cannot be undone from here.                                       │
│  ( ) ask                              │                                                                        │
│      a write inside the fence waits   │ [ Allow once ] [ Allow for session ]                                   │
│      for you, one prompt per object   │ [ Deny ]                                                               │
│                                       │                                                                        │
│ Model    vertex/gemini-3.8-flash      │ The reason is the sentence the tool                                    │
│                                       │ server wrote, not a paraphrase.                                        │
│ [ Start ]                             │                                                                        │
│── what this frame is for ──────────────────────────────────────────────────────────────────────────────────────│
│Today NBMCP_ALLOW_WRITES=1 is a constant, so 'fenced' is the only behaviour that exists                         │
│and 'ask' does not [F-8]. Making the mode a session field turns a hidden constant into a                        │
│choice a user can see, and keeps today's behaviour as the default.                                              │
└────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### F6 · Instructions and skills, with their source

```text
┌────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│────────────────────────────────────────────────────────────────────────────────────────────────────────────────│
│ F6 · instructions and skills: what the agent is told, and where it came from (phase 2)                         │
│────────────────────────────────────────────────────────────────────────────────────────────────────────────────│
│ Settings           │ Instructions                          │ How the agent sees them                           │
│ ───────────────    │ ───────────────────────────────────   │ ───────────────────────────────────               │
│ > Instructions     │ Personal            [ 12 lines ]      │ In the transcript, as a collapsed                 │
│   Skills           │   /Users/me/.assistant/instructions   │ block labelled by SOURCE:                         │
│   Models           │   edited by you, 2 days ago           │                                                   │
│   Providers        │   [ Edit ]  [ Preview as the agent ]  │  v Context from your instructions                 │
│   Hooks            │                                       │     personal  12 lines   (you)                    │
│   Budget           │ Workspace           [ 31 lines ]      │  v Context from the workspace                     │
│                    │   Workspace/.assistant/instructions   │     workspace 31 lines   (dana@)                  │
│ Personal scope     │   edited by dana@, 1 week ago         │  v Context from AGENTS.md                         │
│  /Users/me/        │   read-only to you [ View ]           │     folder    8 lines                             │
│   .assistant/      │                                       │                                                   │
│    instructions.md │ AGENTS.md            [ found ]        │ Never merged into your message: a                 │
│    skills/         │   /Users/me/agent_scratch/AGENTS.md   │ user must be able to tell what they               │
│     revenue.md     │   committed to the folder             │ typed from what the team configured.              │
│     dq.md          │                                       │                                                   │
│                    │ Order: workspace, then personal,      │ A skill is loaded only when the                   │
│ Workspace scope    │ then AGENTS.md, then this session's   │ agent asks for it (dbx_skill), so                 │
│  Workspace/        │ fence rules (always last, always      │ 40 skills cost nothing until one is               │
│   .assistant/      │ wins).                                │ relevant.                                         │
│    skills/         │                                       │                                                   │
│     naming.md      │                                       │                                                   │
│── what this frame is for ──────────────────────────────────────────────────────────────────────────────────────│
│Genie Code reads AGENTS.md and CLAUDE.md and offers personal and workspace instructions and                     │
│skills [C13-C15]. OpenGenie WRITES an AGENTS.md and reads none [G-5]. The labelling is the                      │
│part that matters for governance: configured context must never look like the user's words.                     │
└────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### F7 · A proposed edit, accepted or rejected

```text
┌────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│────────────────────────────────────────────────────────────────────────────────────────────────────────────────│
│ F7 · a proposed edit, accepted or rejected (phase 3, [R-22])                                                   │
│────────────────────────────────────────────────────────────────────────────────────────────────────────────────│
│── the notebook, with a proposal over cell 3 ───────────────────────────────────────────────────────────────────│
│  cell 1  python   v ok                    [ Run ] [ Ask ]                                                      │
│    df = spark.table('samples.nyctaxi.trips')                                                                   │
│                                                                                                                │
│  cell 2  python   v ok                    [ Run ] [ Ask ]                                                      │
│    daily = df.groupBy('pickup_date').count()                                                                   │
│                                                                                                                │
│  cell 3  python   PROPOSED                [ Keep ] [ Reject ]                                                  │
│   -  daily.write.mode('overwrite').saveAsTable('revenue')                                                      │
│   +  (daily                                                                                                    │
│   +    .withColumnRenamed('count', 'trips')                                                                    │
│   +    .write.mode('overwrite')                                                                                │
│   +    .saveAsTable('main.agent_scratch.revenue'))                                                             │
│    why: 'revenue' had no catalog, so it resolved to whatever the warehouse defaulted to.                       │
│    Accepting writes to the working folder; the original notebook is untouched.                                 │
│── what this frame is for ──────────────────────────────────────────────────────────────────────────────────────│
│Genie Code presents edits for accept/reject [C24]; OpenGenie has no proposal at all -                           │
│editor/diff.ts computes a minimal change to map a remote edit onto an open document, which                      │
│is a different job. The fence is what makes this safe: 'Keep' writes inside the folder only.                    │
└────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### F8 · What this conversation cost, and on which model

```text
┌────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│────────────────────────────────────────────────────────────────────────────────────────────────────────────────│
│ F8 · what this conversation has cost (phase 2, [R-24])                                                         │
│────────────────────────────────────────────────────────────────────────────────────────────────────────────────│
│ inspector - session         │ which turn used which model                                                      │
│ ──────────────────────────  │ ──────────────────────────────────────────────────                               │
│ model   gemini-3.8-flash    │ #   model                 provider    in   out                                   │
│ wire    vertex-native       │ 1   gemini-3.8-flash      vertex      18k   4k                                   │
│ limits  1M ctx / 8k out     │ 2   gemini-3.8-flash      vertex      42k   6k                                   │
│ evidence  measured          │ 3   gemini-3.8-flash      vertex      61k   7k                                   │
│                             │ 4   gpt-oss-120b          databricks  58k   3k                                   │
│ turns        7 of 200       │ 5   gpt-oss-120b          databricks  71k   5k                                   │
│ input       412k tokens     │ 6   gemini-3.8-flash      vertex      88k   6k                                   │
│ output       38k tokens     │ 7   gemini-3.8-flash      vertex      74k   7k                                   │
│ cached       96k tokens     │ ──────────────────────────────────────────────────                               │
│                             │ The switch happened at turn 4 and again at turn 6.                               │
│ est. cost        $0.41      │ Every pin was written BEFORE the prompt and never                                │
│ budget           $2.00      │ rewritten (llm.llm_turn_model), so this table is                                 │
│ [############----------]    │ a record, not a reconstruction.                                                  │
│                             │                                                                                  │
│ A turn that would cross     │ This is the column Genie Code cannot offer: its                                  │
│ the budget is BLOCKED       │ model is not a setting a customer can inspect per                                │
│ with the number in the      │ turn.                                                                            │
│ message, before it spends.  │                                                                                  │
│── what this frame is for ──────────────────────────────────────────────────────────────────────────────────────│
│The product's first promise is 'the model is a setting'. A setting nobody can audit is a                        │
│preference. The turn pins already exist; this frame gives them a surface, and adds the one                      │
│thing Genie Code's budgets cannot be: a limit that stops work before it spends.                                 │
└────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### F9 · Declarative hooks

```text
┌────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│────────────────────────────────────────────────────────────────────────────────────────────────────────────────│
│ F9 · declarative hooks: a platform team's rules, evaluated in the fence (phase 4, [R-13])                      │
│────────────────────────────────────────────────────────────────────────────────────────────────────────────────│
│── Workspace/.opengenie/hooks.yaml - read as the user, shown read-only ─────────────────────────────────────────│
│  hooks:                                                                                                        │
│    - name: block-delete-on-gold                                                                                │
│      on: before_tool                                                                                           │
│      match: { tool: dbx_run_sql }                                                                              │
│      when:  sql.matches('(?i)^\\s*delete\\s+from\\s+main\\.gold\\.')                                           │
│      then:  refuse                                                                                             │
│      say:   'main.gold is append-only. Write to a branch and merge.'                                           │
│                                                                                                                │
│    - name: format-after-write                                                                                  │
│      on: after_tool                                                                                            │
│      match: { tool: dbx_write_notebook }                                                                       │
│      then:  run                                                                                                │
│      run:   ['ruff', 'format', '--stdin']                                                                      │
│── what the user sees when one fires ───────────────────────────────────────────────────────────────────────────│
│  x dbx_run_sql                       refused by hook                                                           │
│    main.gold is append-only. Write to a branch and merge.                                                      │
│    [ Ask the agent to use a branch ]   [ Explain this rule ]                                                   │
│── why it lives in the fence and not in a script ───────────────────────────────────────────────────────────────│
│A hook that runs as a separate process would need its own identity, its own timeout and                         │
│its own failure mode. Evaluated in the tool server, it inherits all three from the process                      │
│that already refuses writes: the same place, the same reason sentence, the same audit row.                      │
└────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### F10 · 820 px: the dock is a drawer

```text
┌──────────────────────────────────────────────────────────────────────────┐
│──────────────────────────────────────────────────────────────────────────│
│ F10 · 820 px: the dock is a drawer and the rail is a chooser             │
│──────────────────────────────────────────────────────────────────────────│
│ Document: revenue_demo        [ < ] [ dock ]                             │
│ -----------------------------------------------                          │
│  cell 1   python                   [ Run ] [ Ask ]                       │
│    df = spark.table('samples.nyctaxi.trips')                             │
│                                                                          │
│  cell 2   python                   [ Run ] [ Ask ]                       │
│    display(df.limit(10))                                                 │
│                                                                          │
│ + Code   + Text                                                          │
│ -----------------------------------------------                          │
│ [ drawer: conversation, 380 px, over the work ]                          │
│  revenue            working 0:12                                         │
│  v dbx_describe_table          ok 0.9s                                   │
│  > dbx_run_sql              running                                      │
│  -------------------------------------------                             │
│  Ask about revenue...                [ m ]                               │
│                                                                          │
│  Below 480 + 380 the assistant overlays;                                 │
│  the centre keeps CENTRE_MIN = 480 px.                                   │
└──────────────────────────────────────────────────────────────────────────┘
```

### F11 · Navigation

```text
┌────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│────────────────────────────────────────────────────────────────────────────────────────────────────────────────│
│ F11 · navigation: every surface, and the key that reaches it                                                   │
│────────────────────────────────────────────────────────────────────────────────────────────────────────────────│
│  cmd+k  palette            -> any doc, any session, any command                                                │
│  cmd+1  rail: sessions     cmd+shift+n  new session                                                            │
│  cmd+2  rail: files        cmd+p        find a notebook or file                                                │
│  cmd+3  rail: catalog      cmd+4        rail: data (jobs, runs, pipelines)                                     │
│  cmd+j  toggle assistant   cmd+i        toggle inspector                                                       │
│  cmd+b  toggle navigator   cmd+l        focus the composer                                                     │
│  cmd+shift+i  ask about the focused cell                                                                       │
│  cmd+shift+m  change the model          cmd+,  providers and keys                                              │
│  cmd+shift+[ / ]  previous / next conversation tab      (phase 3)                                              │
│  cmd+z  undo (structural, in a notebook)  cmd+w  close a document tab                                          │
│  cmd+shift+t  reopen the last closed tab                                                                       │
│── the grammar behind the keys ─────────────────────────────────────────────────────────────────────────────────│
│  cmd+digit   panes          cmd+letter   an action                                                             │
│  cmd+shift   a destructive or session-level twin of the plain chord                                            │
│  Nothing is bound twice: domain/keys.ts is one table and a test walks it.                                      │
└────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## What the frames decide, in words

| Decision | Frame | Why it is decided here and not in a component |
|---|---|---|
| A conversation tab is a **cursor**, not a copy | F2 | If a tab held state the server did not, switching tabs would lose work. The journal makes a tab a `seq` and nothing else |
| **Four words** for session state, never five | F4 | `needs you`, `ready`, `archived`, `working`. A fifth word is how a product acquires a screen nobody can explain |
| An approval **quotes the tool server** | F5 | The sentence that refused the write is the sentence the user reads. A paraphrase is a second policy |
| Configured context is **labelled by source** | F6 | A user must be able to tell what they typed from what their team configured, or the audit trail is a story about the wrong author |
| A proposal says **why**, in the agent's words | F7 | "Accept" with no reason is a coin flip. The reason line is what makes the diff reviewable |
| Cost is **per turn, per model**, not a total | F8 | A total tells you nothing actionable. The turn pin already records it; the frame only stops hiding it |
| A hook is a **rule in the fence** | F9 | One place evaluates rules, one sentence explains a refusal, one audit row records it |
| The assistant **yields to the code** | F10 | `CENTRE_MIN` 480 px is the one number `layout.ts` exists to defend; a drawer is the assistant giving way |
