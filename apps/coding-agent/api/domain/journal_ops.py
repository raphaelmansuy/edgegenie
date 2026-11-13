"""Forking a conversation, and searching inside one. Pure. `[R-15]`, `[R-16]`.

Two features that look unrelated and share one fact: **the journal is an ordered, addressable log**, so both
are cheap here and expensive anywhere else.

**`[R-16]` fork.** Genie Code branches a chat and edits an earlier message to regenerate from that point.
Here a fork is a copy of a **prefix** of an append-only log: the events up to one turn's completion, into a
new session with its own id and its own fence. No re-execution, no model call, no re-derivation — the
history already exists and only needs a new key.

The rule that decides the shape: a fork **keeps what happened**, including a `blocked` turn and its
evidence gap. A "clean" fork would be a rewrite of the past, and a user branching to try a different ending
still needs to see the ending they had.

**`[R-15]` search.** The rail searches `title + folder` (`[G-2]`); the journal holds every word the agent
and the user said. A search is a query over committed events, and the result names the **turn**, because
"find the conversation" is half an answer — the user wants the moment.

Both are here, and not in a router, for the same reason every other rule is: a decision that can be
asserted without a database gets asserted without one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: How many events a search returns before it says there are more. A search that silently stops is the
#: defect `[R-3]` fixed for tool results.
MAX_HITS = 50
#: Characters of context on each side of a match.
CONTEXT = 90


@dataclass(frozen=True, slots=True)
class Event:
    """One committed event, as search and fork need it. Not the domain `Event`: this must not import it."""

    seq: int
    type: str
    turn_id: str = ""
    text: str = ""


@dataclass(frozen=True, slots=True)
class Hit:
    session_id: str
    turn_id: str
    seq: int
    snippet: str
    #: The event type, so a result can say whether it was the question or the answer.
    kind: str


# -- [R-16] fork ---------------------------------------------------------------------------------
#: The event that closes a turn. A fork may only be cut at one of these: cutting mid-turn would copy a
#: conversation that never reached a conclusion, and the new session would open with a spinner forever.
_TURN_END = frozenset({"turn.completed", "turn.blocked", "turn.cancelled", "turn.interrupted",
                       "turn.failed"})


def fork_point(events: list[Event], turn_id: str) -> int | None:
    """The `seq` a fork at `turn_id` includes, or None when that turn never finished.

    The LAST terminal event for that turn, so a turn that was audited (and emitted several terminal-ish
    events) forks at its real end.
    """
    seqs = [e.seq for e in events if e.turn_id == turn_id and e.type in _TURN_END]
    return max(seqs) if seqs else None


def fork_prefix(events: list[Event], *, turn_id: str) -> list[Event] | None:
    """The events a fork keeps: everything up to and including that turn's end. None when uncuttable."""
    upto = fork_point(events, turn_id)
    if upto is None:
        return None
    return [e for e in events if e.seq <= upto]


def can_fork(events: list[Event], turn_id: str) -> bool:
    return fork_point(events, turn_id) is not None


# -- [R-15] search -------------------------------------------------------------------------------
_WORD = re.compile(r"[a-z0-9_]{2,}")


def _snippet(text: str, at: int, length: int) -> str:
    start = max(0, at - CONTEXT)
    end = min(len(text), at + length + CONTEXT)
    body = " ".join(text[start:end].split())
    return ("…" if start else "") + body + ("…" if end < len(text) else "")


def search(
    events: list[Event],
    query: str,
    *,
    session_id: str,
    limit: int = MAX_HITS,
) -> tuple[list[Hit], bool]:
    """Matching events, newest first, plus whether there were more.

    Every word must appear — an AND, not an OR, because `gold late` should not return every conversation
    that mentions gold. Matching is case-insensitive and over the STORED text, which means a redacted
    secret cannot be found ([E-19]): the redaction happened before the commit, and a search that could
    undo it would undo the reason it exists.
    """
    words = [w.lower() for w in query.split() if w.strip()]
    if not words:
        return [], False
    out: list[Hit] = []
    for e in events:
        hay = (e.text or "").lower()
        if not hay:
            continue
        if not all(w in hay for w in words):
            continue
        at = hay.find(words[0])
        out.append(Hit(session_id, e.turn_id, e.seq, _snippet(e.text, max(0, at), len(words[0])),
                       e.type.split(".")[0]))
    out.sort(key=lambda h: h.seq, reverse=True)
    more = len(out) > limit
    return out[:limit], more


def rank(hits: list[Hit], *, prefer_turns: set[str] | None = None) -> list[Hit]:
    """Order results the way a person remembers them: a turn they can name first, then the newest.

    `prefer_turns` is the set of turns in conversations the user opened recently, which the caller knows
    and this module does not. Empty means "no preference", and the order is unchanged.
    """
    if not prefer_turns:
        return hits
    return sorted(hits, key=lambda h: (h.turn_id not in prefer_turns, -h.seq))
