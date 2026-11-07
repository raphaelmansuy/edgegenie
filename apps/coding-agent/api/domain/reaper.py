"""Which sessions may be reaped. A pure decision, so the rule is testable without a clock.

The server leaked a subprocess per session: `archive()` tears a session down properly, but nothing
ever called it, so every session a user opened kept its agent process for the life of the process.
An afternoon of testing accumulated 29 live agents, which is what produced intermittent
`Target crashed` renderer failures.

The fix is a reaper, and a reaper is the kind of code that quietly destroys work if its condition is
wrong. So the condition lives here, pure and total:

    reapable(candidate) -> Reason | None

The rules, in order of how much damage getting them wrong would do:

1. **Never a session with a turn in flight.** Killing an agent mid-answer is data loss.
2. **Never a session someone is watching.** A stream connection is a heartbeat: an open tab is
   activity, even if nothing is being typed.
3. **Never one that failed to archive last time** (already archived, so nothing to do).
4. Only after a generous idle window, and only if we are above the soft cap — a single idle session
   on a quiet machine costs one process and is not worth the churn of killing it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum


class Why(str, Enum):
    """Why a session is NOT reapable. Returned instead of a bool so a test can assert the reason."""

    BUSY = "a turn is running"
    WATCHED = "a stream is connected"
    ARCHIVED = "already archived"
    YOUNG = "within the idle window"
    UNDER_CAP = "below the soft cap"


@dataclass(frozen=True, slots=True)
class Candidate:
    session_id: str
    status: str
    #: Epoch seconds of the last activity (turn, stream connect, creation).
    last_seen: float
    #: Live stream subscribers. Non-zero means a human is looking.
    watchers: int = 0
    #: Turns this session has produced. Zero means it was opened and never used.
    turns: int = 0


@dataclass(frozen=True, slots=True)
class Policy:
    """Thresholds. One object so the numbers are visible in one place and can be overridden in a test."""

    #: Idle this long before a session is a candidate at all. Overridable by env so the behaviour
    #: can be exercised against a running server without waiting half an hour.
    idle_seconds: float = float(os.environ.get("APP_REAP_IDLE_SECONDS", 30 * 60))
    #: An **unused** session (no turns) is reaped far sooner. It holds a subprocess and has nothing
    #: to lose: measured at 36 orphan agents after one afternoon of audit runs, every one of them a
    #: session that was created and never spoken to.
    empty_idle_seconds: float = float(os.environ.get("APP_REAP_EMPTY_SECONDS", 5 * 60))
    #: Keep at least this many live sessions even if idle: one process is cheap, churn is not.
    keep_minimum: int = int(os.environ.get("APP_REAP_KEEP_MINIMUM", 8))


def reapable(c: Candidate, *, now: float, live_count: int, policy: Policy) -> Why | None:
    """`None` means reap it; otherwise the reason it must be left alone."""
    if c.status in ("provisioning", "streaming", "blocked", "auditing"):
        # Anything mid-flight. `blocked` is included on purpose: it is waiting for a human answer,
        # and killing it would discard the question the human is about to answer.
        return Why.BUSY
    if c.status == "archived":
        return Why.ARCHIVED
    if c.watchers > 0:
        return Why.WATCHED
    idle = now - c.last_seen
    # An unused session is a different thing from an idle one. It holds a subprocess and has nothing
    # worth returning to, so it does not deserve the long window AND it is not protected by the
    # floor — the floor exists to avoid churn on sessions someone might come back to.
    if c.turns == 0:
        # No floor: an unused session costs a subprocess and protects nobody.
        return None if idle >= policy.empty_idle_seconds else Why.YOUNG
    if idle < policy.idle_seconds:
        return Why.YOUNG
    if live_count <= policy.keep_minimum:
        return Why.UNDER_CAP
    return None
