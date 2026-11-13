"""Runtime-only session state; durable values stay in domain.session."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from ..domain.evidence import ToolCall
from ..domain.llm import ResolvedModel
from ..domain.session import (
    SessionState,
)
from ..ports import RuntimeHandle

MAX_TURNS = 200
from ..domain.tool_catalogue import CORE_TOOLS

TOOL_COUNT_CORE = len(CORE_TOOLS)
#: The folder the agent may write to, handed to the child so it can name real paths. A reference
#: agent's scenarios record `/Users/you/…` as a placeholder; without this it reported a path that
#: does not exist and every demo turn opened a 404.
FENCE_ENV = "APP_WORKSPACE_FOLDER"


@dataclass
class Live:
    """Everything belonging to one running session. Rebuilt on restart; the store is truth."""

    state: SessionState
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    #: The folder the agent may write to in the WORKSPACE (the fence), e.g. /Users/me/agent_scratch.
    #: Distinct from the agent process's local cwd; conflating them made the fence meaningless.
    workspace_folder: str = ""
    #: The agent process's own working directory on the local filesystem.
    agent_cwd: str = ""
    handle: RuntimeHandle | None = None
    mcp_url: str = ""
    tools: int = 0
    task: asyncio.Task | None = None
    cancel: bool = False
    extra: dict[str, Any] = field(default_factory=dict)
    #: Epoch seconds of the last activity (a turn, a stream connect, or creation). The reaper reads
    #: this; nothing else should. Without it a session is unreapable because "idle" is unknowable.
    last_seen: float = 0.0
    #: The resolved model this process was started with. A switch compares protocols against it.
    resolved: ResolvedModel | None = None

    def record(self, call_id: str, name: str, status: str, summary: str = "", args: str = "", proof=None) -> None:
        c = self.state.calls.setdefault(call_id, {"name": name, "status": "running"})
        if name:
            c["name"] = name
        if status:
            c["status"] = status
        if summary:
            c["summary"] = summary
        if args:
            c["args"] = args
        if proof is not None:
            c["proof"] = proof

    def tool_calls(self) -> list[ToolCall]:
        return [
            ToolCall(
                call_id=cid,
                name=c.get("name", ""),
                status=c.get("status", ""),
                summary=c.get("summary", ""),
                proof=c.get("proof"),
            )
            for cid, c in self.state.calls.items()
        ]
