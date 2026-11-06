"""The supervisor: decides whether a turn is done, needs another pass, or is blocked.

Pure. It never calls a tool and never writes. The runner feeds it the transcript so far
and obeys the verdict. This is the rule that took our measured score from 19% to 94%,
so it lives in domain code with tests, not in a prompt.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .evidence import Requirement, ToolCall, dedupe, gaps, limit_to, parse_evidence_block, verify


class Verdict(str, Enum):
    CONTINUE = "continue"  # the agent stopped without saying anything useful
    AUDIT = "audit"  # it answered, but some requirement has no evidence
    DONE = "done"  # every requirement has a verified tool result
    BLOCKED = "blocked"  # out of attempts, or the agent says it cannot proceed


@dataclass(frozen=True, slots=True)
class State:
    requirements: list[Requirement]
    calls: list[ToolCall]
    answer: str
    continuations: int = 0
    audits: int = 0
    #: The user only asked about attached context: an answer is the deliverable, no tool needed.
    read_only: bool = False


@dataclass(frozen=True, slots=True)
class Decision:
    verdict: Verdict
    message: str = ""
    missing: tuple[str, ...] = ()
    evidence: tuple[dict, ...] = ()

    @property
    def finished(self) -> bool:
        return self.verdict in (Verdict.DONE, Verdict.BLOCKED)


MAX_CONTINUATIONS = 5
MAX_AUDITS = 2
AUDIT_PROMPT = (
    "Audit pass. Re-read the original task. For EACH requirement, name the tool call whose real result "
    "proves it. Describing or planning is not evidence: if a requirement has no tool-call evidence, do the "
    "work now with your tools, then check again. Finish with a section titled EVIDENCE containing a markdown "
    "table with the columns: requirement | tool | summary."
)
CONTINUE_PROMPT = (
    "You stopped without a final answer. Continue the task from where you left off: finish the remaining "
    "work, verify it by running a check, then write your final report."
)

_BLOCKED_CUES = (
    "cannot continue",
    "cannot proceed",
    "permission denied",
    "insufficient privileges",
    "not authorized",
    "unable to complete",
    "blocked by",
    "i cannot",
)


def decide(state: State) -> Decision:
    answer = state.answer.strip()
    calls = [c for c in state.calls if c.status != "running"]

    if not answer:
        if state.continuations < MAX_CONTINUATIONS:
            return Decision(Verdict.CONTINUE, CONTINUE_PROMPT)
        return Decision(Verdict.BLOCKED, "the agent stopped without an answer", ("no final answer",))

    rows = limit_to(state.requirements, dedupe(verify(parse_evidence_block(answer), calls)))
    missing = gaps(state.requirements, rows)
    lower = answer.lower()
    admits = any(cue in lower for cue in _BLOCKED_CUES)

    if admits and not rows:
        return Decision(
            Verdict.BLOCKED,
            "the agent reported that it cannot proceed",
            tuple(missing) or ("unknown",),
            tuple(r.to_dict() for r in rows),
        )
    if not missing or (state.read_only and not admits):
        return Decision(Verdict.DONE, evidence=tuple(r.to_dict() for r in rows))
    if state.audits < MAX_AUDITS:
        return Decision(Verdict.AUDIT, AUDIT_PROMPT, tuple(missing), tuple(r.to_dict() for r in rows))
    return Decision(
        Verdict.BLOCKED,
        "requirements without verified evidence",
        tuple(missing),
        tuple(r.to_dict() for r in rows),
    )
