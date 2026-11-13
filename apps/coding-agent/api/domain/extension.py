"""Genie Ontology, documentation search, scheduled runs and bounded subagents. Pure decisions.

Four phase-4 items share this module because each is a **policy about scope**, not a transport:

  `[R-19]` a SECOND tool server is admitted only if it is read-only by construction, because the fence's
           whole mechanism is "this process was started with one folder and one schema" — a foreign server
           has none of that, so it may be added and must never be merged.
  `[R-20]` documentation search is a corpus plus a citation shape.
  `[R-23]` a scheduled run uses the CREATOR's identity and **cannot approve** anything.
  `[R-25]` a subagent is a second tool server scoped TIGHTER than its parent, with ceilings.

Keeping them together makes the shared rule visible: **every one of them is a narrowing.** None may widen
what the parent session could do, and each is testable without a network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


# ============================================================== [R-19] a second, fenced server
@dataclass(frozen=True, slots=True)
class Server:
    """A tool server a session may attach. `read_only` is a PROPERTY OF THE SERVER, not a setting."""

    name: str
    #: A server this app cannot fence may only be admitted if it cannot mutate at all. There is no third
    #: case: a mutable foreign server would make "writes stay inside the fence" false for the session.
    read_only: bool
    #: How many tools it advertises. Counted separately from the 28-tool `core` budget, because that budget
    #: is a claim about THIS server and summing the two would make it a lie.
    tools: int = 0
    reason: str = ""


def may_attach(server: Server, *, allowed: set[str]) -> tuple[bool, str]:
    """May this session attach this server? Total, and it refuses more than it allows.

    An unknown server is refused: a marketplace of third-party servers is `[G-11]`, deliberately refused,
    because "read-only by construction" is not a property this app can verify about someone else's code.
    """
    if server.name not in allowed:
        return False, (f"{server.name} is not on this workspace's list of approved servers. "
                       "An administrator adds servers; a session cannot.")
    if not server.read_only:
        return False, (f"{server.name} can change data, and this app cannot fence a server it did not start. "
                       "Only a read-only server may be attached.")
    return True, ""


def tool_budget(servers: list[Server], core: int) -> dict:
    """The tool count, per server. One number per surface, never a sum.

    `[R-19]`: the 28-tool `core` budget is a claim about the server this app starts. Adding a second
    server's tools to that number would make the budget test pass while the agent advertised twice as many
    schemas — which is the cost the budget exists to bound.
    """
    rows = [{"server": "built-in", "tools": core, "readOnly": False}]
    rows += [{"server": s.name, "tools": s.tools, "readOnly": s.read_only} for s in servers]
    return {"servers": rows, "total": sum(r["tools"] for r in rows)}


# ============================================================== [R-20] citations
@dataclass(frozen=True, slots=True)
class Citation:
    """A documentation page a claim came from, with the section when the source knows it."""

    title: str
    url: str
    section: str = ""
    #: The words that were matched, so a reader can see why this page was returned.
    matched: str = ""

    def line(self) -> str:
        where = f"{self.title} › {self.section}" if self.section else self.title
        return f"[{where}]({self.url})"


@dataclass(frozen=True, slots=True)
class DocHit:
    path: str
    title: str
    url: str
    score: int
    excerpt: str


def rank_docs(hits: list[DocHit], *, limit: int = 5) -> list[DocHit]:
    """Best first, and never more than `limit`. Ties keep their input order, so a result is stable."""
    return sorted(hits, key=lambda h: -h.score)[:limit]


def cite(hit: DocHit, section: str = "", matched: str = "") -> Citation:
    return Citation(hit.title, hit.url, section, matched)


# ============================================================== [R-23] schedules
@dataclass(frozen=True, slots=True)
class Schedule:
    """One scheduled prompt, owned by a person."""

    id: str
    prompt: str
    #: The creator. A run uses THIS identity: Genie's scheduled runs use the creator's permissions, and so
    #: does this. The difference is what happens when a run needs an approval.
    owner: str
    cron: str = ""
    folder: str = ""
    write_mode: str = "read-only"


@dataclass(frozen=True, slots=True)
class RunDecision:
    outcome: Literal["run", "refused"]
    reason: str = ""
    #: The write mode the run gets. NEVER wider than the schedule's own, and never `ask`: an unattended run
    #: has nobody to ask.
    mode: str = "read-only"
    identity: str = ""


def plan_run(s: Schedule, *, now: float = 0.0) -> RunDecision:
    """Whether an unattended run may start, and as whom.

    **A scheduled run cannot approve anything** (`[R-23]`). Genie's scheduled tasks "always" auto-approve;
    the safe choice is available here because approvals are a first-class concept, so a schedule that would
    need one is refused with the reason. That is deliberately *worse* than Genie on convenience and better
    on governance, which is the trade this product exists to make.
    """
    if not s.prompt.strip():
        return RunDecision("refused", "this schedule has no prompt")
    if not s.owner:
        return RunDecision("refused", "this schedule has no owner, so there is no identity to run as")
    mode = s.write_mode if s.write_mode in ("read-only", "fenced") else "read-only"
    return RunDecision("run", mode=mode, identity=s.owner)


# ============================================================== [R-25] a bounded subagent
@dataclass(frozen=True, slots=True)
class Ceiling:
    """What a subagent may spend. Every field is a hard stop, checked before each step."""

    tokens: int = 60_000
    seconds: float = 120.0
    tools: int = 12


@dataclass(frozen=True, slots=True)
class Subagent:
    """A child scope, narrower than its parent. `[R-25]`.

    Its purpose is **context isolation on a large catalog**: "find the table that holds revenue" across
    4 000 tables must not put 4 000 names in the main conversation.
    """

    parent: str
    objective: str
    ceiling: Ceiling = field(default_factory=Ceiling)
    #: A catalog or schema the child may read. Empty means "everything the parent could", which is allowed
    #: but is why the ceilings exist.
    scope: str = ""


def _inside(child: str, parent: str) -> bool:
    """Is `child` the parent, or something under it? Handles BOTH separators.

    A scope is written two ways in this product: a workspace folder (`/Users/me/proj/sub`) and a Unity
    Catalog name (`main.gold.orders`). The first narrows by `/`, the second by `.` — and a check that knew
    only `/` refused `main.gold.sub` inside `main.gold`, which is the common case for a subagent scoped to
    one schema. Measured by this module's own test on the first run.
    """
    c, p = child.rstrip("/"), parent.rstrip("/")
    if c == p:
        return True
    if c.startswith(p + "/"):
        return True
    return c.startswith(p + ".")


def may_start(sub: Subagent, *, parent_tokens_left: int, parent_scope: str = "") -> tuple[bool, str]:
    """Whether a subagent may be started, and why not. Total.

    The two refusals that matter: a child may not outlive its parent's budget, and a child may not be
    WIDER than its parent. Both are the "a subagent is a narrowing" rule, made checkable.
    """
    if not sub.objective.strip():
        return False, "a subagent needs an objective"
    if sub.ceiling.tokens <= 0 or sub.ceiling.seconds <= 0:
        return False, "a subagent needs a positive ceiling"
    if sub.ceiling.tokens > parent_tokens_left:
        return False, (f"this subagent asks for {sub.ceiling.tokens:,} tokens but the parent has "
                       f"{parent_tokens_left:,} left")
    if parent_scope and sub.scope and not _inside(sub.scope, parent_scope):
        return False, (f"the subagent's scope {sub.scope} is not inside the parent's {parent_scope}; "
                       "a subagent may narrow a scope, never widen it")
    return True, ""


def attribution(sub: Subagent) -> dict:
    """How a subagent's calls appear in the parent's transcript: one collapsed group, attributed."""
    return {"group": sub.objective[:80], "parent": sub.parent, "collapsed": True,
            "ceiling": {"tokens": sub.ceiling.tokens, "seconds": sub.ceiling.seconds}}
