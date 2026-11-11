"""Lakebase/Postgres journal. One database connection holds the execution-owner advisory lock.

This is deliberately a single active server. Losing that connection fences commits and fails
closed; it never reconnects a stale worker behind a replacement owner's back.
"""

import asyncio
from dataclasses import replace

from ...domain.events import Event
from ..llm.store import migrate
from ..memory.broadcast import Broadcast

OWNER_LOCK = 0x4F50454E47454E49


class PostgresSessionStore(Broadcast):
    durable = True

    def __init__(self, cfg) -> None:
        super().__init__()
        self._cfg = cfg
        self._conn = None
        self._lock = asyncio.Lock()

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
            target = await asyncio.to_thread(resolve_target, self._cfg.llm_pg_endpoint,
                                            self._cfg.llm_pg_database, self._cfg.llm_pg_user)
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
        self._conn = conn

    async def snapshots(self) -> list[dict]:
        await self.open()
        async with self._lock, self._conn.cursor() as cur:
            await cur.execute("SELECT body FROM agent.session_snapshot ORDER BY session_id")
            return [r[0] for r in await cur.fetchall()]

    async def commit(self, event: Event, snapshot: dict) -> Event:
        """Append the event AND write the projection, in one transaction.

        Kept for callers that genuinely want both (the terminal event of a turn, an archive, a state
        change where the snapshot is the point). The hot streaming path uses `append()` + a policy
        checkpoint instead, because writing the whole projection per delta was ≈1.8 GB a turn (`[F-4]`).
        """
        from psycopg.types.json import Jsonb
        if self._conn is None:
            raise RuntimeError("session journal was not opened during startup")
        async with self._lock, self._conn.transaction(), self._conn.cursor() as cur:
            await cur.execute("""INSERT INTO agent.session_snapshot (session_id, body, latest_seq)
                VALUES (%s, %s, 1) ON CONFLICT (session_id) DO UPDATE
                SET body=EXCLUDED.body, latest_seq=agent.session_snapshot.latest_seq+1
                RETURNING latest_seq""", (event.session_id, Jsonb(snapshot)))
            seq = (await cur.fetchone())[0]
            stored = replace(event, seq=seq)
            await cur.execute("INSERT INTO agent.session_event VALUES (%s, %s, %s)",
                              (event.session_id, seq, Jsonb(stored.to_dict())))
        self.publish(event.session_id, stored.to_dict())
        return stored

    async def checkpoint(self, session_id: str, seq: int, body: dict) -> None:
        """Rewrite the projection only. O(size), and NOT on the append path (`[R-5]`).

        `latest_seq` is deliberately not advanced: the sequence belongs to the events, and a checkpoint
        that moved it would make `since(seq)` skip the events written between the last append and this
        write. The checkpoint records what the projection CONTAINS, not how far the log has gone.
        """
        from psycopg.types.json import Jsonb
        if self._conn is None:
            raise RuntimeError("session journal was not opened during startup")
        async with self._lock, self._conn.cursor() as cur:
            await cur.execute("""INSERT INTO agent.session_snapshot (session_id, body, latest_seq)
                VALUES (%s, %s, %s) ON CONFLICT (session_id) DO UPDATE
                SET body=EXCLUDED.body""", (session_id, Jsonb(body), seq))

    async def append(self, event: Event) -> Event:
        """Append one event and publish it. O(1) in the event's size: no snapshot is read or written.

        This is the streaming path, and the reason `[F-4]` is fixed: the previous implementation read the
        whole snapshot and wrote it back per event, inside the process-wide lock.
        """
        from psycopg.types.json import Jsonb
        if self._conn is None:
            raise RuntimeError("session journal was not opened during startup")
        async with self._lock, self._conn.transaction(), self._conn.cursor() as cur:
            # `latest_seq` lives on the snapshot row, so it is bumped here — a counter, not a payload.
            await cur.execute("""INSERT INTO agent.session_snapshot (session_id, body, latest_seq)
                VALUES (%s, '{}'::jsonb, 1) ON CONFLICT (session_id) DO UPDATE
                SET latest_seq=agent.session_snapshot.latest_seq+1
                RETURNING latest_seq""", (event.session_id,))
            seq = (await cur.fetchone())[0]
            stored = replace(event, seq=seq)
            await cur.execute("INSERT INTO agent.session_event VALUES (%s, %s, %s)",
                              (event.session_id, seq, Jsonb(stored.to_dict())))
        self.publish(event.session_id, stored.to_dict())
        return stored

    async def since(self, session_id: str, seq: int, limit: int = 2000) -> list[dict]:
        async with self._lock, self._conn.cursor() as cur:
            await cur.execute("SELECT body FROM agent.session_event WHERE session_id=%s AND seq>%s ORDER BY seq LIMIT %s",
                              (session_id, seq, limit))
            return [r[0] for r in await cur.fetchall()]

    async def latest_seq(self, session_id: str) -> int:
        async with self._lock, self._conn.cursor() as cur:
            await cur.execute("SELECT latest_seq FROM agent.session_snapshot WHERE session_id=%s", (session_id,))
            row = await cur.fetchone()
            return row[0] if row else 0

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
