"""What a session may change. Three modes, one total decision. Pure. `[R-9]`, `[F-8]`.

The defect this closes. `NBMCP_ALLOW_WRITES=1` was a **constant** set by the registry for every session,
so the tool server's own docstring — *"every mutating tool is behind `NBMCP_ALLOW_WRITES=1` … this mirrors
Genie Code's approval modes but is enforced by the server"* — described a mode the product never used.
A SQL write inside the schema executed with no human gate, and there was no way to ask for a read-only
conversation at all.

**Three modes, and what each does with a fence verdict** (`scope.check_sql`/`check_path` answer *"is the
target inside the fence"*; this module answers *"what does this mode do about that"*):

    read-only   every mutating tool refused, with the reason
    fenced      inside the fence executes; outside needs a human   (today's intent, and the default)
    ask         any write needs a human, one prompt per object

**Why the two concerns are separate.** A mode is a *policy chosen by a person*; placement inside the
fence is a *fact about a target*. Merging them is how `ASK` and `DENY` became one word, and why the fence
could not say which one it meant. `permits()` is the only place they meet, and it is total over the grid.

The tool server receives the mode as a string and applies the same rule through `_scope_unset` +
`NBMCP_WRITE_MODE`; `tests/test_write_mode.py` holds both sides to one table.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal


class WriteMode(str, Enum):
    READ_ONLY = "read-only"
    FENCED = "fenced"
    ASK = "ask"

    @property
    def mutates(self) -> bool:
        """Whether any write may happen at all. `read-only` never does."""
        return self is not WriteMode.READ_ONLY

    @property
    def label(self) -> str:
        return {
            WriteMode.READ_ONLY: "Read only",
            WriteMode.FENCED: "Fenced",
            WriteMode.ASK: "Ask me",
        }[self]

    @property
    def sentence(self) -> str:
        """What the UI says. One sentence per mode, so two screens cannot describe it differently."""
        return {
            WriteMode.READ_ONLY: "The agent may read. Every change is refused.",
            WriteMode.FENCED: "The agent may change things inside your folder and schema. Anything else asks you first.",
            WriteMode.ASK: "Every change waits for your approval.",
        }[self]


DEFAULT = WriteMode.FENCED

_ALIASES = {
    "read_only": WriteMode.READ_ONLY, "readonly": WriteMode.READ_ONLY,
    "read-only": WriteMode.READ_ONLY, "ro": WriteMode.READ_ONLY,
    "fenced": WriteMode.FENCED, "default": WriteMode.FENCED, "": WriteMode.FENCED,
    "ask": WriteMode.ASK, "approve": WriteMode.ASK, "approval": WriteMode.ASK,
}


def parse(value: str | None) -> WriteMode:
    """A mode from anything a caller may send. Unknown text falls back to the DEFAULT, never to a wider
    mode: a typo must not grant writes."""
    return _ALIASES.get((value or "").strip().lower(), DEFAULT)


@dataclass(frozen=True, slots=True)
class Permit:
    """What happens to one call, and the words for a refusal."""

    outcome: Literal["allow", "ask", "refuse"]
    reason: str = ""

    @property
    def allowed(self) -> bool:
        return self.outcome == "allow"


#: The grid: (mode, is the target inside the fence) -> outcome. One table, so a test walks it and a new
#: mode is a new row rather than a new `if`.
_GRID: dict[tuple[WriteMode, bool], str] = {
    (WriteMode.READ_ONLY, True): "refuse",
    (WriteMode.READ_ONLY, False): "refuse",
    (WriteMode.FENCED, True): "allow",
    (WriteMode.FENCED, False): "ask",
    (WriteMode.ASK, True): "ask",
    (WriteMode.ASK, False): "ask",
}


def permits(mode: WriteMode, *, inside: bool, target: str = "") -> Permit:
    """May this write happen, must a human decide, or is it refused?

    Total over (mode × placement). `inside` is the fence's verdict — `scope.check_sql(...).allowed` —
    and is meaningless for a read-only session, which refuses both cases identically.
    """
    outcome = _GRID[(mode, bool(inside))]
    if outcome == "allow":
        return Permit("allow")
    if outcome == "refuse":
        return Permit(
            "refuse",
            f"this session is read-only, so it cannot change {target or 'anything'}. "
            "Start a conversation with a write mode to make changes.")
    named = target or "this change"
    if not inside:
        return Permit("ask", f"{mode.label} mode: {named} is outside the session's fence.")
    return Permit("ask", f"{mode.label} mode: {named} needs your approval.")
