"""Ports: the only contracts the domain and services know. Adapters implement these."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ..domain.events import Event
from ..domain.llm import ModelSpec, ProviderKind, ResolvedModel


@dataclass(slots=True)
class SessionSpec:
    session_id: str
    cwd: str
    model: str
    mcp_url: str
    env: dict[str, str] = field(default_factory=dict)
    allow_builtin_shell: bool = False
    agent_session_id: str = ""


@dataclass(slots=True)
class Capabilities:
    protocol_version: int = 0
    agent: str = ""
    version: str = ""
    load_session: bool = False
    #: From `agentCapabilities.promptCapabilities`. ACP says an agent MUST support `text` and
    #: `resource_link`; everything else is opted in per agent. Sending an unadvertised block gets a
    #: `-32602` rejection, so this is asked, never assumed (spec 009 [D7]).
    images: bool = False
    embedded_context: bool = False
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RuntimeHandle:
    session_id: str  # the agent's own session id
    capabilities: Capabilities
    models: list[str] = field(default_factory=list)
    current_model: str = ""
    #: OUR session id — the key the runtime stores this process under. Carried on the handle because
    #: the agent's own id is not unique per process: the fake agent reports the same id for every
    #: instance, so `_by_agent` (agent id -> our id) collapsed three processes onto one key and
    #: `close()` could only ever find the last of them. Measured: three sessions archived with
    #: `handle=True`, two processes left running.
    ours: str = ""


class AgentError(Exception):
    pass


class AgentAuthError(AgentError):
    """The agent needs provider credentials it does not have. A configuration incident, not a user error."""


class AgentCrashed(AgentError):
    """The agent process died."""


@runtime_checkable
class AgentRuntime(Protocol):
    """One agent process, possibly serving many sessions."""

    async def start(self, spec: SessionSpec) -> RuntimeHandle: ...
    async def prompt(self, h: RuntimeHandle, text: str, images: list[dict] | None = None) -> dict: ...
    async def prompt_in_background(self, h: RuntimeHandle, text: str, images: list[dict] | None = None) -> None: ...
    def set_turn(self, session_id: str, turn_id: str) -> None: ...
    async def cancel(self, h: RuntimeHandle) -> None: ...
    async def set_model(self, h: RuntimeHandle, model: str) -> None: ...
    async def respond_permission(
        self, h: RuntimeHandle, request_id: str, option_id: str | None
    ) -> None: ...
    def events(self, h: RuntimeHandle) -> AsyncIterator[dict]: ...
    async def close(self, h: RuntimeHandle) -> None: ...


class ToolRegistry(Protocol):
    """Starts the per-session tool server and reports its URL and tool count."""

    async def start(self, session_id: str, folder: str, schema: str | None,
                    token_file: str | None = None, sp_token_file: str | None = None) -> str: ...
    async def stop(self, session_id: str) -> None: ...
    async def health(self, url: str) -> int: ...


class EventStore(Protocol):
    durable: bool

    async def append(self, event: Event) -> Event: ...
    async def since(self, session_id: str, seq: int, limit: int = 2000) -> list[dict]: ...
    async def latest_seq(self, session_id: str) -> int: ...
    async def commit(self, event: Event, snapshot: dict) -> Event: ...
    async def snapshots(self) -> list[dict]: ...


class Identity(Protocol):
    def user_id(self, headers: dict[str, str]) -> str: ...
    def token(self, headers: dict[str, str]) -> str | None: ...


class Groups(Protocol):
    """Group membership, from the identity provider — never from this app's tables."""

    def groups_for(self, user_id: str) -> frozenset[str]: ...


class ModelCatalog(Protocol):
    """The catalogue, as the rest of the app sees it.

    Extended, not replaced: `allowed`/`check` are the shape 001 shipped, and they now delegate to
    the registry. `specs`/`find`/`grants` are what the resolver needs.
    """

    def allowed(self, user_id: str) -> list[dict]: ...
    def check(self, user_id: str, model: str) -> None: ...
    def specs(self, user_id: str) -> list[ModelSpec]: ...
    def find(self, model_id: str) -> ModelSpec: ...
    def grants(self, model_id: str): ...


class RegistryStore(Protocol):
    """Where providers and models are persisted. Three implementations: seed, memory, Postgres."""

    #: `seed` | `database` | `degraded` | `memory`
    source: str

    async def providers(self) -> list[dict]: ...
    async def models(self, user_id: str) -> list[ModelSpec]: ...
    async def grants(self, model_id: str): ...
    async def health_state(self, model_id: str) -> tuple[str, str, float] | None: ...
    async def upsert_provider(self, provider: dict) -> None: ...
    async def upsert_model(self, spec: ModelSpec) -> None: ...
    async def record_health(self, model_id: str, state: str, detail: str, *, source: str) -> None: ...
    async def record_turn_model(self, pin: dict) -> None: ...
    async def turn_models(self, session_id: str) -> list[dict]: ...
    async def discovery_runs(self, limit: int = 20) -> list[dict]: ...
    async def record_discovery(self, provider: str, outcome: str, seen: int, detail: str) -> None: ...
    async def note_limits(self, model_id: str, output: int, source: str) -> None: ...
    async def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class Secret:
    """A decrypted credential, in memory for one spawn. Carries its own redaction in `__repr__`."""

    value: str
    kind: str = "api_key"
    ref: str = ""

    def __repr__(self) -> str:  # never print the value, even in a traceback
        return f"Secret(kind={self.kind!r}, ref={self.ref!r})"

    __str__ = __repr__


@dataclass(frozen=True, slots=True)
class CredentialRef:
    """An opaque handle to a stored credential. Never the credential."""

    id: str
    provider: ProviderKind
    kind: str
    scope_kind: str = "user"
    scope_id: str = ""
    last4: str = ""
    project_hint: str = ""
    #: `sha256(plaintext)[:16]`. Answers "was it this key?" without decrypting anything.
    fingerprint: str = ""

    def public(self) -> dict[str, str]:
        return {
            "id": self.id,
            "provider": self.provider.value,
            "kind": self.kind,
            "scope": self.scope_kind,
            "last4": self.last4,
            "projectHint": self.project_hint,
            "fingerprint": self.fingerprint,
        }


class CredentialVault(Protocol):
    """Store, open, revoke. No method returns plaintext except `open`, and `open` needs a context."""

    @property
    def available(self) -> bool: ...
    @property
    def mode(self) -> str: ...
    async def put(self, provider: ProviderKind, kind: str, secret: str,
                  *, user_id: str, scope: str = "user") -> CredentialRef: ...
    async def open(self, ref: str, *, user_id: str, session_id: str = "") -> Secret: ...
    async def revoke(self, ref: str, *, user_id: str) -> None: ...
    async def list(self, *, user_id: str) -> list[CredentialRef]: ...
    async def find(self, provider: ProviderKind, *, user_id: str) -> CredentialRef | None: ...


@dataclass(frozen=True, slots=True)
class ProviderDescriptor:
    """URL, npm package, wire protocol, tool-streaming flag. Pure; no network, no secret."""

    kind: ProviderKind
    wire: object
    base_url: str
    npm: str
    model_key: str
    tool_streaming: bool = True
    extra_headers: dict[str, str] = field(default_factory=dict)
    extra_body: dict[str, Any] = field(default_factory=dict)
    #: The model's name inside the agent's catalogue, when it differs from `model_key` (the name the
    #: provider's HTTP API takes). Vertex's native block lists `gemini-3.8-flash`, not `google/…`.
    agent_key: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "wire": getattr(self.wire, "value", str(self.wire)),
            "baseURL": self.base_url,
            "npm": self.npm,
            "modelKey": self.model_key,
            "toolStreaming": self.tool_streaming,
            "headers": dict(self.extra_headers),
            "extraBody": dict(self.extra_body),
        }


@dataclass(frozen=True, slots=True)
class ChildEnv:
    """What an adapter says the agent process needs in order to authenticate.

    `vars` are plain environment values. `files` maps a variable NAME to file CONTENT: the caller
    writes each to a private file (mode 0600, own directory, removed with the child) and exports the
    variable as that file's path. A provider whose SDK only reads a credential from a path (Google's
    `GOOGLE_APPLICATION_CREDENTIALS`) is the reason this exists; the orchestrator needs no vendor
    knowledge to honour it.
    """

    vars: dict[str, str] = field(default_factory=dict)
    files: dict[str, str] = field(default_factory=dict)


class ProviderAdapter(Protocol):
    """One per wire protocol. The adapter knows the wire; the domain knows the model."""

    kind: ProviderKind

    def descriptor(self, spec: ModelSpec, *, host: str = "", project: str = "") -> ProviderDescriptor: ...
    def env_var(self, spec: ModelSpec) -> str: ...
    async def child_env(self, resolved: ResolvedModel, secret: Secret) -> ChildEnv: ...
    async def probe(self, desc: ProviderDescriptor, secret: Secret | None) -> tuple[str, str]: ...


class Discovery(Protocol):
    """What a provider currently serves. `None` means "unreadable: do not filter" (FR-14)."""

    async def fetch(self, token: str | None) -> list[ModelSpec] | None: ...


class ModelResolver(Protocol):
    """id -> everything a child needs. The one resolution path (C-3)."""

    async def resolve(self, model_id: str, *, user_id: str,
                      session_id: str = "") -> tuple[object, Secret | None]: ...


# -- blobs (spec 009) ----------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class BlobRow:
    """A stored blob's metadata. The bytes are addressed by `storage_key`, never carried here."""

    id: str
    session_id: str
    user_id: str
    original_name: str
    stored_name: str
    mime: str
    family: str
    size: int
    sha256: str
    storage_key: str
    state: str          # pending | ready | attached | swept
    created_at: float
    attached_at: float | None = None

    def to_dict(self) -> dict:
        return {
            "blobId": self.id, "name": self.original_name, "mime": self.mime,
            "bytes": self.size, "family": self.family, "state": self.state,
            "sha256": self.sha256, "createdAt": self.created_at,
        }


class BlobStore(Protocol):
    """Bytes the user handed us, addressed by an opaque id (spec 009 [BLB-1], [BLB-5]).

    Two implementations exist today — memory for tests, files for development — and the contract test runs
    against both, which is what makes Liskov a fact rather than a claim. A database implementation is a
    third implementation of this same interface, not a migration of the feature.
    """

    async def put(self, session_id: str, user_id: str, spec, raw: bytes) -> BlobRow: ...
    async def meta(self, blob_id: str, user_id: str) -> BlobRow: ...
    async def bytes_for(self, blob_id: str, user_id: str) -> bytes: ...
    async def mark_attached(self, blob_id: str, turn_id: str, display_name: str,
                            session_id: str = "") -> None: ...
    async def refcount(self, blob_id: str) -> int: ...
    async def sweep(self, now: float) -> dict[str, int]: ...
    async def delete_session(self, session_id: str) -> int: ...


class BlobReader(Protocol):
    """What a *read* of a blob means, decided by its verified family (spec 009 [D9]).

    One method, so a new family is a new class rather than a new branch in a shared function.
    """

    async def read(self, row: BlobRow, raw: bytes, *, offset: int = 0, max_chars: int = 0,
                   unseen: bool = False) -> tuple[str, str]: ...
