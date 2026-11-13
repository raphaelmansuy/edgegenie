"""Asset/change values. Tokens and runtime credentials are never serializable ledger fields."""

from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass, field
from .scope import Scope
from .policy.verdict import ActionClass


def digest(value) -> str:
    raw = (
        value
        if isinstance(value, str)
        else json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    )
    return hashlib.sha256(raw.encode()).hexdigest()


class WorkError(Exception):
    def __init__(self, message: str, status: int = 409, *, current: str = ""):
        super().__init__(message)
        self.status, self.current = status, current


class RemoteRefused(WorkError, RuntimeError):
    """A native API explicitly refused a request before an effect was accepted."""


class PendingCleanup(RuntimeError):
    def __init__(self, operation_id):
        self.operation_id = operation_id
        super().__init__("Cleanup is still being observed; never resubmit it automatically.")


@dataclass(frozen=True, slots=True)
class AssetRef:
    kind: str
    id: str

    def to_dict(self):
        return {"kind": self.kind, "id": self.id}


@dataclass(frozen=True, slots=True)
class Actor:
    session_id: str
    user_id: str
    turn_id: str
    scope: Scope
    workspace: str = ""
    token: str | None = field(default=None, repr=False)
    expires_at: float | None = None
    delegated: bool = False
    scopes: tuple[str, ...] = ()
    username: str = ""

    @property
    def run_as(self):
        return self.username or self.user_id


@dataclass(frozen=True, slots=True)
class AssetContent:
    ref: AssetRef
    revision: str
    content: str
    language: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Plan:
    ref: AssetRef
    base: str
    before: str
    after: str
    operations: list[dict]
    diff: str
    action: ActionClass = ActionClass.CHANGE
    language: str = ""
    undo_available: bool = True
    effect: str = "edit"


def public_record(row: dict) -> dict:
    return {k: v for k, v in row.items() if not k.startswith("_")}
