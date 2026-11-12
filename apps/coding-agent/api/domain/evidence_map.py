"""Which completed tool call proves which kind of requirement. A closed table, pure.

The defect this closes. `supervisor.decide` matched claims to calls through the **agent's own** EVIDENCE
table. If the agent completed `dbx_write_notebook` and `dbx_run_notebook` and then wrote a correct prose
answer *without* appending the table, `parse_evidence_block` returned nothing, every requirement became a
gap, and after two audit passes the turn ended **`blocked`** — with both completed calls in the
transcript. Measured.

That is a false negative in the one place this product claims to be better than its competitors: *"done
means proven"* punished a compliant agent for forgetting a formatting step.

**The rule, and its limits.**

  * A row may be **added** here only from a call whose status is `completed`. An incomplete call proves
    nothing, and the negative test asserts that.
  * The mapping is **closed**: a tool not in the table proves nothing. A generous mapping (any call
    proves anything) would defeat the supervisor.
  * A derived row is **weaker than a reported one**: it says "this call exists", not "this call proves
    this exact sentence". So it is used only to fill a *missing* requirement, never to override a
    reported row, and never when the agent said it could not proceed.
  * **`[E-6]` stays open on purpose.** A real call with a *fabricated summary* still passes verification,
    because checking that needs a diff of the tool's own result against the claim — and getting that
    wrong produces false `blocked` turns, which is this same failure inverted. Recorded, not fixed.

`[R-31]`, `[F-17]`. See specs/001-opengenie-assessment 07 §5.2.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Requirement verbs → the tool families that can prove them. Ordered: the first match wins, so a
#: specific mapping (`notebook` + `write`) beats a general one.
#:
#: Each entry is (requirement pattern, tool pattern, the class of work it proves). The class is what the
#: evidence row reports, so a derived row is honest about being derived.
_MAP: tuple[tuple[re.Pattern[str], re.Pattern[str], str], ...] = (
    # writing or creating something
    (re.compile(r"\b(write|create|build|make|rewrite|refactor|save|generate|add)\b", re.I),
     re.compile(r"(write_notebook|write_file|create_job|create_pipeline|create_app|lakebase_create)$"),
     "wrote"),
    # running or executing something
    (re.compile(r"\b(run|execute|trigger|start|schedule|deploy)\b", re.I),
     re.compile(r"(run_sql|run_notebook|run_job|start_pipeline|job_run_status|lakebase_sql)$"),
     "ran"),
    # checking or verifying
    (re.compile(r"\b(check|verify|confirm|describe|inspect|profile)\b", re.I),
     re.compile(r"(describe_table|list_tables|sample_rows|grep_notebook|read_notebook|job_failure_context)$"),
     "checked"),
    # querying or aggregating
    (re.compile(r"\b(query|select|join|aggregate|count|calculate|compute|investigate|find|search)\b", re.I),
     re.compile(r"(run_sql|search_tables|list_tables|sample_rows|table_lineage|lakebase_sql)$"),
     "queried"),
)


@dataclass(frozen=True, slots=True)
class Derived:
    """A requirement a completed call can prove without the agent having tabulated it."""

    requirement: str
    tool_name: str
    call_id: str
    summary: str
    work: str  # "wrote" | "ran" | "checked" | "queried"

    def to_row(self) -> dict:
        """The evidence row, in the same shape `verify()` produces, so callers cannot tell them apart
        by accident — and `derived: true` says so on purpose."""
        return {
            "requirement": self.requirement,
            "toolCallId": self.call_id,
            "tool": self.tool_name,
            "summary": self.summary,
            "verified": True,
            "derived": True,
        }


def _tool_matches(requirement: str, tool: str) -> str | None:
    """The work class this tool proves for this requirement, or None. Closed: no entry, no proof."""
    for req_re, tool_re, work in _MAP:
        if req_re.search(requirement) and tool_re.search(tool):
            return work
    return None


def derive(requirements, calls, *, already: set[str]) -> list[Derived]:
    """Rows for requirements no reported row covers, using completed calls only.

    `already` is the set of requirement texts that a reported row already covers. Those are skipped:
    a derived row may fill a hole, never stand in for the agent's own account.
    """
    out: list[Derived] = []
    used: set[str] = set()
    for req in requirements:
        text = req.text
        if text in already:
            continue
        for call in calls:
            if call.call_id in used or call.status != "completed":
                continue
            work = _tool_matches(text, call.name)
            if work is None:
                continue
            out.append(Derived(text, call.name, call.call_id, call.summary or "", work))
            used.add(call.call_id)
            break
    return out
