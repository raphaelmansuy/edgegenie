"""In-memory blob store: the reference implementation, and what every test uses.

It exists so the contract can be proven without a disk, a database or a bucket. The file store passes the
same tests, which is what makes them interchangeable (spec 009 [BLB-5], [V3]).
"""

from __future__ import annotations

import time
import uuid

from ...domain import retention
from ...domain.retention import PENDING_TTL, READY_TTL
from ...ports import BlobRow

__all__ = ["MemoryBlobStore", "PENDING_TTL", "READY_TTL", "_as_dict"]


class MemoryBlobStore:
    """Rows in a dict, bytes in a dict. Nothing is copied on read, so a test can assert identity."""

    def __init__(self, clock=time.time) -> None:
        self._rows: dict[str, BlobRow] = {}
        self._bytes: dict[str, bytes] = {}
        self._refs: dict[str, set[str]] = {}
        self._clock = clock

    async def put(self, session_id: str, user_id: str, spec, raw: bytes) -> BlobRow:
        # The same bytes in the same session are the same blob: a retry must not create a second row that
        # looks like a different file. Content-addressed within a session, id-addressed globally.
        for row in self._rows.values():
            if row.session_id == session_id and row.sha256 == spec.sha256 and row.state != "swept":
                return row
        blob_id = f"blb_{uuid.uuid4().hex[:12]}"
        row = BlobRow(
            id=blob_id,
            session_id=session_id,
            user_id=user_id,
            original_name=spec.original_name,
            stored_name=spec.stored_name,
            mime=spec.mime,
            family=spec.family.value,
            size=spec.size,
            sha256=spec.sha256,
            storage_key=blob_id,          # in memory the key IS the id; the file store uses a path
            state="ready",
            created_at=self._clock(),
        )
        self._rows[blob_id] = row
        self._bytes[blob_id] = raw
        self._refs[blob_id] = set()
        return row

    async def meta(self, blob_id: str, user_id: str) -> BlobRow:
        row = self._rows.get(blob_id)
        # 404 for another user, not 403: a 403 confirms the id exists, which is an enumeration oracle.
        if row is None or row.user_id != user_id:
            raise LookupError("no such blob")
        return row

    async def bytes_for(self, blob_id: str, user_id: str) -> bytes:
        row = await self.meta(blob_id, user_id)
        raw = self._bytes.get(row.id)
        if raw is None:
            raise LookupError("the bytes for this attachment are gone")
        return raw

    async def mark_attached(self, blob_id: str, turn_id: str, display_name: str,
                            session_id: str = "") -> None:
        """Record the reference, and ADOPT the session when the blob was uploaded before one existed.

        A blob attached on the home screen is stored under `pending:<user>`, because there is no session to
        name yet. The moment a message carries it, the session is known and the row moves to it — otherwise
        it would never be swept with its session, and `delete_session` would not reach it.
        """
        row = self._rows.get(blob_id)
        if row is None:
            return
        self._refs.setdefault(blob_id, set()).add(turn_id)
        updates = {}
        if row.state == "ready":
            updates = {"state": "attached", "attached_at": self._clock()}
        if session_id and row.session_id.startswith("pending:"):
            updates["session_id"] = session_id
        if updates:
            self._rows[blob_id] = BlobRow(**{**_as_dict(row), **updates})

    async def refcount(self, blob_id: str) -> int:
        return len(self._refs.get(blob_id, ()))

    async def sweep(self, now: float) -> dict[str, int]:
        """Delete what `domain/retention.py` says may go. See the note in `adapters/blob/files.py`:
        the old body branched on a state `put()` never writes, so a blob waiting for its session was
        swept on the ready TTL."""
        report = {"pending": 0, "ready": 0}
        for blob_id, row in list(self._rows.items()):
            decision = retention.retention(
                retention.candidate(row, self._refs.get(blob_id, ())), now=now)
            if not retention.is_sweep(decision):
                continue
            self._sweep_one(blob_id)
            report["pending" if decision is retention.Disposition.SWEEP_PENDING else "ready"] += 1
        return report

    def _sweep_one(self, blob_id: str) -> None:
        row = self._rows.pop(blob_id, None)
        self._bytes.pop(blob_id, None)
        self._refs.pop(blob_id, None)
        _ = row

    async def delete_session(self, session_id: str) -> int:
        gone = [b for b, r in self._rows.items() if r.session_id == session_id]
        for blob_id in gone:
            self._sweep_one(blob_id)
        return len(gone)


def _as_dict(row: BlobRow) -> dict:
    """`BlobRow` is a slots dataclass, so it has no `__dict__`. Rebuild it field by field."""
    return {name: getattr(row, name) for name in BlobRow.__dataclass_fields__}
