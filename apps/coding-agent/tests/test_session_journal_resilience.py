"""The Postgres/Lakebase session journal under the failures a deployment actually has.

The screenshot that started this file: the assistant panel answered "Hello" with
`the agent did not start: sending query failed: another command is already in progress`, repeated
thirty times. First principles: the journal holds ONE connection for every session. If anything
leaves that connection with a command in flight, every later query on it fails, for every user, until
the process restarts. What leaves a command in flight is a cancelled `await` — a closed tab, a client
timeout, a cancelled turn — and nothing in the old code stopped a cancel landing inside psycopg.

These tests need a REAL Postgres (a fake cursor cannot have an unread result). They skip, with the
reason, when none is reachable:   scripts/pg-test.sh start
"""

from __future__ import annotations

import asyncio
import os
import random
import time
from uuid import uuid4

import pytest

psycopg = pytest.importorskip("psycopg")

from api.adapters.durable import postgres as journal  # noqa: E402
from api.adapters.durable.postgres import JournalUnavailable, PostgresSessionStore  # noqa: E402
from api.config import Settings  # noqa: E402
from api.domain.events import Event  # noqa: E402

#: A database of its own. The owner lock is per database, and other files (test_long_running) take it
#: while the suite runs files in parallel; sharing one database would make them fight over it.
DSN = os.environ.get("TEST_JOURNAL_PG_DSN", "host=/tmp port=55432 user=postgres dbname=journaltest")


def _ensure_database() -> None:
    """Create the private database if a server is there and it is missing. No server: tests skip."""
    from psycopg.conninfo import conninfo_to_dict, make_conninfo
    info = conninfo_to_dict(DSN)
    name = info["dbname"]
    try:
        with psycopg.connect(make_conninfo(DSN, dbname="postgres"), autocommit=True, connect_timeout=3) as c:
            if not c.execute("SELECT 1 FROM pg_database WHERE datname=%s", (name,)).fetchone():
                c.execute(f'CREATE DATABASE "{name}"')
    except Exception:  # noqa: BLE001 - no server: the tests below skip with the reason
        pass


_ensure_database()


def _settings() -> Settings:
    return Settings(session_database_url=DSN)


@pytest.fixture
async def store():
    probe = PostgresSessionStore(_settings())
    try:
        await probe.open()
    except Exception as exc:  # noqa: BLE001 - a missing database is a skip with a reason
        pytest.skip(f"no Postgres at {DSN}: {exc}")
    yield probe
    await probe.close()


def _sid() -> str:
    return uuid4().hex


async def _healthy(store: PostgresSessionStore, sid: str) -> None:
    """The store must still do ordinary work, and what it writes must be readable back."""
    ev = await store.append(Event(sid, "message.delta", {"text": "ok"}))
    assert ev.seq == await store.latest_seq(sid)
    assert any(e["seq"] == ev.seq for e in await store.since(sid, 0))


@pytest.mark.asyncio
async def test_cancelling_a_caller_mid_transaction_does_not_wedge_the_connection(store):
    """The production bug. 4 of 6 runs of this loop wedged the old store permanently."""
    sids = [_sid() for _ in range(4)]
    errors: set[str] = set()

    async def op():
        sid = random.choice(sids)
        r = random.random()
        try:
            if r < .4:
                await store.append(Event(sid, "message.delta", {"t": "x" * random.randint(1, 50_000)}))
            elif r < .6:
                await store.commit(Event(sid, "x"), {"b": "y" * random.randint(1, 200_000)})
            elif r < .8:
                await store.since(sid, 0)
            elif r < .9:
                await store.checkpoint(sid, 1, {"b": "z" * 100_000})
            else:
                await store.latest_seq(sid)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            errors.add(f"{type(exc).__name__}: {exc}"[:160])

    for _ in range(25):
        tasks = [asyncio.create_task(op()) for _ in range(40)]
        await asyncio.sleep(random.random() * 0.02)
        for t in random.sample(tasks, 15):
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    assert not errors, errors
    await _healthy(store, sids[0])


@pytest.mark.asyncio
async def test_a_cancelled_write_still_lands_and_is_published(store):
    """Cancelling the CALLER must not tear the write in half: the event is committed and announced."""
    sid = _sid()
    q = store.subscribe(sid)
    task = asyncio.create_task(store.commit(Event(sid, "turn.completed"), {"big": "q" * 400_000}))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    # The statement ran to completion in the background; wait for it, bounded.
    deadline = time.monotonic() + 5
    while await store.latest_seq(sid) == 0 and time.monotonic() < deadline:
        await asyncio.sleep(0.05)
    assert await store.latest_seq(sid) == 1
    assert not q.empty() and q.get_nowait()["seq"] == 1


@pytest.mark.asyncio
async def test_a_server_that_killed_our_backend_is_survived(store):
    """Lakebase suspends idle computes; the next statement finds a dead socket. It must reconnect."""
    sid = _sid()
    await _healthy(store, sid)
    killer = await psycopg.AsyncConnection.connect(DSN, autocommit=True)
    try:
        await killer.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                             "WHERE pid <> pg_backend_pid() AND datname = current_database() "
                             "AND query LIKE '%%' AND pid = %s", (store._conn.pgconn.backend_pid,))
    finally:
        await killer.close()
    await asyncio.sleep(0.2)
    # A write after the kill is not lost and not an error: the idle ping or the usability check sees it.
    store._last_used = time.monotonic() - 3600
    await _healthy(store, sid)
    # And a read on a freshly killed connection is retried once.
    killer = await psycopg.AsyncConnection.connect(DSN, autocommit=True)
    try:
        await killer.execute("SELECT pg_terminate_backend(%s)", (store._conn.pgconn.backend_pid,))
    finally:
        await killer.close()
    await asyncio.sleep(0.2)
    store._last_used = time.monotonic()        # so the ping does not hide the retry path
    assert await store.latest_seq(sid) >= 1


@pytest.mark.asyncio
async def test_a_write_on_a_connection_that_dies_mid_flight_is_reported_not_repeated(store):
    """A lost answer to a write is ambiguous: the write may have happened. It is reported, never replayed."""
    sid = _sid()
    killer = await psycopg.AsyncConnection.connect(DSN, autocommit=True)
    try:
        await killer.execute("SELECT pg_terminate_backend(%s)", (store._conn.pgconn.backend_pid,))
    finally:
        await killer.close()
    await asyncio.sleep(0.2)
    store._last_used = time.monotonic()        # no ping: the write is the first to find out
    with pytest.raises(JournalUnavailable) as err:
        await store.append(Event(sid, "message.delta", {"text": "x"}))
    # A sentence a person can act on, not a driver dump.
    assert "another command" not in str(err.value) and "try again" in str(err.value)
    await _healthy(store, sid)                  # and the very next call works


@pytest.mark.asyncio
async def test_a_second_server_still_cannot_take_ownership():
    first, second = PostgresSessionStore(_settings()), PostgresSessionStore(_settings())
    try:
        try:
            await first.open()
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"no Postgres at {DSN}: {exc}")
        with pytest.raises(RuntimeError, match="server owner"):
            await second.open()
    finally:
        await first.close()
        await second.close()


@pytest.mark.asyncio
async def test_a_reconnect_fails_closed_when_a_replacement_owns_the_journal(monkeypatch, store):
    """Reconnecting must win the owner lock again. A replacement server holding it is never overridden."""
    monkeypatch.setattr(journal, "OWNER_RETRY_SECONDS", 0.6)
    killer = await psycopg.AsyncConnection.connect(DSN, autocommit=True)
    await killer.execute("SELECT pg_terminate_backend(%s)", (store._conn.pgconn.backend_pid,))
    await killer.close()
    # A replacement takes the lock in the gap.
    rival = await psycopg.AsyncConnection.connect(DSN, autocommit=True)
    try:
        for _ in range(50):
            cur = await rival.execute("SELECT pg_try_advisory_lock(%s)", (journal.OWNER_LOCK,))
            if (await cur.fetchone())[0]:
                break
            await asyncio.sleep(0.1)
        store._last_used = time.monotonic() - 3600
        with pytest.raises(RuntimeError, match="server owner"):
            await store.append(Event(_sid(), "message.delta", {}))
    finally:
        await rival.close()


@pytest.mark.asyncio
async def test_concurrent_opens_do_not_mistake_us_for_a_rival():
    s = PostgresSessionStore(_settings())
    try:
        try:
            await s.open()
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"no Postgres at {DSN}: {exc}")
        results = await asyncio.gather(*(s.open() for _ in range(8)), return_exceptions=True)
        assert all(r is None for r in results), results
    finally:
        await s.close()


@pytest.mark.asyncio
async def test_operations_after_close_say_so(store):
    await store.close()
    with pytest.raises(JournalUnavailable, match="closed"):
        await store.latest_seq(_sid())


# -- what the user sees ------------------------------------------------------
def test_a_wedged_driver_message_is_one_sentence_not_thirty():
    from api.routers.api import plain_reason
    raw = "sending query failed: another command is already in progress\n" + (
        "another command is already in progress\n" * 30)
    assert plain_reason(RuntimeError(raw)).count("another command is already in progress") == 2
    assert len(plain_reason(RuntimeError("x" * 5000))) <= 300
    assert plain_reason(RuntimeError("")) == "RuntimeError"


def test_a_journal_outage_on_any_route_is_a_503_with_one_sentence(tmp_path):
    """Routes that journal (send, archive, approve ...) must not turn an outage into a 500 trace."""
    from fastapi.testclient import TestClient
    from api.main import build

    cfg = Settings(agent_mode="fake", default_model="fake/model-a", allowed_models=["fake/model-a"],
                   dev_user="alice")
    app = build(cfg)

    async def down(*_a, **_k):
        raise JournalUnavailable("the session journal (Lakebase) is not reachable; try again in a moment")

    with TestClient(app) as client:
        app.state.orchestrator._store.commit = down          # noqa: SLF001
        r = client.post("/api/sessions", json={"folder": "/Users/alice/agent_scratch"})
        assert r.status_code == 503
        assert r.json()["detail"].startswith("the agent did not start: the session journal")
        assert "another command" not in r.text
        assert client.get("/api/sessions").json() == {"sessions": []}, "no ghost session after the failure"


@pytest.mark.asyncio
async def test_the_model_registry_pool_survives_its_backends_being_killed():
    """Same failure, the other Postgres consumer: a pool must not hand out a connection the server closed."""
    from api.adapters.llm.store.pg import PgRegistryStore
    dsn = DSN
    try:
        registry = await PgRegistryStore.connect(dsn)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"no Postgres at {dsn}: {exc}")
    try:
        before = len(await registry.all_models())
        killer = await psycopg.AsyncConnection.connect(dsn, autocommit=True)
        try:
            await killer.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                                 "WHERE pid <> pg_backend_pid() AND datname = current_database()")
        finally:
            await killer.close()
        await asyncio.sleep(0.3)
        assert len(await registry.all_models()) == before
    finally:
        await registry.close()
