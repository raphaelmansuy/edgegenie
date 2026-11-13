"""Pure rules: does a turn's evidence actually exist?

No I/O. Given the requirements the agent claims and the tool calls it really made,
decide which claims are verified. A citation to a call that never happened is the
failure mode we care most about, so it is an explicit verdict, not a warning.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

REQUIREMENT_RE = re.compile(r"^\s*(?:\d+[.)]|[-*])\s+(.{4,160})$", re.M)
# A demo-mode hint, not part of what the user asked for. Stripped before anything is derived.
DEMO_MARKER = re.compile(r"\s*\[\[scenario:\w+\]\]\s*", re.I)


@dataclass(frozen=True, slots=True)
class Requirement:
    text: str


@dataclass(frozen=True, slots=True)
class ToolCall:
    call_id: str
    name: str
    status: str = "running"
    summary: str = ""
    proof: dict | None = None


def successful_call(call: ToolCall, requirement: str = "") -> bool:
    if call.status != "completed":
        return False
    if call.name.endswith(("dbx_run_query", "dbx_query_run_status")):
        p = call.proof or {}
        if not _valid_receipt(p) or p.get("kind") != "sql-run":
            return False
        if re.search(r"\b(cancel|stop)\b", requirement, re.I):
            return p.get("state") == "canceled" or (p.get("cancelRequested") is True and p.get("state") in {"succeeded", "failed"})
        if re.search(r"\b(status|state)\b", requirement, re.I) and not re.search(r"\b(run|execute)\b", requirement, re.I):
            return p.get("state") in {"pending", "running", "succeeded", "failed", "canceled", "cancel_requested", "submission_unknown", "outcome_unknown"}
        return (_valid_receipt(p) and p.get("kind") == "sql-run" and p.get("state") == "succeeded"
                and p.get("resultAvailable") is True and bool(p.get("statementId")))
    if call.name.endswith(("dbx_read_query", "dbx_update_query")):
        p = call.proof or {}
        action = "updated" if call.name.endswith("dbx_update_query") else "read"
        return (_valid_receipt(p) and p.get("kind") == "sql-query" and p.get("action") == action
                and isinstance(p.get("version"), int) and p["version"] > 0)
    # Legacy synchronous SQL reports PENDING/FAILED as a completed RPC. Those are not execution proof.
    return not (call.name.endswith("dbx_run_sql") and re.search(r'"(?:state|error)"\s*:', call.summary))


def _valid_receipt(proof: dict) -> bool:
    from uuid import UUID

    try:
        UUID(proof.get("draftId", ""))
    except (ValueError, AttributeError, TypeError):
        return False
    return bool(re.fullmatch(r"[0-9a-f]{64}", str(proof.get("sourceHash", ""))))


def receipt_summary(call: ToolCall) -> str:
    p = call.proof or {}
    if p.get("kind") == "sql-query":
        return f"SQL draft {p.get('action')}; version {p.get('version')}; source {p.get('sourceHash')}"
    if p.get("kind") == "sql-run":
        return f"SQL {p.get('state')}; run {p.get('runId')}; source {p.get('sourceHash')}; preview rows {p.get('rowCount', 'unavailable')}"
    return call.summary


@dataclass(frozen=True, slots=True)
class EvidenceRow:
    requirement: str
    tool_call_id: str
    tool_name: str
    result_summary: str
    verified: bool

    def to_dict(self) -> dict:
        return {
            "requirement": self.requirement,
            "toolCallId": self.tool_call_id,
            "tool": self.tool_name,
            "summary": self.result_summary,
            "verified": self.verified,
        }


# A sentence that restricts the work is not itself work to prove: "Do not change anything." has no
# tool call that could evidence it, and treating it as a requirement blocks every read-only request.
CONSTRAINT_RE = re.compile(
    r"^\s*(?:please\s+)?(?:make\s+no\b|do\s+not|don'?t|never|without|avoid|leave\b|keep\b.*\b(?:untouched|unchanged|as is)|"
    r"no\s+(?:changes|writes|edits)|only\b|make\s+sure\s+(?:not|nothing)|it\s+must\s+not)",
    re.I,
)
# Verbs that ask for an explanation of something already in front of the agent.
INFORMATIONAL_RE = re.compile(
    r"^\s*(?:please\s+)?(?:explain|summari[sz]e|describe|walk\s+(?:me\s+)?through|tell\s+me|what|why|how|"
    r"which|who|when|where)\b",
    re.I,
)


# A sentence that asks to explain AND to do something is not read-only.
CHANGE_RE = re.compile(
    r"\b(?:write|create|build|make|fix|run|add|update|delete|drop|rename|schedule|deploy|optimi[sz]e|modify|"
    r"insert|save|generate|rewrite|refactor|then)\b",
    re.I,
)


#: A verb that names something a tool could prove.
#:
#: The list is deliberately generous, because the cost of the two mistakes is not symmetric: a verb
#: that is MISSING makes a real request count as conversation, so the turn completes with no evidence
#: at all — the one failure the product claims does not happen. A verb that is present but does not
#: apply costs one audit pass that finds nothing, which the supervisor then reports honestly.
#:
#: Measured gap this closed: `migrate`, `convert`, `export`, `upload` and `move` were absent, so
#: "migrate the SQL dialects" was classified as conversation and finished `DONE` with zero tool calls.
ACTION_RE = re.compile(
    r"\b(?:write|create|build|make|fix|run|execute|add|remove|update|delete|drop|rename|schedule|deploy|"
    r"optimi[sz]e|modify|insert|save|generate|rewrite|refactor|replace|edit|document|profile|query|select|join|aggregate|"
    r"plot|chart|list|find|search|check|verify|describe|explain|summari[sz]e|investigate|compare|compute|"
    r"count|calculate|show|tell|why|how many|what|which|"
    # The verbs that move data or code somewhere. Each one names work a tool does.
    r"migrate|convert|export|import|upload|download|move|copy|clone|restore|backfill|refresh|truncate|"
    r"grant|revoke|comment|catalog|partition|vacuum|analyze|sample|validate|test|assert|"
    r"install|configure|connect|attach|detach|publish|release|rollback|revert|sync)\b",
    re.I,
)


def needs_evidence(text: str) -> bool:
    """Whether a requirement names something a tool call can prove.

    Anything else is conversation: a request to remember, acknowledge, or comment. It is answered,
    not evidenced, and treating it as a requirement blocked perfectly good turns.
    """
    return bool(ACTION_RE.search(text))


def is_constraint(text: str) -> bool:
    return bool(CONSTRAINT_RE.match(text))


def extract_requirements(prompt: str) -> list[Requirement]:
    """Split a user prompt into requirements: numbered/bulleted lines, else sentences of substance.

    Constraints ("do not change anything") are not requirements: nothing could prove them.
    """
    prompt = DEMO_MARKER.sub(" ", prompt).strip()
    found = [Requirement(m.group(1).strip()) for m in REQUIREMENT_RE.finditer(prompt)]
    if found:
        return [r for r in found if not is_constraint(r.text)]
    parts = [p.strip() for p in re.split(r"(?<=[.?!])\s+|\n+", prompt) if len(p.strip()) >= 12]
    return [Requirement(p) for p in parts[:6] if not is_constraint(p)]


# The user said, in words, that no tool or code is wanted. "Just explain", "no tools", "don't run any
# code", "without using tools". Honouring it is not a style choice: Genie Code documents the same escape
# hatch, and an audit pass that runs SQL after "answer without using tools" breaks the instruction.
NO_TOOLS_RE = re.compile(
    r"\b(?:without\s+(?:(?:using|calling|running|any|the)\s+)*(?:tools?|code|queries|sql)\b"
    r"|(?:do\s+not|don'?t|no\s+need\s+to|never)\s+(?:use|call|run|execute)\s+(?:any\s+|the\s+|your\s+)?(?:tools?|code|queries|sql)\b"
    r"|no\s+tools?\b"
    r"|just\s+(?:explain|tell\s+me|answer|describe|say)\b)",
    re.I,
)


def says_no_tools(prompt: str) -> bool:
    """True when the user explicitly asked to be answered without tools or code."""
    clean = DEMO_MARKER.sub(" ", prompt)
    matches = list(NO_TOOLS_RE.finditer(clean))
    if not matches:
        return False
    if any(re.search(r"\btools?\b", m.group(), re.I) for m in matches):
        return True
    # "Do not run code or SQL" restricts execution, not a requested source edit. It must not
    # turn an unperformed edit into an informational answer exempt from the proof floor.
    positive = NO_TOOLS_RE.sub(" ", clean)
    if any(
        CHANGE_RE.search(r.text) and not INFORMATIONAL_RE.match(r.text)
        for r in extract_requirements(positive)
    ):
        return False
    return True


def is_read_only(requirements: list[Requirement], has_context: bool) -> bool:
    """True when the user asked only to be told about context they attached.

    Without context the agent has to look things up, so an explanation is a claim that needs
    evidence like any other. With context, the evidence is the attachment itself.
    """
    return (
        has_context
        and bool(requirements)
        and all(INFORMATIONAL_RE.match(r.text) and not CHANGE_RE.search(r.text) for r in requirements)
    )


def parse_evidence_block(text: str, *, full_citations: bool = False) -> list[dict]:
    """The agent is asked to end with an EVIDENCE table. Parse leniently: JSON first, then rows."""
    rows: list[dict] = []
    for block in re.findall(r"```(?:json)?\s*(\[\s*\{.*?\}\s*\])\s*```", text, re.S):
        try:
            data = json.loads(block)
            if isinstance(data, list):
                rows += [r for r in data if isinstance(r, dict)]
        except json.JSONDecodeError:
            pass
    if rows:
        return rows
    # markdown table: | requirement | tool | ... |
    for line in text.splitlines():
        if not line.strip().startswith("|") or "---" in line:
            continue
        cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and cells[0].lower() not in ("requirement", "#"):
            tool = cells[1] if full_citations else cells[1].split()[0] if cells[1] else ""
            rows.append(
                {"requirement": cells[0], "tool": tool, "summary": cells[2] if len(cells) > 2 else ""}
            )
    return rows


def verify(claimed: list[dict], calls: list[ToolCall]) -> list[EvidenceRow]:
    """A claim counts only if a real, completed call of that name exists (or it names the call id)."""
    by_name: dict[str, list[ToolCall]] = {}
    by_id = {}
    for c in calls:
        by_name.setdefault(c.name, []).append(c)
        by_id[c.call_id] = c
    rows: list[EvidenceRow] = []
    for claim in claimed:
        tool = (claim.get("tool") or claim.get("toolName") or "").strip()
        cid = (claim.get("callId") or claim.get("toolCallId") or "").strip()
        match: ToolCall | None = by_id.get(cid) if cid else None
        if match is None and tool:
            candidates = by_name.get(tool, [])
            if not candidates:  # tolerate the agent dropping a server prefix
                candidates = [c for name, cs in by_name.items() if name.endswith(tool) for c in cs]
            match = next(
                (c for c in candidates if successful_call(c, str(claim.get("requirement", "")))), candidates[0] if candidates else None
            )
        # Submission and terminal observation are different calls for the SAME native run.
        # Cite its actual terminal observation instead of leaving a proven run marked unverified
        # because the model named the earlier PENDING submission in its evidence table.
        requirement = str(claim.get("requirement", ""))
        if match and (match.proof or {}).get("kind") == "sql-run" and not successful_call(match, requirement):
            p = match.proof
            terminal = next((c for c in reversed(calls) if c.name.endswith(("dbx_run_query", "dbx_query_run_status"))
                            and (c.proof or {}).get("runId") == p.get("runId")
                            and p.get("runId") and all((c.proof or {}).get(k) == p.get(k) for k in ("draftId", "sourceHash"))
                            and (not p.get("statementId") or (c.proof or {}).get("statementId") == p["statementId"])
                            and successful_call(c, requirement)), None)
            if terminal:
                match = terminal
        rows.append(
            EvidenceRow(
                requirement=str(claim.get("requirement") or claim.get("text") or "")[:200],
                tool_call_id=match.call_id if match else cid or "",
                tool_name=match.name if match else tool,
                result_summary=(receipt_summary(match) if match and match.proof else str(claim.get("summary") or (match.summary if match else "")))[:300],
                verified=bool(match and successful_call(match, str(claim.get("requirement", "")))),
            )
        )
    return rows


def dedupe(rows: list[EvidenceRow]) -> list[EvidenceRow]:
    """One row per requirement. The agent often reports the same evidence on every audit pass."""
    seen: dict[str, EvidenceRow] = {}
    for r in rows:
        key = (r.requirement or r.tool_name).strip().lower()
        if key not in seen or (r.verified and not seen[key].verified):
            seen[key] = r
    return list(seen.values())


def _tokens(text: str) -> set[str]:
    import re as _re

    return set(_re.findall(r"[a-z0-9_]{4,}", text.lower()))


def limit_to(requirements: list[Requirement], rows: list[EvidenceRow]) -> list[EvidenceRow]:
    """Order rows by requirement, keep every distinct proven row, drop unrelated ones.

    Matching scores the overlap and prefers the best fit, so "write the notebook" and
    "run the notebook" pick different rows instead of both matching "notebook".
    """
    if not requirements:
        return rows[:6]
    out: list[EvidenceRow] = []
    used: set[int] = set()
    for req in requirements:
        words = _tokens(req.text)
        best, best_score = -1, 0
        for i, r in enumerate(rows):
            if i in used:
                continue
            score = len(words & _tokens(r.requirement + " " + r.tool_name))
            if score > best_score:
                best, best_score = i, score
        if best >= 0:
            out.append(rows[best])
            used.add(best)
    out += [r for i, r in enumerate(rows) if i not in used and r.verified]
    return out[: max(len(requirements), 1) + 2]


def gaps(requirements: list[Requirement], rows: list[EvidenceRow]) -> list[str]:
    """Requirements with no verified evidence. Matching is deliberately forgiving on wording."""
    if not requirements:
        return [] if any(r.verified for r in rows) else ["no evidence at all"]
    out = []
    for req in requirements:
        words = {w for w in re.findall(r"[a-z0-9_]{4,}", req.text.lower())}
        covered = any(
            r.verified
            and (
                req.text.strip().casefold() == r.requirement.strip().casefold()
                or words & set(re.findall(r"[a-z0-9_]{4,}", (r.requirement + " " + r.tool_name).lower()))
            )
            for r in rows
        )
        if not covered:
            out.append(req.text[:120])
    return out
