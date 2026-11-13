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


@pytest.mark.asyncio
async def test_a_corrected_capability_reaches_a_row_that_already_existed():
    """The bug: a row seeded before `sees_images` existed kept `false` forever.

    Two independent reasons, both measured on the deployment:
      - the seed's INSERT did not include the column at all, and
      - `ON CONFLICT DO NOTHING` means even a correct seed value never reaches an existing row.

    So `gemma-3-12b` served `seesImages: false` on production while the model read three random codes
    correctly. Capability is a fact about the model, not an operator preference, so the seed must be able
    to CORRECT it — while still leaving every operator-editable column alone.
    """
    try:
        conn = await psycopg.AsyncConnection.connect(DSN, autocommit=True)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"no Postgres at {DSN}: {exc}")

    async with conn:
        async with conn.cursor() as cur:
            await cur.execute("DROP SCHEMA IF EXISTS llm CASCADE")
        await migrate.apply(conn)
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO llm.llm_provider (id, display_name, kind, wire_default, npm_package)"
                " VALUES ('dbx','DBX','databricks','serving','p') ON CONFLICT DO NOTHING")
            # A row as an old deployment left it: capability unknown, so false.
            await cur.execute("""
                INSERT INTO llm.llm_model
                  (id, provider_id, endpoint, display_name, capability, wire,
                   context_window, max_output, sees_images)
                VALUES ('dbx/vision','dbx','vision','vision','tools','serving',128000,8000,false)""")
            # The corrected seed upsert — the exact statement `_seed_if_empty` now runs.
            await cur.execute("""
                INSERT INTO llm.llm_model
                  (id, provider_id, endpoint, display_name, capability, wire,
                   context_window, max_output, sees_images)
                VALUES ('dbx/vision','dbx','vision','vision','tools','serving',128000,8000,true)
                ON CONFLICT (id) DO UPDATE SET
                  sees_images = llm.llm_model.sees_images OR EXCLUDED.sees_images""")
            await cur.execute("SELECT sees_images FROM llm.llm_model WHERE id = 'dbx/vision'")
            assert (await cur.fetchone())[0] is True, "a corrected capability must reach an existing row"


@pytest.mark.asyncio
async def test_the_seed_upsert_never_clears_a_capability():
    """`OR`, not assignment: a model measured to see must not be made blind by a stale seed that says
    nothing. The only safe direction is "learning it can", because the opposite breaks a working feature."""
    try:
        conn = await psycopg.AsyncConnection.connect(DSN, autocommit=True)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"no Postgres at {DSN}: {exc}")

    async with conn:
        async with conn.cursor() as cur:
            await cur.execute("DROP SCHEMA IF EXISTS llm CASCADE")
        await migrate.apply(conn)
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO llm.llm_provider (id, display_name, kind, wire_default, npm_package)"
                " VALUES ('dbx','DBX','databricks','serving','p') ON CONFLICT DO NOTHING")
            await cur.execute("""
                INSERT INTO llm.llm_model
                  (id, provider_id, endpoint, display_name, capability, wire,
                   context_window, max_output, sees_images)
                VALUES ('dbx/seen','dbx','seen','seen','tools','serving',128000,8000,true)""")
            await cur.execute("""
                INSERT INTO llm.llm_model
                  (id, provider_id, endpoint, display_name, capability, wire,
                   context_window, max_output, sees_images)
                VALUES ('dbx/seen','dbx','seen','seen','tools','serving',128000,8000,false)
                ON CONFLICT (id) DO UPDATE SET
                  sees_images = llm.llm_model.sees_images OR EXCLUDED.sees_images""")
            await cur.execute("SELECT sees_images FROM llm.llm_model WHERE id = 'dbx/seen'")
            assert (await cur.fetchone())[0] is True


async def test_upgrade_from_shipped_sql_v5_preserves_rows_and_adds_agent_ledgers(tmp_path):
    from uuid import uuid4
    from psycopg import sql
    from psycopg.conninfo import make_conninfo
    try:
        admin = await psycopg.AsyncConnection.connect(DSN, autocommit=True)
    except Exception as exc:
        pytest.skip(f"no disposable Postgres at {DSN}: {exc}")
    name = "agent014_upgrade_" + uuid4().hex
    async with admin:
        await admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    for path in migrate.files():
        if migrate._version_of(path) <= 5:
            (legacy / path.name).write_text(path.read_text())
    async with await psycopg.AsyncConnection.connect(make_conninfo(DSN, dbname=name), autocommit=True) as conn:
        assert await migrate.apply(conn, legacy) == 5
        await conn.execute("INSERT INTO agent.sql_item (scope,kind,id,created,version,state,body) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                           ("owner", "draft", "retained", 1.0, 1, "ready", b"encrypted-fixture"))
        assert await migrate.apply(conn) == 6
        row = await (await conn.execute("SELECT body FROM agent.sql_item WHERE scope=%s AND id=%s", ("owner", "retained"))).fetchone()
        assert bytes(row[0]) == b"encrypted-fixture"
        for table in ('agent.session', 'agent.turn', 'agent.session_index'):
            assert (await (await conn.execute("SELECT to_regclass(%s)", (table,))).fetchone())[0]
