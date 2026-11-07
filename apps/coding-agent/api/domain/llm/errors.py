"""The model error taxonomy, and the classifier that produces it from a provider's own words.

Two jobs, both pure:

1. `ModelError` subclasses are the only failures the resolver raises, so a route maps them to a
   status without knowing a provider exists.
2. `classify(text)` turns the string ACP gives us — a stderr tail, a provider JSON body, a mapper
   message — into one of the six health states plus a named cause. The mapping is a table, so
   adding a provider's phrasing is one line and one recorded fixture.

Every entry in `_RULES` corresponds to a string this repository actually captured; the source is
named beside each one. A rule without a captured example is a guess, and guesses are how the old
stderr heuristic became unmaintainable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class ModelError(ValueError):
    """A model could not be used. The message is shown to a person, so it is a sentence.

    A `ValueError` as well as an exception because that is what the pre-registry catalogue raised,
    and three call sites still catch `ValueError` around session creation. Narrowing the base class
    would silently turn a 422 into a 500, which is exactly the kind of quiet regression this spec is
    written against.
    """

    #: HTTP status a route should return for this error.
    status = 422
    #: Stable machine code, for the client and for logs.
    code = "model_error"


class UnknownModel(ModelError):
    code = "unknown_model"
    status = 422

    def __init__(self, model_id: str) -> None:
        super().__init__(f"no model named {model_id!r} is in the catalogue")
        self.model_id = model_id


class NotGranted(ModelError):
    code = "not_granted"
    status = 403

    def __init__(self, model_id: str) -> None:
        super().__init__(f"you do not have access to {model_id}. Ask a workspace admin to grant it.")
        self.model_id = model_id


class NoCredential(ModelError):
    code = "no_credential"
    status = 409

    def __init__(self, model_id: str, provider: str) -> None:
        super().__init__(f"{provider} needs a key before {model_id} can run.")
        self.model_id = model_id
        self.provider = provider


class NotSelectable(ModelError):
    code = "not_selectable"
    status = 409

    def __init__(self, model_id: str, reason: str) -> None:
        super().__init__(reason or f"{model_id} cannot be used here")
        self.model_id = model_id


class ProviderUnhealthy(ModelError):
    code = "provider_unhealthy"
    status = 409


class Cause(str, Enum):
    """What went wrong, named. `cap_exceeded` is the only one that writes to the registry."""

    CAP_EXCEEDED = "cap_exceeded"
    PROTOCOL_ERROR = "protocol_error"
    NOT_ENABLED = "not_enabled"
    UNREACHABLE = "unreachable"
    UNAUTHORISED = "unauthorised"
    NOT_FOUND = "not_found"
    RATE_LIMITED = "rate_limited"
    STALLED = "stalled"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Classification:
    cause: Cause
    state: str                 # one of the six model states, as a string for the wire
    detail: str                # the provider's own words, already the useful part
    retryable: bool = False


@dataclass(frozen=True, slots=True)
class _Rule:
    cause: Cause
    state: str
    pattern: re.Pattern[str]
    retryable: bool = False


def _r(cause: Cause, state: str, pattern: str, retryable: bool = False) -> _Rule:
    return _Rule(cause, state, re.compile(pattern, re.I), retryable)


#: Ordered, most specific first. Each pattern is anchored on a phrase that only that failure uses.
_RULES: tuple[_Rule, ...] = (
    # measured: `docs/genie-code-replacement-spec.md` §3.2, three different models
    _r(Cause.CAP_EXCEEDED, "degraded", r"cannot exceed|cannot be greater than max_output_tokens"),
    # measured: `docs/e2e/07_gemini_thought_signature_failure.txt`
    _r(Cause.PROTOCOL_ERROR, "degraded", r"thought_signature"),
    # measured: the gated roster
    _r(Cause.NOT_ENABLED, "not_enabled", r"MODEL is not enabled|INVALID_STATE"),
    # measured: `docs/e2e/20_acp_config_probe.txt` §C
    _r(Cause.UNREACHABLE, "degraded", r"ENOTFOUND|ECONNREFUSED|getaddrinfo|connect ETIMEDOUT"),
    _r(Cause.UNAUTHORISED, "unauthorised",
       r"\b401\b|\b403\b|unauthor|incorrect api key|invalid api key|permission denied|forbidden|expired"),
    _r(Cause.RATE_LIMITED, "degraded", r"\b429\b|rate limit|too many requests|quota exceeded", retryable=True),
    _r(Cause.NOT_FOUND, "degraded", r"\b404\b|does not exist|model not found|no such model"),
    # measured: the runtime's own idle guard
    _r(Cause.STALLED, "degraded", r"sent nothing for|stalled|no result"),
    _r(Cause.TIMEOUT, "degraded", r"timed out|timeout", retryable=True),
)

_JSON_MESSAGE = re.compile(r'"message"\s*:\s*"(.{8,400}?)"')
_JSON_ERROR = re.compile(r'"error"\s*:\s*"(.{8,400}?)"')


def useful_text(text: str, limit: int = 400) -> str:
    """The most informative part of a provider's response: its own sentence, not the whole blob."""
    raw = (text or "").strip()
    if not raw:
        return ""
    for pattern in (_JSON_MESSAGE, _JSON_ERROR):
        m = pattern.search(raw)
        if m:
            raw = m.group(1)
            break
    raw = " ".join(raw.split())
    return raw[:limit]


def classify(text: str) -> Classification:
    """Map a provider's words to a state. Unknown text is `unknown`, never `degraded` by default.

    "Unknown" is the honest answer: a failure we cannot name must not be reported as a failure we
    understand, because the copy that follows tells the user what to do about it.
    """
    raw = text or ""
    detail = useful_text(raw)
    for rule in _RULES:
        if rule.pattern.search(raw):
            return Classification(rule.cause, rule.state, detail, rule.retryable)
    return Classification(Cause.UNKNOWN, "unknown", detail)
