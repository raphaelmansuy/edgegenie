"""The migration runner, tested against a REAL Postgres.

Why a real database: this file exists because the runner executed SQL and never recorded the version, so
`schema_version` stayed at 2 no matter how many migrations ran. Every unit test passed — the SQL was
valid, the column appeared — and the bookkeeping was wrong in a way only a database can show you. A fake
cursor would have kept passing, because the bug was in what was NOT executed.

The test is skipped when no Postgres is reachable, and says so. It is not skipped silently: a migration
suite that quietly does nothing is worse than no suite.
"""

from __future__ import annotations

import os

import pytest

psycopg = pytest.importorskip("psycopg")

from api.adapters.llm.store import migrate  # noqa: E402

#: Any libpq DSN. The default points at the throwaway server this suite starts with `scripts/pg-test.sh`.
DSN = os.environ.get("TEST_PG_DSN", "host=/tmp port=55432 user=postgres dbname=llmtest")


async def _fresh(conn) -> None:
    """An empty schema, so a test sees the migrations applied from nothing."""
    async with conn.cursor() as cur:
        await cur.execute("DROP SCHEMA IF EXISTS llm CASCADE")


@pytest.mark.asyncio
async def test_the_runner_records_every_version_it_applies():
    """The bug this file exists for. `apply` ran the files and never inserted into `schema_version`, so
    the table stopped at the highest version a migration had written ITSELF (2), and `EXPECTED_VERSION`
    could never be reached or checked."""
    try:
        conn = await psycopg.AsyncConnection.connect(DSN, autocommit=True)
    except Exception as exc:  # noqa: BLE001 - a missing database is a skip with a reason, not a failure
        pytest.skip(f"no Postgres at {DSN}: {exc}")

    async with conn:
        await _fresh(conn)
        version = await migrate.apply(conn)
        assert version == migrate.EXPECTED_VERSION, "the returned version must be the expected one"
        async with conn.cursor() as cur:
            await cur.execute("SELECT version FROM llm.schema_version ORDER BY version")
            recorded = [r[0] for r in await cur.fetchall()]
        assert recorded == list(range(1, migrate.EXPECTED_VERSION + 1)), (
            f"every applied migration must be recorded; got {recorded}")


@pytest.mark.asyncio
async def test_applying_twice_changes_nothing():
    """Forward-only and idempotent: a second boot must not re-run or fail."""
    try:
        conn = await psycopg.AsyncConnection.connect(DSN, autocommit=True)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"no Postgres at {DSN}: {exc}")

    async with conn:
        await _fresh(conn)
        first = await migrate.apply(conn)
        second = await migrate.apply(conn)
        assert first == second == migrate.EXPECTED_VERSION
        async with conn.cursor() as cur:
            await cur.execute("SELECT count(*) FROM llm.schema_version")
            assert (await cur.fetchone())[0] == migrate.EXPECTED_VERSION


@pytest.mark.asyncio
async def test_the_vision_column_exists_and_defaults_to_false():
    """[D7]: the column is the fact. `false` is the safe default — an image is labelled, never sent blind."""
    try:
        conn = await psycopg.AsyncConnection.connect(DSN, autocommit=True)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"no Postgres at {DSN}: {exc}")

    async with conn:
        await _fresh(conn)
        await migrate.apply(conn)
        async with conn.cursor() as cur:
            await cur.execute("""
                SELECT data_type, is_nullable, column_default
                  FROM information_schema.columns
                 WHERE table_schema = 'llm' AND table_name = 'llm_model'
                   AND column_name = 'sees_images'""")
            row = await cur.fetchone()
        assert row is not None, "migration 003 did not add llm_model.sees_images"
        data_type, nullable, default = row
        assert data_type == "boolean"
        assert nullable == "NO"
        assert "false" in (default or "")
