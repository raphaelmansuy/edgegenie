"""Forward-only SQL migrations, guarded at boot.

Four rules (05 §Migrations):
1. forward only — a rolled-back schema loses keys, and a lost key is not recoverable;
2. idempotent — every file is `IF NOT EXISTS` / `ON CONFLICT DO NOTHING`;
3. no data migration in code — a migration never calls a provider;
4. applied at boot, and a schema *ahead* of the code refuses to start rather than guessing.

This runner exists once. Spec 004 must adopt it rather than add a second (11 R-10).
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger("app.llm.migrations")

MIGRATIONS = Path(__file__).resolve().parent / "migrations"

#: The version this build understands. A database stamped higher refuses to start (E-17).
EXPECTED_VERSION = 2


class SchemaAhead(RuntimeError):
    """The database is newer than this code. Fail fast: degrading would corrupt data quietly."""

    def __init__(self, found: int, expected: int) -> None:
        super().__init__(
            f"the llm schema is version {found} but this build understands {expected}. "
            f"Refusing to start: deploy the matching version rather than writing against unknown columns."
        )
        self.found = found
        self.expected = expected


def files(directory: Path | None = None) -> list[Path]:
    return sorted((directory or MIGRATIONS).glob("*.sql"))


async def apply(conn, directory: Path | None = None) -> int:
    """Apply every pending file, in order. Returns the resulting schema version.

    `conn` is a psycopg async connection. The runner is a thin loop on purpose: the files are the
    specification, and a runner that reorders or skips them is a second specification.
    """
    async with conn.cursor() as cur:
        await cur.execute("CREATE SCHEMA IF NOT EXISTS llm")
        await cur.execute(
            "CREATE TABLE IF NOT EXISTS llm.schema_version ("
            " version integer PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        await cur.execute("SELECT coalesce(max(version), 0) FROM llm.schema_version")
        row = await cur.fetchone()
        current = int(row[0]) if row else 0
        if current > EXPECTED_VERSION:
            raise SchemaAhead(current, EXPECTED_VERSION)
        for path in files(directory):
            if _version_of(path) <= current:
                continue
            log.info("applying %s", path.name)
            await cur.execute(path.read_text("utf-8"))
        await conn.commit()
        await cur.execute("SELECT coalesce(max(version), 0) FROM llm.schema_version")
        row = await cur.fetchone()
        return int(row[0]) if row else 0


def _version_of(path: Path) -> int:
    head = path.name.split("_", 1)[0]
    try:
        return int(head)
    except ValueError:
        raise ValueError(f"{path.name}: a migration must start with its version number") from None
