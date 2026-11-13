"""Single server session journal. Commit snapshot + event before publishing or acknowledging.

SQLite must live on persistent POSIX storage for recovery across host replacement. An exclusive
process lock deliberately refuses a second worker: an in-process task is never a distributed lease.
"""

from __future__ import annotations

import fcntl
import json
import os
import sqlite3
from ...domain.session_index import header, cursor_decode, cursor_encode
from dataclasses import replace
from pathlib import Path

from ...domain.events import Event
from ..memory.broadcast import Broadcast


class SqliteSessionStore(Broadcast):
    durable = True

    def __init__(self, path: str) -> None:
        super().__init__()
        self.path = Path(path).expanduser().resolve()
        self._db = None
        self._owner = None

    def open(self) -> None:
        if self._db is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._owner = open(str(self.path) + ".owner", "a+")
        os.chmod(self._owner.name, 0o600)
        try:
            fcntl.flock(self._owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self._owner.close()
            self._owner = None
            raise RuntimeError("session journal already has a server owner; use one worker") from exc
        try:
            self._db = sqlite3.connect(self.path, check_same_thread=False)
            os.chmod(self.path, 0o600)
            if self._db.execute("PRAGMA user_version").fetchone()[0] > 2:
                raise RuntimeError("session journal schema is newer than this build")
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=FULL")
            self._db.executescript("""
                CREATE TABLE IF NOT EXISTS session_snapshot (
                    session_id TEXT PRIMARY KEY, body TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS session_event (
                    session_id TEXT NOT NULL, seq INTEGER NOT NULL, body TEXT NOT NULL,
                    PRIMARY KEY (session_id, seq)
                );
                CREATE TABLE IF NOT EXISTS session_index (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, updated REAL NOT NULL, state TEXT NOT NULL, header TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS session_index_owner ON session_index(owner,state,updated DESC,id DESC);

            """)
            if self._db.execute("PRAGMA user_version").fetchone()[0] < 2:
                self._db.execute(
                    "INSERT OR IGNORE INTO session_index SELECT session_id,json_extract(body,'$.session.user_id'),coalesce(json_extract(body,'$.lastSeen'),0),json_extract(body,'$.session.status'),json_extract(body,'$.session') FROM session_snapshot WHERE json_extract(body,'$.session.id') IS NOT NULL"
                )
                self._db.execute("PRAGMA user_version=2")
                self._db.commit()
        except Exception:
            self.close()
            raise

    def _connection(self):
        self.open()
        return self._db

    def ledger_connection(self):
        """Paired ledger adapter shares this single database and execution owner."""
        return self._connection()

    async def commit(self, event: Event, snapshot: dict, *, participant=None) -> Event:
        db = self._connection()
        with db:
            if participant:
                await participant(db)
            seq = db.execute(
                "SELECT COALESCE(MAX(seq), 0)+1 FROM session_event WHERE session_id=?", (event.session_id,)
            ).fetchone()[0]
            stored = replace(event, seq=seq)
            db.execute(
                "INSERT INTO session_event VALUES (?, ?, ?)",
                (event.session_id, seq, json.dumps(stored.to_dict())),
            )
            if snapshot is not None:
                db.execute(
                    "INSERT INTO session_snapshot VALUES (?, ?) ON CONFLICT(session_id) DO UPDATE SET body=excluded.body",
                    (event.session_id, json.dumps(snapshot)),
                )
            if snapshot is not None and snapshot.get("session"):
                h = header(snapshot)
                db.execute(
                    "INSERT INTO session_index VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET updated=excluded.updated,state=excluded.state,header=excluded.header",
                    (event.session_id, h["user_id"], h["updatedAt"], h["status"], json.dumps(h)),
                )
        self.publish(event.session_id, stored.to_dict())
        return stored

    async def append(self, event: Event) -> Event:
        db = self._connection()
        row = db.execute(
            "SELECT body FROM session_snapshot WHERE session_id=?", (event.session_id,)
        ).fetchone()
        return await self.commit(event, json.loads(row[0]) if row else {})

    async def snapshot(self, sid):
        row = (
            self._connection()
            .execute("SELECT body FROM session_snapshot WHERE session_id=?", (sid,))
            .fetchone()
        )
        if not row:
            raise KeyError(sid)
        return json.loads(row[0])

    async def session_page(self, user, cursor="", limit=50):
        limit = min(max(limit, 1), 100)
        position = cursor_decode(cursor)
        condition = " AND (updated,id)<(?,?)" if position else ""
        params = (user, *position, limit + 1) if position else (user, limit + 1)
        rows = (
            self._connection()
            .execute(
                "SELECT header,updated,id FROM session_index WHERE owner=? AND state!='archived'"
                + condition
                + " ORDER BY updated DESC,id DESC LIMIT ?",
                params,
            )
            .fetchall()
        )
        items = [json.loads(r[0]) for r in rows[:limit]]
        return {
            "items": items,
            "nextCursor": cursor_encode(rows[limit - 1][1], rows[limit - 1][2])
            if len(rows) > limit
            else "",
        }

    async def snapshots(self) -> list[dict]:
        return [json.loads(r[0]) for r in self._connection().execute("SELECT body FROM session_snapshot")]

    async def since(self, session_id: str, seq: int, limit: int = 2000) -> list[dict]:
        return [
            json.loads(r[0])
            for r in self._connection().execute(
                "SELECT body FROM session_event WHERE session_id=? AND seq>? ORDER BY seq LIMIT ?",
                (session_id, seq, limit),
            )
        ]

    async def latest_seq(self, session_id: str) -> int:
        return (
            self._connection()
            .execute("SELECT COALESCE(MAX(seq), 0) FROM session_event WHERE session_id=?", (session_id,))
            .fetchone()[0]
        )

    async def storage(self, sid):
        db = self._connection()
        count, size = db.execute(
            "SELECT COUNT(*),COALESCE(SUM(length(CAST(body AS BLOB))),0) FROM session_event WHERE session_id=?",
            (sid,),
        ).fetchone()
        snapshot = db.execute(
            "SELECT length(CAST(body AS BLOB)) FROM session_snapshot WHERE session_id=?", (sid,)
        ).fetchone()
        return {
            "eventRows": count,
            "eventPayloadBytes": size,
            "snapshotPayloadBytes": snapshot[0] if snapshot else 0,
        }

    async def purge_session(self, sid, *, participant=None):
        db = self._connection()
        with db:
            if participant:
                await participant(db)
            for name in ("session_event", "session_snapshot"):
                db.execute(f"DELETE FROM {name} WHERE session_id=?", (sid,))
            db.execute("DELETE FROM session_index WHERE id=?", (sid,))

    def close(self) -> None:
        if self._db is not None:
            self._db.close()
            self._db = None
        if self._owner is not None:
            self._owner.close()
            self._owner = None
