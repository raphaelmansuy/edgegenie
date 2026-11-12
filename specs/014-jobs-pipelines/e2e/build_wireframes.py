#!/usr/bin/env python3
"""Emit the ASCII wireframes for spec 014 with exact alignment.

A box drawn by hand drifts by one column on the third edit and the defect is invisible in a diff, so
the frames are GENERATED: `frame()` is the only place a border is written, and
`node scripts/verify-spec-ascii.mjs` is the independent check that the result is a grid.

Two rules this file keeps, both learned from the verifier:

  * **No text in a border.** The top border may contain only `─` and `┬`, so a section title is a row
    INSIDE the frame (`── Last run ─────────`), never a label welded into `┌`.
  * **No nested frames.** A diagram made of small boxes is drawn UNBOXED, because a nested box's
    content legitimately extends past the outer right border and the checker reads that as an overflow.

Run:  python3 build_wireframes.py > 04-generated.md
"""
from __future__ import annotations

W = 116  # total character width of every frame


def _line(text: str) -> str:
    if len(text) > W - 4:
        raise ValueError(f"line is {len(text)} chars, max {W - 4}: {text!r}")
    return text


def frame(lines: list[str]) -> list[str]:
    """One frame: a border, the content, a border. Nothing else."""
    inner = W - 2
    out = ["┌" + "─" * inner + "┐"]
    for line in lines:
        out.append("│ " + _line(line).ljust(inner - 2) + " │")
    out.append("└" + "─" * inner + "┘")
    return out


def head(title: str) -> str:
    """A section heading as a CONTENT row: `── Last run ──────...`, filling the frame exactly.

    The label is inside the rule rather than in a top border, because the ASCII verifier reads a label
    in a `┌...┐` border as a broken border — and it is right to: a border is a line, not a place for text.
    """
    label = f"── {title} "
    if len(label) > W - 6:
        raise ValueError(f"section title too long: {title!r}")
    return label + "─" * (W - 4 - len(label))


def rule() -> str:
    return "─" * (W - 4)


def art(*lines: str) -> list[str]:
    """An unboxed diagram, for figures whose shape is the point."""
    return [_line(x) for x in lines]


def stack(*blocks: list[str]) -> list[str]:
    out: list[str] = []
    for i, b in enumerate(blocks):
        if i:
            out.append("")
        out.extend(b)
    return out


def emit(name: str, blocks: list[str]) -> None:
    print(f"### {name}\n")
    print("```text")
    print("\n".join(blocks))
    print("```")
    print()


# ---------------------------------------------------------------- F1: the shell
def three(left: list[str], centre: list[str], right: list[str]) -> list[str]:
    """One frame with two internal gutters.

    The verifier reads a second box's right border as content that "runs past" the first one's, so a
    three-pane layout is drawn as ONE frame with `│` gutters inside it — which is also how spec 013
    drew the shell. Widths come from `COLUMNS`, not from typing spaces.
    """
    a, b, c = COLUMNS
    body = []
    height = max(len(left), len(centre), len(right))
    for i in range(height):
        la = left[i] if i < len(left) else ""
        lb = centre[i] if i < len(centre) else ""
        lc = right[i] if i < len(right) else ""
        for text, width, name in ((la, a, "left"), (lb, b, "centre"), (lc, c, "right")):
            if len(text) > width:
                raise ValueError(f"{name} line is {len(text)}, max {width}: {text!r}")
        body.append(f"{la.ljust(a)}│{lb.ljust(b)}│{lc.ljust(c)}")
    return frame(body)


COLUMNS = (28, 48, 28)


def f1() -> list[str]:
    return stack(
        art(
            "The `Data` tab is the one 013 introduced; it gains two groups. Nothing about the shell moves: the rail",
            "keeps its column, the centre keeps its minimum, and the dock keeps its binding [012].",
        ),
        three(
            [
                " rail · Data",
                "",
                " Lakebase",
                "   pg_tickets      v17",
                "   pg_orders       v17",
                " Jobs",
                "   daily_revenue   failed",
                "   nightly_silver  ok",
                " Pipelines",
                "   sales_medallion ok",
                " Apps",
                "   tickets-app     running",
                "",
                " cmd+4 · what you see",
            ],
            [
                " centre · start screen",
                "",
                " Your workspace, ready for",
                " what's next.",
                "",
                " What can I help you build?",
                "",
                " [ Build a notebook ] [ Investigate ]",
                " [ Create a job     ] [ Lakebase    ]",
                "",
                " Recent",
                "   avg_fare_by_hour  notebook",
                "   daily_revenue     job",
                "   sales_medallion   pipeline",
            ],
            [
                " assistant · the job",
                "",
                " created a job    ok",
                " ran it once  FAILED",
                "   task gold:",
                "   ANALYSIS_ERROR",
                "",
                " [ Open the run ]",
                " [ Fix it       ]",
                "",
                " Ask about",
                " daily_revenue…",
                "",
            ],
        ),
    )


# ---------------------------------------------------------------- F2: job page
def f2() -> list[str]:
    return frame([
        "daily_revenue                                        [ failed ]   <- the LAST RUN's word",
        "812345678901 · copy                [Run now] [Refresh] [Databricks]",
        "agent_4ff4405d_daily_revenue · schedule PAUSED · owner me@example.com",
        rule(),
        head("Last run"),
        "run 812345679    FAILED    1 m 42 s    today 06:00    manual",
        "  task 'gold' failed: ANALYSIS_ERROR: cannot resolve 'fare_amount' in main.silver.trips",
        "",
        "[Open the run]    [Repair the failed tasks]",
        rule(),
        head("Schedule"),
        "cron       0 0 6 * * ?        every day at 06:00",
        "timezone   UTC",
        "state      PAUSED — the agent creates every schedule paused",
        "next       nothing will run until you resume",
        "",
        "[Resume schedule]   <- the control that creates a recurring cost; it asks first",
        rule(),
        head("Tasks · 3 tasks, in 2 levels"),
        "level 1   silver    notebook   /Users/me/agent_scratch/daily_revenue/silver",
        "                    timeout 0 · retries 0",
        "level 2   gold      notebook   /Users/me/agent_scratch/daily_revenue/gold",
        "                    after silver · timeout 3600 · retries 2",
        "level 2   audit     notebook   /Users/me/agent_scratch/daily_revenue/audit",
        "                    after silver · timeout 0 · retries 0",
        rule(),
        head("Settings"),
        "owner      me@example.com        queueing   on (Jobs API 2.2 default)",
        "timeout    none                  retries    0",
        "tags       agent=opengenie  session=4ff4405d",
        "created    today 05:58 by me@example.com",
    ])


# ---------------------------------------------------------------- F3: run page
def f3() -> list[str]:
    return frame([
        "run 812345679  ·  daily_revenue                                  [ failed ]",
        "started today 06:00 · 1 m 42 s · manual                       [Cancel] [Repair]",
        rule(),
        head("Tasks · 3, of which 2 finished"),
        "task      life cycle    result     duration   detail",
        "silver    TERMINATED    SUCCESS    38 s       exit \"1234 rows\"",
        "gold      TERMINATED    FAILED     64 s       ANALYSIS_ERROR: cannot resolve 'fare_amount'",
        "audit     SKIPPED       —          —          upstream 'gold' failed",
        rule(),
        head("Error · gold"),
        "AnalysisException: cannot resolve 'fare_amount' given input columns:",
        "   [trip_id, pickup_at, dropoff_at, total]",
        "   line 12   select fare_amount from main.silver.trips",
        "",
        "[Copy]   [Ask the agent to fix it]      the prompt carries the exception and the task key",
    ])


# ---------------------------------------------------------------- F4: pipeline page
def f4() -> list[str]:
    return frame([
        "sales_medallion                                             [ succeeded ]",
        "f0e1c4a2-…-9a2b · serverless · ADVANCED",
        "[Start] [Full refresh] [Check the code] [Stop]        each label states its cost, below",
        rule(),
        head("Last update"),
        "update 8a0b6d02    COMPLETED    today 05:58    3 m 07 s",
        "incremental · 6 flows · 0 expectations failed · started by API_CALL",
        "",
        "[Open the update]   reads the run page's shape, one row per flow",
        rule(),
        head("Libraries · 3"),
        "notebook   /Users/me/agent_scratch/sales_medallion/bronze_orders",
        "notebook   /Users/me/agent_scratch/sales_medallion/silver_orders",
        "notebook   /Users/me/agent_scratch/sales_medallion/gold_revenue",
        rule(),
        head("Configuration"),
        "catalog     main             schema       sales",
        "edition     ADVANCED         channel      CURRENT",
        "compute     serverless       continuous   no",
        "storage     platform managed",
        rule(),
        head("Events · errors and warnings first"),
        "ERROR  05:59:12   expectation 'valid_total' failed on 12 rows (warn threshold)",
        "INFO   05:58:44   update 8a0b6d02 started by API_CALL",
        "INFO   05:58:41   pipeline is IDLE",
        "[Show 20 more]",
    ])


# ---------------------------------------------------------------- F5: run in flight
def f5() -> list[str]:
    return frame([
        "run 812345680  ·  daily_revenue                                [ running ]",
        "started 12 s ago · still running                              [Cancel]",
        rule(),
        head("Tasks · 1 of 3 finished"),
        "silver    TERMINATED   SUCCESS    38 s    exit \"1234 rows\"",
        "gold      RUNNING      —          12 s    not finished yet",
        "audit     BLOCKED      —          —       waiting for 'gold'",
        rule(),
        head("What the page is doing"),
        "polling every 3 s while this tab is visible; it stops the moment the run is terminal",
        "a cold serverless start reads `pending`, never `failed`: a wait is a state, not an error",
        "Cancel stays available while active, and says the cancellation is asynchronous",
        "nothing here animates: a still picture must be readable as the truth",
    ])


# ---------------------------------------------------------------- F6: refusal
def f6() -> list[str]:
    return frame([
        "daily_revenue                                                [ unreadable ]",
        "812345678901 · copy                                          [Databricks]",
        rule(),
        head("Last run"),
        "PERMISSION_DENIED: user does not have CAN_MANAGE_RUN on job 812345678901",
        "ask the job's owner for CAN_MANAGE_RUN; a retry cannot grant it",
        rule(),
        head("Schedule"),
        "—",
        "not read: the same denial applies to this block",
        rule(),
        head("Tasks"),
        "silver    notebook   /Users/me/agent_scratch/daily_revenue/silver",
        "gold      notebook   /Users/me/agent_scratch/daily_revenue/gold    <- still readable",
        rule(),
        head("What stays true"),
        "one block's refusal does not blank its siblings",
        "no Retry is offered for a permanent refusal (013's isPermanent, reused)",
        "the composer still works: ask the agent for access, in words",
    ])


# ---------------------------------------------------------------- F7: empty states
def f7() -> list[str]:
    return stack(
        frame([
            head("A job that has never run"),
            "Last run",
            "  This job has not run yet. [Run now] starts the first run; it has never spent compute.",
        ]),
        frame([
            head("A pipeline that has never updated"),
            "Last update",
            "  Never run. [Check the code] validates every flow without materialising anything.",
        ]),
        frame([
            head("A Data tab with nothing in it"),
            "Jobs",
            "  No jobs yet. Ask the agent to build one, or open Databricks.",
            "Pipelines",
            "  No pipelines yet. A pipeline needs a catalog and a schema to publish into.",
        ]),
        frame([
            head("A task that has not started"),
            "audit     PENDING     —    —    not started",
            "the word is `not started`, never `running`: a queued task is not doing work",
        ]),
    )


# ---------------------------------------------------------------- F8: narrow
def f8() -> list[str]:
    return stack(
        art(
            "The widths are `modeFor`'s, not a drawing's: mid is <= 1180 px, narrow is <= 820 px.",
            "013's S7 corrected this exact mistake in a wireframe. The pages are one component at every",
            "width; only the columns change.",
            "",
        ),
        art(
            "900 px · mid: the rail keeps its column, the dock becomes an edge tab",
            "┌──────────────┬──────────────────────────────────────────────────┬──────┐",
            "│ rail 276 px  │ job page — header, last run, schedule, tasks,    │ CHAT │",
            "│ four groups  │ settings; the centre keeps its 480 px minimum    │ edge │",
            "│ scrolls      │ and nothing is clipped                           │ tab  │",
            "└──────────────┴──────────────────────────────────────────────────┴──────┘",
            "",
        ),
        frame([
            head("620 px · narrow: one column, no clipping, no horizontal scroll"),
            "daily_revenue                                   [ failed ]",
            "812345678901 · copy",
            "[Run now] [Refresh] [Databricks]",
            rule(),
            "Last run    FAILED   1 m 42 s   today 06:00",
            rule(),
            "Schedule    PAUSED · 0 0 6 * * ? · UTC",
            rule(),
            "Tasks       3, in 2 levels",
        ]),
    )


# ---------------------------------------------------------------- F9: navigation
def f9() -> list[str]:
    return stack(
        art(
            "Six kinds reachable five ways. `touched()` is the single reducer that turns a tool call into one of",
            "them; the table it reads is what makes a seventh kind a row rather than a new branch.",
            "",
            "        #/  the start screen",
            "         │",
            "         │ a card, a typed prompt",
            "         ▼",
            "   #/session/<id>  ◀────────────────▶  the turn: tool rows and the answer",
            "   the mission view                          │",
            "         │                                   │ a tool row names an object",
            "         │ a recent entry, a palette row,    ▼",
            "         │ a Data-tab row, or a deep link   touched(name, args, result)",
            "         │                                   │",
            "         └───────────────┬───────────────────┘",
            "                         ▼",
            "   ┌─────────────┬──────────────┬─────────────┬─────────────┬────────────────┐",
            "   │ job         │ pipeline     │ run         │ lakebase    │ app            │",
            "   │ #/job/      │ #/pipeline/  │ #/run/      │ #/lakebase/ │ #/app/         │",
            "   │ 812345678   │ f0e1c4a2-…   │ 812345679   │ projects/…  │ tickets-app    │",
            "   └─────────────┴──────────────┴─────────────┴─────────────┴────────────────┘",
            "",
            "Every edge is a route, so every edge is pasteable into a ticket and reloadable in a cold browser.",
            "An id of the wrong shape parses to the empty route: a stale link opens the app, never a blank page.",
        ),
    )


print("<!-- GENERATED by build_wireframes.py; edit the generator, then re-run it. -->\n")
emit("F1 · The shell, `Data` selected: four groups", f1())
emit("F2 · A job page: five sections, the last run first", f2())
emit("F3 · A run page: every task's own outcome", f3())
emit("F4 · A pipeline page: the last update, not the pipeline state", f4())
emit("F5 · A run in flight", f5())
emit("F6 · A refusal, in the platform's words", f6())
emit("F7 · The four empty states", f7())
emit("F8 · Two narrow widths", f8())
emit("F9 · Navigation: how every object is reached", f9())
