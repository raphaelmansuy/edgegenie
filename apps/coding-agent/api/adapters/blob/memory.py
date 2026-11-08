"""In-memory blob store: the reference implementation, and what every test uses.

It exists so the contract can be proven without a disk, a database or a bucket. The file store passes the
same tests, which is what makes them interchangeable (spec 009 [BLB-5], [V3]).
"""

from __future__ import annotations

import time
import uuid

from ...ports import BlobRow

PENDING_TTL = 60 * 60          # 1 h: a chip that never finished uploading
READY_TTL = 24 * 60 * 60       # 24 h: uploaded, never sent


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

    async def mark_attached(self, blob_id: str, turn_id: str, display_name: str) -> None:
        row = self._rows.get(blob_id)
        if row is None:
            return
        self._refs.setdefault(blob_id, set()).add(turn_id)
        if row.state == "ready":
            self._rows[blob_id] = BlobRow(**{**_as_dict(row), "state": "attached",
                                             "attached_at": self._clock()})

    async def refcount(self, blob_id: str) -> int:
        return len(self._refs.get(blob_id, ()))

    async def sweep(self, now: float) -> dict[str, int]:
        """Delete what can no longer be reached. A referenced blob is NEVER swept — [V3]."""
        pending, ready = 0, 0
        for blob_id, row in list(self._rows.items()):
            if row.state == "swept":
                continue
            if self._refs.get(blob_id):
                continue
            age = now - row.created_at
            if row.state == "pending" and age > PENDING_TTL:
                self._sweep_one(blob_id)
                pending += 1
            elif row.state == "ready" and age > READY_TTL:
                self._sweep_one(blob_id)
                ready += 1
        return {"pending": pending, "ready": ready}

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
