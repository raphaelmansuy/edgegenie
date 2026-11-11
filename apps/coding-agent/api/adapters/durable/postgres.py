"""Lakebase/Postgres journal. One database connection holds the execution-owner advisory lock.

This is deliberately a single active server: one process owns the journal, and the owner lock is a
session-level advisory lock, so it lives exactly as long as the connection that took it.

What this module guarantees, and why each guarantee exists (measured, not assumed):

1. **A caller that is cancelled never interrupts a statement.** Every operation runs as its own
   task, shielded from the caller. A browser tab that closes mid-stream, a client timeout, or a
   cancelled turn used to cancel the `await` *inside* psycopg while a command was in flight. libpq
   then still owned an unread result, so every later query on the shared connection failed with
   `sending query failed: another command is already in progress` — for every session, until the
   process restarted. Reproduced: `tests/test_session_journal_resilience.py` (4 runs of 6 before the
   fix, 0 after).
2. **A connection that is not provably healthy is never reused.** Before an operation the connection
   must be open, not broken, and idle. Otherwise it is discarded and a new one is made.
3. **Reconnecting never steals ownership.** A new connection must win the owner lock again. If a
   replacement server holds it, this one fails closed with the owner error, as before.
4. **A connection that sat idle is proved alive before a write.** Lakebase suspends idle computes and
   NATs drop idle sockets; a write must not be the first thing to find out.
"""

import asyncio
import contextlib
import logging
import time
from dataclasses import replace

from ...domain.events import Event
from ..llm.store import migrate
from ..memory.broadcast import Broadcast

log = logging.getLogger("app.journal")

OWNER_LOCK = 0x4F50454E47454E49

#: Prove a connection alive before using it if it has been idle this long.
IDLE_PING_SECONDS = 15.0
#: After losing our own connection, the dead session's lock can take a moment to be released.
OWNER_RETRY_SECONDS = 10.0
#: libpq options that make a silently dead network path an error instead of a hang.
CONNECT_OPTIONS = {"keepalives": 1, "keepalives_idle": 30, "keepalives_interval": 10,
                   "keepalives_count": 3, "tcp_user_timeout": 30_000, "connect_timeout": 10}


class JournalUnavailable(RuntimeError):
    """The journal could not be reached. Said in a sentence a person can act on, not a driver dump."""


def _is_connection_error(exc: BaseException) -> bool:
    import psycopg
    return isinstance(exc, (psycopg.OperationalError, psycopg.InterfaceError, OSError, TimeoutError))


class PostgresSessionStore(Broadcast):
    durable = True

    def __init__(self, cfg) -> None:
        super().__init__()
        self._cfg = cfg
        self._conn = None
        self._lock = asyncio.Lock()
        self._owned_once = False
        self._last_used = 0.0
        self._closed = False

    # -- connection lifecycle ---------------------------------------------------
    async def _connect(self):
        """A new connection that holds the owner lock, with the schema applied."""
        import psycopg
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
        conn = await cls.connect(dsn, autocommit=True, **CONNECT_OPTIONS)
        try:
            # A reconnect may race the release of the lock held by the connection it replaces.
            deadline = time.monotonic() + (OWNER_RETRY_SECONDS if self._owned_once else 0.0)
            while True:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT pg_try_advisory_lock(%s)", (OWNER_LOCK,))
                    if (await cur.fetchone())[0]:
                        break
                if time.monotonic() >= deadline:
                    raise RuntimeError("session journal already has a server owner; use one worker")
                await asyncio.sleep(0.5)
            await migrate.apply(conn)
        except BaseException:
            await self._close_quietly(conn)
            raise
        self._owned_once = True
        self._last_used = time.monotonic()
        return conn

    @staticmethod
    async def _close_quietly(conn) -> None:
        if conn is None:
            return
        with contextlib.suppress(Exception, asyncio.CancelledError):
            await asyncio.wait_for(conn.close(), 5)

    @staticmethod
    def _usable(conn) -> bool:
        """Open, not broken, and between commands. Anything else may hold an unread result."""
        from psycopg.pq import TransactionStatus
        if conn is None or conn.closed or conn.broken:
            return False
        return conn.pgconn.transaction_status == TransactionStatus.IDLE

    async def _discard(self) -> None:
        conn, self._conn = self._conn, None
        await self._close_quietly(conn)

    async def _ensure(self) -> None:
        """Called with the lock held. Leaves `self._conn` usable or raises."""
        if self._closed:
            raise JournalUnavailable("the session journal is closed")
        if self._conn is not None and not self._usable(self._conn):
            log.warning("session journal connection is not usable (closed, broken or mid-command); reconnecting")
            await self._discard()
        if self._conn is not None and time.monotonic() - self._last_used > IDLE_PING_SECONDS:
            try:
                async with self._conn.cursor() as cur:
                    await cur.execute("SELECT 1")
                    await cur.fetchone()
            except Exception:  # noqa: BLE001 - any failure to answer means the connection is gone
                log.warning("session journal connection did not answer after idling; reconnecting")
                await self._discard()
        if self._conn is None:
            try:
                self._conn = await self._connect()
            except RuntimeError:
                raise                      # owner taken, or misconfigured: say so as it is
            except Exception as exc:  # noqa: BLE001
                raise JournalUnavailable(
                    "the session journal (Lakebase) is not reachable; try again in a moment") from exc

    async def open(self) -> None:
        async with self._lock:
            self._closed = False
            await self._ensure()

    # -- running one operation ---------------------------------------------------
    async def _run(self, op, *, retry: bool = False):
        """Run `op(conn)` exclusively, to completion, whatever happens to the caller.

        The work is a separate task awaited through `shield`: cancelling the caller raises in the
        caller only. The statement finishes, the connection is left idle, and the lock is released by
        the task that took it. `retry` is only for reads: a write whose answer was lost may have
        happened, so it is reported, not repeated.
        """
        async def guarded():
            attempts = 2 if retry else 1
            for attempt in range(attempts):
                async with self._lock:
                    await self._ensure()
                    try:
                        return await op(self._conn)
                    except BaseException as exc:
                        if _is_connection_error(exc) or not self._usable(self._conn):
                            await self._discard()
                            if retry and attempt + 1 < attempts and _is_connection_error(exc):
                                continue
                            if _is_connection_error(exc):
                                raise JournalUnavailable(
                                    "the session journal (Lakebase) dropped the connection; "
                                    "try again in a moment") from exc
                        raise
                    finally:
                        self._last_used = time.monotonic()

        task = asyncio.ensure_future(guarded())
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            # Nobody is waiting for this task any more: collect its outcome so it is not "never retrieved".
            task.add_done_callback(lambda t: t.cancelled() or t.exception())
            raise

    # -- the journal ---------------------------------------------------------------
    async def snapshots(self) -> list[dict]:
        async def op(conn):
            async with conn.cursor() as cur:
                await cur.execute("SELECT body FROM agent.session_snapshot ORDER BY session_id")
                return [r[0] for r in await cur.fetchall()]
        return await self._run(op, retry=True)

    async def commit(self, event: Event, snapshot: dict) -> Event:
        """Append the event AND write the projection, in one transaction.

        Kept for callers that genuinely want both (the terminal event of a turn, an archive, a state
        change where the snapshot is the point). The hot streaming path uses `append()` + a policy
        checkpoint instead, because writing the whole projection per delta was ≈1.8 GB a turn (`[F-4]`).
        """
        from psycopg.types.json import Jsonb

        async def op(conn):
            async with conn.transaction(), conn.cursor() as cur:
                await cur.execute("""INSERT INTO agent.session_snapshot (session_id, body, latest_seq)
                    VALUES (%s, %s, 1) ON CONFLICT (session_id) DO UPDATE
                    SET body=EXCLUDED.body, latest_seq=agent.session_snapshot.latest_seq+1
                    RETURNING latest_seq""", (event.session_id, Jsonb(snapshot)))
                seq = (await cur.fetchone())[0]
                stored = replace(event, seq=seq)
                await cur.execute("INSERT INTO agent.session_event VALUES (%s, %s, %s)",
                                  (event.session_id, seq, Jsonb(stored.to_dict())))
            # Published by the task that wrote it, so a cancelled caller cannot leave a committed
            # event that no subscriber is ever told about.
            self.publish(event.session_id, stored.to_dict())
            return stored
        return await self._run(op)

    async def checkpoint(self, session_id: str, seq: int, body: dict) -> None:
        """Rewrite the projection only. O(size), and NOT on the append path (`[R-5]`).

        `latest_seq` is deliberately not advanced: the sequence belongs to the events, and a checkpoint
        that moved it would make `since(seq)` skip the events written between the last append and this
        write. The checkpoint records what the projection CONTAINS, not how far the log has gone.
        """
        from psycopg.types.json import Jsonb

        async def op(conn):
            async with conn.cursor() as cur:
                await cur.execute("""INSERT INTO agent.session_snapshot (session_id, body, latest_seq)
                    VALUES (%s, %s, %s) ON CONFLICT (session_id) DO UPDATE
                    SET body=EXCLUDED.body""", (session_id, Jsonb(body), seq))
        await self._run(op)

    async def append(self, event: Event) -> Event:
        """Append one event and publish it. O(1) in the event's size: no snapshot is read or written.

        This is the streaming path, and the reason `[F-4]` is fixed: the previous implementation read the
        whole snapshot and wrote it back per event, inside the process-wide lock.
        """
        from psycopg.types.json import Jsonb

        async def op(conn):
            async with conn.transaction(), conn.cursor() as cur:
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
        return await self._run(op)

    async def since(self, session_id: str, seq: int, limit: int = 2000) -> list[dict]:
        async def op(conn):
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT body FROM agent.session_event WHERE session_id=%s AND seq>%s ORDER BY seq LIMIT %s",
                    (session_id, seq, limit))
                return [r[0] for r in await cur.fetchall()]
        return await self._run(op, retry=True)

    async def latest_seq(self, session_id: str) -> int:
        async def op(conn):
            async with conn.cursor() as cur:
                await cur.execute("SELECT latest_seq FROM agent.session_snapshot WHERE session_id=%s",
                                  (session_id,))
                row = await cur.fetchone()
                return row[0] if row else 0
        return await self._run(op, retry=True)

    async def close(self) -> None:
        self._closed = True
        # Wait for an in-flight statement, but not forever: shutdown must finish inside the platform's grace.
        try:
            await asyncio.wait_for(self._lock.acquire(), 5)
            locked = True
        except asyncio.TimeoutError:
            locked = False
        try:
            await self._discard()
        finally:
            if locked:
                self._lock.release()
