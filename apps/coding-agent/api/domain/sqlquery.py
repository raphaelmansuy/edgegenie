"""SQL domain contracts: native assets, private drafts and execution attempts stay distinct."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

MAX_SOURCE = 200 * 1024
TERMINAL = frozenset({"succeeded", "failed", "canceled", "outcome_unknown"})
ACTIVE = frozenset(
    {"submitting", "pending", "running", "cancel_requested", "reconciling", "submission_unknown"}
)


def check_operation(fingerprint: str, previous: str, created: float) -> None:
    """Both journals apply identical replay/expiry policy inside their atomic transaction."""
    if previous != fingerprint:
        raise SqlError("CONFLICT", "This operation key belongs to different input.", 409)
    if time.time() - created > 86400:
        raise SqlError("CONFLICT", "This operation key has expired; it cannot be replayed.", 409)


def check_run_capacity(own_sources: list[str], total: int, source: str) -> None:
    if len(own_sources) >= 4 or total >= 32:
        raise SqlError("RUN_LIMIT", "Too many active SQL runs. Cancel or resolve an existing run first.", 409)
    if source and source in own_sources:
        raise SqlError("RUN_LIMIT", "This query already has an active or unresolved run.", 409)


class SqlError(Exception):
    def __init__(self, code: str, message: str, status: int = 422):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


@dataclass(frozen=True)
class SqlActor:
    workspace: str
    user: str
    token: str | None = None

    @property
    def scope(self) -> str:
        return digest([self.workspace, self.user])


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def native_id(value: str) -> str:
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise SqlError(
            "INVALID_REFERENCE", "A Query must use its native UUID, not an editor object ID."
        ) from exc


def selected_source(text: str, selection: dict | None) -> str:
    try:
        length = len(text.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise SqlError("INVALID_SOURCE", "The SQL source contains an invalid Unicode character.") from exc
    if length > MAX_SOURCE:
        raise SqlError("SOURCE_TOO_LARGE", "SQL source exceeds the 200 KiB editor limit.")
    if not selection:
        return text
    start, end = selection.get("start"), selection.get("end")
    raw = text.encode("utf-16-le")
    if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start < end <= len(raw) // 2:
        raise SqlError("INVALID_SELECTION", "Select one complete SQL statement.")
    try:
        return raw[start * 2 : end * 2].decode("utf-16-le")
    except UnicodeDecodeError as exc:
        raise SqlError("INVALID_SELECTION", "The selection splits a Unicode character.") from exc


class QueryProvider(Protocol):
    demo: bool
    dialect: object

    async def list(self, actor: SqlActor, cursor: str, size: int) -> dict: ...
    async def get(self, actor: SqlActor, query_id: str) -> dict: ...
    async def create(self, actor: SqlActor, query: dict) -> dict: ...
    async def warehouses(self, actor: SqlActor) -> list[dict]: ...
    async def submit(self, actor: SqlActor, payload: dict) -> dict: ...
    async def status(self, actor: SqlActor, statement_id: str) -> dict: ...
    async def cancel(self, actor: SqlActor, statement_id: str) -> None: ...


class QueryStore(Protocol):
    durable: bool

    async def get(self, scope: str, kind: str, key: str) -> dict: ...
    async def put(
        self, scope: str, kind: str, key: str, body: dict, expected: int | None = None
    ) -> dict: ...
    async def list(self, scope: str, kind: str, before: float = 0, limit: int = 50) -> list[dict]: ...
    async def reserve(self, scope: str, key: str, fingerprint: str, body: dict) -> tuple[dict, bool]: ...
