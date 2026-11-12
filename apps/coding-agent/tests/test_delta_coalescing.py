"""Delta coalescing: the reduction, the ordering, and the five flush paths. `[R-6]`, `[F-4]`, `[E-15]`.

The defect: a 60 000-character answer arrives as ~15 000 `message.delta` events, and every one became a
journal commit that wrote the **whole snapshot** — ≈1.8 GB per turn — plus a 60 000-character string
rebuild in the browser per delta. Quadratic in answer length, at both ends.

The risk this introduces is a **lost tail** and a **reordered card**, so the tests are:
  * the reduction (≤ 600 events for a 60 000-character answer);
  * text identity (the concatenation is byte-identical to the input);
  * every flush path, including cancel and shutdown;
  * a tool event flushes pending text FIRST, so a card never appears above the text that requested it;
  * ordering is preserved within a type.
"""

from __future__ import annotations

import pytest

from api.domain.events import Event
from api.services.coalesce import DELTA_TYPES, Coalescer


class Clock:
    """A clock a test moves by hand, so "100 ms elapsed" needs no sleep."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _delta(text: str, tid: str = "t1") -> Event:
    return Event("s1", "message.delta", {"text": text}, turn_id=tid)


def _thought(text: str) -> Event:
    return Event("s1", "thought.delta", {"text": text}, turn_id="t1")


def _tool(name: str = "dbx_run_sql") -> Event:
    return Event("s1", "tool_call.started", {"callId": "c1", "name": name})


async def _collect(**kw):
    """A coalescer wired to a list, plus the clock it uses."""
    out: list[Event] = []

    async def emit(e):
        out.append(e)
        return e

    clock = Clock()
    return Coalescer(emit, clock=clock, **kw), out, clock


# ============================================================== the reduction
async def test_a_long_answer_is_emitted_as_a_few_events_not_thousands():
    """The number that matters: a 60 000-character answer, 2 000-character deltas."""
    answer = "x" * 60_000
    co, out, _ = await _collect(chars=2048)
    for i in range(0, len(answer), 4):        # 15 000 deltas of 4 chars, as the agent sends them
        await co.push(_delta(answer[i:i + 4]))
    await co.flush()
    assert co.received == 15_000
    assert len(out) <= 600, f"emitted {len(out)} events for one answer"
    assert "".join(e.payload["text"] for e in out) == answer


async def test_the_batch_size_is_bounded_so_the_ui_still_streams():
    """A coalescer that buffered a whole answer would look frozen: the dock would show nothing for
    seconds. `chars` bounds the batch, not the total."""
    co, out, _ = await _collect(chars=2048)
    for _ in range(2000):
        await co.push(_delta("abcdefgh"))
    sizes = [len(e.payload["text"]) for e in out]
    assert max(sizes) <= 4096, f"one batch was {max(sizes)} characters"


# ============================================================== text identity
async def test_the_concatenation_is_byte_identical_to_the_input():
    parts = ["The ", "revenue ", "table ", "has ", "5 ", "rows.\n", "Done."]
    co, out, _ = await _collect(chars=10_000)
    for p in parts:
        await co.push(_delta(p))
    await co.flush()
    assert "".join(e.payload["text"] for e in out) == "".join(parts)


async def test_thought_and_message_stay_separate_types():
    """Two streams, two buffers: a coalescer must not merge reasoning into the answer."""
    co, out, _ = await _collect(chars=10_000)
    await co.push(_thought("thinking"))
    await co.push(_delta("answer"))
    await co.flush()
    by_type = {e.type: e.payload["text"] for e in out}
    assert by_type["thought.delta"] == "thinking"
    assert by_type["message.delta"] == "answer"


async def test_an_empty_delta_is_ignored_rather_than_emitted():
    co, out, _ = await _collect()
    await co.push(_delta(""))
    await co.flush()
    assert out == []


# ============================================================== the five flush paths
async def test_flush_on_the_character_bound():
    co, out, _ = await _collect(chars=8)
    await co.push(_delta("12345678"))
    assert len(out) == 1, "the size bound did not flush"


async def test_flush_on_the_interval():
    co, out, clock = await _collect(chars=10_000, ms=100)
    await co.push(_delta("a"))
    assert out == [], "a single small delta must wait for the timer"
    clock.advance(0.11)
    await co.push(_delta("b"))
    assert len(out) == 1
    assert out[0].payload["text"] == "ab"


async def test_flush_at_the_end_of_a_turn():
    """The tail: without this the last sentence is lost."""
    co, out, _ = await _collect(chars=10_000)
    await co.push(_delta("the last words"))
    await co.flush()
    assert out[0].payload["text"] == "the last words"


async def test_flush_before_a_tool_event_so_a_card_never_precedes_its_text():
    """`[E-15]`: the ordering bug a batching change introduces. The card must come after."""
    co, out, _ = await _collect(chars=10_000)
    await co.push(_delta("let me check "))
    await co.push(_delta("the table"))
    await co.push(_tool())
    assert [e.type for e in out] == ["message.delta", "tool_call.started"], (
        "a tool card appeared before the text that requested it")
    assert out[0].payload["text"] == "let me check the table"


@pytest.mark.parametrize("terminal", ["turn.completed", "turn.blocked", "turn.cancelled",
                                      "turn.interrupted", "turn.failed"])
async def test_every_terminal_event_flushes_first(terminal):
    co, out, _ = await _collect(chars=10_000)
    await co.push(_delta("partial"))
    await co.push(Event("s1", terminal, {}, turn_id="t1"))
    assert [e.type for e in out] == ["message.delta", terminal]


async def test_flushing_twice_is_harmless():
    co, out, _ = await _collect()
    await co.push(_delta("a"))
    await co.flush()
    await co.flush()
    assert len(out) == 1


# ============================================================== ordering
async def test_order_is_preserved_across_batches():
    co, out, _ = await _collect(chars=4)
    for chunk in ("aaaa", "bbbb", "cccc"):
        await co.push(_delta(chunk))
    await co.flush()
    assert [e.payload["text"] for e in out] == ["aaaa", "bbbb", "cccc"]


async def test_the_event_identity_is_kept_so_the_reducer_can_place_it():
    """A coalesced delta must still point at its turn, or the reducer cannot find the turn to paint."""
    co, out, _ = await _collect()
    await co.push(_delta("hello", tid="turn-7"))
    await co.flush()
    assert out[0].turn_id == "turn-7"
    assert out[0].session_id == "s1"


def test_only_the_two_text_streams_are_batched():
    assert DELTA_TYPES == frozenset({"message.delta", "thought.delta"})
