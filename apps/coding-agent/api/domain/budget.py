"""Whether a turn may spend. One pure decision, made BEFORE the model is called. `[R-24]`, `[C33]`.

The gap this closes. Genie Code's budgets are a ceiling it says are not a cap — *"Do not use this feature
as a way to ensure an absolute spend cap on final billed amounts"* (`docs/en/genie/budgets`). This product
had the opposite problem: no ceiling at all, only a lever (13 models) and a report. Meanwhile
`llm.llm_turn_model` already records exactly what each turn cost, so a real cap was one pure function
away.

**The rule, and the word that matters.** A turn that *would* cross the budget is **blocked before it
calls the model**, with the number and the limit in the message. A turn that is already running is
allowed to finish: stopping mid-answer loses work and the cost is already spent. That is why `[R-24]`
says "before a turn is claimed" and not "during".

**Why the usage is summed and not re-counted.** `SESSION_BUDGET` accrues from the turn pins, which are
written before each prompt. Re-summing the whole history on every check would be a full scan per turn; a
maintained counter is O(1) and the pins remain the audit trail.

**Cost is never guessed.** Tokens are the unit, because a token count is a fact the pin records and a
dollar figure depends on a price list this app does not own. A UI that shows "$0.41" for a model whose
price it invented is worse than one that shows tokens.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Verdict(str, Enum):
    ALLOW = "allow"
    #: This turn would cross the ceiling. Blocked BEFORE a model call.
    BLOCKED = "blocked"
    #: No ceiling configured. Not a refusal: most sessions have none.
    UNLIMITED = "unlimited"


@dataclass(frozen=True, slots=True)
class Usage:
    """What a conversation has spent. Tokens, which the turn pins record exactly."""

    input: int = 0
    output: int = 0
    cached: int = 0
    turns: int = 0

    @property
    def total(self) -> int:
        """Input plus output. `cached` is a subset of input, so it is reported but not added: counting it
        twice would make a cached conversation look more expensive than an uncached one."""
        return max(0, self.input) + max(0, self.output)


@dataclass(frozen=True, slots=True)
class Decision:
    verdict: Verdict
    used: int = 0
    limit: int = 0
    message: str = ""

    @property
    def allowed(self) -> bool:
        return self.verdict is not Verdict.BLOCKED

    @property
    def fraction(self) -> float:
        """How much of the ceiling is spent, for a bar. `0` when there is no ceiling."""
        if self.limit <= 0:
            return 0.0
        return min(1.0, max(0.0, self.used / self.limit))


def decide(usage: Usage, *, limit: int, reserve: int = 0) -> Decision:
    """May this turn start?

    `limit <= 0` means unlimited, which is the default and is not a failure: a session without a budget
    behaves exactly as it did before this module existed. `reserve` is the estimated cost of the turn
    about to run, so the check is *"would this cross?"* rather than *"has it already?"* — the difference
    between a cap and a warning.
    """
    used = usage.total
    if limit <= 0:
        return Decision(Verdict.UNLIMITED, used=used, limit=0)
    if used + max(0, reserve) > limit:
        return Decision(
            Verdict.BLOCKED, used=used, limit=limit,
            message=(f"this conversation has used {used:,} of its {limit:,} token budget"
                     + (f", and this turn is estimated at {reserve:,}" if reserve else "")
                     + ". Start a new conversation, or raise the budget in settings."),
        )
    return Decision(Verdict.ALLOW, used=used, limit=limit)


def sentence(d: Decision) -> str:
    """The one line the inspector shows. Empty when there is no ceiling, because "unlimited" is noise."""
    if d.verdict is Verdict.UNLIMITED:
        return ""
    pct = round(d.fraction * 100)
    return f"{d.used:,} of {d.limit:,} tokens used ({pct}%)"
