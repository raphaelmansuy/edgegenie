#!/usr/bin/env python3
"""Generate 06-wireframes.md.

Every frame is built by `Frame`, which pads each row to a fixed inner width, so a box cannot drift by
one column. `node scripts/verify-spec-ascii.mjs <dir>` parses the result, and the same script is the
gate on specs 013 and 014 — one convention for the whole repository.

Two rules the frames follow, both learned from the verifier:

  * a border is a line, not a place for text. A section title is a row inside the frame
    ("--- Last run ---"), never a label welded into the top border;
  * a multi-pane layout is ONE frame with vertical gutters, not three boxes side by side. A second
    box's right border reads as content escaping the first.

Run:  python3 tools/build_wireframes.py
"""

from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "06-wireframes.md"

WIDE = 114
NARROW = 76


class Frame:
    """A box whose every row is exactly `inner` characters between two vertical borders."""

    def __init__(self, inner: int = WIDE - 2) -> None:
        self.inner = inner
        self.rows: list[str] = []

    def top(self, label: str = "") -> "Frame":
        """The frame's own top border. It is always a plain line: a label in the border is a label
        the verifier reads as a break, and a title belongs in a row inside the frame."""
        self.rows.append("\u2500" * self.inner)
        if label:
            self.rows.append(f" {label}".ljust(self.inner))
            self.rows.append("\u2500" * self.inner)
        return self

    def line(self, text: str = "") -> "Frame":
        assert len(text) <= self.inner, f"{len(text)} > {self.inner}: {text!r}"
        self.rows.append(text.ljust(self.inner))
        return self

    def rule(self, label: str = "") -> "Frame":
        """An inner horizontal rule: a section divider that is not a box border."""
        if label:
            head = f"\u2500\u2500 {label} "
            self.rows.append(head + "\u2500" * (self.inner - len(head)))
        else:
            self.rows.append("\u2500" * self.inner)
        return self

    def blank(self) -> "Frame":
        return self.line("")

    def render(self) -> str:
        top = "\u250c" + "\u2500" * self.inner + "\u2510"
        body = "\n".join("\u2502" + r + "\u2502" for r in self.rows)
        bottom = "\u2514" + "\u2500" * self.inner + "\u2518"
        return "\n".join([top, body, bottom])


def panes(cells: list[list[str]]) -> list[str]:
    """Turn N panes into rows with vertical gutters, each column sized to its own content.

    Sizing from content rather than from guessed shares is the only way a wireframe stays honest:
    a share that is 3 characters too narrow silently truncates a label, and a truncated label is a
    claim about the screen that the screen does not make.
    """
    widths = [max((len(line) for line in cell), default=0) + 1 for cell in cells]
    height = max(len(c) for c in cells)
    rows: list[str] = []
    for i in range(height):
        parts = []
        for w, cell in zip(widths, cells):
            text = cell[i] if i < len(cell) else ""
            # A row made only of hyphens is a section rule, not content. Drawn with the box-drawing
            # horizontal it matches the frame's own borders, so the surface reads as one wireframe
            # rather than as three lists with ASCII underlines in them. A bar chart ("[###---]") is
            # content and keeps its hyphens: it is a measurement, not a divider.
            if text.strip() and not text.strip(" -") and "[" not in text:
                text = text.replace("-", "\u2500")
            parts.append(text.ljust(w))
        rows.append("\u2502".join(parts).rstrip())
    return rows


def total_width(cells: list[list[str]]) -> int:
    """What `panes` will produce, so a frame can assert it fits before it is drawn."""
    return sum(max((len(line) for line in cell), default=0) + 1 for cell in cells) + len(cells) - 1


# ===================================================================================== the frames

def f1_today() -> str:
    f = Frame()
    f.top("F1 · the shell as it exists today (measured, 1440 px)")
    body = panes([
            [
                " rail - Sessions        ",
                "",
                " SessionList            ",
                "  groups by day         ",
                "  order: RANDOM [F-6]   ",
                "",
                "  Today                 ",
                "   Fix the revenue  ok  ",
                "   Why is gold late  !  ",
                "   New session      ok  ",
                "",
                "  Yesterday             ",
                "   Build a job      ok  ",
                "   Lakebase app     ok  ",
                "",
                "  search: title+folder  ",
                "  only           [G-2]  ",
                "",
                "  cmd+1 sessions        ",
                "  cmd+2 files           ",
                "  cmd+3 catalog         ",
                "  cmd+4 data            ",
            ],
            [
                " Document tabs: mission | notebook | job        ",
                " ---------------------------------------------- ",
                " Mission overview                               ",
                "                                                ",
                "  What you asked                                ",
                "  Fix the daily revenue notebook and prove      ",
                "  the number is right.                          ",
                "                                                ",
                "  Plan                              2 of 4      ",
                "  [######----------------------]                ",
                "   v Read the notebook                          ",
                "   v Check the column names                     ",
                "   > Write the corrected copy                   ",
                "   . Run it and quote the result                ",
                "                                                ",
                "  Evidence                                      ",
                "   v requirement 1  verified  source >          ",
                "   ! requirement 2  NOT verified                ",
                "                                                ",
                "  Outputs & references                          ",
                "   notebook  /Users/me/agent_scratch/rev        ",
                "   job 812345678901                             ",
            ],
            [
                " conversation · in context: revenue  ",
                " ----------------------------------- ",
                " You                                 ",
                "  Fix the daily revenue notebook     ",
                "                                     ",
                " Agent                    blocked    ",
                "  I could not verify requirement 2.  ",
                "                                     ",
                "  v dbx_read_notebook       ok 1.2s  ",
                "  v dbx_describe_table      ok 0.9s  ",
                "  x dbx_write_notebook    denied    ",
                "     outside the folder             ",
                "                                     ",
                " ----------------------------------- ",
                " Ask about revenue...       [model]  ",
                " ONE stream per page      [G-1]      ",
            ],
        ],
    )
    for row in body:
        f.line(row)
    f.rule("what this frame is for")
    f.line("The shell is good and the dock is the best decision in it. Three annotations mark the")
    f.line("gaps this spec closes: the session list order [F-6], the search scope [G-2], and the fact")
    f.line("that there is exactly one live conversation per page [G-1].")
    return f.render()


def f2_threads() -> str:
    f = Frame()
    f.top("F2 · parallel chats: a tab strip of conversations (phase 3, [R-14])")
    body = panes([
            [
                " rail - Sessions ",
                "",
                " Running   2     ",
                "  > revenue  ...  ",
                "  > gold     ...  ",
                " Waiting   1     ",
                "  * tickets  !   ",
                " Ready     3     ",
                "  . job audit    ",
                "  . pipeline     ",
                "",
                " A dot means it is",
                " working whether or",
                " not you are looking",
                " at it.          ",
                "",
                " cmd+shift+[ / ]  ",
                " next / prev tab ",
            ],
            [
                " [ revenue x] [ gold x] [ tickets !] [+]      ",
                " -------------------------------------------- ",
                " revenue                running  0:42  12k t ",
                "                                              ",
                " You   Fix the daily revenue notebook...      ",
                "                                              ",
                " Agent                                        ",
                "  Reading the notebook.                       ",
                "  v dbx_read_notebook               ok 1.2s   ",
                "  v dbx_describe_table              ok 0.9s   ",
                "  > dbx_write_notebook           running      ",
                "                                              ",
                "  Each tab keeps its OWN stream and its own   ",
                "  reducer state. Switching does not cancel.   ",
                " -------------------------------------------- ",
                " Ask in revenue...                       [m]  ",
            ],
            [
                " other conversations ",
                " ------------------- ",
                " gold    running 31s ",
                "  task silver_agg    ",
                "  reading 4 tables   ",
                "                    ",
                " tickets waiting     ",
                "  needs your OK on   ",
                "  CREATE TABLE       ",
                "  main.gold.tickets  ",
                "  [ Review ]         ",
                "                    ",
                " Never a silent      ",
                " background failure: ",
                " a waiting tab says  ",
                " so in the strip.    ",
            ],
        ],
    )
    for row in body:
        f.line(row)
    f.rule("what this frame is for")
    f.line("Parallel chats are the largest UX gap against Genie Code [C2] and against Cursor/Claude")
    f.line("Code background sessions. The journal already supports it: a stream is a cursor into")
    f.line("committed events, so N tabs are N cursors and nothing on the server changes.")
    return f.render()


def f3_search() -> str:
    f = Frame()
    f.top("F3 · search inside conversations (phase 3, [R-15])")
    body = panes([
            [
                " search conversations      ",
                " ------------------------- ",
                " gold late          2 hits ",
                "                           ",
                " Today                     ",
                "  revenue  Fix the daily   ",
                "     ... gold is late ...  ",
                "  gold     Why is the ...  ",
                "     ... gold arrived at.. ",
                "                           ",
                " Yesterday                 ",
                "  job audit  Check the...  ",
                "     ... gold table ...    ",
                "                           ",
                " Searches the JOURNAL, not ",
                " the title. The rail used  ",
                " to search titles + folder ",
                " only                      ",
            ],
            [
                " gold      in 3 conversations                        ",
                " --------------------------------------------------- ",
                " revenue   Fix the daily revenue notebook            ",
                "   Today 14:02   12 hits   4 turns                   ",
                "   ... the gold table arrived at 06:11 but the       ",
                "   notebook reads it at 06:00 ...                    ",
                "                                                     ",
                "   Open at this turn >                               ",
                "                                                     ",
                " gold      Why is the pipeline late                  ",
                "   Today 11:20   5 hits    2 turns                   ",
                "   ... silver finished 06:04, gold depends on it ... ",
                "                                                     ",
                " job audit Check the gold row count                  ",
                "   Yesterday 17:44  2 hits  1 turn                   ",
                "   ... gold had 0 rows on the 9th ...                ",
                "                                                     ",
                " Opens the turn, not just the conversation, and      ",
                " scrolls to the matching answer. That is the thing   ",
                " a person actually wants when they remember a word.  ",
            ],
        ],
    )
    for row in body:
        f.line(row)
    f.rule("what this frame is for")
    f.line("Genie Code searches chats [C4]. OpenGenie searches labels. The journal makes full-text")
    f.line("search cheap and exact, and 'open at this turn' is only possible because events are")
    f.line("ordered and addressable by seq.")
    return f.render()


def f4_restart() -> str:
    f = Frame()
    f.top("F4 · after a restart: three sessions, three different truths (phase 2, [R-10])")
    body = panes([
            [
                " a session that WAS mid-turn ",
                " --------------------------- ",
                " revenue        needs you    ",
                "                            ",
                " Your progress is saved.    ",
                " The server restarted while ",
                " this turn was running, so  ",
                " nothing was repeated.      ",
                "                            ",
                " 4 tool calls completed     ",
                " 1 was in flight            ",
                "                            ",
                " [ Review progress ]        ",
                " [ Restore and continue ]   ",
                "                            ",
                " requires_resume = true     ",
                " status = blocked           ",
            ],
            [
                " a session that was IDLE      ",
                " ---------------------------- ",
                " job audit          ready     ",
                "                             ",
                " This conversation was idle  ",
                " when the server restarted.  ",
                " Nothing was in flight, so   ",
                " nothing needs your decision.",
                "                             ",
                " Type to continue. The agent ",
                " starts on your first message.",
                "                             ",
                " [ Ask something ]           ",
                "                             ",
                "                             ",
                " requires_resume = FALSE     ",
                " (today: true, which is the  ",
                "  defect [F-9])              ",
            ],
            [
                " a session that was EVICTED    ",
                " ----------------------------- ",
                " pipeline audit     archived   ",
                "                              ",
                " The transcript is in the      ",
                " journal, so this page loads   ",
                " from Postgres on demand.      ",
                "                              ",
                " 12 turns  ·  last 6 Nov      ",
                " 3 objects created            ",
                "                              ",
                " [ Read the transcript ]       ",
                " [ Start a new conversation ]  ",
                "                              ",
                " Today: 404 'no such session'  ",
                " although the row exists.      ",
                " That is [F-9], second half.   ",
            ],
        ],
    )
    for row in body:
        f.line(row)
    f.rule("what this frame is for")
    f.line("The three states must not share a word. 'Needs you' is a fact about work in flight; 'ready'")
    f.line("is a fact about an idle conversation; 'archived' is the user's own delete. Today all three")
    f.line("render as 'needs attention', which teaches users that the app is fragile.")
    return f.render()


def f5_write_mode() -> str:
    f = Frame()
    f.top("F5 · write mode, and what an approval actually shows (phase 2, [R-9])")
    body = panes([
            [
                " Session setup                        ",
                " ------------------------------------ ",
                " Folder   /Users/me/agent_scratch     ",
                " Schema   main.agent_scratch          ",
                "                                      ",
                " Write mode                           ",
                "  ( ) read-only                       ",
                "      the agent may read; every write ",
                "      is refused with a reason        ",
                "  (*) fenced            recommended   ",
                "      writes only inside the folder   ",
                "      and the schema above            ",
                "  ( ) ask                             ",
                "      a write inside the fence waits  ",
                "      for you, one prompt per object  ",
                "                                      ",
                " Model    vertex/gemini-3.8-flash     ",
                "                                      ",
                " [ Start ]                            ",
            ],
            [
                " an approval, inline in the dock        ",
                " -------------------------------------- ",
                " needs your decision                    ",
                "                                        ",
                " dbx_run_sql wants to write             ",
                "                                        ",
                "   CREATE OR REPLACE TABLE              ",
                "   main.agent_scratch.revenue_daily     ",
                "   AS SELECT ...                        ",
                "                                        ",
                " Inside your fence. 1 table replaced.   ",
                " This cannot be undone from here.       ",
                "                                        ",
                " [ Allow once ] [ Allow for session ]   ",
                " [ Deny ]                               ",
                "                                        ",
                " The reason is the sentence the tool    ",
                " server wrote, not a paraphrase.        ",
            ],
        ],
    )
    for row in body:
        f.line(row)
    f.rule("what this frame is for")
    f.line("Today NBMCP_ALLOW_WRITES=1 is a constant, so 'fenced' is the only behaviour that exists")
    f.line("and 'ask' does not [F-8]. Making the mode a session field turns a hidden constant into a")
    f.line("choice a user can see, and keeps today's behaviour as the default.")
    return f.render()


def f6_instructions() -> str:
    f = Frame()
    f.top("F6 · instructions and skills: what the agent is told, and where it came from (phase 2)")
    body = panes([
            [
                " Settings        ",
                " --------------- ",
                " > Instructions  ",
                "   Skills        ",
                "   Models        ",
                "   Providers     ",
                "   Hooks         ",
                "   Budget        ",
                "",
                " Personal scope  ",
                "  /Users/me/",
                "   .assistant/",
                "    instructions.md",
                "    skills/",
                "     revenue.md",
                "     dq.md",
                "",
                " Workspace scope ",
                "  Workspace/",
                "   .assistant/",
                "    skills/",
                "     naming.md",
            ],
            [
                " Instructions                        ",
                " ----------------------------------- ",
                " Personal            [ 12 lines ]    ",
                "   /Users/me/.assistant/instructions  ",
                "   edited by you, 2 days ago         ",
                "   [ Edit ]  [ Preview as the agent ]",
                "                                     ",
                " Workspace           [ 31 lines ]    ",
                "   Workspace/.assistant/instructions  ",
                "   edited by dana@, 1 week ago       ",
                "   read-only to you [ View ]         ",
                "                                     ",
                " AGENTS.md            [ found ]      ",
                "   /Users/me/agent_scratch/AGENTS.md ",
                "   committed to the folder           ",
                "                                     ",
                " Order: workspace, then personal,    ",
                " then AGENTS.md, then this session's ",
                " fence rules (always last, always    ",
                " wins).                              ",
            ],
            [
                " How the agent sees them             ",
                " ----------------------------------- ",
                " In the transcript, as a collapsed   ",
                " block labelled by SOURCE:           ",
                "                                     ",
                "  v Context from your instructions   ",
                "     personal  12 lines   (you)      ",
                "  v Context from the workspace       ",
                "     workspace 31 lines   (dana@)    ",
                "  v Context from AGENTS.md           ",
                "     folder    8 lines               ",
                "                                     ",
                " Never merged into your message: a   ",
                " user must be able to tell what they ",
                " typed from what the team configured.",
                "                                     ",
                " A skill is loaded only when the     ",
                " agent asks for it (dbx_skill), so   ",
                " 40 skills cost nothing until one is ",
                " relevant.                           ",
            ],
        ],
    )
    for row in body:
        f.line(row)
    f.rule("what this frame is for")
    f.line("Genie Code reads AGENTS.md and CLAUDE.md and offers personal and workspace instructions and")
    f.line("skills [C13-C15]. OpenGenie WRITES an AGENTS.md and reads none [G-5]. The labelling is the")
    f.line("part that matters for governance: configured context must never look like the user's words.")
    return f.render()


def f7_diff() -> str:
    f = Frame()
    f.top("F7 · a proposed edit, accepted or rejected (phase 3, [R-22])")
    f.rule("the notebook, with a proposal over cell 3")
    f.line("  cell 1  python   v ok                    [ Run ] [ Ask ]")
    f.line("    df = spark.table('samples.nyctaxi.trips')")
    f.blank()
    f.line("  cell 2  python   v ok                    [ Run ] [ Ask ]")
    f.line("    daily = df.groupBy('pickup_date').count()")
    f.blank()
    f.line("  cell 3  python   PROPOSED                [ Keep ] [ Reject ]")
    f.line("   -  daily.write.mode('overwrite').saveAsTable('revenue')")
    f.line("   +  (daily")
    f.line("   +    .withColumnRenamed('count', 'trips')")
    f.line("   +    .write.mode('overwrite')")
    f.line("   +    .saveAsTable('main.agent_scratch.revenue'))")
    f.line("    why: 'revenue' had no catalog, so it resolved to whatever the warehouse defaulted to.")
    f.line("    Accepting writes to the working folder; the original notebook is untouched.")
    f.rule("what this frame is for")
    f.line("Genie Code presents edits for accept/reject [C24]; OpenGenie has no proposal at all -")
    f.line("editor/diff.ts computes a minimal change to map a remote edit onto an open document, which")
    f.line("is a different job. The fence is what makes this safe: 'Keep' writes inside the folder only.")
    return f.render()


def f8_budget() -> str:
    f = Frame()
    f.top("F8 · what this conversation has cost (phase 2, [R-24])")
    body = panes([
            [
                " inspector - session        ",
                " -------------------------- ",
                " model   gemini-3.8-flash   ",
                " wire    vertex-native      ",
                " limits  1M ctx / 8k out    ",
                " evidence  measured         ",
                "                            ",
                " turns        7 of 200      ",
                " input       412k tokens    ",
                " output       38k tokens    ",
                " cached       96k tokens    ",
                "                            ",
                " est. cost        $0.41     ",
                " budget           $2.00     ",
                " [############----------]  ",
                "                            ",
                " A turn that would cross    ",
                " the budget is BLOCKED      ",
                " with the number in the     ",
                " message, before it spends. ",
            ],
            [
                " which turn used which model                        ",
                " -------------------------------------------------- ",
                " #   model                 provider    in   out     ",
                " 1   gemini-3.8-flash      vertex      18k   4k     ",
                " 2   gemini-3.8-flash      vertex      42k   6k     ",
                " 3   gemini-3.8-flash      vertex      61k   7k     ",
                " 4   gpt-oss-120b          databricks  58k   3k     ",
                " 5   gpt-oss-120b          databricks  71k   5k     ",
                " 6   gemini-3.8-flash      vertex      88k   6k     ",
                " 7   gemini-3.8-flash      vertex      74k   7k     ",
                " -------------------------------------------------- ",
                " The switch happened at turn 4 and again at turn 6. ",
                " Every pin was written BEFORE the prompt and never ",
                " rewritten (llm.llm_turn_model), so this table is  ",
                " a record, not a reconstruction.                    ",
                "                                                   ",
                " This is the column Genie Code cannot offer: its   ",
                " model is not a setting a customer can inspect per ",
                " turn.                                             ",
            ],
        ],
    )
    for row in body:
        f.line(row)
    f.rule("what this frame is for")
    f.line("The product's first promise is 'the model is a setting'. A setting nobody can audit is a")
    f.line("preference. The turn pins already exist; this frame gives them a surface, and adds the one")
    f.line("thing Genie Code's budgets cannot be: a limit that stops work before it spends.")
    return f.render()


def f9_hooks() -> str:
    f = Frame()
    f.top("F9 · declarative hooks: a platform team's rules, evaluated in the fence (phase 4, [R-13])")
    f.rule("Workspace/.opengenie/hooks.yaml - read as the user, shown read-only")
    f.line("  hooks:")
    f.line("    - name: block-delete-on-gold")
    f.line("      on: before_tool")
    f.line("      match: { tool: dbx_run_sql }")
    f.line("      when:  sql.matches('(?i)^\\\\s*delete\\\\s+from\\\\s+main\\\\.gold\\\\.')")
    f.line("      then:  refuse")
    f.line("      say:   'main.gold is append-only. Write to a branch and merge.'")
    f.blank()
    f.line("    - name: format-after-write")
    f.line("      on: after_tool")
    f.line("      match: { tool: dbx_write_notebook }")
    f.line("      then:  run")
    f.line("      run:   ['ruff', 'format', '--stdin']")
    f.rule("what the user sees when one fires")
    f.line("  x dbx_run_sql                       refused by hook")
    f.line("    main.gold is append-only. Write to a branch and merge.")
    f.line("    [ Ask the agent to use a branch ]   [ Explain this rule ]")
    f.rule("why it lives in the fence and not in a script")
    f.line("A hook that runs as a separate process would need its own identity, its own timeout and")
    f.line("its own failure mode. Evaluated in the tool server, it inherits all three from the process")
    f.line("that already refuses writes: the same place, the same reason sentence, the same audit row.")
    return f.render()


def f10_narrow() -> str:
    f = Frame(inner=NARROW - 2)
    f.top("F10 · 820 px: the dock is a drawer and the rail is a chooser")
    f.line(" Document: revenue_demo        [ < ] [ dock ]")
    f.line(" -----------------------------------------------")
    f.line("  cell 1   python                   [ Run ] [ Ask ]")
    f.line("    df = spark.table('samples.nyctaxi.trips')")
    f.line("")
    f.line("  cell 2   python                   [ Run ] [ Ask ]")
    f.line("    display(df.limit(10))")
    f.line("")
    f.line(" + Code   + Text")
    f.line(" -----------------------------------------------")
    f.line(" [ drawer: conversation, 380 px, over the work ]")
    f.line("  revenue            working 0:12")
    f.line("  v dbx_describe_table          ok 0.9s")
    f.line("  > dbx_run_sql              running")
    f.line("  -------------------------------------------")
    f.line("  Ask about revenue...                [ m ]")
    f.line("")
    f.line("  Below 480 + 380 the assistant overlays;")
    f.line("  the centre keeps CENTRE_MIN = 480 px.")
    return f.render()


def f11_navigation() -> str:
    f = Frame()
    f.top("F11 · navigation: every surface, and the key that reaches it")
    f.line("  cmd+k  palette            -> any doc, any session, any command")
    f.line("  cmd+1  rail: sessions     cmd+shift+n  new session")
    f.line("  cmd+2  rail: files        cmd+p        find a notebook or file")
    f.line("  cmd+3  rail: catalog      cmd+4        rail: data (jobs, runs, pipelines)")
    f.line("  cmd+j  toggle assistant   cmd+i        toggle inspector")
    f.line("  cmd+b  toggle navigator   cmd+l        focus the composer")
    f.line("  cmd+shift+i  ask about the focused cell")
    f.line("  cmd+shift+m  change the model          cmd+,  providers and keys")
    f.line("  cmd+shift+[ / ]  previous / next conversation tab      (phase 3)")
    f.line("  cmd+z  undo (structural, in a notebook)  cmd+w  close a document tab")
    f.line("  cmd+shift+t  reopen the last closed tab")
    f.rule("the grammar behind the keys")
    f.line("  cmd+digit   panes          cmd+letter   an action")
    f.line("  cmd+shift   a destructive or session-level twin of the plain chord")
    f.line("  Nothing is bound twice: domain/keys.ts is one table and a test walks it.")
    return f.render()


HEADER = """[Index](README.md) · prev: [05 Gaps and improvements](05-gaps-and-improvements.md) · next: [07 Diagrams](07-diagrams.md)

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
"""


def main() -> None:
    parts = [
        HEADER,
        "### F1 · The shell as it is, and the three places it falls short\n",
        "```text\n" + f1_today() + "\n```\n",
        "### F2 · Parallel chats: a tab strip of live conversations\n",
        "```text\n" + f2_threads() + "\n```\n",
        "### F3 · Search inside conversations\n",
        "```text\n" + f3_search() + "\n```\n",
        "### F4 · After a restart: three sessions, three different truths\n",
        "```text\n" + f4_restart() + "\n```\n",
        "### F5 · Write mode, and what an approval shows\n",
        "```text\n" + f5_write_mode() + "\n```\n",
        "### F6 · Instructions and skills, with their source\n",
        "```text\n" + f6_instructions() + "\n```\n",
        "### F7 · A proposed edit, accepted or rejected\n",
        "```text\n" + f7_diff() + "\n```\n",
        "### F8 · What this conversation cost, and on which model\n",
        "```text\n" + f8_budget() + "\n```\n",
        "### F9 · Declarative hooks\n",
        "```text\n" + f9_hooks() + "\n```\n",
        "### F10 · 820 px: the dock is a drawer\n",
        "```text\n" + f10_narrow() + "\n```\n",
        "### F11 · Navigation\n",
        "```text\n" + f11_navigation() + "\n```\n",
        """---

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
""",
    ]
    OUT.write_text("\n".join(parts))
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
