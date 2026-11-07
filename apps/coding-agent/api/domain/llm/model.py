"""A model, as the domain understands it. Pure: dataclasses, enums, and one alias table.

Three things live here and nowhere else:

* **`ModelId`** — the canonical `provider/model` string, parsed once. Law 1: an id resolves through
  a table, never through string surgery. `ALIASES` is that table for every id this app has stored.
* **`ModelSpec`** — one row of the catalogue: what exists, what it costs in context, how healthy it
  is. A value object; the resolver turns it into a `ResolvedModel`.
* **`ResolvedModel`** — everything a child process needs to reach one model, and the only object
  that crosses from the resolver into the orchestrator, so there is exactly one place a model can be
  wrong.

No vendor name appears in a comparison anywhere in this module: `ProviderKind` is an enum and the
behaviour that differs per provider lives in `adapters/llm/providers/` (Axiom A2, CI gate C-2).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any

from .errors import UnknownModel
from .limits import DEFAULT_LIMITS, Limits


class ProviderKind(str, Enum):
    """Where a model lives, as a *kind of wire*, not as a brand.

    `FAKE` is the deterministic demo provider (`agent_mode="fake"`): it has no wire and no
    credential, and it exists because demo mode and the test suite must run without a network. It is
    a test double, not a fifth vendor — the four real kinds are the ones in FR-3.
    """

    DATABRICKS = "databricks"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE_VERTEX = "google_vertex"
    FAKE = "fake"


class WireProtocol(str, Enum):
    """The shape of the HTTP conversation. A provider kind maps to one, or to a pair to choose from."""

    SERVING = "serving"                    # Databricks serving endpoints (OpenAI-compatible + caps)
    OPENAI = "openai"                      # any OpenAI-compatible base URL
    ANTHROPIC = "anthropic"                # messages API, x-api-key + anthropic-version
    VERTEX_OPENAI = "vertex_openai"        # Vertex AI's OpenAI-compatible endpoint
    VERTEX_NATIVE = "vertex_native"        # Vertex generateContent, round-trips thought_signature
    FAKE = "fake"                          # no wire: the demo agent replays a recording


def agent_prefix(provider: "ProviderKind", wire: WireProtocol | None = None) -> str:
    """The provider block name the agent uses, for the config file **and** for `set_model`.

    One function, so the file the app writes and the id the app sends cannot disagree. The wire takes
    part because Vertex has two blocks: opencode's built-in `google-vertex` (the native wire, which
    round-trips `thought_signature`) and a custom OpenAI-compatible `vertex` block.
    """
    if provider is ProviderKind.GOOGLE_VERTEX:
        return "google-vertex" if wire in (None, WireProtocol.VERTEX_NATIVE) else "vertex"
    return {
        ProviderKind.DATABRICKS: "dbx",
        ProviderKind.OPENAI: "openai",
        ProviderKind.ANTHROPIC: "anthropic",
        ProviderKind.FAKE: "dbx",
    }.get(provider, provider.value)


class Capability(str, Enum):
    """What the model can actually do. A model that cannot call tools cannot do this product's job."""

    TOOLS = "tools"
    TOOLS_AND_REASONING = "tools_and_reasoning"
    CHAT_ONLY = "chat_only"

    @property
    def selectable(self) -> bool:
        return self is not Capability.CHAT_ONLY


class CredentialKind(str, Enum):
    NONE = "none"                          # the workspace token covers it (Databricks)
    API_KEY = "api_key"
    SERVICE_ACCOUNT_JSON = "service_account_json"
    ACCESS_TOKEN = "access_token"


class ModelState(str, Enum):
    """Six states, each with copy and an action. Health is derived, never stored as an opinion."""

    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAUTHORISED = "unauthorised"
    NOT_SERVED = "not_served"              # discovery no longer lists it
    NOT_ENABLED = "not_enabled"            # the platform says the model is gated
    UNKNOWN = "unknown"                    # never probed, or discovery unreadable

    @property
    def usable(self) -> bool:
        """Whether a turn could be attempted. `unknown` is usable: never probed is not broken."""
        return self in (ModelState.AVAILABLE, ModelState.UNKNOWN)


#: Where a credential comes from. `NONE` means the workspace token already covers this model.
class CredentialSource(str, Enum):
    WORKSPACE_TOKEN = "workspace_token"
    USER = "user"
    WORKSPACE = "workspace"
    ENV = "env"
    NONE = "none"


# --------------------------------------------------------------------------------------------
# The alias table
# --------------------------------------------------------------------------------------------

#: Every id this app has ever stored or sent, mapped to the canonical id. This is a literal table on
#: purpose (Law 1): the old resolver *derived* an endpoint from an id, so a typo became a plausible
#: wrong URL instead of an error. `tests/test_llm_domain.py` asserts every entry resolves and that
#: the mapping is injective where it must be.
#:
#: The `databricks/system.ai.<x>` entries exist because the gateway advertises a foundation-model name
#: while the agent needs the serving-endpoint name; carrying both as one table is what makes the
#: switch send the right id.
ALIASES: dict[str, str] = {
    # identity forms (already canonical)
    "databricks/databricks-llama-4-maverick": "databricks/databricks-llama-4-maverick",
    "databricks/databricks-meta-llama-3-3-70b-instruct": "databricks/databricks-meta-llama-3-3-70b-instruct",
    "databricks/databricks-claude-sonnet-4-5": "databricks/databricks-claude-sonnet-4-5",
    # the foundation-model ids the old allow-list offered
    "databricks/system.ai.gpt-oss-120b": "databricks/databricks-gpt-oss-120b",
    "databricks/system.ai.gpt-oss-20b": "databricks/databricks-gpt-oss-20b",
    "databricks/system.ai.qwen3-next-80b-a3b-instruct": "databricks/databricks-qwen3-next-80b-a3b-instruct",
    "databricks/system.ai.databricks-qwen35-122b-a10b": "databricks/databricks-qwen35-122b-a10b",
    "databricks/system.ai.gemma-3-12b-it": "databricks/databricks-gemma-3-12b",
    "databricks/system.ai.claude-sonnet-4-5": "databricks/databricks-claude-sonnet-4-5",
    # the agent's internal dialect, written into opencode.json before this spec
    "dbx/databricks-gpt-oss-120b": "databricks/databricks-gpt-oss-120b",
    "dbx/databricks-gpt-oss-20b": "databricks/databricks-gpt-oss-20b",
    "dbx/databricks-qwen3-next-80b-a3b-instruct": "databricks/databricks-qwen3-next-80b-a3b-instruct",
    "dbx/databricks-llama-4-maverick": "databricks/databricks-llama-4-maverick",
    "dbx/databricks-meta-llama-3-3-70b-instruct": "databricks/databricks-meta-llama-3-3-70b-instruct",
    # the dash form the old string surgery produced: `databricks-system.ai.gpt-oss-120b`
    "databricks-system.ai.gpt-oss-120b": "databricks/databricks-gpt-oss-120b",
    "databricks-system.ai.gpt-oss-20b": "databricks/databricks-gpt-oss-20b",
    "databricks-system.ai.qwen3-next-80b-a3b-instruct": "databricks/databricks-qwen3-next-80b-a3b-instruct",
    # the Vertex form the exam harness and templates use
    "vertex/google/gemini-3.8-flash": "google_vertex/google/gemini-3.8-flash",
    "vertex/google/gemini-3.8-pro": "google_vertex/google/gemini-3.8-pro",
    "vertex/google/gemini-3.5-flash": "google_vertex/google/gemini-3.5-flash",
}


@dataclass(frozen=True, slots=True, order=True)
class ModelId:
    """`provider/model`, canonical. Constructed through `ModelId.parse`, never by hand.

    The model part may contain slashes (`google_vertex/google/gemini-3.8-flash`), because Vertex
    names a publisher *and* a model. Splitting on the first slash is the whole grammar.
    """

    provider: ProviderKind
    name: str

    @property
    def value(self) -> str:
        return f"{self.provider.value}/{self.name}"

    def __str__(self) -> str:  # pragma: no cover - convenience
        return self.value

    @classmethod
    def parse(cls, text: str) -> ModelId:
        """Canonicalise any id the app may hold. Raises `UnknownModel` when the grammar is wrong.

        The alias table is consulted first, so a stored legacy id resolves to exactly one canonical
        id (NFR-7). Anything left is checked against the grammar: a provider this build knows and a
        non-empty model name. An unknown *model* is not an error here — that is the catalogue's job,
        and it produces a different message.
        """
        raw = (text or "").strip()
        if not raw:
            raise UnknownModel(text)
        alias = ALIASES.get(raw.lower())
        if alias is not None:
            raw = alias
        provider, _, name = raw.partition("/")
        try:
            kind = ProviderKind(provider.lower())
        except ValueError:
            raise UnknownModel(text) from None
        if not name or " " in name:
            raise UnknownModel(text)
        return cls(kind, name.lower())

    def alias_forms(self) -> tuple[str, ...]:
        """Every stored spelling that resolves to this id. Used by the injectivity test and by docs."""
        return tuple(sorted(k for k, v in ALIASES.items() if v == self.value))


# --------------------------------------------------------------------------------------------
# The catalogue row
# --------------------------------------------------------------------------------------------

#: Group headings, in picker order (07 §Grouping and order). Data, not a switch in the UI.
GROUP_GATEWAY = "Databricks · AI Gateway"
GROUP_YOURS = "Your providers"
GROUP_WORKSPACE = "Workspace providers"
GROUP_UNAVAILABLE = "Not available here"


@dataclass(frozen=True, slots=True)
class Grant:
    """Authorisation for one model. Comes only from the database: never from a file."""

    model_id: str
    #: `("user", email, True)` / `("group", name, False)` / `("all", "*", True)`
    rows: tuple[tuple[str, str, bool], ...] = ()

    def allows(self, user: str, groups: frozenset[str] = frozenset()) -> bool:
        """Deny always wins; an explicit user grant beats a group grant; no rows means open.

        The default-open rule is stated in 05 §llm_model_grant and kept because the opposite choice
        would break the product on day one: today every user can use every allowed model.
        """
        if not self.rows:
            return True
        explicit_deny = any(
            allow is False and kind == "user" and subject == user for kind, subject, allow in self.rows
        )
        if explicit_deny:
            return False
        if any(kind == "user" and subject == user and allow for kind, subject, allow in self.rows):
            return True
        if any(kind == "group" and subject in groups and allow for kind, subject, allow in self.rows):
            return True
        return any(kind == "all" and allow for kind, _subject, allow in self.rows)


@dataclass(frozen=True, slots=True)
class ModelSpec:
    """One selectable model, as the catalogue knows it.

    Every field that can be wrong carries its provenance: `limits` carries its evidence, `state`
    carries where it came from (`health`), and `credential_kind` says what is needed to use it.
    """

    id: ModelId
    display_name: str
    provider_name: str
    wire: WireProtocol
    endpoint: str
    limits: Limits = DEFAULT_LIMITS
    capability: Capability = Capability.TOOLS
    credential_kind: CredentialKind = CredentialKind.NONE
    credential_source: CredentialSource = CredentialSource.NONE
    #: `api_key …7f3a` when a live key exists; empty otherwise. Never the key.
    credential_hint: str = ""
    #: The opaque ref of the live credential, so the resolver does not repeat the lookup. Never a secret.
    credential_ref_id: str = ""
    state: ModelState = ModelState.UNKNOWN
    #: The provider's own words about the last failure, redacted and truncated.
    detail: str = ""
    #: When the health observation was made, epoch seconds. 0 means never.
    checked_at: float = 0.0
    #: Free-form group override from the database; empty means "derive it" (see picker_order).
    group: str = ""
    enabled: bool = True
    #: Why this model may not be offered, when it may not. Empty means "no reason to refuse".
    refusal: str = ""
    #: Where the discovery/health fact came from: `seed`, `database`, `discovery`, `probe`.
    origin: str = "seed"

    def with_health(self, state: ModelState, detail: str = "", checked_at: float = 0.0) -> ModelSpec:
        return replace(self, state=state, detail=detail, checked_at=checked_at)

    @property
    def selectable(self) -> bool:
        """Chat-only models and gated models are catalogued but never offered as a choice."""
        return (
            self.enabled
            and self.capability.selectable
            and self.state is not ModelState.NOT_ENABLED
            and self.state is not ModelState.NOT_SERVED
            and not self.refusal
        )

    def to_dict(self) -> dict[str, Any]:
        """The wire shape. One place, so the front end cannot disagree with the catalogue."""
        return {
            "id": self.id.value,
            "name": self.display_name,
            "provider": self.id.provider.value,
            "providerName": self.provider_name,
            "wire": self.wire.value,
            "capability": self.capability.value,
            "state": self.state.value,
            "selectable": self.selectable,
            "refusal": self.refusal,
            "detail": self.detail,
            "checkedAt": self.checked_at or None,
            "limits": self.limits.to_dict(),
            "credential": {
                "kind": self.credential_kind.value,
                "source": self.credential_source.value,
                "hint": self.credential_hint,
            },
            "group": self.group,
            "origin": self.origin,
            "endpoint": self.endpoint,
        }


# --------------------------------------------------------------------------------------------
# The resolved model
# --------------------------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ResolvedModel:
    """Everything a child process needs to reach one model. The resolver's only return value.

    There is **no field for a secret**: `env_var` names the variable and the credential travels
    separately, as a value handed to the child. That separation is what makes Axiom A4 mechanical
    rather than a promise.
    """

    id: ModelId
    provider: ProviderKind
    wire: WireProtocol
    endpoint: str
    base_url: str
    limits: Limits
    capability: Capability
    #: The environment variable the credential is delivered in. Empty when none is needed.
    env_var: str = ""
    #: The npm package the agent needs for this wire.
    npm: str = ""
    #: Extra provider options, templated only (never a secret).
    options: dict[str, Any] = field(default_factory=dict)
    #: The id the agent itself advertises for this model, when it advertises one (E-21).
    agent_id: str = ""
    #: An opaque credential reference for the audit record. Never the credential.
    credential_ref: str = ""
    credential_source: CredentialSource = CredentialSource.NONE

    @property
    def context(self) -> int:
        return self.limits.context

    @property
    def output(self) -> int:
        return self.limits.output

    def to_dict(self) -> dict[str, Any]:
        """What a turn records and what the inspector shows. No secret, by construction."""
        return {
            "id": self.id.value,
            "provider": self.provider.value,
            "wire": self.wire.value,
            "endpoint": self.endpoint,
            "context": self.limits.context,
            "output": self.limits.output,
            "evidence": self.limits.evidence.value,
            "source": self.limits.source,
            "capability": self.capability.value,
            "credentialRef": self.credential_ref,
        }
