"""Encrypted SQL journal, independent of chat. Atomic reservations never replay an external POST."""

from __future__ import annotations

import asyncio
import fcntl
import json
import os
import sqlite3
import time
from pathlib import Path

from cryptography.fernet import Fernet

from ...domain.sqlquery import ACTIVE, SqlError


class SqliteQueryStore:
    def __init__(self, path: str = "", key: str = "", production: bool = False):
        self.path, self.key, self.production = path, key, production
        self.durable = bool(path)
        self._db = None
        self._owner = None
        self._lock = asyncio.Lock()

    def open(self):
        if self._db is not None:
            return self._db
        key = self.key.encode()
        if self.path:
            path = Path(self.path).expanduser().resolve()
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if not key:
                if self.production:
                    raise SqlError(
                        "STORAGE_UNAVAILABLE", "Configure APP_SQL_KEY for encrypted SQL recovery.", 503
                    )
                keypath = Path(str(path) + ".key")
                try:
                    fd = os.open(keypath, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                except FileExistsError:
                    key = keypath.read_bytes()
                else:
                    key = Fernet.generate_key()
                    with os.fdopen(fd, "wb") as stream:
                        stream.write(key)
            self._owner = open(str(path) + ".owner", "a+")  # noqa: SIM115 - held until service shutdown
            os.chmod(self._owner.name, 0o600)
            try:
                fcntl.flock(self._owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                self._owner.close()
                self._owner = None
                raise SqlError(
                    "STORAGE_UNAVAILABLE", "SQL journal has another server owner; use one worker.", 503
                ) from exc
            self._db = sqlite3.connect(path, check_same_thread=False)
            os.chmod(path, 0o600)
        else:
            self._db = sqlite3.connect(":memory:", check_same_thread=False)
            key = key or Fernet.generate_key()
        self._cipher = Fernet(key)
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS sql_item (
              scope TEXT NOT NULL, kind TEXT NOT NULL, id TEXT NOT NULL, created REAL NOT NULL,
              version INTEGER NOT NULL, state TEXT NOT NULL, body BLOB NOT NULL,
              PRIMARY KEY(scope, kind, id));
            CREATE INDEX IF NOT EXISTS sql_recent ON sql_item(scope,kind,created DESC,id DESC);
            CREATE INDEX IF NOT EXISTS sql_active ON sql_item(kind,state,scope);
            CREATE TABLE IF NOT EXISTS sql_operation (
              scope TEXT NOT NULL, key TEXT NOT NULL, fingerprint TEXT NOT NULL,
              id TEXT NOT NULL, kind TEXT NOT NULL, created REAL NOT NULL, PRIMARY KEY(scope,key));
        """)
        return self._db

    def _encode(self, body):
        return self._cipher.encrypt(json.dumps(body, ensure_ascii=False).encode())

    def _read(self, scope, kind, key):
        row = (
            self.open()
            .execute("SELECT body FROM sql_item WHERE scope=? AND kind=? AND id=?", (scope, kind, key))
            .fetchone()
        )
        if not row:
            raise SqlError("NOT_FOUND", "This item is unavailable or no longer accessible.", 404)
        return json.loads(self._cipher.decrypt(row[0]))

    async def get(self, scope, kind, key):
        async with self._lock:
            return self._read(scope, kind, key)

    def _write(self, scope, kind, key, body, expected=None):
        db = self.open()
        old = db.execute(
            "SELECT version FROM sql_item WHERE scope=? AND kind=? AND id=?", (scope, kind, key)
        ).fetchone()
        if expected is not None and (not old or old[0] != expected):
            raise SqlError(
                "CONFLICT",
                "This draft or run changed in another request. Reload before applying changes.",
                409,
            )
        body = {**body, "version": (old[0] + 1) if old else 1}
        db.execute(
            "INSERT INTO sql_item VALUES (?,?,?,?,?,?,?) ON CONFLICT(scope,kind,id) DO UPDATE SET version=excluded.version,state=excluded.state,body=excluded.body",
            (
                scope,
                kind,
                key,
                body["createdAt"],
                body["version"],
                body.get("state", ""),
                self._encode(body),
            ),
        )
        return body

    async def put(self, scope, kind, key, body, expected=None):
        async with self._lock:
            with self.open():
                return self._write(scope, kind, key, body, expected)

    async def list(self, scope, kind, before=0, limit=50):
        async with self._lock:
            # This is an explicitly bounded recent window, deterministically ordered by time and ID.
            rows = (
                self.open()
                .execute(
                    "SELECT body FROM sql_item WHERE scope=? AND kind=? AND created<? ORDER BY created DESC,id DESC LIMIT ?",
                    (scope, kind, before or time.time() + 1, min(limit, 50)),
                )
                .fetchall()
            )
            return [json.loads(self._cipher.decrypt(row[0])) for row in rows]

    async def reserve(self, scope, key, fingerprint, body):
        async with self._lock:
            db = self.open()
            with db:
                old = db.execute(
                    "SELECT fingerprint,id,kind,created FROM sql_operation WHERE scope=? AND key=?",
                    (scope, key),
                ).fetchone()
                if old:
                    if old[0] != fingerprint:
                        raise SqlError("CONFLICT", "This operation key belongs to different input.", 409)
                    if time.time() - old[3] > 86400:
                        raise SqlError(
                            "CONFLICT", "This operation key has expired; it cannot be replayed.", 409
                        )
                    return self._read(scope, old[2], old[1]), False
                kind = body.get("operationKind", "run")
                if kind == "run":
                    states = tuple(ACTIVE)
                    marks = ",".join("?" for _ in states)
                    count = db.execute(
                        f"SELECT COUNT(*) FROM sql_item WHERE scope=? AND kind='run' AND state IN ({marks})",
                        (scope, *states),
                    ).fetchone()[0]
                    total = db.execute(
                        f"SELECT COUNT(*) FROM sql_item WHERE kind='run' AND state IN ({marks})", states
                    ).fetchone()[0]
                    if count >= 4 or total >= 32:
                        raise SqlError(
                            "RUN_LIMIT",
                            "Too many active SQL runs. Cancel or resolve an existing run first.",
                            409,
                        )
                    source = body.get("sourceRef", "")
                    if source:
                        active = db.execute(
                            f"SELECT body FROM sql_item WHERE scope=? AND kind='run' AND state IN ({marks})",
                            (scope, *states),
                        ).fetchall()
                        if any(
                            json.loads(self._cipher.decrypt(row[0])).get("sourceRef") == source
                            for row in active
                        ):
                            raise SqlError(
                                "RUN_LIMIT", "This query already has an active or unresolved run.", 409
                            )
                saved = self._write(scope, kind, body["id"], body)
                db.execute(
                    "INSERT INTO sql_operation VALUES (?,?,?,?,?,?)",
                    (scope, key, fingerprint, body["id"], kind, time.time()),
                )
                return saved, True

    def close(self):
        if self._db is not None:
            self._db.close()
            self._db = None
        if self._owner is not None:
            self._owner.close()
            self._owner = None
