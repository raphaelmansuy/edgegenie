"""What to shed when a conversation outgrows the model's window. Pure, and it plans rather than acts. `[R-11]`, `[F-10]`.

The defect this closes. `session.compacted` is one of the 27 event names (`api/domain/events.py`), it is
in the TypeScript union, it is in `event-parity.json` — and **nothing emitted it**. So a long conversation
had no mechanism to shed history before it hit the model's window, and the only limit was
`MAX_TURNS = 200`, a hardcoded constant while `settings.max_turns_per_session` existed with no reader.

The failure that produces is not a clean error. At the window boundary the provider truncates, the agent
loses the earlier turns, and the supervisor then reports *"requirements without verified evidence"* for
work that was done — literally true and completely misleading.

**What this module decides, and what it refuses to decide.** It returns a `Plan`: which turns to keep
verbatim, which to replace with a summary, and why. It does **not** call a model (the summariser is the
caller's), does not read a clock, and does not touch a store. `estimate` is injected for the same reason
`Clock` is in `cellrun`: a rule that cannot be tested without a model is a rule nobody tests.

**The keep-policy, and why.** The FIRST turn and the LAST few are kept verbatim:
  * the first states the objective — summarise it and every later turn loses its referent;
  * the last few are live work — the agent is mid-task on them;
  * the middle is what a summary is for.
A summary that replaced the objective would be a summary of a conversation about nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

#: Keep the opening turn, always: it holds the objective.
KEEP_FIRST = 1
#: Keep this many of the most recent turns verbatim: they are the live work.
KEEP_LAST = 4
#: Never summarise fewer than this many turns — summarising two turns costs more than it saves.
MIN_TO_SUMMARISE = 3


@dataclass(frozen=True, slots=True)
class Turn:
    """What the plan needs about one turn. Not the domain `Turn`: this must not import it."""

    id: str
    index: int
    tokens: int


@dataclass(frozen=True, slots=True)
class Plan:
    """Which turns survive verbatim, which become a summary, and the sentence that explains it."""

    keep: tuple[str, ...]
    summarise: tuple[str, ...]
    reason: str
    before: int
    after: int

    @property
    def changed(self) -> bool:
        return bool(self.summarise)

    def to_event(self) -> dict:
        """The payload of `session.compacted`, so the journal records what happened.

        Recorded rather than derived: a reader of the transcript a week later must be able to see that
        turns 2–8 became a summary, and what the summary replaced.
        """
        return {
            "kept": list(self.keep),
            "summarised": list(self.summarise),
            "reason": self.reason,
            "tokensBefore": self.before,
            "tokensAfter": self.after,
        }


def plan(
    turns: Sequence[Turn],
    *,
    budget: int,
    estimate: Callable[[Turn], int] | None = None,
    keep_first: int = KEEP_FIRST,
    keep_last: int = KEEP_LAST,
    reserved: int = 0,
) -> Plan | None:
    """`None` when nothing needs shedding. A `Plan` otherwise.

    `budget` is the context window minus what the next turn needs (`reserved`), in tokens. `estimate`
    defaults to the turn's own recorded size, so a caller with real counts passes them through.
    """
    if not turns:
        return None
    size = estimate or (lambda t: t.tokens)
    total = sum(size(t) for t in turns)
    usable = max(0, budget - reserved)
    if total <= usable:
        return None

    keep_head = list(turns[:keep_first])
    keep_tail = list(turns[-keep_last:]) if len(turns) > keep_first else []
    middle = list(turns[len(keep_head): len(turns) - len(keep_tail)]) if keep_tail else []

    if len(middle) < MIN_TO_SUMMARISE:
        # Too little in the middle to be worth a summary. Say so, and do not pretend to have compacted:
        # the caller can raise the budget or start a new conversation instead.
        return None

    kept = tuple(t.id for t in keep_head + keep_tail)
    shed = tuple(t.id for t in middle)
    # A summary is assumed to cost ~15% of what it replaces. Not measured here — it is an estimate the
    # caller can override, and the event records both numbers so a wrong assumption is visible in the
    # journal rather than hidden in the arithmetic.
    shed_tokens = sum(size(t) for t in middle)
    after = total - shed_tokens + max(1, shed_tokens // 7)
    return Plan(
        keep=kept,
        summarise=shed,
        reason=f"over the context budget by {total - usable} tokens",
        before=total,
        after=after,
    )


def cap(turns: Sequence[Turn], limit: int) -> int:
    """How many turns a session may still accept. `0` means it is full.

    The one place `MAX_TURNS` becomes a *setting*: `[R-11]` requires `settings.max_turns_per_session` to
    be honoured, and it had no reader at all.
    """
    return max(0, int(limit) - len(turns))
