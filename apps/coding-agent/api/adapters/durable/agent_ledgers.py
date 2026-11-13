"""Encrypted per-entity ledgers. SQLite and memory share the same transactional contract.

One row is one session, turn, invocation, change, approval, operation, resource, wake-up or usage pass.
The indexed columns support bounded reads; content and previous revisions are envelope encrypted.
"""

from __future__ import annotations
import asyncio
import base64
import dataclasses
import json
import os
import sqlite3
import time
from pathlib import Path
from ...domain.asset import WorkError
from ..llm.vault.envelope import Sealed, seal, open_sealed
from ..llm.vault.kek import EnvKek

KINDS = (
    "session",
    "turn",
    "invocation",
    "change",
    "approval",
    "resource",
    "operation",
    "wakeup",
    "fake_asset",
    "fake_run",
    "previous_content",
    "evidence",
    "usage_pass",
    "preference",
    "outbox",
)


class LedgerCodec:
    def __init__(self, key="", path="", production=False):
        if not key:
            if production:
                raise RuntimeError(
                    "Agent ledgers require APP_AGENT_KEY or the configured LLM KEK in production."
                )
            keyfile = Path(str(path) + ".key") if path else None
            if keyfile and keyfile.exists():
                key = keyfile.read_text()
            else:
                key = base64.urlsafe_b64encode(os.urandom(32)).decode()
                if keyfile:
                    keyfile.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    fd = os.open(keyfile, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                    with os.fdopen(fd, "w") as stream:
                        stream.write(key)
        self.kek = EnvKek(key)

    def encode(self, row):
        sealed = dataclasses.asdict(seal(json.dumps(row, ensure_ascii=False), self.kek))
        return json.dumps(
            {k: base64.b64encode(v).decode() if isinstance(v, bytes) else v for k, v in sealed.items()}
        ).encode()

    def decode(self, raw):
        value = json.loads(bytes(raw))
        return json.loads(
            open_sealed(
                Sealed(**{k: base64.b64decode(v) if k != "kek_key_id" else v for k, v in value.items()}),
                self.kek,
            )
        )


def table(kind):
    if kind not in KINDS:
        raise ValueError("Unknown ledger entity")
    return "agent_" + kind


def cursor_value(cursor):
    if not cursor:
        return (float("inf"), "\uffff")
    try:
        at, key = json.loads(base64.urlsafe_b64decode(cursor))
        return float(at), str(key)
    except Exception:
        raise WorkError("Invalid ledger cursor.", 422) from None


def next_cursor(rows, more):
    return (
        base64.urlsafe_b64encode(json.dumps([rows[-1]["createdAt"], rows[-1]["id"]]).encode()).decode()
        if rows and more
        else ""
    )


class SqliteAgentLedgers:
    def __init__(self, path="", key="", production=False, *, journal=None):
        self.path = path
        self.durable = bool(path)
        self.key = key
        self.production = production
        self._db = None
        self._lock = asyncio.Lock()
        self.journal = journal
        self._borrowed = False

    def open(self):
        if self._db is not None:
            return self._db
        if self.path:
            Path(self.path).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.codec = LedgerCodec(self.key, self.path, self.production)
        if self.journal is not None and hasattr(self.journal, "ledger_connection"):
            self._db = self.journal.ledger_connection()
            self._borrowed = True
        else:
            self._db = sqlite3.connect(self.path or ":memory:", check_same_thread=False)
        if self.path and not self._borrowed:
            os.chmod(self.path, 0o600)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        for kind in KINDS:
            name = table(kind)
            self._db.executescript(f"""CREATE TABLE IF NOT EXISTS {name} (
              id TEXT PRIMARY KEY, session_id TEXT NOT NULL, owner TEXT NOT NULL,
              asset_kind TEXT NOT NULL, asset_id TEXT NOT NULL, native_id TEXT NOT NULL,
              state TEXT NOT NULL, created REAL NOT NULL, version INTEGER NOT NULL, body BLOB NOT NULL);
              CREATE INDEX IF NOT EXISTS {name}_session ON {name}(session_id,created DESC,id DESC);
              CREATE INDEX IF NOT EXISTS {name}_owner ON {name}(owner,created DESC,id DESC);
              CREATE INDEX IF NOT EXISTS {name}_state ON {name}(state,created,id);""")
        self._db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS agent_operation_native ON agent_operation(asset_kind,native_id) WHERE native_id<>''"
        )
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS agent_request (kind TEXT NOT NULL, key TEXT NOT NULL, id TEXT NOT NULL, PRIMARY KEY(kind,key))"
        )
        if self._borrowed:
            self._import_legacy()
        return self._db

    def _import_legacy(self):
        """Copy the former separate database once; keep its file and encryption key intact."""
        self._db.execute("CREATE TABLE IF NOT EXISTS agent_import (source TEXT PRIMARY KEY)")
        if not self.path or not Path(self.path).is_file():
            return
        source = str(Path(self.path).resolve())
        if (
            source == str(self.journal.path)
            or self._db.execute("SELECT 1 FROM agent_import WHERE source=?", (source,)).fetchone()
        ):
            return
        legacy = sqlite3.connect(Path(source).as_uri() + "?mode=ro", uri=True)
        try:
            tables = {r[0] for r in legacy.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            with self._db:
                for name in [*(table(k) for k in KINDS), "agent_request"]:
                    if name not in tables:
                        continue
                    cursor = legacy.execute(f"SELECT * FROM {name}")
                    marks = ",".join("?" for _ in cursor.description)
                    while rows := cursor.fetchmany(100):
                        self._db.executemany(f"INSERT OR IGNORE INTO {name} VALUES ({marks})", rows)
                self._db.execute("INSERT INTO agent_import VALUES (?)", (source,))
        finally:
            legacy.close()

    async def commit_transition(self, journal, event, snapshot, turn):
        async with self._lock:
            db = self.open()

            async def participate(connection):
                if connection is not None and connection is not db:
                    raise RuntimeError("The journal and ledgers must share one SQLite database")
                try:
                    old = self._get("turn", turn["id"])
                except WorkError:
                    old = None
                self._put(
                    "turn",
                    {**turn, "createdAt": old["createdAt"] if old else time.time()},
                    old["version"] if old else None,
                )

            # The memory journal also rolls back ledger writes if acceptance fails.
            with db:
                return await journal.commit(event, snapshot, participant=participate)

    def _get(self, kind, key):
        row = self.open().execute(f"SELECT body FROM {table(kind)} WHERE id=?", (key,)).fetchone()
        if not row:
            raise WorkError("No such ledger item.", 404)
        return self.codec.decode(row[0])

    async def get(self, kind, key):
        async with self._lock:
            return self._get(kind, key)

    def _put(self, kind, row, expected):
        db = self.open()
        name = table(kind)
        old = db.execute(f"SELECT version FROM {name} WHERE id=?", (row["id"],)).fetchone()
        if (expected is None and old) or (expected is not None and (not old or old[0] != expected)):
            raise WorkError("This item was already decided or changed. Reload its current state.")
        saved = {
            **row,
            "createdAt": row.get("createdAt", time.time()),
            "version": expected + 1 if expected is not None else 1,
        }
        asset = row.get("asset") or {}
        try:
            db.execute(
                f"""INSERT INTO {name} VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
              session_id=excluded.session_id,owner=excluded.owner,asset_kind=excluded.asset_kind,asset_id=excluded.asset_id,
              native_id=excluded.native_id,state=excluded.state,version=excluded.version,body=excluded.body""",
                (
                    saved["id"],
                    saved.get("sessionId", ""),
                    saved.get("owner", ""),
                    asset.get("kind", ""),
                    asset.get("id", ""),
                    saved.get("nativeId", ""),
                    saved.get("state", ""),
                    saved["createdAt"],
                    saved["version"],
                    self.codec.encode(saved),
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise WorkError("The native operation is already tracked.") from exc
        return saved

    async def put(self, kind, row, expected=None):
        return (await self.batch([(kind, row, expected)]))[0]

    async def batch(self, writes):
        async with self._lock:
            with self.open():
                return [self._put(kind, row, expected) for kind, row, expected in writes]

    async def reserve(self, kind, key, row):
        async with self._lock:
            db = self.open()
            with db:
                found = db.execute(
                    "SELECT id FROM agent_request WHERE kind=? AND key=?", (kind, key)
                ).fetchone()
                if found:
                    return self._get(kind, found[0]), False
                saved = self._put(kind, row, None)
                db.execute("INSERT INTO agent_request VALUES (?,?,?)", (kind, key, row["id"]))
                return saved, True

    async def page(self, kind, *, session_id="", owner="", cursor="", limit=50, states=()):
        limit = max(1, min(int(limit), 100))
        at, key = cursor_value(cursor)
        where = ["(created<? OR (created=? AND id<?))"]
        args = [at, at, key]
        for column, value in [("session_id", session_id), ("owner", owner)]:
            if value:
                where.append(column + "=?")
                args.append(value)
        if states:
            where.append("state IN (" + ",".join("?" for _ in states) + ")")
            args.extend(states)
        async with self._lock:
            raw = (
                self.open()
                .execute(
                    f"SELECT body FROM {table(kind)} WHERE "
                    + " AND ".join(where)
                    + " ORDER BY created DESC,id DESC LIMIT ?",
                    (*args, limit + 1),
                )
                .fetchall()
            )
            rows = [self.codec.decode(r[0]) for r in raw]
            more = len(rows) > limit
            rows = rows[:limit]
        return {"items": rows, "nextCursor": next_cursor(rows, more)}

    async def storage(self, sid):
        async with self._lock:
            db = self.open()
            return {
                kind: dict(
                    zip(
                        ("rows", "payloadBytes"),
                        db.execute(
                            f"SELECT COUNT(*),COALESCE(SUM(length(body)),0) FROM {table(kind)} WHERE session_id=?",
                            (sid,),
                        ).fetchone(),
                    )
                )
                for kind in KINDS
            }

    async def purge_session(self, journal, sid):
        async with self._lock:
            db = self.open()

            async def participate(connection):
                if connection is not None and connection is not db:
                    raise RuntimeError("Session purge requires a shared database")
                for kind in KINDS:
                    db.execute(
                        f"DELETE FROM agent_request WHERE kind=? AND id IN (SELECT id FROM {table(kind)} WHERE session_id=?)",
                        (kind, sid),
                    )
                    db.execute(f"DELETE FROM {table(kind)} WHERE session_id=?", (sid,))

            with db:
                await journal.purge_session(sid, participant=participate)

    async def close(self):
        if self._db is not None:
            if not self._borrowed:
                self._db.close()
            self._db = None

    async def prune_previous(self, before, limit=100):
        """Bounded retention applies only to undo content, never to the audit or resources."""
        async with self._lock:
            db = self.open()
            with db:
                db.execute(
                    "DELETE FROM agent_request WHERE kind='previous_content' AND id IN (SELECT id FROM agent_previous_content WHERE created<? ORDER BY created,id LIMIT ?)",
                    (before, max(1, min(int(limit), 1000))),
                )
                result = db.execute(
                    "DELETE FROM agent_previous_content WHERE id IN (SELECT id FROM agent_previous_content WHERE created<? ORDER BY created,id LIMIT ?)",
                    (before, max(1, min(int(limit), 1000))),
                )
                return result.rowcount

    async def prune_wakeups(self, limit=100):
        """Retain armed work; fired/cancelled scheduling rows have no further authority."""
        async with self._lock:
            db = self.open()
            with db:
                # Migrate legacy fired rows before discarding their deduplication receipt.
                rows = db.execute(
                    "SELECT id,state,created FROM agent_wakeup WHERE state IN ('fired','cancelled') ORDER BY created,id LIMIT ?",
                    (max(1, min(int(limit), 1000)),),
                ).fetchall()
                for oid, state, created in rows:
                    if state != "fired":
                        continue
                    try:
                        operation = self._get("operation", oid)
                    except WorkError:
                        continue
                    if not operation.get("wakeFiredAt"):
                        self._put(
                            "operation",
                            {**operation, "wakeFiredAt": created or time.time(), "wakeup": "none"},
                            operation["version"],
                        )
                result = db.execute(
                    "DELETE FROM agent_wakeup WHERE id IN (SELECT id FROM agent_wakeup WHERE state IN ('fired','cancelled') ORDER BY created,id LIMIT ?)",
                    (max(1, min(int(limit), 1000)),),
                )
                return result.rowcount


class MemoryAgentLedgers(SqliteAgentLedgers):
    """The same transactional engine in memory, with no file or persistent key."""

    def __init__(self):
        super().__init__()
