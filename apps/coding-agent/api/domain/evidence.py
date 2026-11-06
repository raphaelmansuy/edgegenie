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


def extract_requirements(prompt: str) -> list[Requirement]:
    """Split a user prompt into requirements: numbered/bulleted lines, else sentences of substance."""
    prompt = DEMO_MARKER.sub(" ", prompt).strip()
    found = [Requirement(m.group(1).strip()) for m in REQUIREMENT_RE.finditer(prompt)]
    if found:
        return found
    parts = [p.strip() for p in re.split(r"(?<=[.?!])\s+|\n+", prompt) if len(p.strip()) >= 12]
    return [Requirement(p) for p in parts[:6]]


def parse_evidence_block(text: str) -> list[dict]:
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
            tool = cells[1].split()[0] if cells[1] else ""
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
                (c for c in candidates if c.status == "completed"), candidates[0] if candidates else None
            )
        rows.append(
            EvidenceRow(
                requirement=str(claim.get("requirement") or claim.get("text") or "")[:200],
                tool_call_id=match.call_id if match else cid or "",
                tool_name=match.name if match else tool,
                result_summary=str(claim.get("summary") or (match.summary if match else ""))[:300],
                verified=bool(match and match.status == "completed"),
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
            and (words & set(re.findall(r"[a-z0-9_]{4,}", (r.requirement + " " + r.tool_name).lower())))
            for r in rows
        )
        if not covered:
            out.append(req.text[:120])
    return out
