"""Accumulate deltas; emit at most every `ms` or every `chars`, and ALWAYS at the end.

The defect this closes. `[F-4]`/`[F-5]`: every `message.delta` from the agent became one journalled
event, and every event wrote the **whole snapshot**. A 60 000-character answer arrives as roughly
15 000 deltas, so a turn wrote ≈1.8 GB and the browser rebuilt a 60 000-character string 15 000 times —
quadratic in the length of the answer, at both ends.

**Why this lives in `services/` and not `domain/`.** It holds state and reads a clock, which `domain/`
forbids. It is not in `adapters/acp/` because the *runtime* must not own a batching policy: a second
runtime would reimplement it, and the two would disagree about when text appears.

**The rule that must not move.** `docs/10-data-model.md`: *the commit happens before the publish, and
the queue is a wake-up while the journal is truth*. Coalescing changes **how many** events there are. It
does not change the order: `push()` calls the emitter, which commits then publishes, exactly as before.

**The five flush paths**, each of which is a test, because a missing flush is a lost tail:
  1. the interval elapsed;
  2. the buffer reached `chars`;
  3. a **non-delta** event arrived (see `flush_before` — a tool card must never appear above the text
     that requested it);
  4. the turn ended;
  5. the turn was cancelled or the server is shutting down.

`[R-6]`, `[E-15]`.
"""

from __future__ import annotations

import time
from typing import Awaitable, Callable

#: The event types that are worth batching. Everything else is a boundary and flushes what is pending.
DELTA_TYPES = frozenset({"message.delta", "thought.delta"})


class Coalescer:
    """One per turn. Not shared: two turns must never batch into each other's stream.

    `emit` is awaited with each accumulated event, so the caller keeps the existing
    commit-then-publish contract and this class never touches a store.
    """

    def __init__(
        self,
        emit: Callable[[object], Awaitable[object]],
        *,
        ms: int = 100,
        chars: int = 2048,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._emit = emit
        self._interval = max(0.0, ms / 1000.0)
        self._chars = max(1, chars)
        self._clock = clock
        self._pending: dict[str, list[str]] = {}   # event type -> accumulated text
        self._template: dict[str, object] = {}     # event type -> the last event, to copy its shape
        self._since = 0.0
        #: Counters a test asserts instead of counting bytes. `emitted` is the reduction.
        self.emitted = 0
        self.received = 0

    def pending(self) -> int:
        """Characters buffered, not parts. The bound is a size, and comparing a count of deltas to a
        character budget is how the first draft's flush never fired."""
        return sum(sum(len(part) for part in parts) for parts in self._pending.values())

    async def push(self, event) -> None:
        """Accept one event. A delta is buffered; anything else flushes first, then passes through."""
        kind = getattr(event, "type", "")
        self.received += 1
        if kind not in DELTA_TYPES:
            await self.flush()
            await self._emit(event)
            self.emitted += 1
            return

        text = str((event.payload or {}).get("text", ""))
        if not text:
            return
        if not self._pending:
            self._since = self._clock()
        # Flush BEFORE appending when this delta would take the buffer past `chars`. Appending first and
        # then checking (which the first draft did) makes every batch overshoot by one delta, so the
        # bound holds only approximately — and a bound that holds approximately is not a bound.
        buffered = self.pending()
        if buffered and buffered + len(text) > self._chars:
            await self.flush()
            self._since = self._clock()
        self._pending.setdefault(kind, []).append(text)
        self._template[kind] = event
        if self.pending() >= self._chars or (self._clock() - self._since) >= self._interval:
            await self.flush()

    async def flush(self) -> None:
        """Emit everything buffered, as ONE event per type, preserving arrival order within a type."""
        if not self._pending:
            return
        pending, template = self._pending, self._template
        self._pending, self._template = {}, {}
        for kind, parts in pending.items():
            base = template[kind]
            text = "".join(parts)
            # `replace` keeps the event's identity (session, turn, seq) and swaps only the payload, so
            # a consumer cannot tell a coalesced delta from a single one except by its length.
            await self._emit(_with_text(base, text))
            self.emitted += 1
        self._since = self._clock()


def _with_text(event, text: str):
    """The same event with its `text` payload replaced. Imported lazily so this module stays cheap."""
    import dataclasses

    payload = dict(getattr(event, "payload", {}) or {})
    payload["text"] = text
    try:
        return dataclasses.replace(event, payload=payload)
    except TypeError:
        # A non-dataclass event (a test double): mutate a copy if possible, else pass through.
        try:
            clone = type(event)(**{**getattr(event, "__dict__", {}), "payload": payload})
            return clone
        except Exception:  # noqa: BLE001 - the fallback must not break a turn
            return event
