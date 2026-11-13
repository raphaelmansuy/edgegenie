"""The scaffold's seven steps, computed from what actually happened.

A step is `done` only when a tool call **completed and returned the step's proof field**. A model's
sentence cannot promote a step, because this function never reads the model's prose: it reads the tool
calls the app observed (spec 013 [SCF-1], [P1]). That is the same principle as the evidence supervisor
(`domain/evidence.verify`), applied to infrastructure instead of requirements.

Pure and total: two lists in, one list out. No I/O, so it is tested with literals and cannot fail on a
malformed payload — an unrecognised field is simply not a proof.

The steps are defined in `web/src/domain/scaffold-steps.json`, which the TypeScript mirror
(`web/src/domain/scaffold.ts`) also reads. One rule, two runtimes (`[07 §2.1]`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable

STEPS_FILE = Path(__file__).resolve().parents[2] / "web" / "src" / "domain" / "scaffold-steps.json"


class StepState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class Step:
    key: str
    label: str
    detail: str
    tools: tuple[str, ...]
    proof: str
    alt_proof: tuple[str, ...] = ()
    why: str = ""


def load_steps(path: Path | None = None) -> tuple[Step, ...]:
    """The definition, read once per call. Small file, and a deploy may ship a changed one."""
    raw = json.loads((path or STEPS_FILE).read_text())
    return tuple(
        Step(key=s["key"], label=s["label"], detail=s["detail"], tools=tuple(s["tools"]),
             proof=s["proof"], alt_proof=tuple(s.get("alt_proof") or ()), why=s.get("why", ""))
        for s in raw["steps"]
    )


@dataclass(frozen=True, slots=True)
class Call:
    """One tool call as the app saw it. `result` is the reply text, which may be JSON."""

    name: str
    status: str = "completed"
    call_id: str = ""
    result: str = ""


@dataclass(frozen=True, slots=True)
class Outcome:
    key: str
    label: str
    detail: str
    state: StepState
    proof: str = ""
    tool: str = ""
    reason: str = ""

    def to_dict(self) -> dict:
        return {"key": self.key, "label": self.label, "detail": self.detail,
                "state": self.state.value, "proof": self.proof, "tool": self.tool,
                "reason": self.reason}


def _fields(result: str) -> dict:
    """The reply as a mapping, or {}. A tool reply is JSON when it came from `_trim`."""
    if not result:
        return {}
    try:
        data = json.loads(result)
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _proved(step: Step, call: Call) -> str:
    """The proof value this call supplies for this step, or "" when it supplies none.

    `done` requires the field to be PRESENT AND NOT EMPTY. `{"ok": true}` is not a proof of a table;
    `{"ok": true, "row_count": 12}` is, and so is `{"rows": [["12"]]}`.
    """
    if call.status != "completed" or call.name not in step.tools:
        return ""
    data = _fields(call.result)
    if not data or data.get("error"):
        return ""
    for field in (step.proof, *step.alt_proof):
        value = data.get(field)
        if value is None or value == "" or value == [] or value == {}:
            continue
        if field == "rows":                      # a SQL read returns columns/rows, not a count
            rows = data.get("rows")
            if isinstance(rows, list) and rows and isinstance(rows[0], list):
                return str(rows[0][0])
            continue
        if field == "resources":
            names = [r.get("name") if isinstance(r, dict) else str(r) for r in value] \
                if isinstance(value, list) else [str(value)]
            postgres = [n for n in names if n == "postgres"]
            if not postgres:
                return ""
            return ", ".join(postgres)
        if field == "deploy_http_status":
            code = int(value) if str(value).isdigit() else 0
            return str(code) if 200 <= code < 300 else ""
        if field == "status":
            code = int(value) if str(value).isdigit() else 0
            return str(code) if 200 <= code < 300 else ""
        return str(value)[:120]
    return ""


def compute(steps: Iterable[Step], calls: Iterable[Call]) -> list[Outcome]:
    """One outcome per step, in order.

    `O(c + s)`: the calls are grouped once, then each step reads its own group. The first draft scored
    every step against every call, which is `O(s · c)` per *render tick* — the mistake spec 012 found
    in the evidence-heading scan ([06 §6.4]).

    Precedence, stated because it is a judgement and not an accident:

    * `done` wins. A step whose call completed and returned its proof HAPPENED, and hiding it because
      an earlier step blocked would be a lie in the other direction. It carries a reason saying it ran
      after a block, so the plan cannot read as a tidy chain over a broken one.
    * a `blocked` step stops every LATER step: they become `pending` with a reason naming the blocker
      ([SCF-2], [E-8]). Creating an app over a missing table is not a partial success.
    """
    ordered = list(steps)
    by_name: dict[str, list[Call]] = {}
    for call in calls:
        by_name.setdefault(call.name, []).append(call)

    out: list[Outcome] = []
    blocker = ""
    for step in ordered:
        mine = [c for name in step.tools for c in by_name.get(name, ())]

        proof, tool = "", ""
        for call in mine:
            found = _proved(step, call)
            if found:
                proof, tool = found, call.name      # the latest proof wins ([E-10])

        reason = ""
        if proof:
            state = StepState.DONE
            if blocker:
                reason = f"ran after '{blocker}' was blocked"
        elif blocker:
            state = StepState.PENDING
            reason = f"not attempted: '{blocker}' is blocked"
        elif any(c.status == "error" for c in mine):
            state = StepState.BLOCKED
            blocker = step.key
            bad = next(c for c in mine if c.status == "error")
            reason = (_fields(bad.result).get("error")
                      or _fields(bad.result).get("platform_error")
                      or "the call failed")
        elif any(c.status == "running" for c in mine):
            state = StepState.RUNNING
        else:
            state = StepState.PENDING

        out.append(Outcome(step.key, step.label, step.detail, state, proof, tool, reason))
    return out


def progress(outcomes: Iterable[Outcome]) -> dict:
    """A one-line summary, for the dock's plan header: `4 of 7 proven`."""
    rows = list(outcomes)
    return {"done": sum(1 for o in rows if o.state is StepState.DONE), "total": len(rows)}
