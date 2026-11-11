"""When a snapshot is written. One reason to change: the policy. `[R-5]`, `[F-4]`.

`commit()` did two jobs in one method, and that is the whole defect:

  1. **record a fact** — append the event to `agent.session_event`. O(1), must happen for every event,
     must be durable before publish.
  2. **cache the projection** — write `body` to `agent.session_snapshot`. O(size), need not happen for
     every event, and is an *optimisation* of a rebuild that (1) already makes possible.

Because they were one call, every `message.delta` wrote the whole snapshot: ≈1.8 GB per turn for a
60 000-character answer, inside one process-wide lock shared by every session.

This module owns (2) and nothing else. `append()` keeps the order (`docs/10-data-model.md`): append →
publish → *maybe* checkpoint. **The checkpoint may fail; the truth may not** — a failed checkpoint is
logged and the turn continues, because the journal is complete and the next boot rebuilds from it.

Why both a counter and a clock: a fast turn of 15 000 deltas must not wait for a timer to make progress,
and a slow turn of three events must not checkpoint three times. Either bound alone is wrong.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

log = logging.getLogger("app.journal.checkpoint")

#: Write a checkpoint at most this often...
EVERY_EVENTS = 50
#: ...or at most this often, whichever comes first. 5 s is short enough that a crash loses at most a few
#: seconds of projection (the events themselves are never lost) and long enough that a slow turn is not
#: writing a snapshot per event.
EVERY_SECONDS = 5.0


@dataclass
class Checkpointer:
    """Per-session state for "should this commit also write the snapshot?".

    One instance per session, held by the `Live` projection. It holds no I/O: the caller writes when
    this says yes, which keeps the policy testable without a database.
    """

    every_events: int = EVERY_EVENTS
    every_seconds: float = EVERY_SECONDS
    clock: object = time.monotonic

    _since_seq: int = 0
    #: `None` until the first event, so the window starts at the FIRST event rather than at
    #: construction. Defaulting to `time.monotonic()` at construction ignored an injected clock (a test's
    #: clock starts at 0, the real one at ~67 000 s, so the time bound was always already elapsed) — which
    #: is how a policy test passes while the policy is wrong.
    _since_at: float | None = None
    #: Counters a test asserts. `writes` is the reduction that matters.
    appends: int = 0
    writes: int = 0

    def should_write(self, *, seq: int, force: bool = False) -> bool:
        """After appending the event at `seq`, is a checkpoint due?

        `force` is for the cases that must not wait: a turn's terminal event, an archive, a shutdown.
        A terminal snapshot is what a restart reads, so leaving it to a counter would lose the last
        forty events of every turn.

        **The watermark advances when the write is DECIDED**, not when it succeeds. The first draft
        advanced it only in `note_written`, so a writer that forgot to call that — or a store with no
        `checkpoint` — left the window open and every subsequent event looked due: measured, 951 writes
        for 1 000 events instead of 20. A failure is corrected by `note_written` not being called, which
        the `test_a_failed_write_is_retried` case pins.

        **The first event always writes.** A session with no snapshot row cannot be restored at all.
        """
        self.appends += 1
        now = self.clock()
        first = self._since_at is None
        if first:
            self._since_at = now
        due = (
            first
            or force
            or seq - self._since_seq >= self.every_events
            or (now - self._since_at) >= self.every_seconds
        )
        if due:
            self.writes += 1
            self._since_seq = seq
            self._since_at = now
        return due

    def note_failed(self, seq: int, previous_seq: int) -> None:
        """A write failed: reopen the window so the next event retries.

        Called by `checkpoint()` on an exception. Without it a failed write would be forgotten until the
        next interval, and a container that never checkpoints successfully would restore a projection
        that is hours old.
        """
        self._since_seq = previous_seq

    def note_written(self, seq: int) -> None:
        """Confirm a successful checkpoint. The watermark has usually advanced already; this is the
        explicit acknowledgement a caller may use when it writes out of band."""
        self._since_seq = max(self._since_seq, seq)
        self._since_at = self.clock()

    @property
    def last_good(self) -> int:
        """The highest seq a checkpoint definitely covers. Used to reopen the window on a failure."""
        return self._since_seq


async def checkpoint(store, session_id: str, seq: int, body: dict, *, checkpointer: Checkpointer,
                     force: bool = False) -> bool:
    """Write the projection if the policy says so. Returns whether it wrote.

    Never raises: a cache write is not a reason to fail a turn. The failure is logged once per attempt
    rather than per event, because a broken snapshot writer would otherwise produce 15 000 log lines for
    one turn and hide whatever else went wrong.
    """
    if not checkpointer.should_write(seq=seq, force=force):
        return False
    writer = getattr(store, "checkpoint", None)
    if writer is None:
        # A store that predates the split (a test double): it has no separate writer, and the caller
        # already recorded the fact. Not an error, and not silent either.
        return False
    try:
        await writer(session_id, seq, body)
        return True
    except Exception:  # noqa: BLE001 - the truth is already durable; the cache is not
        checkpointer.note_failed(seq, checkpointer.last_good)
        log.warning("checkpoint failed for session %s at seq %s; the journal is intact",
                    session_id, seq, exc_info=True)
        return False
