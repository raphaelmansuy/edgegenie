"""The supervisor: decides whether a turn is done, needs another pass, or is blocked.

Pure. It never calls a tool and never writes. The runner feeds it the transcript so far
and obeys the verdict. This is the rule that took our measured score from 19% to 94%,
so it lives in domain code with tests, not in a prompt.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .evidence import (
    Requirement,
    ToolCall,
    dedupe,
    gaps,
    is_constraint,
    limit_to,
    needs_evidence,
    parse_evidence_block,
    successful_call,
    verify,
)
from .evidence_map import derive
from .query_intent import query_goals


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
    query_target: str = ""


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

ACT_PROMPT = (
    "Your last turn ended with reasoning only: no tool was called and nothing was written. Planning is "
    "finished. Do not think about it again. Call the tool now (for a notebook: dbx_write_notebook with "
    "the full path and the cells), then continue."
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
            # A model that narrates "let's do that" and stops needs a different instruction than one
            # that stopped midway: repeating the same prompt got the same empty turn five times.
            return Decision(Verdict.CONTINUE, ACT_PROMPT if not calls else CONTINUE_PROMPT)
        return Decision(Verdict.BLOCKED, "the agent stopped without an answer", ("no final answer",))

    claimed = parse_evidence_block(answer)
    if state.query_target:
        # Prohibitions have no positive tool receipt. Do not turn an honored "do not run"
        # into a misleading unverified action in the SQL evidence panel.
        claimed = [r for r in claimed if not is_constraint(str(r.get("requirement", "")))]
    rows = limit_to(state.requirements, dedupe(verify(claimed, calls)))
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
    if state.query_target and not state.read_only:
        requested = " ".join(r.text for r in state.requirements)
        edit, run = query_goals(requested)
        receipts = [c for c in calls if successful_call(c) and (c.proof or {}).get("draftId") == state.query_target]
        updates = [c for c in receipts if c.name.endswith("dbx_update_query") and (c.proof or {}).get("action") == "updated"]
        runs = [c for c in receipts if c.name.endswith(("dbx_run_query", "dbx_query_run_status")) and (c.proof or {}).get("kind") == "sql-run"]
        if edit and updates:
            runs = [c for c in runs if c.proof["sourceHash"] == updates[-1].proof["sourceHash"]]
        missing_query = (["Update the attached SQL draft in the editor"] if edit and not updates else [])
        if run and not runs:
            missing_query.append("Observe successful execution of the same attached SQL source revision")
        if missing_query:
            return Decision(Verdict.AUDIT if state.audits < MAX_AUDITS else Verdict.BLOCKED,
                "Use dbx_read_query and dbx_update_query for the attached editor draft. For requested execution, "
                "use dbx_run_query and poll dbx_query_run_status for that same source hash. Generic SQL results "
                "or a code block do not prove an editor change. Never resubmit an unknown outcome.",
                tuple(missing_query), tuple(r.to_dict() for r in rows))
    if not missing or (state.read_only and not admits):
        return Decision(Verdict.DONE, evidence=tuple(r.to_dict() for r in rows))
    if not any(needs_evidence(r.text) for r in state.requirements):
        # Nothing here names work a tool could prove: the answer IS the deliverable.
        return Decision(Verdict.DONE, evidence=tuple(r.to_dict() for r in rows))

    # Before demanding another pass: does a COMPLETED call already prove a missing requirement?
    # The agent forgot the table, not the work ([F-17], [R-31]). A derived row fills a hole only —
    # it never overrides what the agent reported, and never applies when the agent admitted it could
    # not proceed (handled above).
    covered = {r.requirement for r in rows if r.verified}
    if not admits:
        found = derive(state.requirements, state.calls, already=covered)
        if found:
            filled = tuple(d.to_row() for d in found)
            remaining = [m for m in missing if m not in {d.requirement for d in found}]
            if not remaining:
                return Decision(Verdict.DONE,
                                evidence=tuple(r.to_dict() for r in rows) + filled)
            # Some gaps remain: report what was derived and keep the missing list honest.
            missing = remaining
            if state.audits < MAX_AUDITS:
                return Decision(Verdict.AUDIT, AUDIT_PROMPT, tuple(missing),
                                tuple(r.to_dict() for r in rows) + filled)

    if state.audits < MAX_AUDITS:
        return Decision(Verdict.AUDIT, AUDIT_PROMPT, tuple(missing), tuple(r.to_dict() for r in rows))
    return Decision(
        Verdict.BLOCKED,
        "requirements without verified evidence",
        tuple(missing),
        tuple(r.to_dict() for r in rows),
    )
