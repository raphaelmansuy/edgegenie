"""What a restored session becomes. One pure decision, so a restart stops asking for a click. `[R-10]`, `[F-9]`.

The defect this closes. `restore()` marked **every** non-archived session `BLOCKED + requires_resume`,
including a conversation that was idle and had no turn in flight. The user then had to press **Restore**
on each one — an app redeploy turned every conversation into a "needs attention" banner, which teaches
people the app is fragile when the journal is in fact the strongest part of the product.

**Three dispositions, and the distinction that matters:**

    busy      a turn was in flight -> blocked + requiresResume (the only case that needs a human)
    idle      nothing was running  -> ready, and the agent is provisioned on the next message
    archived  the user's delete    -> untouched

`busy` is the only one that may set `requiresResume`. An idle conversation is *resumable without asking*,
because there is nothing to decide: the projection restored, the turns are intact, and the agent process
is simply absent until the next message.

**Why `ready` is honest** even though no agent process exists. `SessionState` distinguishes "the
projection is usable" from "a process is running", and `blocked + requiresResume` is what the composer
gates on (`domain/compose.ts`). So `ready` means exactly what it says, and `_provision` starts the child
on the first `submit`, which is the same path a brand-new session takes.

This follows the shape of `reaper.reapable`, `projection.disposition` and `retention.retention`:
**total** (every input gets a named answer), **valued** (a `Disposition`, never a bool), and **clockless**,
so a test asserts the rule rather than the plumbing.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

#: Statuses that carried work in flight when the process died.
_IN_FLIGHT = ("running", "auditing", "queued")


class Disposition(str, Enum):
    """Why a restored session is in the state it is in."""

    WAS_BUSY = "mid_turn"
    WAS_IDLE = "idle"
    WAS_ARCHIVED = "archived"
    WAS_FAILED = "failed"

    @property
    def requires_resume(self) -> bool:
        """Only `WAS_BUSY`. A failed provision is retried by its own route, not by a Restore banner."""
        return self is Disposition.WAS_BUSY

    @property
    def status(self) -> str:
        """The session status this disposition implies."""
        return {
            Disposition.WAS_BUSY: "blocked",
            Disposition.WAS_IDLE: "ready",
            Disposition.WAS_ARCHIVED: "archived",
            Disposition.WAS_FAILED: "blocked",
        }[self]

    @property
    def sentence(self) -> str:
        """What the user reads. Empty for the two states that need no announcement."""
        if self is Disposition.WAS_BUSY:
            return ("The server restarted while this turn was running. Saved progress is available; "
                    "no action was repeated.")
        if self is Disposition.WAS_FAILED:
            return "This session did not start. Retry to begin it again."
        return ""


@dataclass(frozen=True, slots=True)
class Snapshot:
    """What the decision needs about one restored session, and nothing else."""

    status: str
    #: The statuses of this session's turns, as they were committed.
    turn_statuses: tuple[str, ...] = ()


def disposition(snap: Snapshot) -> Disposition:
    """What this session becomes after a restart. Total: every input gets an answer, none raise."""
    status = (snap.status or "").lower()
    if status == "archived":
        return Disposition.WAS_ARCHIVED
    if any(t in _IN_FLIGHT for t in snap.turn_statuses):
        # The only case that needs a human: work was interrupted mid-flight and must not be replayed.
        return Disposition.WAS_BUSY
    if status == "failed":
        # A session that never started is retried by `resume`, which is a different action from
        # "Restore this conversation": it re-runs provisioning rather than trusting a saved projection.
        return Disposition.WAS_FAILED
    return Disposition.WAS_IDLE


def apply(snap: Snapshot) -> dict:
    """The changes to make, as a dict, so the caller has one place to apply them.

    A dict rather than a mutated `Session` keeps this module pure: the orchestrator owns the state and
    this owns the rule.
    """
    d = disposition(snap)
    return {
        "status": d.status,
        "requires_resume": d.requires_resume,
        "resume_reason": d.value if d.requires_resume else "",
        "detail": d.sentence,
    }
