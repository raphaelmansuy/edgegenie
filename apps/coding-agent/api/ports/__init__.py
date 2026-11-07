"""Ports: the only contracts the domain and services know. Adapters implement these."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ..domain.events import Event


@dataclass(slots=True)
class SessionSpec:
    session_id: str
    cwd: str
    model: str
    mcp_url: str
    env: dict[str, str] = field(default_factory=dict)
    allow_builtin_shell: bool = False


@dataclass(slots=True)
class Capabilities:
    protocol_version: int = 0
    agent: str = ""
    version: str = ""
    load_session: bool = False
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
    async def prompt(self, h: RuntimeHandle, text: str) -> dict: ...
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
                    token_file: str | None = None) -> str: ...
    async def stop(self, session_id: str) -> None: ...
    async def health(self, url: str) -> int: ...


class EventStore(Protocol):
    async def append(self, event: Event) -> Event: ...
    async def since(self, session_id: str, seq: int) -> list[dict]: ...
    async def latest_seq(self, session_id: str) -> int: ...


class Identity(Protocol):
    def user_id(self, headers: dict[str, str]) -> str: ...
    def token(self, headers: dict[str, str]) -> str | None: ...


class ModelCatalog(Protocol):
    def allowed(self, user_id: str) -> list[dict]: ...
    def check(self, user_id: str, model: str) -> None: ...
