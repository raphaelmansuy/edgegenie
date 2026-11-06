"""Session and turn state machine. Pure: transitions return new values or raise DomainError."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from uuid import uuid4


class DomainError(Exception):
    """A request that is valid HTTP but invalid for the current state (maps to 409)."""


class SessionStatus(str, Enum):
    PROVISIONING = "provisioning"
    READY = "ready"
    STREAMING = "streaming"
    BLOCKED = "blocked"
    ARCHIVED = "archived"
    FAILED = "failed"


class TurnStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    AUDITING = "auditing"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"
    FAILED = "failed"


TERMINAL = {
    TurnStatus.COMPLETED,
    TurnStatus.BLOCKED,
    TurnStatus.CANCELLED,
    TurnStatus.INTERRUPTED,
    TurnStatus.FAILED,
}

_ALLOWED = {
    SessionStatus.PROVISIONING: {SessionStatus.READY, SessionStatus.FAILED},
    SessionStatus.READY: {SessionStatus.STREAMING, SessionStatus.ARCHIVED, SessionStatus.FAILED},
    SessionStatus.STREAMING: {
        SessionStatus.READY,
        SessionStatus.BLOCKED,
        SessionStatus.FAILED,
        SessionStatus.ARCHIVED,
    },
    SessionStatus.BLOCKED: {SessionStatus.STREAMING, SessionStatus.READY, SessionStatus.ARCHIVED},
    SessionStatus.FAILED: {SessionStatus.PROVISIONING, SessionStatus.ARCHIVED},
    SessionStatus.ARCHIVED: set(),
}


@dataclass(frozen=True, slots=True)
class Session:
    id: str
    user_id: str
    folder: str
    schema: str | None
    model: str
    title: str = "New session"
    status: SessionStatus = SessionStatus.PROVISIONING
    tools: int = 0
    agent: str = ""
    agent_version: str = ""
    tokens: int = 0

    def transition(self, to: SessionStatus) -> Session:
        if to == self.status:
            return self
        if to not in _ALLOWED[self.status]:
            raise DomainError(f"cannot go from {self.status.value} to {to.value}")
        return replace(self, status=to)


@dataclass(frozen=True, slots=True)
class Turn:
    id: str
    session_id: str
    index: int
    prompt: str
    model: str
    status: TurnStatus = TurnStatus.QUEUED
    stop_reason: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    error: str = ""
    queued_reason: str = ""
    cancelled: bool = False

    def start(self) -> Turn:
        if self.status not in (TurnStatus.QUEUED, TurnStatus.INTERRUPTED):
            raise DomainError(f"turn is {self.status.value}, cannot start")
        return replace(self, status=TurnStatus.RUNNING)

    def finish(
        self, status: TurnStatus, stop_reason: str = "", usage: dict | None = None, error: str = ""
    ) -> Turn:
        if status not in TERMINAL:
            raise DomainError("finish needs a terminal status")
        u = usage or {}
        return replace(
            self,
            status=status,
            stop_reason=stop_reason,
            error=error,
            input_tokens=int(u.get("inputTokens", 0) or 0),
            output_tokens=int(u.get("outputTokens", 0) or 0),
            cached_tokens=int(u.get("cachedReadTokens", 0) or 0),
        )


@dataclass
class SessionState:
    """The in-memory projection the runner mutates while a turn streams."""

    session: Session
    turns: list[Turn] = field(default_factory=list)
    calls: dict[str, dict] = field(default_factory=dict)

    def next_index(self) -> int:
        return len(self.turns) + 1

    def new_turn(self, prompt: str) -> Turn:
        """Create the next turn. If one is already running, the new turn is queued behind it."""
        running = self.running()
        t = Turn(
            id=uuid4().hex[:12],
            session_id=self.session.id,
            index=self.next_index(),
            prompt=prompt,
            model=self.session.model,
            queued_reason=f"after turn {running.index}" if running else "",
        )
        self.turns.append(t)
        return t

    def running(self) -> Turn | None:
        """The turn holding the foreground. A freshly submitted turn is QUEUED until it starts,
        but it still holds the foreground, so a second message must queue behind it."""
        return next(
            (
                t
                for t in self.turns
                if t.status
                in (
                    TurnStatus.RUNNING,
                    TurnStatus.AUDITING,
                    TurnStatus.QUEUED if t is self.turns[-1] else TurnStatus.RUNNING,
                )
            ),
            None,
        )

    def claim(self, turn_id: str) -> Turn:
        """Move a turn to RUNNING in place. The single writer for turn status."""
        for i, t in enumerate(self.turns):
            if t.id == turn_id:
                started = t.start()
                self.turns[i] = started
                return started
        raise DomainError(f"no turn {turn_id}")

    def update(self, turn: Turn) -> None:
        for i, t in enumerate(self.turns):
            if t.id == turn.id:
                self.turns[i] = turn
                return
        raise DomainError(f"no turn {turn.id}")


def updated(obj, **changes):
    """Immutable update that works on slots dataclasses (no __dict__)."""
    return replace(obj, **changes)
