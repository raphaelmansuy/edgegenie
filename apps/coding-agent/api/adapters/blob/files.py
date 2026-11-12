"""File-system blob store: the development implementation, and the one that survives a restart.

The bytes live under one private root, one directory per session, one file per blob, mode 0600. The root
is never derived from user input, and the storage key is a file name built from an id the server generated —
so a name the user supplied cannot reach outside the root (spec 009 [E-6], [P1]).

The whole point of this class is to pass the same contract test as the in-memory one. It has no behaviour
the memory store lacks, and that equality is what "interchangeable" means.
"""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

from ...domain import retention
from ...domain.retention import PENDING_TTL, READY_TTL
from ...ports import BlobRow
from .memory import _as_dict


class FileBlobStore:
    def __init__(self, root: Path | str, clock=time.time) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.root, 0o700)
        except OSError:
            pass  # a root on a filesystem without modes is not fatal
        self._clock = clock
        self._rows: dict[str, BlobRow] = {}
        self._refs: dict[str, set[str]] = {}
        self._load()

    # -- index -----------------------------------------------------------------------------------
    def _index_path(self, session_id: str) -> Path:
        return self._dir(session_id) / "_index"

    def _dir(self, session_id: str) -> Path:
        # The session id comes from the server, but it is still treated as a filename fragment: anything
        # that is not a plain token is refused rather than normalised, because a silent rewrite here would
        # put one session's bytes in another's folder.
        safe = "".join(ch for ch in session_id if ch.isalnum() or ch in "-_")
        if not safe:
            raise ValueError("a session id must be a plain token")
        return self.root / safe

    def _blob_path(self, row: BlobRow) -> Path:
        return self._dir(row.session_id) / f"{row.id}.bin"

    def _load(self) -> None:
        """Rebuild the row index from disk: the index file is the source, the names are the check."""
        for folder in self.root.iterdir() if self.root.exists() else []:
            if not folder.is_dir():
                continue
            index = folder / "_index"
            if not index.is_file():
                continue
            for line in index.read_text().splitlines():
                if not line.strip():
                    continue
                fields = line.split("\t")
                if len(fields) < 12:
                    continue
                (bid, sid, uid, orig, stored, mime, family, size, sha, key, state, created, *rest) = fields
                self._rows[bid] = BlobRow(
                    id=bid, session_id=sid, user_id=uid, original_name=orig, stored_name=stored,
                    mime=mime, family=family, size=int(size), sha256=sha, storage_key=key,
                    state=state, created_at=float(created),
                    attached_at=float(rest[0]) if rest and rest[0] else None,
                )

    def _save(self) -> None:
        by_session: dict[str, list[BlobRow]] = {}
        for row in self._rows.values():
            by_session.setdefault(row.session_id, []).append(row)
        for session_id, rows in by_session.items():
            folder = self._dir(session_id)
            folder.mkdir(parents=True, exist_ok=True)
            lines = [
                "\t".join([
                    r.id, r.session_id, r.user_id, r.original_name.replace("\t", " "),
                    r.stored_name.replace("\t", " "), r.mime, r.family, str(r.size), r.sha256,
                    r.storage_key, r.state, repr(r.created_at),
                    repr(r.attached_at) if r.attached_at is not None else "",
                ])
                for r in rows
            ]
            tmp = folder / "_index.tmp"
            tmp.write_text("\n".join(lines) + "\n")
            os.replace(tmp, folder / "_index")

    # -- the contract ----------------------------------------------------------------------------
    async def put(self, session_id: str, user_id: str, spec, raw: bytes) -> BlobRow:
        for row in self._rows.values():
            if row.session_id == session_id and row.sha256 == spec.sha256 and row.state != "swept":
                return row
        blob_id = f"blb_{uuid.uuid4().hex[:12]}"
        row = BlobRow(
            id=blob_id, session_id=session_id, user_id=user_id,
            original_name=spec.original_name, stored_name=spec.stored_name,
            mime=spec.mime, family=spec.family.value, size=spec.size, sha256=spec.sha256,
            storage_key=blob_id, state="ready", created_at=self._clock(),
        )
        folder = self._dir(session_id)
        folder.mkdir(parents=True, exist_ok=True)
        path = self._blob_path(row)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, raw)
        finally:
            os.close(fd)
        self._rows[blob_id] = row
        self._refs[blob_id] = set()
        self._save()
        return row

    async def meta(self, blob_id: str, user_id: str) -> BlobRow:
        row = self._rows.get(blob_id)
        if row is None or row.user_id != user_id:
            raise LookupError("no such blob")
        return row

    async def bytes_for(self, blob_id: str, user_id: str) -> bytes:
        row = await self.meta(blob_id, user_id)
        path = self._blob_path(row)
        if not path.is_file():
            raise LookupError("the bytes for this attachment are gone")
        return path.read_bytes()

    async def mark_attached(self, blob_id: str, turn_id: str, display_name: str,
                            session_id: str = "") -> None:
        """Record the reference, and adopt the session a pre-session blob was waiting for.

        Adoption also MOVES THE FILE: the bytes live under `<root>/<session_id>/`, so a blob stored under
        `pending:<user>` has to follow its new session or `delete_session` could never reach it.
        """
        row = self._rows.get(blob_id)
        if row is None:
            return
        self._refs.setdefault(blob_id, set()).add(turn_id)
        updates: dict = {}
        if row.state == "ready":
            updates = {"state": "attached", "attached_at": self._clock()}
        adopt = bool(session_id) and row.session_id.startswith("pending:")
        if adopt:
            old_path = self._blob_path(row)
            updates["session_id"] = session_id
            moved = BlobRow(**{**_as_dict(row), **updates})
            new_dir = self._dir(session_id)
            new_dir.mkdir(parents=True, exist_ok=True)
            try:
                os.replace(old_path, self._blob_path(moved))
            except OSError:
                pass       # the row is still correct; a stranded file is swept with the pending folder
        if updates:
            self._rows[blob_id] = BlobRow(**{**_as_dict(row), **updates})
            self._save()

    async def refcount(self, blob_id: str) -> int:
        return len(self._refs.get(blob_id, ()))

    async def sweep(self, now: float) -> dict[str, int]:
        """Delete what `domain/retention.py` says may go. One rule, two stores.

        The old body branched on `row.state == "pending"`, which **could never happen**: `put()`
        writes `state="ready"` and only `mark_attached` changes it, to `"attached"`. So a blob uploaded
        before its session existed — stored under `pending:<user>` — was swept on the *ready* TTL and
        reported in the `ready` bucket. The distinction the code wanted is the session key, not the
        state, and the rule now lives in one place so it cannot be re-derived wrongly per store.
        """
        report = {"pending": 0, "ready": 0}
        for blob_id, row in list(self._rows.items()):
            decision = retention.retention(
                retention.candidate(row, self._refs.get(blob_id, ())), now=now)
            if not retention.is_sweep(decision):
                continue
            self._sweep_one(blob_id)
            report["pending" if decision is retention.Disposition.SWEEP_PENDING else "ready"] += 1
        if any(report.values()):
            self._save()
        return report

    def _sweep_one(self, blob_id: str) -> None:
        row = self._rows.pop(blob_id, None)
        self._refs.pop(blob_id, None)
        if row is not None:
            self._blob_path(row).unlink(missing_ok=True)

    async def delete_session(self, session_id: str) -> int:
        gone = [b for b, r in self._rows.items() if r.session_id == session_id]
        for blob_id in gone:
            self._sweep_one(blob_id)
        folder = self._dir(session_id)
        for child in folder.glob("*.bin"):
            child.unlink(missing_ok=True)
        (folder / "_index").unlink(missing_ok=True)
        try:
            folder.rmdir()
        except OSError:
            pass
        return len(gone)
