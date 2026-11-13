"""Catalogue assets: metadata first, then one bounded name query with named parameters."""

import json
import asyncio
import time
from uuid import uuid4
from ....domain.asset import AssetContent, WorkError, PendingCleanup, digest
from ....domain.asset import AssetRef
from ....domain.policy.sql import classify


class TableHandler:
    def __init__(self, catalog, sql=None):
        self.catalog = catalog
        self.sql = sql

    async def probe(self, who):
        await self.catalog.children(who.token)
        return {
            "read": True,
            "change": False,
            "run": False,
            "tier": "api",
            "reason": "Unity Catalog privileges are the permission boundary.",
        }

    async def read(self, ref, who):
        row = await self.catalog.table(ref.id, who.token)
        return AssetContent(ref, digest(row), json.dumps(row, ensure_ascii=False, indent=2), metadata=row)

    def inside(self, ref, who):
        parts = ref.id.split(".")
        return (
            len(parts) == 3
            and bool(who.scope.schema)
            and ".".join(parts[:2]).casefold() == who.scope.schema.casefold()
        )

    async def creation_candidates(self, source, who):
        candidates = []
        for target in classify(source).created_tables:
            ref = AssetRef("table", target)
            if not self.inside(ref, who):
                raise WorkError("Table creation is outside the working schema.", 403)
            try:
                await self.catalog.table(target, who.token)
            except LookupError:
                candidates.append(target)
        return candidates

    async def cleanup_snapshot(self, ref, who):
        """Cleanup needs object identity and data version, not just a schema hash."""
        value = await self.read(ref, who)
        if value.metadata.get("format", "").upper() != "DELTA" or not value.metadata.get("tableId"):
            raise WorkError("Cleanup requires a verified Delta table identity and data version.")
        quoted = ".".join("`" + part.replace("`", "``") + "`" for part in ref.id.split("."))
        result, _ = await self.catalog.run_sql(
            "DESCRIBE HISTORY " + quoted + " LIMIT 1", who.token, limit=1, wait_seconds=10
        )
        if (result.get("status") or {}).get("state") != "SUCCEEDED":
            raise WorkError("Table data-version observation is pending. Refresh before cleanup.", 503)
        names = [c["name"] for c in result.get("manifest", {}).get("schema", {}).get("columns", [])]
        rows = result.get("result", {}).get("data_array", [])
        if "version" not in names or not rows or len(rows[0]) != len(names):
            raise WorkError("The table history did not expose a verified data version.", 422)
        metadata = {**value.metadata, "dataVersion": rows[0][names.index("version")]}
        return AssetContent(
            ref,
            digest({k: v for k, v in metadata.items() if k != "updatedAt"}),
            json.dumps(metadata, ensure_ascii=False),
            metadata=metadata,
        )

    async def created_resources(self, candidates, who):
        result = []
        for target in candidates:
            ref = AssetRef("table", target)
            if not self.inside(ref, who):
                raise WorkError("Created table moved outside the working schema.", 403)
            value = await self.cleanup_snapshot(ref, who)
            if value.metadata.get("owner") != who.run_as:
                raise PermissionError("The created table owner could not be verified as you.")
            result.append({"asset": ref.to_dict(), "revision": value.revision, "undoAvailable": False})
        return result

    async def remove(self, ref, expect, who):
        if not self.inside(ref, who):
            raise WorkError("Cleanup refused: table is outside the working schema.", 403)
        value = await self.cleanup_snapshot(ref, who)
        if value.revision != expect:
            raise WorkError(
                "Cleanup refused: the table identity, metadata or data version changed.",
                current=value.revision,
            )
        if value.metadata.get("owner") != who.run_as:
            raise PermissionError("Cleanup refused: the table owner changed.")
        if who.delegated:
            if self.sql is None or not self.sql.capabilities()["run"]:
                raise WorkError("SQL cleanup is unavailable for this app identity.", 403)
            # Choose the available SQL tier before calling a native mutation. A denied native
            # API is never used as a signal to retry through another permission boundary.
            from .sql import StatementHandler

            statement = StatementHandler(self.sql)
            quoted = ".".join("`" + part.replace("`", "``") + "`" for part in ref.id.split("."))
            submitted = await statement.submit(
                AssetRef("statement", "cleanup:" + ref.id),
                {"sql": "DROP TABLE " + quoted},
                who,
                "cleanup_" + uuid4().hex,
            )
            if submitted["state"] == "failed":
                raise WorkError("The warehouse refused table cleanup.")
            native = submitted["nativeId"]
            until = time.monotonic() + 15
            while time.monotonic() < until:
                observed = await statement.observe(native, who)
                if observed["state"] == "succeeded":
                    return
                if observed["state"] == "failed":
                    raise WorkError("The table cleanup statement failed. Review SQL history.")
                await asyncio.sleep(0.25)
            raise PendingCleanup(native)
        await self.catalog.remove_table(ref.id, who.token)

    async def cleanup_outcome(self, native, who):
        from .sql import StatementHandler

        return (await StatementHandler(self.sql).observe(native, who))["state"]

    async def describe(self, ref, who):
        value = await self.read(ref, who)
        return {"asset": ref.to_dict(), "revision": value.revision, **value.metadata}

    async def find(self, query, who, limit):
        schema = await self.catalog.table("system.information_schema.tables", who.token)
        columns = {c["name"] for c in schema["columns"]}
        required = {"table_catalog", "table_schema", "table_name"}
        if not required <= columns:
            raise WorkError("Catalogue metadata does not expose the required name fields.", 422)
        limit = min(max(int(limit), 1), 100)
        sql = (
            "SELECT table_catalog, table_schema, table_name FROM system.information_schema.tables "
            "WHERE contains(lower(concat(table_catalog, '.', table_schema, '.', table_name)), :needle) LIMIT "
            + str(limit + 1)
        )
        response, _ = await self.catalog.run_sql(
            sql,
            who.token,
            limit=limit + 1,
            wait_seconds=10,
            parameters=[{"name": "needle", "value": query.casefold(), "type": "STRING"}],
        )
        if (response.get("status") or {}).get("state") != "SUCCEEDED":
            raise WorkError("Catalogue search did not finish within the bounded read.", 503)
        rows = (response.get("result") or {}).get("data_array", [])
        return [
            {"kind": "table", "id": ".".join(row[:3]), "name": row[2], "capped": len(rows) > limit}
            for row in rows[:limit]
        ]
