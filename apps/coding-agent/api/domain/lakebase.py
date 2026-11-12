"""Lakebase rules, pure and total. No I/O, no async, no SDK.

Three things live here because they are *rules*, not plumbing:

* **object identity** — a project is `projects/{id}`, a branch is `projects/{p}/branches/{b}`, an
  endpoint is `…/endpoints/{e}`. One object, one key: two spellings of one project made two tabs for
  a notebook once (spec 003), and the same class of bug applies to a project (spec 013 [LB-5], [E-24]).
* **the autoscaling arithmetic** — `max − min ≤ 16`, `max ≤ 64`, `min ≥ 0.5`. The platform enforces
  these; a user who types `0.5 → 32` should learn why in the same turn, not from a 400
  (spec 013 [LB-4], [E-7]).
* **the state words** — what a project's state means to a person, and whether it is ready.

The tool server carries its own copy of the arithmetic (`_capacity_problem`) because it is a separate
process; `tests/test_fence_parity.py` and `tests/test_lakebase_domain.py` hold the two to one table.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: The platform's pattern for a project id, which also becomes the project id on create.
PROJECT_ID = re.compile(r"^[a-z][a-z0-9-]{1,62}$")
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")

MIN_CU = 0.5
MAX_CU = 64.0
MAX_SPREAD_CU = 16.0
#: Scale-to-zero needs a maximum at or below this (the platform's rule, in CU).
SCALE_TO_ZERO_MAX_CU = 32.0

READY_STATES = frozenset({"READY", "AVAILABLE", "ACTIVE"})

#: What a state word means to a person. A state not in this table is shown verbatim, because a
#: plausible paraphrase of an unknown state is worse than the platform's own word.
STATE_WORDS = {
    "READY": "ready",
    "AVAILABLE": "ready",
    "ACTIVE": "ready",
    "PROVISIONING": "starting",
    "STARTING": "starting",
    "SUSPENDED": "asleep",
    "IDLE": "asleep",
    "STOPPED": "stopped",
    "FAILED": "failed",
    "ERROR": "failed",
    "DELETING": "deleting",
    "DELETED": "deleted",
}


class LakebaseError(ValueError):
    """A malformed reference or a rule the platform would refuse. Maps to HTTP 422."""


def project_ref(name: str) -> str:
    """`pg_tickets` and `projects/pg_tickets` are one object."""
    n = (name or "").strip().strip("/")
    if not n:
        raise LakebaseError("a project is named by its id, for example 'pg_tickets'")
    return n if n.startswith("projects/") else f"projects/{n}"


def project_id(ref: str) -> str:
    """The short id, which is what a URL, a page title and a tool argument carry."""
    return project_ref(ref).rsplit("/", 1)[-1]


def branch_ref(project: str, branch: str = "production") -> str:
    """`production` -> `projects/{p}/branches/production`. A full path is passed through."""
    b = (branch or "production").strip().strip("/")
    if b.startswith("projects/"):
        return b
    return f"{project_ref(project)}/branches/{b}"


def branch_id(ref: str) -> str:
    """`projects/p/branches/agent-9` -> `agent-9`; `agent-9` -> `agent-9`."""
    parts = [p for p in (ref or "").split("/") if p]
    if "branches" in parts:
        at = parts.index("branches")
        if at + 1 < len(parts):
            return parts[at + 1]
    return parts[-1] if parts else ""


def endpoint_ref(project: str, branch: str = "production", endpoint: str = "primary") -> str:
    """The read-write compute of one branch. A credential is minted for this, never for a project."""
    return f"{branch_ref(project, branch)}/endpoints/{endpoint or 'primary'}"


def database_ref(project: str, branch: str, database: str = "databricks_postgres") -> str:
    return f"{branch_ref(project, branch)}/databases/{database or 'databricks_postgres'}"


def check_project_id(name: str) -> str | None:
    """Why this id would be refused, or None. Says what to change, not only that it is wrong."""
    if not PROJECT_ID.match(name or ""):
        return ("a project id is 2–63 lowercase letters, digits and hyphens, starting with a letter. "
                f"Got {name!r}; lowercase it and replace underscores with hyphens")
    return None


def check_identifier(value: str, what: str = "identifier") -> str | None:
    """An identifier that needs escaping is not an identifier (spec 013 [E-19])."""
    if not IDENTIFIER.match(value or ""):
        return (f"{what} must be letters, digits and underscores, starting with a letter or "
                f"underscore; got {value!r}")
    return None


@dataclass(frozen=True, slots=True)
class Range:
    """An autoscaling range, and whether it is legal."""

    min_cu: float
    max_cu: float
    scale_to_zero: bool = False

    @property
    def spread(self) -> float:
        return round(self.max_cu - self.min_cu, 2)

    @property
    def problem(self) -> str | None:
        """The first violated rule, as a sentence with the number in it."""
        if self.min_cu < MIN_CU:
            return f"the minimum is {MIN_CU} CU; got {self.min_cu}"
        if self.max_cu > MAX_CU:
            return f"the maximum is {MAX_CU} CU; got {self.max_cu}"
        if self.max_cu < self.min_cu:
            return f"the maximum ({self.max_cu}) is below the minimum ({self.min_cu})"
        if self.spread > MAX_SPREAD_CU:
            return (f"max − min must not exceed {MAX_SPREAD_CU:g} CU; "
                    f"{self.max_cu:g} − {self.min_cu:g} = {self.spread:g}. "
                    f"Choose a maximum of at most {self.min_cu + MAX_SPREAD_CU:g}")
        if self.scale_to_zero and self.max_cu > SCALE_TO_ZERO_MAX_CU:
            return (f"scale to zero needs a maximum of {SCALE_TO_ZERO_MAX_CU:g} CU or less; "
                    f"got {self.max_cu:g}")
        return None

    @property
    def valid(self) -> bool:
        return self.problem is None

    def describe(self) -> str:
        """What a page shows beside the range: the rule, evaluated. This is the string in S2."""
        return f"{self.min_cu:g} – {self.max_cu:g} CU   max − min = {self.spread:g}  {'✓' if self.valid else '✗'} (≤ {MAX_SPREAD_CU:g})"


def range_from(payload: dict) -> Range:
    """The range an endpoint reports, tolerating either the spec or the status shape."""
    spec = payload.get("spec") or {}
    status = payload.get("status") or {}
    lo = status.get("autoscaling_limit_min_cu", spec.get("autoscaling_limit_min_cu", MIN_CU))
    hi = status.get("autoscaling_limit_max_cu", spec.get("autoscaling_limit_max_cu", MIN_CU))
    return Range(float(lo or MIN_CU), float(hi or MIN_CU))


def state_word(state: str) -> str:
    """A state as a person reads it. An unknown state is returned verbatim, never guessed."""
    return STATE_WORDS.get((state or "").upper(), (state or "").lower())


def is_ready(state: str) -> bool:
    return (state or "").upper() in READY_STATES


def is_suspended(state: str) -> bool:
    """True when a connection will take a few seconds to wake the compute (spec 013 [RB-7])."""
    return (state or "").upper() in ("SUSPENDED", "IDLE", "STOPPED")
