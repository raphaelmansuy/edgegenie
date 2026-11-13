"""Lakebase/Postgres journal. One database connection holds the execution-owner advisory lock.

This is deliberately a single active server. Losing that connection fences commits and fails
closed; it never reconnects a stale worker behind a replacement owner's back.
"""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace

from ...domain.events import Event
from ..llm.store import migrate
from ..memory.broadcast import Broadcast
from ...domain.session_index import header, cursor_decode, cursor_encode

OWNER_LOCK = 0x4F50454E47454E49


class PostgresSessionStore(Broadcast):
    durable = True

    def __init__(self, cfg) -> None:
        super().__init__()
        self._cfg = cfg
        self._conn = None
        self._lock = asyncio.Lock()
        self._reader = None
        self._read_lock = asyncio.Lock()

    async def open(self) -> None:
        import psycopg

        if self._conn is not None:
            return
        cls = psycopg.AsyncConnection
        dsn = self._cfg.session_database_url
        if self._cfg.session_use_lakebase:
            from ..llm.store.lakebase import TokenSource, connection_class, resolve_target

            if not self._cfg.llm_pg_endpoint:
                raise RuntimeError("APP_LLM_PG_ENDPOINT is required for the Lakebase session journal")
            target = await asyncio.to_thread(
                resolve_target, self._cfg.llm_pg_endpoint, self._cfg.llm_pg_database, self._cfg.llm_pg_user
            )
            cls = connection_class(TokenSource(target.endpoint))
            dsn = target.conninfo
        conn = await cls.connect(dsn, autocommit=True, connect_timeout=10)
        try:
            async with conn.cursor() as cur:
                await cur.execute("SELECT pg_try_advisory_lock(%s)", (OWNER_LOCK,))
                if not (await cur.fetchone())[0]:
                    raise RuntimeError("session journal already has a server owner; use one worker")
            await migrate.apply(conn)
        except Exception:
            await conn.close()
            raise
        try:
            self._reader = await cls.connect(dsn, autocommit=True, connect_timeout=10)
        except Exception:
            await conn.close()
            raise
        self._conn = conn

    @asynccontextmanager
    async def transaction(self):
        await self.open()
        async with self._lock, self._conn.transaction():
            yield self._conn

    async def snapshot(self, sid):
        await self.open()
        async with self._read_lock, self._reader.cursor() as cur:
            await cur.execute("SELECT body FROM agent.session_snapshot WHERE session_id=%s", (sid,))
            row = await cur.fetchone()
            if not row:
                raise KeyError(sid)
            return row[0]

    async def session_page(self, user, cursor="", limit=50):
        await self.open()
        limit = min(max(limit, 1), 100)
        position = cursor_decode(cursor)
        condition = " AND (updated,id)<(%s,%s)" if position else ""
        params = (user, *position, limit + 1) if position else (user, limit + 1)
        async with self._read_lock, self._reader.cursor() as cur:
            await cur.execute(
                "SELECT header,updated,id FROM agent.session_index WHERE owner=%s AND state!='archived'"
                + condition
                + " ORDER BY updated DESC,id DESC LIMIT %s",
                params,
            )
            rows = await cur.fetchall()
            return {
                "items": [r[0] for r in rows[:limit]],
                "nextCursor": cursor_encode(rows[limit - 1][1], rows[limit - 1][2])
                if len(rows) > limit
                else "",
            }

    async def snapshots(self) -> list[dict]:
        await self.open()
        async with self._read_lock, self._reader.cursor() as cur:
            await cur.execute("SELECT body FROM agent.session_snapshot ORDER BY session_id")
            return [r[0] for r in await cur.fetchall()]

    async def commit(self, event: Event, snapshot: dict, *, participant=None) -> Event:
        from psycopg.types.json import Jsonb

        if self._conn is None:
            raise RuntimeError("session journal was not opened during startup")
        async with self._lock, self._conn.transaction(), self._conn.cursor() as cur:
            if participant:
                await participant(cur)
            if snapshot is None:
                await cur.execute(
                    "UPDATE agent.session_snapshot SET latest_seq=latest_seq+1 WHERE session_id=%s RETURNING latest_seq",
                    (event.session_id,),
                )
            else:
                await cur.execute(
                    """INSERT INTO agent.session_snapshot (session_id, body, latest_seq)
                    VALUES (%s, %s, 1) ON CONFLICT (session_id) DO UPDATE
                    SET body=EXCLUDED.body, latest_seq=agent.session_snapshot.latest_seq+1
                    RETURNING latest_seq""",
                    (event.session_id, Jsonb(snapshot)),
                )
            seq = (await cur.fetchone())[0]
            if snapshot is not None and snapshot.get("session"):
                h = header(snapshot)
                await cur.execute(
                    "INSERT INTO agent.session_index VALUES (%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET updated=EXCLUDED.updated,state=EXCLUDED.state,header=EXCLUDED.header",
                    (event.session_id, h["user_id"], h["updatedAt"], h["status"], Jsonb(h)),
                )
            stored = replace(event, seq=seq)
            await cur.execute(
                "INSERT INTO agent.session_event VALUES (%s, %s, %s)",
                (event.session_id, seq, Jsonb(stored.to_dict())),
            )
        self.publish(event.session_id, stored.to_dict())
        return stored

    async def append(self, event: Event) -> Event:
        async with self._lock, self._conn.cursor() as cur:
            await cur.execute(
                "SELECT body FROM agent.session_snapshot WHERE session_id=%s", (event.session_id,)
            )
            row = await cur.fetchone()
        return await self.commit(event, row[0] if row else {})

    async def since(self, session_id: str, seq: int, limit: int = 2000) -> list[dict]:
        async with self._read_lock, self._reader.cursor() as cur:
            await cur.execute(
                "SELECT body FROM agent.session_event WHERE session_id=%s AND seq>%s ORDER BY seq LIMIT %s",
                (session_id, seq, limit),
            )
            return [r[0] for r in await cur.fetchall()]

    async def latest_seq(self, session_id: str) -> int:
        async with self._read_lock, self._reader.cursor() as cur:
            await cur.execute(
                "SELECT latest_seq FROM agent.session_snapshot WHERE session_id=%s", (session_id,)
            )
            row = await cur.fetchone()
            return row[0] if row else 0

    async def storage(self, sid):
        await self.open()
        async with self._read_lock, self._reader.cursor() as cur:
            await cur.execute(
                "SELECT COUNT(*),COALESCE(SUM(octet_length(body::text)),0) FROM agent.session_event WHERE session_id=%s",
                (sid,),
            )
            count, size = await cur.fetchone()
            await cur.execute(
                "SELECT octet_length(body::text) FROM agent.session_snapshot WHERE session_id=%s", (sid,)
            )
            snapshot = await cur.fetchone()
            return {
                "eventRows": count,
                "eventPayloadBytes": size,
                "snapshotPayloadBytes": snapshot[0] if snapshot else 0,
            }

    async def purge_session(self, sid, *, participant=None):
        async with self.transaction() as conn:
            async with conn.cursor() as cur:
                if participant:
                    await participant(cur)
                for name in ("session_event", "session_snapshot"):
                    await cur.execute(f"DELETE FROM agent.{name} WHERE session_id=%s", (sid,))
                await cur.execute("DELETE FROM agent.session_index WHERE id=%s", (sid,))

    async def close(self) -> None:
        if self._reader is not None:
            await self._reader.close()
            self._reader = None
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
