"""Generate the ASCII wireframes for spec 013.

One outer box per screen, with the panes divided by internal `│` separators: that is what the app is
(one surface, three zones), and it is what `verify-spec-ascii.mjs` accepts, because content past one
box's right border cannot be attributed to a drawing by the checker.

Geometry is derived, not typed: `RAIL_W`, `MAIN_W`, `DOCK_W` produce the separator columns and the
total width, so a pane can never be drawn past the frame. Every write goes through `Pane.line`, which
clips to that pane's own writable columns and records a warning when it had to. A frame with a warning
is a frame whose copy does not fit, and the fix is shorter copy — not a wider box.
"""

RAIL_W, MAIN_W, DOCK_W = 30, 45, 27
W = 1 + RAIL_W + 1 + MAIN_W + 1 + DOCK_W + 1
SEP1 = 1 + RAIL_W
SEP2 = SEP1 + 1 + MAIN_W
INNER_R = W - 2
BODY_TOP, BODY_H = 3, 20
BOTTOM = BODY_TOP + BODY_H - 1


class Screen:
    def __init__(self, w=W, h=24):
        self.w, self.h = w, h
        self.g = [[" "] * w for _ in range(h)]
        self.clipped = []

    def raw(self, x, y, s, limit=None):
        if limit is not None and x + len(s) - 1 > limit:
            s = s[: max(0, limit - x + 1)]
        for i, ch in enumerate(s):
            if 0 <= x + i < self.w and 0 <= y < self.h:
                self.g[y][x + i] = ch

    def frame(self, x, y, w, h):
        self.raw(x, y, "┌" + "─" * (w - 2) + "┐")
        for j in range(y + 1, y + h - 1):
            self.raw(x, j, "│")
            self.raw(x + w - 1, j, "│")
        self.raw(x, y + h - 1, "└" + "─" * (w - 2) + "┘")

    def vline(self, x, y0, y1):
        for j in range(y0, y1 + 1):
            self.raw(x, j, "│")

    def pane(self, x0, x1, y0):
        return Pane(self, x0, x1, y0)

    def out(self):
        rows = ["".join(r).rstrip() for r in self.g]
        while rows and not rows[-1]:
            rows.pop()
        return "\n".join(rows)


class Pane:
    """Columns x0..x1 inclusive are writable; borders sit strictly outside that range."""

    def __init__(self, s, x0, x1, y0):
        self.s, self.x0, self.x1, self.y0 = s, x0, x1, y0
        self.width = x1 - x0 + 1

    def line(self, row, text, indent=0):
        avail = self.width - indent
        if avail <= 0:
            return
        if len(text) > avail:
            self.s.clipped.append((avail, text))
            text = text[: avail - 1] + "…"
        self.s.raw(self.x0 + indent, self.y0 + row, text, limit=self.x1)

    def bar(self, row):
        self.s.raw(self.x0, self.y0 + row, "─" * self.width, limit=self.x1)


RAIL = (1, SEP1 - 1)
MAIN = (SEP1 + 1, SEP2 - 1)
DOCK = (SEP2 + 1, INNER_R)

FRAMES = []
ANNOT = {
    "S1": "The rail's fourth tab is new `[UI-2]`. Every node kind in it opens a document `[UI-1]`. "
          "The dock still answers the [012] rule: a state word, the binding it is about, and a composer "
          "that never refuses a keystroke.",
    "S2": "Every value is a fact from a call, never a paraphrase `[UI-3]`. The autoscaling range shows "
          "the rule being evaluated (`max − min = 3.5 ✓ (≤ 16)`) because that is the number a user gets "
          "wrong `[LB-4]`. The branch line exists because SQL now runs on a named branch `[LB-3]`.",
    "S3": "The health block is the answer to \"is it working\" `[UI-4]`, backed by one HTTP call "
          "`[AP-4]`. `/logz` is a link, not a promise: logs are lost when compute stops `[E-14]`.",
    "S4": "Creating an app outside the working folder is a decision, not a background effect `[SCF-4]`. "
          "The three outcomes are one click each and none of them is dismissible with Escape, which is "
          "the [012] rule for a decision that must be made rather than escaped.",
    "S5": "The platform's sentence, verbatim, then who can fix it, then one action `[UI-6]`. No retry: "
          "a missing `CAN MANAGE` does not change on the second try `[E-8]`.",
    "S6": "Seven steps, and a step is `✓` only when a call proved it `[SCF-1]`. Step 5 is `▸` because "
          "it is running; 6 and 7 are `·` because nothing has been attempted `[SCF-2]`. A failure at "
          "step 3 leaves 4–7 empty rather than creating an app over a missing table.",
    "S7": "The dock keeps a column and the rail becomes a drawer, which is [006]'s arithmetic unchanged: "
          "`centre 480 + dock 380 = 860`. The new tab does not change that rule `[UI-2]`.",
    "S8": "Search finds the two new kinds by name, beside notebooks and tables `[UI-5]`. A project is "
          "matched on its id and an app on its name, which are the two identities `[LB-5]` and `[AP-1]` "
          "assign.",
}


def frame(sid, title):
    def deco(fn):
        FRAMES.append((sid, title, fn))
        return fn

    return deco


def chrome(s, model="gemini-3.8-flash", state="ready"):
    s.frame(0, 0, W, 3)
    p = s.pane(1, INNER_R, 0)
    p.line(1, f"⌘ OpenGenie   ▸ {model}  ● {state}", indent=1)
    s.raw(W - 42, 1, "[ ⌘K   search or run a command ]", limit=W - 10)
    s.raw(W - 8, 1, "RM ▾", limit=INNER_R)


def columns(s):
    s.frame(0, BODY_TOP, W, BODY_H)
    s.vline(SEP1, BODY_TOP + 1, BOTTOM - 1)
    s.vline(SEP2, BODY_TOP + 1, BOTTOM - 1)
    return s.pane(*RAIL, BODY_TOP), s.pane(*MAIN, BODY_TOP), s.pane(*DOCK, BODY_TOP)


def dock_head(d, state, ctx=None):
    d.line(1, state, indent=1)
    if ctx:
        d.line(2, ctx, indent=1)
    d.bar(3)


def composer(d, text="+  @  /   model ▾  Send", row=BODY_H - 3):
    d.bar(row)
    d.line(row + 1, text, indent=1)


def tabs(r):
    r.line(1, "Sessions Files Catalog Data", indent=1)
    r.bar(2)


# --------------------------------------------------------------------------- S1
@frame("S1", "The shell, with the new `Data` rail tab")
def s1():
    s = Screen()
    chrome(s)
    rail, main, dock = columns(s)
    tabs(rail)
    for i, r in enumerate([
        "▾ Lakebase",
        "  ● pg_tickets      project",
        "  ○ pg_orders       project",
        "▾ Databricks Apps",
        "  ▲ tickets_app         app",
        "  △ orders_api          app",
        "▾ Unity Catalog",
        "  samples.nyctaxi.trips",
    ]):
        rail.line(3 + i, r, indent=1)
    main.line(1, "pg_tickets", indent=1)
    main.bar(2)
    for i, r in enumerate([
        "Lakebase project · projects/pg-tickets",
        "postgres 17 · production · scale to zero",
        "",
        "COMPUTE",
        "  primary  READ_WRITE  0.5–4 CU   ready",
        "  host     ep-cool-butterfly-9f2",
        "",
        "BRANCHES",
        "  production          default",
        "  agent-4ff4405d      from production",
        "",
        "DATABASES",
        "  databricks_postgres 3 tables 12 rows",
        "",
        "USED BY",
        "  tickets_app        CAN_CONNECT_AND_CREATE",
    ]):
        main.line(3 + i, r, indent=1)
    dock_head(dock, "● ready", "in context: pg_tickets")
    for i, r in enumerate([
        "╭─ created a database ─╮",
        "│ pg_tickets        ✓  │",
        "╰──────────────────────╯",
        "╭─ created an app ─────╮",
        "│ tickets_app       ✓  │",
        "│ running · /logz      │",
        "╰──────────────────────╯",
        "",
        "Both exist. The app",
        "reads the table you",
        "seeded.",
    ]):
        dock.line(4 + i, r, indent=1)
    composer(dock)
    return s


# --------------------------------------------------------------------------- S2
@frame("S2", "A Lakebase project, opened as a document")
def s2():
    s = Screen()
    chrome(s)
    rail, main, dock = columns(s)
    tabs(rail)
    for i, r in enumerate(["▾ Lakebase", "  ● pg_tickets", "  ○ pg_orders",
                           "▾ Databricks Apps", "  ▲ tickets_app", "  △ orders_api"]):
        rail.line(3 + i, r, indent=1)
    main.line(1, "pg_tickets · branch agent-4ff4405d", indent=1)
    main.bar(2)
    for i, r in enumerate([
        "COMPUTE  primary  READ_WRITE",
        "  0.5–4 CU    max − min = 3.5  ✓ (≤ 16)",
        "  scale to zero  24 h idle",
        "  218 connections at 1 CU",
        "",
        "TABLES IN databricks_postgres / app",
        "  name        rows     size",
        "  tickets       12     8 kB",
        "  agents         3     8 kB",
        "",
        "SQL RUNS ON THIS BRANCH ONLY",
        "  production was never written to",
    ]):
        main.line(3 + i, r, indent=1)
    dock_head(dock, "● ready", "in branch agent-4f…")
    for i, r in enumerate([
        "╭─ ran SQL ────────────╮",
        "│ 12 rows · 0.4 s   ✓  │",
        "╰──────────────────────╯",
        "",
        "The table is in the",
        "branch, not in",
        "production.",
    ]):
        dock.line(4 + i, r, indent=1)
    composer(dock)
    return s


# --------------------------------------------------------------------------- S3
@frame("S3", "A Databricks App, opened as a document")
def s3():
    s = Screen()
    chrome(s)
    rail, main, dock = columns(s)
    tabs(rail)
    for i, r in enumerate(["▾ Lakebase", "  ● pg_tickets", "▾ Databricks Apps",
                           "  ▲ tickets_app", "  △ orders_api"]):
        rail.line(3 + i, r, indent=1)
    main.line(1, "tickets_app", indent=1)
    main.bar(2)
    for i, r in enumerate([
        "RUNNING  ·  deployment SUCCEEDED",
        "URL      tickets-app-1.aws.datab…",
        "COMPUTE  MEDIUM · 1 instance · scale to 0",
        "",
        "RESOURCES",
        "  postgres   …/branches/agent-4ff4405d",
        "             CAN_CONNECT_AND_CREATE",
        "",
        "HEALTH",
        "  GET /           200   41 ms",
        "  GET /api/rows   200   63 ms  12 rows",
        "",
        "LOGS (tail)   /logz",
        "  10:42:01 uvicorn running on :8000",
    ]):
        main.line(3 + i, r, indent=1)
    dock_head(dock, "● ready", "in context: tickets_app")
    for i, r in enumerate([
        "╭─ verified the app ───╮",
        "│ HTTP 200          ✓  │",
        "│ 12 rows returned  ✓  │",
        "╰──────────────────────╯",
        "",
        "Proven, not claimed:",
        "the URL answered.",
    ]):
        dock.line(4 + i, r, indent=1)
    composer(dock)
    return s


# --------------------------------------------------------------------------- S4
@frame("S4", "The approval moment: a deploy outside the folder")
def s4():
    s = Screen()
    chrome(s, state="working")
    rail, main, dock = columns(s)
    tabs(rail)
    for i, r in enumerate(["▾ Databricks Apps", "  ▲ tickets_app"]):
        rail.line(3 + i, r, indent=1)
    main.line(1, "tickets_app", indent=1)
    main.bar(2)
    for i, r in enumerate([
        "A deployment is waiting for you.",
        "",
        "The agent wrote the files and asks before",
        "deploying: an app is visible to the whole",
        "workspace.",
        "",
        "Nothing has been deployed yet.",
    ]):
        main.line(3 + i, r, indent=1)
    dock_head(dock, "● decide")
    for i, r in enumerate([
        "╭─ needs your decision ╮",
        "│ deploy an app outside│",
        "│ your working folder  │",
        "╰──────────────────────╯",
        "/Users/you/agent_scra…",
        "  tickets_app",
        "",
        "why: an app is",
        "workspace-wide, so it",
        "is named after this",
        "session",
        "[Allow once] [Session]",
        "[        Deny        ]",
    ]):
        dock.line(4 + i, r, indent=1)
    composer(dock, "readOnly · decide above")
    return s


# --------------------------------------------------------------------------- S5
@frame("S5", "A refusal, in the platform's own words")
def s5():
    s = Screen()
    chrome(s, state="blocked")
    rail, main, dock = columns(s)
    tabs(rail)
    rail.line(3, "▾ Lakebase", indent=1)
    rail.line(4, "  (nothing yet)", indent=1)
    main.line(1, "Cannot create a Lakebase project", indent=1)
    main.bar(2)
    for i, r in enumerate([
        "The workspace refused:",
        "",
        "  PERMISSION_DENIED: you need CAN MANAGE",
        "  on project pg-tickets",
        "",
        "That is your access, not the app's.",
        "Ask the owner, or pick a project you own.",
        "",
        "  [ Choose another project ]   [ Copy ]",
    ]):
        main.line(3 + i, r, indent=1)
    dock_head(dock, "● blocked")
    for i, r in enumerate([
        "The agent stopped.",
        "",
        "Nothing was created.",
        "",
        "The platform's own words",
        "are in the centre,",
        "verbatim.",
    ]):
        dock.line(4 + i, r, indent=1)
    composer(dock)
    return s


# --------------------------------------------------------------------------- S6
@frame("S6", "A scaffold in progress: seven proven steps")
def s6():
    s = Screen()
    chrome(s, state="working")
    rail, main, dock = columns(s)
    tabs(rail)
    main.line(1, "New app · from a Lakebase table", indent=1)
    main.bar(2)
    for i, r in enumerate([
        "1  ✓  project     pg_tickets",
        "2  ✓  branch      agent-4ff4405d",
        "3  ✓  table       app.tickets · 12 rows",
        "4  ✓  resource    postgres CAN_CONNECT",
        "5  ▸  files       app.yaml · main.py",
        "6  ·  deploy      —",
        "7  ·  verify      —",
        "",
        "A step is drawn done only when a call proved",
        "it. Unproven steps stay empty.",
    ]):
        main.line(3 + i, r, indent=1)
    dock_head(dock, "● working")
    for i, r in enumerate([
        "╭─ plan ───────────────╮",
        "│ create database    ✓ │",
        "│ seed a table       ✓ │",
        "│ scaffold the app   ▸ │",
        "│ deploy             · │",
        "│ verify HTTP 200    · │",
        "╰──────────────────────╯",
    ]):
        dock.line(4 + i, r, indent=1)
    dock.bar(12)
    dock.line(13, "[ Stop ]", indent=1)
    return s


# --------------------------------------------------------------------------- S7
@frame("S7", "Below 1180 px: the rail is a drawer, the dock keeps a column")
def s7():
    w, split = 58, 33
    s = Screen(w, 17)
    s.frame(0, 0, w, 3)
    top = s.pane(1, w - 2, 0)
    top.line(1, "⌘ OpenGenie  ▸ gemini-3.8-flash", indent=1)
    s.raw(w - 15, 1, "☰   ⌘K   RM ▾", limit=w - 2)
    s.frame(0, 3, w, 14)
    s.vline(split, 4, 15)
    m = s.pane(1, split - 1, 3)
    d = s.pane(split + 1, w - 2, 3)
    m.line(1, "tickets_app", indent=1)
    m.bar(2)
    for i, r in enumerate([
        "RUNNING · deployment SUCCEEDED",
        "GET /           200  41 ms",
        "GET /api/rows   200  63 ms",
        "",
        "☰ opens the navigator:",
        "   Data → Lakebase",
    ]):
        m.line(3 + i, r, indent=1)
    d.line(1, "● ready", indent=1)
    d.line(2, "in context:", indent=1)
    d.line(3, "tickets_app", indent=1)
    d.bar(4)
    for i, r in enumerate(["The app answers", "on the URL above.", "",
                           "Under 1180 px the", "rail is a drawer.", "",
                           "⌘J closes this."]):
        d.line(5 + i, r, indent=1)
    d.bar(11)
    d.line(12, "+ @ /  model  Send", indent=1)
    return s


# --------------------------------------------------------------------------- S8
@frame("S8", "The palette, with the new objects in it")
def s8():
    w = 66
    s = Screen(w, 13)
    s.frame(0, 0, w, 13)
    p = s.pane(1, w - 2, 0)
    p.line(1, "⌘K   search or run a command", indent=1)
    p.bar(2)
    p.line(3, "› lakeb", indent=1)
    p.bar(4)
    for i, r in enumerate([
        "Lakebase   pg_tickets          project",
        "Lakebase   pg_orders           project",
        "Apps       tickets_app          running",
        "Apps       orders_api           stopped",
        "Action     Create a Lakebase project",
        "Action     Scaffold an app from a table",
        "Table      samples.nyctaxi.trips",
    ]):
        p.line(5 + i, r, indent=1)
    return s


if __name__ == "__main__":
    import sys

    blocks, warnings = [], []
    for sid, title, fn in FRAMES:
        s = fn()
        note = ANNOT.get(sid, "")
        blocks.append(f"#### {sid} — {title}\n\n```text\n{s.out()}\n```\n\n{note}")
        warnings += [(sid, a, t) for a, t in s.clipped]
    print("\n\n".join(blocks))
    for sid, avail, text in warnings:
        print(f"CLIP {sid} avail={avail:3d} len={len(text):3d}  {text}", file=sys.stderr)
    if warnings:
        print(f"{len(warnings)} clipped line(s)", file=sys.stderr)
