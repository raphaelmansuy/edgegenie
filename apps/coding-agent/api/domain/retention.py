"""How long an attachment may live. A pure decision, for the same reason the reaper's is pure.

The defect this closes. `BlobStore.sweep()` and `delete_session()` were implemented on both stores and
covered by the same contract test — and **nothing called them**. So attachment bytes accumulated for
the life of the container, and an archived session's bytes were never removed. Two working functions
with no caller is not a feature; it is a leak with a test suite.

The fix is not "call `sweep()` on a timer". A sweeper is the kind of code that quietly deletes a file
someone is about to open, exactly as the session reaper is the kind of code that kills a running turn.
So the *decision* lives here, pure and total, and the timer only obeys it:

    retention(row, refcount, now) -> Keep | Sweep

Three questions, in order of how much a mistake would cost:

1. **Is a turn using it?** A referenced blob is never swept, at any age. A transcript chip pointing at
   bytes that no longer exist is the failure the feature exists to prevent, and a reference is the only
   evidence that a person can still reach it.
2. **Was it ever sent?** `ready` means uploaded and never attached. It is reachable from nowhere — the
   composer lost it, or the tab closed — so it goes at `READY_TTL`.
3. **Is it still waiting for a session?** `pending:<user>` means uploaded before the first message. A
   user who uploads and then walks away should not leave bytes forever, so it goes at `PENDING_TTL`.

Anything else is kept. A state this module does not recognise is kept, not swept: an unknown row is a
reason to leave it alone, because guessing here destroys a file.

Both implementations already encode two of these three constants (`PENDING_TTL`, `READY_TTL` in
`adapters/blob/memory.py`). They are re-exported here so the policy and the stores cannot disagree —
and `tests/test_blob_retention.py` pins the numbers, because a TTL that silently becomes 0 deletes
everything on the first pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

#: A chip that never finished uploading. One hour: longer than any plausible paste, shorter than a
#: workday, and it costs nothing to ask the user to attach it again.
PENDING_TTL = 60 * 60
#: Uploaded, validated, and never sent. A day: long enough to survive an overnight pause in a task,
#: short enough that a forgotten screenshot is not permanent.
READY_TTL = 24 * 60 * 60


class Disposition(str, Enum):
    """Why a blob is kept, or not. Never a bare boolean: a test needs to assert the reason."""

    KEPT_REFERENCED = "a turn references it"
    KEPT_FRESH = "within its time to live"
    KEPT_UNKNOWN_STATE = "its state is not one this policy understands"
    SWEEP_PENDING = "never attached, past the pending limit"
    SWEEP_READY = "uploaded and never sent, past the ready limit"


def is_sweep(d: Disposition) -> bool:
    return d in (Disposition.SWEEP_PENDING, Disposition.SWEEP_READY)


@dataclass(frozen=True, slots=True)
class Candidate:
    """What the policy needs about one row, and nothing else. No bytes, no name, no owner.

    Building one of these is how the caller proves it is deciding about a row rather than about a
    filename: a policy that took a `BlobRow` could start depending on `original_name`, and a name is
    the one field a user controls.
    """

    blob_id: str
    state: str
    created_at: float
    refcount: int = 0


def retention(c: Candidate, *, now: float) -> Disposition:
    """Keep or sweep one row. Total: every `state` gets an answer, and none of them raise."""
    if c.refcount > 0:
        return Disposition.KEPT_REFERENCED
    age = now - c.created_at
    if c.state == "pending" and age > PENDING_TTL:
        return Disposition.SWEEP_PENDING
    if c.state == "ready" and age > READY_TTL:
        return Disposition.SWEEP_READY
    if c.state in ("pending", "ready", "attached"):
        return Disposition.KEPT_FRESH
    # `swept`, or a state a newer version wrote. Both mean "leave it alone".
    return Disposition.KEPT_UNKNOWN_STATE


def sweepable(candidates: list[Candidate], *, now: float) -> list[str]:
    """The ids to delete, in the order given. The one function a timer needs."""
    return [c.blob_id for c in candidates if is_sweep(retention(c, now=now))]


def candidate(row, refcount) -> Candidate:
    """Build a `Candidate` from a stored row, and decide *which state it is really in*.

    The stores set `state="ready"` in `put()` and only `mark_attached` changes it, so a row's `state`
    alone cannot say whether it is waiting for a session. The session key can: a blob uploaded before
    the first message is stored under `pending:<user>` and adopts its session when a message carries
    it. Reading that here, once, is why two stores cannot disagree about which TTL applies — and why
    a branch on a state that is never written cannot sit in both of them looking correct.
    """
    waiting = str(getattr(row, "session_id", "")).startswith("pending:")
    return Candidate(
        blob_id=row.id,
        state="pending" if waiting and row.state == "ready" else row.state,
        created_at=row.created_at,
        refcount=len(refcount) if not isinstance(refcount, int) else refcount,
    )
