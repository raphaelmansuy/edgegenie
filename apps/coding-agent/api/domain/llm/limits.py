"""Limits: a measurement with provenance, or an explicit unknown.

Axiom A3. The app asks the model for `output` tokens on every call and an endpoint rejects a request
above its own cap ("max_tokens 24000 cannot exceed 8192"), so a wrong number makes the model unusable
*after* the user waited. This module is the only place a cap is decided, and it always carries where
the number came from — so "unknown" is representable and a guess can never be presented as a fact.

Pure: no I/O, no vendor names.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

#: The conservative pair used when nothing is known. Chosen because it is below every cap this
#: repository has measured, so an unverified model still runs.
DEFAULT_CONTEXT = 64_000
DEFAULT_OUTPUT = 4_000


class LimitEvidence(str, Enum):
    """Where a number came from. Ordered by trust, strongest first."""

    MEASURED = "measured"      # a test in this workspace rejected a request and named the cap
    DOCUMENTED = "documented"  # a vendor document, a template in this repository, a URL
    DEFAULT = "default"        # nothing is known: the conservative pair, marked as assumed


@dataclass(frozen=True, slots=True)
class Limits:
    """A model's believed window. Frozen, total, and never silently larger than reality."""

    context: int
    output: int
    evidence: LimitEvidence = LimitEvidence.DEFAULT
    source: str = "assumed"

    def __post_init__(self) -> None:
        if self.context <= 0 or self.output <= 0:
            raise ValueError(f"limits must be positive, got context={self.context} output={self.output}")
        if self.output > self.context:
            raise ValueError(f"output {self.output} cannot exceed context {self.context}")

    @property
    def unverified(self) -> bool:
        """True when no evidence exists. The picker says so; the resolver clamps to the default."""
        return self.evidence is LimitEvidence.DEFAULT

    def to_dict(self) -> dict:
        return {
            "context": self.context,
            "output": self.output,
            "evidence": self.evidence.value,
            "source": self.source,
            "unverified": self.unverified,
        }


DEFAULT_LIMITS = Limits(DEFAULT_CONTEXT, DEFAULT_OUTPUT)


def clamp(limits: Limits | None, requested_context: int | None = None,
          requested_output: int | None = None) -> Limits:
    """Never return more than the believed cap, and never return an invalid pair.

    Total by construction: `None` becomes the conservative default, a request above the cap is
    lowered, a non-positive request falls back to the cap. This is the one function that decides
    what the app actually asks for, so it carries the property test in `tests/test_llm_domain.py`.
    """
    base = limits or DEFAULT_LIMITS
    context = base.context
    output = base.output
    if requested_context is not None and requested_context > 0:
        context = min(context, requested_context)
    if requested_output is not None and requested_output > 0:
        output = min(output, requested_output)
    output = min(output, context)
    if (context, output) == (base.context, base.output):
        return base
    return Limits(context, output, base.evidence, base.source)


#: "max_tokens (24000) cannot exceed 8192" and "max_new_tokens 32000 cannot be greater than
#: max_output_tokens 25000" are both measured shapes. Only the *second* number is a cap.
_CAP_PATTERNS = (
    re.compile(r"max_tokens\s*\(\s*\d+\s*\)\s*cannot\s*exceed\s*(\d+)", re.I),
    re.compile(r"max_new_tokens\s+\d+\s+cannot\s+be\s+greater\s+than\s+max_output_tokens\s+(\d+)", re.I),
    re.compile(r"max_tokens\s+\d+\s+cannot\s+exceed\s+(\d+)", re.I),
)


def cap_from_error(text: str) -> int | None:
    """The cap the provider named in a rejection, or None.

    Used to *lower* a stored limit and never to raise one: a number in an error can be a proxy's cap
    rather than the model's, so only a reduction is safe to apply automatically (05 §Limit evidence).
    """
    for pattern in _CAP_PATTERNS:
        m = pattern.search(text or "")
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                return None
    return None
