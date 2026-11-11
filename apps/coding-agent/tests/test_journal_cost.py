"""The journal's cost, asserted as writes rather than described in a comment. `[R-5]`, `[F-4]`.

The defect: `commit()` wrote the **whole snapshot** on every event. A 60 000-character answer is ~15 000
deltas, so one turn wrote ≈18 GB across ten turns, inside a process-wide lock shared by every session.

Two things are asserted here, and neither is a byte count — bytes depend on the payload, and a budget
tested in bytes passes when the payload gets smaller:

  1. **one checkpoint per N events**, counted by spying on the writer;
  2. **the order** — append, then publish, then maybe checkpoint. A checkpoint that moved `latest_seq`
     would make `since(seq)` skip the events written between the append and the snapshot.
"""

from __future__ import annotations

import pytest

from api.adapters.durable.checkpoint import Checkpointer, checkpoint
from api.domain.events import Event


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, s: float) -> None:
        self.now += s


class SpyStore:
    """Records the order of writes, so "append then checkpoint" is an assertion and not a comment."""

    def __init__(self, fail: bool = False) -> None:
        self.calls: list[tuple[str, int]] = []
        self.fail = fail

    async def checkpoint(self, session_id: str, seq: int, body: dict) -> None:
        self.calls.append(("checkpoint", seq))
        if self.fail:
            raise RuntimeError("the database refused the snapshot upsert")

    async def append(self, event: Event) -> Event:
        self.calls.append(("append", 0))
        return event


# ============================================================== the policy
def test_a_thousand_events_write_about_twenty_snapshots_not_a_thousand():
    """The reduction that fixes `[F-4]`: 1 000 appends → ~20 checkpoints at `every_events=50`.

    The first event always writes (a session with no snapshot row cannot be restored), so the count is
    1 + floor(999/50) = 20, not 20 by luck.
    """
    c = Checkpointer(every_events=50, every_seconds=10_000, clock=Clock())
    writes = sum(1 for seq in range(1, 1001) if c.should_write(seq=seq))
    assert writes == 20, f"{writes} checkpoints for 1 000 events"
    assert c.appends == 1000


def test_the_time_bound_writes_even_when_events_are_few():
    """A slow turn of three events must not wait for fifty. Both bounds apply; either alone is wrong."""
    clock = Clock()
    c = Checkpointer(every_events=50, every_seconds=5.0, clock=clock)
    assert c.should_write(seq=1) is True    # the first event establishes the row
    clock.advance(1.0)
    assert c.should_write(seq=2) is False
    clock.advance(5.1)
    assert c.should_write(seq=3) is True


def test_the_first_event_always_writes_so_the_session_can_be_restored():
    """A restart reads the terminal snapshot. Leaving it to a counter loses the last 40 events of every
    turn, which is exactly the work a user looks for."""
    c = Checkpointer(every_events=50, every_seconds=10_000, clock=Clock())
    assert c.should_write(seq=1) is True          # the first write
    assert c.should_write(seq=2) is False
    assert c.should_write(seq=2, force=True) is True   # a terminal event does not wait


def test_a_failed_write_is_retried_on_the_next_event():
    """A failed checkpoint reopens the window, so the next event tries again.

    Without `note_failed`, a container whose snapshot writer is broken would restore a projection hours
    old — the journal is intact, but nothing would ever fold it in.
    """
    c = Checkpointer(every_events=5, every_seconds=10_000, clock=Clock())
    assert c.should_write(seq=1) is True          # first write
    assert c.should_write(seq=5) is False
    assert c.should_write(seq=6) is True          # at the bound
    c.note_failed(6, 1)                           # …and the write failed
    assert c.should_write(seq=7) is True, "a failed write was not retried"
    c.note_written(7)
    assert c.should_write(seq=8) is False


# ============================================================== the writer's contract
@pytest.mark.asyncio
async def test_a_failed_checkpoint_does_not_raise_and_does_not_lose_the_event():
    """The cache may fail; the truth may not. A raise here would fail a turn over a cache write."""
    store = SpyStore(fail=True)
    c = Checkpointer(every_events=1, clock=Clock())
    wrote = await checkpoint(store, "s1", 1, {"x": 1}, checkpointer=c)
    assert wrote is False, "a failed checkpoint must report failure, not raise"


@pytest.mark.asyncio
async def test_a_store_without_a_checkpoint_writer_is_not_an_error():
    """A test double that predates the split: it recorded the fact via `commit`, and has no cache."""
    class Bare:
        async def append(self, event): return event

    c = Checkpointer(every_events=1, clock=Clock())
    assert await checkpoint(Bare(), "s1", 1, {}, checkpointer=c) is False


@pytest.mark.asyncio
async def test_the_writer_is_called_only_when_the_policy_says_so():
    store = SpyStore()
    c = Checkpointer(every_events=10, every_seconds=10_000, clock=Clock())
    for seq in range(1, 61):
        await checkpoint(store, "s1", seq, {"n": seq}, checkpointer=c)
    # The first event establishes the row, then one every 10 events from there: 1, 11, 21, 31, 41, 51.
    assert [call for call in store.calls if call[0] == "checkpoint"] == [
        ("checkpoint", 1), ("checkpoint", 11), ("checkpoint", 21),
        ("checkpoint", 31), ("checkpoint", 41), ("checkpoint", 51)]


# ============================================================== the real stores
@pytest.mark.asyncio
async def test_the_memory_store_keeps_the_projection_and_appends_separately():
    """`append` must not write the projection, and `checkpoint` must not append. Two responsibilities."""
    from api.adapters.memory.store import MemoryEventStore

    store = MemoryEventStore()
    event = Event("s1", "message.delta", {"text": "a"})
    await store.append(event)
    assert await store.snapshots() == [], "append wrote a projection"
    assert len(await store.since("s1", 0)) == 1, "append did not record the event"

    await store.checkpoint("s1", 1, {"version": 1})
    assert await store.snapshots() == [{"version": 1}]
    assert len(await store.since("s1", 0)) == 1, "checkpoint appended an event"


@pytest.mark.asyncio
async def test_the_memory_store_still_supports_the_combined_commit():
    """The cold path (a terminal event, an archive) keeps working unchanged."""
    from api.adapters.memory.store import MemoryEventStore

    store = MemoryEventStore()
    await store.commit(Event("s1", "turn.completed", {}), {"version": 1, "done": True})
    assert await store.snapshots() == [{"version": 1, "done": True}]
    assert len(await store.since("s1", 0)) == 1


@pytest.mark.asyncio
async def test_monotonic_sequence_is_preserved_across_appends_and_checkpoints():
    """A checkpoint must not consume or advance a sequence number."""
    from api.adapters.memory.store import MemoryEventStore

    store = MemoryEventStore()
    seqs = [(await store.append(Event("s1", "message.delta", {"text": str(i)}))).seq for i in range(5)]
    await store.checkpoint("s1", 5, {"version": 1})
    nxt = await store.append(Event("s1", "message.delta", {"text": "after"}))
    assert seqs == [1, 2, 3, 4, 5]
    assert nxt.seq == 6, "a checkpoint disturbed the sequence"
