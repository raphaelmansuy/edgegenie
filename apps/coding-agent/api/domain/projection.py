"""Which archived projections may leave memory. A pure decision, like the reaper's and the sweeper's.

The defect this closes. `Orchestrator._live` is the in-memory projection: one `Live` per conversation,
holding the session, its turns, and its recorded tool calls. Nothing ever removed an entry —
`archive()` stops the processes and sets the status, and the dictionary kept the object. A long-lived
server therefore grew by one conversation's worth of memory per conversation, for the life of the
process. Small per entry, and unbounded in total.

The wrong fix is a size cap: "keep the last 100 and drop the rest". That deletes a *snapshot* the
server would have to re-read from the journal to answer a request, and it makes behaviour depend on
how many sessions happened to be open. The right fix is the same shape as the other two reapers: a
pure rule, so a mistake is a test failure rather than lost work.

Three rules, ordered by what a mistake would cost:

1. **Never a session with a turn in flight.** It is not archived, and this never touches it.
2. **Never one someone is watching.** An open stream is a human looking at a transcript.
3. **Only an ARCHIVED one, and only after a grace period.** Archiving is the user's delete, so the
   projection is already gone from every list; the grace period is what lets a caller that is mid-read
   finish, and what keeps "delete then immediately re-open" from thrashing the journal.

Eviction is *not* deletion. The snapshot and the events stay in Postgres; `restore()` rebuilds the
projection on the next boot, and a read of an evicted session can be answered by reading the journal.
That is why this rule can be more permissive than the session reaper: the worst case is a cache miss,
not a lost conversation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Disposition(str, Enum):
    """Why a projection is kept, or may go. Never a bare boolean, so a test can assert the reason."""

    KEPT_BUSY = "a turn is in flight"
    KEPT_WATCHED = "a stream is connected"
    KEPT_NOT_ARCHIVED = "the session is not archived"
    KEPT_RECENT = "archived, but inside the grace period"
    EVICT = "archived, unwatched, and past the grace period"


def may_evict(d: Disposition) -> bool:
    return d is Disposition.EVICT


@dataclass(frozen=True, slots=True)
class Candidate:
    session_id: str
    status: str
    #: Epoch seconds of the last activity.
    last_seen: float
    #: Live stream subscribers. Non-zero means a human is looking.
    watchers: int = 0
    #: True when a turn is running/auditing/queued. A bool rather than a status list, because the
    #: question is "is it busy", not "what is it doing".
    busy: bool = False


#: How long an archived projection stays in memory after its last activity. Long enough that a
#: delete-then-read cycle answers from memory, short enough that a busy server does not hold every
#: conversation it ever served. Overridable so a test does not sleep.
GRACE_SECONDS = 10 * 60


def disposition(c: Candidate, *, now: float, grace_seconds: float = GRACE_SECONDS) -> Disposition:
    """Keep or evict one projection. Total: every input gets an answer and none of them raise."""
    if c.busy:
        return Disposition.KEPT_BUSY
    if c.watchers > 0:
        return Disposition.KEPT_WATCHED
    if c.status != "archived":
        return Disposition.KEPT_NOT_ARCHIVED
    if now - c.last_seen < grace_seconds:
        return Disposition.KEPT_RECENT
    return Disposition.EVICT


def evictable(candidates: list[Candidate], *, now: float,
              grace_seconds: float = GRACE_SECONDS) -> list[str]:
    """The ids to drop from memory, in the order given. The one function a caller needs."""
    return [c.session_id for c in candidates
            if may_evict(disposition(c, now=now, grace_seconds=grace_seconds))]
