"""Postgres implementation of the encrypted ledger port, sharing the journal's owner transaction."""

import time
from ...domain.asset import WorkError
from .agent_ledgers import KINDS, LedgerCodec, cursor_value, next_cursor


def table(kind):
    if kind not in KINDS:
        raise ValueError("Unknown ledger entity")
    return 'agent."' + kind + '"'


from functools import wraps


def _operation(read):
    def decorate(method):
        @wraps(method)
        async def call(self, *args, **kwargs):
            async def execute(conn):
                return await method(self, conn, *args, **kwargs)
            run = self.journal.read_operation if read else self.journal.run_operation
            return await run(execute)
        return call
    return decorate


_reader, _writer = _operation(True), _operation(False)


class PostgresAgentLedgers:
    durable = True

    def __init__(self, journal, key):
        self.journal = journal
        self.codec = LedgerCodec(key, production=True)

    async def _get(self, cur, kind, key):
        await cur.execute(f"SELECT body FROM {table(kind)} WHERE id=%s", (key,))
        row = await cur.fetchone()
        if not row:
            raise WorkError("No such ledger item.", 404)
        return self.codec.decode(row[0])

    @_reader
    async def get(self, conn, kind, key):
        async with conn.transaction():
            async with conn.cursor() as cur:
                return await self._get(cur, kind, key)

    async def _put(self, cur, kind, row, expected):
        name = table(kind)
        await cur.execute(f"SELECT version FROM {name} WHERE id=%s FOR UPDATE", (row["id"],))
        old = await cur.fetchone()
        if (expected is None and old) or (expected is not None and (not old or old[0] != expected)):
            raise WorkError("This item was already decided or changed. Reload its current state.")
        saved = {
            **row,
            "createdAt": row.get("createdAt", time.time()),
            "version": expected + 1 if expected is not None else 1,
        }
        asset = saved.get("asset") or {}
        await cur.execute(
            f"""INSERT INTO {name} VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
          ON CONFLICT(id) DO UPDATE SET session_id=EXCLUDED.session_id,owner=EXCLUDED.owner,
          asset_kind=EXCLUDED.asset_kind,asset_id=EXCLUDED.asset_id,native_id=EXCLUDED.native_id,
          state=EXCLUDED.state,version=EXCLUDED.version,body=EXCLUDED.body""",
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
        return saved

    @_writer
    async def batch(self, conn, writes):
        async with conn.transaction():
            async with conn.cursor() as cur:
                return [await self._put(cur, k, r, v) for k, r, v in writes]

    async def put(self, kind, row, expected=None):
        return (await self.batch([(kind, row, expected)]))[0]

    async def commit_transition(self, journal, event, snapshot, turn):
        if journal is not self.journal:
            raise RuntimeError("The journal and ledgers must share one Postgres owner")

        async def participate(cur):
            try:
                old = await self._get(cur, "turn", turn["id"])
            except WorkError:
                old = None
            await self._put(
                cur,
                "turn",
                {**turn, "createdAt": old["createdAt"] if old else time.time()},
                old["version"] if old else None,
            )

        return await journal.commit(event, snapshot, participant=participate)

    @_writer
    async def reserve(self, conn, kind, key, row):
        async with conn.transaction():
            async with conn.cursor() as cur:
                await cur.execute("SELECT id FROM agent.request WHERE kind=%s AND key=%s", (kind, key))
                old = await cur.fetchone()
                if old:
                    return await self._get(cur, kind, old[0]), False
                saved = await self._put(cur, kind, row, None)
                await cur.execute("INSERT INTO agent.request VALUES (%s,%s,%s)", (kind, key, row["id"]))
                return saved, True

    @_reader
    async def page(self, conn, kind, *, session_id="", owner="", cursor="", limit=50, states=()):
        limit = max(1, min(int(limit), 100))
        at, key = cursor_value(cursor)
        where = ["(created<%s OR (created=%s AND id<%s))"]
        args = [at, at, key]
        for column, value in [("session_id", session_id), ("owner", owner)]:
            if value:
                where.append(column + "=%s")
                args.append(value)
        if states:
            where.append("state=ANY(%s)")
            args.append(list(states))
        async with conn.transaction():
            async with conn.cursor() as cur:
                await cur.execute(
                    f"SELECT body FROM {table(kind)} WHERE "
                    + " AND ".join(where)
                    + " ORDER BY created DESC,id DESC LIMIT %s",
                    (*args, limit + 1),
                )
                rows = [self.codec.decode(r[0]) for r in await cur.fetchall()]
        more = len(rows) > limit
        rows = rows[:limit]
        return {"items": rows, "nextCursor": next_cursor(rows, more)}

    @_reader
    async def storage(self, conn, sid):
        async with conn.transaction():
            async with conn.cursor() as cur:
                result = {}
                for kind in KINDS:
                    await cur.execute(
                        f"SELECT COUNT(*),COALESCE(SUM(octet_length(body)),0) FROM {table(kind)} WHERE session_id=%s",
                        (sid,),
                    )
                    count, size = await cur.fetchone()
                    result[kind] = {"rows": count, "payloadBytes": size}
                return result

    async def purge_session(self, journal, sid):
        if journal is not self.journal:
            raise RuntimeError("Session purge requires a shared owner")

        async def participate(cur):
            for kind in KINDS:
                await cur.execute(
                    f"DELETE FROM agent.request WHERE kind=%s AND id IN (SELECT id FROM {table(kind)} WHERE session_id=%s)",
                    (kind, sid),
                )
                await cur.execute(f"DELETE FROM {table(kind)} WHERE session_id=%s", (sid,))

        await journal.purge_session(sid, participant=participate)

    async def close(self):
        pass  # journal owns the connection and its execution-owner lease

    @_writer
    async def prune_previous(self, conn, before, limit=100):
        async with conn.transaction():
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM agent.request WHERE kind='previous_content' AND id IN (SELECT id FROM agent.previous_content WHERE created<%s ORDER BY created,id LIMIT %s)",
                    (before, max(1, min(int(limit), 1000))),
                )
                await cur.execute(
                    "DELETE FROM agent.previous_content WHERE id IN (SELECT id FROM agent.previous_content WHERE created<%s ORDER BY created,id LIMIT %s)",
                    (before, max(1, min(int(limit), 1000))),
                )
                return cur.rowcount

    @_writer
    async def prune_wakeups(self, conn, limit=100):
        async with conn.transaction():
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT id,state,created FROM agent.wakeup WHERE state IN ('fired','cancelled') ORDER BY created,id LIMIT %s",
                    (max(1, min(int(limit), 1000)),),
                )
                for oid, state, created in await cur.fetchall():
                    if state != "fired":
                        continue
                    try:
                        operation = await self._get(cur, "operation", oid)
                    except WorkError:
                        continue
                    if not operation.get("wakeFiredAt"):
                        await self._put(
                            cur,
                            "operation",
                            {**operation, "wakeFiredAt": created or time.time(), "wakeup": "none"},
                            operation["version"],
                        )
                await cur.execute(
                    "DELETE FROM agent.wakeup WHERE id IN (SELECT id FROM agent.wakeup WHERE state IN ('fired','cancelled') ORDER BY created,id LIMIT %s)",
                    (max(1, min(int(limit), 1000)),),
                )
                return cur.rowcount
