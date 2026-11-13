"""Encrypted SQL journal over the existing cancellation-safe Postgres coordinator.

The injected runner owns authentication, reconnection, single-server ownership and shutdown.
Transactions serialize intent reservation before any external SQL submission. Ciphertexts bind
their owner and identity; the deployment KEK derives a separate SQL key, never stored in Postgres.
"""

from __future__ import annotations

import base64
import json
import time

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from ...domain.sqlquery import ACTIVE, SqlError, check_operation, check_run_capacity

SQL_LOCK = 0x53514C4A4F55524E


class PostgresQueryStore:
    durable = True

    def __init__(self, run_operation, key: str = "", shared_key: str = ""):
        self._run = run_operation
        if not key:
            raw = base64.urlsafe_b64decode(shared_key.encode())
            if len(raw) != 32:
                raise ValueError("Persistent SQL recovery requires APP_SQL_KEY or the deployment KEK")
            key = base64.urlsafe_b64encode(HKDF(
                algorithm=hashes.SHA256(), length=32, salt=None,
                info=b"opengenie/sql-journal/v1",
            ).derive(raw)).decode()
        self._cipher = Fernet(key.encode())

    def _encode(self, scope, kind, key, body):
        return self._cipher.encrypt(json.dumps([scope, kind, key, body], ensure_ascii=False).encode())

    def _decode(self, scope, kind, key, data):
        owner, stored_kind, stored_key, body = json.loads(self._cipher.decrypt(bytes(data)))
        if (owner, stored_kind, stored_key) != (scope, kind, key):
            raise SqlError("STORAGE_UNAVAILABLE", "SQL recovery could not be authenticated.", 503)
        return body

    async def _read(self, cur, scope, kind, key):
        await cur.execute("SELECT body FROM agent.sql_item WHERE scope=%s AND kind=%s AND id=%s",
                          (scope, kind, key))
        row = await cur.fetchone()
        if not row:
            raise SqlError("NOT_FOUND", "This item is unavailable or no longer accessible.", 404)
        return self._decode(scope, kind, key, row[0])

    async def get(self, scope, kind, key):
        async def op(conn):
            async with conn.cursor() as cur:
                return await self._read(cur, scope, kind, key)
        return await self._run(op, retry=True)

    async def _write(self, cur, scope, kind, key, body, expected=None):
        await cur.execute("SELECT version FROM agent.sql_item WHERE scope=%s AND kind=%s AND id=%s",
                          (scope, kind, key))
        old = await cur.fetchone()
        if expected is not None and (not old or old[0] != expected):
            raise SqlError("CONFLICT", "This draft or run changed. Reload before applying changes.", 409)
        saved = {**body, "version": old[0] + 1 if old else 1}
        await cur.execute("""INSERT INTO agent.sql_item
            (scope,kind,id,created,version,state,source_ref,body) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(scope,kind,id) DO UPDATE SET version=EXCLUDED.version,
            state=EXCLUDED.state,source_ref=EXCLUDED.source_ref,body=EXCLUDED.body""",
            (scope, kind, key, saved["createdAt"], saved["version"], saved.get("state", ""),
             saved.get("sourceRef", ""), self._encode(scope, kind, key, saved)))
        return saved

    async def put(self, scope, kind, key, body, expected=None):
        async def op(conn):
            async with conn.transaction(), conn.cursor() as cur:
                await cur.execute("SELECT pg_advisory_xact_lock(%s)", (SQL_LOCK,))
                return await self._write(cur, scope, kind, key, body, expected)
        return await self._run(op)

    async def list(self, scope, kind, before=0, limit=50):
        async def op(conn):
            async with conn.cursor() as cur:
                await cur.execute("""SELECT id,body FROM agent.sql_item
                    WHERE scope=%s AND kind=%s AND created<%s ORDER BY created DESC,id DESC LIMIT %s""",
                    (scope, kind, before or time.time() + 1, max(1, min(limit, 50))))
                return [self._decode(scope, kind, row[0], row[1]) for row in await cur.fetchall()]
        return await self._run(op, retry=True)

    async def reserve(self, scope, key, fingerprint, body):
        async def op(conn):
            async with conn.transaction(), conn.cursor() as cur:
                await cur.execute("SELECT pg_advisory_xact_lock(%s)", (SQL_LOCK,))
                await cur.execute("SELECT fingerprint,id,kind,created FROM agent.sql_operation "
                                  "WHERE scope=%s AND key=%s", (scope, key))
                old = await cur.fetchone()
                if old:
                    check_operation(fingerprint, old[0], old[3])
                    return await self._read(cur, scope, old[2], old[1]), False
                kind = body.get("operationKind", "run")
                if kind == "run":
                    await cur.execute("""SELECT scope,source_ref FROM agent.sql_item
                        WHERE kind='run' AND state=ANY(%s) LIMIT 33""", (list(ACTIVE),))
                    active = await cur.fetchall()
                    check_run_capacity([row[1] for row in active if row[0] == scope],
                                       len(active), body.get("sourceRef", ""))
                saved = await self._write(cur, scope, kind, body["id"], body)
                await cur.execute("INSERT INTO agent.sql_operation (scope,key,fingerprint,id,kind,created) "
                                  "VALUES (%s,%s,%s,%s,%s,%s)",
                                  (scope, key, fingerprint, body["id"], kind, time.time()))
                return saved, True
        return await self._run(op)

    def close(self):
        """The shared coordinator owns connection shutdown; no second connection exists here."""
