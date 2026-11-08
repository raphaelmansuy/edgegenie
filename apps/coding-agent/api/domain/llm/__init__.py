"""The `llm` domain: value objects and pure rules for model identity, limits, policy, credentials.

Nothing here imports an adapter, a service, or a vendor SDK. That is what makes the rules testable
without a network and what CI gate C-2 enforces (`rg "== '(openai|anthropic|...)"' api/domain` must
match nothing).
"""

from __future__ import annotations

from .custom import EXTERNAL, InvalidModel, ProviderDefaults, custom_model
from .credentials import (
    CredentialError,
    CredentialParsed,
    fingerprint,
    validate,
    with_project,
)
from .errors import (
    Cause,
    Classification,
    ModelError,
    NoCredential,
    NotGranted,
    NotSelectable,
    ProviderUnhealthy,
    UnknownModel,
    classify,
    useful_text,
)
from .limits import (
    DEFAULT_CONTEXT,
    DEFAULT_LIMITS,
    DEFAULT_OUTPUT,
    LimitEvidence,
    Limits,
    cap_from_error,
    clamp,
)
from .model import (
    ALIASES,
    GROUP_GATEWAY,
    GROUP_UNAVAILABLE,
    GROUP_WORKSPACE,
    GROUP_YOURS,
    Capability,
    CredentialKind,
    CredentialSource,
    Grant,
    ModelId,
    ModelSpec,
    ModelState,
    ProviderKind,
    ResolvedModel,
    WireProtocol,
    agent_prefix,
)
from .policy import Decision, Verdict, may_use

__all__ = [
    "EXTERNAL",
    "InvalidModel",
    "ProviderDefaults",
    "custom_model",
    "ALIASES",
    "Capability",
    "Cause",
    "Classification",
    "CredentialError",
    "CredentialKind",
    "CredentialParsed",
    "CredentialSource",
    "DEFAULT_CONTEXT",
    "DEFAULT_LIMITS",
    "DEFAULT_OUTPUT",
    "Decision",
    "GROUP_GATEWAY",
    "GROUP_UNAVAILABLE",
    "GROUP_WORKSPACE",
    "GROUP_YOURS",
    "Grant",
    "LimitEvidence",
    "Limits",
    "ModelError",
    "ModelId",
    "ModelSpec",
    "ModelState",
    "NoCredential",
    "NotGranted",
    "NotSelectable",
    "ProviderKind",
    "ProviderUnhealthy",
    "ResolvedModel",
    "UnknownModel",
    "Verdict",
    "WireProtocol",
    "agent_prefix",
    "cap_from_error",
    "classify",
    "clamp",
    "fingerprint",
    "may_use",
    "useful_text",
    "validate",
    "with_project",
]
