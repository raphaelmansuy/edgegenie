"""A model an administrator adds by hand: validate it, then build the `ModelSpec`.

Pure rules, no I/O. The route calls `custom_model` and the store persists whatever it returns, so the
same checks guard the API, the tests and any future import path.

What an administrator may add is deliberately narrow: **an external model** (OpenAI, Anthropic, Vertex)
with limits they state. A Databricks model is discovered, never typed in, because a typed endpoint
that the workspace does not serve would be a catalogue row that fails on first use. And a limit an
administrator types is recorded as `documented` with their name as the source: it is a claim by a
person, which is stronger than a guess and weaker than a measurement.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .limits import LimitEvidence, Limits
from .model import (
    Capability,
    CredentialKind,
    ModelId,
    ModelSpec,
    ProviderKind,
    WireProtocol,
)


class InvalidModel(ValueError):
    """A field is wrong. `field` names it so the form can point at it."""

    def __init__(self, field: str, detail: str) -> None:
        super().__init__(detail)
        self.field = field
        self.detail = detail


@dataclass(frozen=True, slots=True)
class ProviderDefaults:
    label: str
    wire: WireProtocol
    credential: CredentialKind
    #: A short hint for the form's model-name field.
    example: str


#: Providers a model can be added to, and what each needs. Keyed by kind, never branched on by name.
EXTERNAL: dict[ProviderKind, ProviderDefaults] = {
    ProviderKind.GOOGLE_VERTEX: ProviderDefaults(
        "Google Vertex AI", WireProtocol.VERTEX_NATIVE, CredentialKind.SERVICE_ACCOUNT_JSON,
        "google/gemini-3.8-flash"),
    ProviderKind.OPENAI: ProviderDefaults(
        "OpenAI", WireProtocol.OPENAI, CredentialKind.API_KEY, "gpt-4.1"),
    ProviderKind.ANTHROPIC: ProviderDefaults(
        "Anthropic", WireProtocol.ANTHROPIC, CredentialKind.API_KEY, "claude-sonnet-4-5"),
}

#: A model name is a path-like token. Anything else would be a typo or an injection attempt.
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,118}$")
MAX_CONTEXT = 10_000_000


def custom_model(provider: ProviderKind, name: str, *, display_name: str = "", context: int,
                 output: int, capability: Capability = Capability.TOOLS_AND_REASONING,
                 added_by: str = "") -> ModelSpec:
    defaults = EXTERNAL.get(provider)
    if defaults is None:
        raise InvalidModel("provider", f"models are not added to {provider.value!r}: "
                           "Databricks models are discovered from the workspace")
    name = (name or "").strip()
    if not _NAME.match(name) or ".." in name or name.endswith("/"):
        raise InvalidModel("model", f"{name!r} is not a model name (letters, digits and . _ : / - only); "
                           f"for example {defaults.example}")
    if capability is Capability.CHAT_ONLY:
        raise InvalidModel("capability", "a chat-only model cannot call tools, so it cannot do this job")
    if not 1 <= context <= MAX_CONTEXT:
        raise InvalidModel("context", f"the context window must be between 1 and {MAX_CONTEXT} tokens")
    if not 1 <= output <= context:
        raise InvalidModel("output", "the output limit must be positive and not larger than the context window")
    who = (added_by or "an administrator").strip()
    return ModelSpec(
        id=ModelId(provider, name),
        display_name=(display_name or name.rsplit("/", 1)[-1]).strip()[:80],
        provider_name=defaults.label,
        wire=defaults.wire,
        endpoint=name,
        limits=Limits(context, output, LimitEvidence.DOCUMENTED, f"stated by {who}"),
        capability=capability,
        credential_kind=defaults.credential,
        origin="database",
    )


__all__ = ["EXTERNAL", "InvalidModel", "ProviderDefaults", "custom_model"]
