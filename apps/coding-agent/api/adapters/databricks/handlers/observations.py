"""System-table observation tier. Verify metadata before composing one bounded read."""

import json
import time
from ....domain.asset import AssetContent, WorkError, digest


class SystemObservationHandler:
    def __init__(
        self,
        catalog,
        table,
        id_column,
        *,
        kind="system-record",
        order_columns=("period_start_time", "event_time", "usage_start_time", "start_time"),
    ):
        self.catalog, self.table, self.id_column = catalog, table, id_column
        self.kind, self.order_columns = kind, order_columns

    async def columns(self, who):
        schema = await self.catalog.table(self.table, who.token)
        columns = {c["name"] for c in schema["columns"]}
        if self.id_column not in columns:
            raise WorkError(
                "The system table does not expose the expected identifier; no query was executed.", 422
            )
        return columns

    async def probe(self, who):
        if who.delegated and "sql" not in who.scopes:
            raise PermissionError("The app has not been granted sql scope for system-table observation.")
        await self.columns(who)
        return {
            "read": True,
            "change": False,
            "run": False,
            "tier": "system-tables",
            "reason": "Observed through SQL as you. System tables can lag behind native runs; refresh time is shown.",
        }

    async def rows(self, who, id="", limit=25):
        columns = await self.columns(who)
        condition = " WHERE CAST(`" + self.id_column + "` AS STRING) = :record_id" if id else ""
        order = next((name for name in self.order_columns if name in columns), "")
        ordering = " ORDER BY `" + order + "` DESC" if order else ""
        sql = (
            "SELECT * FROM "
            + self.table
            + condition
            + ordering
            + " LIMIT "
            + str(min(max(limit, 1), 100) + 1)
        )
        response, _ = await self.catalog.run_sql(
            sql,
            who.token,
            limit=min(limit, 100) + 1,
            wait_seconds=10,
            parameters=[{"name": "record_id", "value": str(id), "type": "STRING"}] if id else [],
        )
        if (response.get("status") or {}).get("state") != "SUCCEEDED":
            raise WorkError(
                "System-table observation is pending; no native API fallback was attempted.", 503
            )
        names = [c["name"] for c in response.get("manifest", {}).get("schema", {}).get("columns", [])]
        values = (response.get("result") or {}).get("data_array", [])
        return {
            "source": self.table,
            "grain": "One row per system-table record; intervals are not combined.",
            "lastRefreshedAt": time.time(),
            "lag": "System tables may lag; absence does not prove no run exists.",
            "rows": [dict(zip(names, row)) for row in values[:limit]],
            "capped": len(values) > limit,
        }

    async def read(self, ref, who):
        result = await self.rows(who, ref.id)
        return AssetContent(
            ref, digest(result["rows"]), json.dumps(result, ensure_ascii=False, indent=2), metadata=result
        )

    async def describe(self, ref, who):
        result = await self.read(ref, who)
        return {"asset": ref.to_dict(), "revision": result.revision, **result.metadata}

    async def find(self, query, who, limit):
        result = await self.rows(who, query, limit)
        return [
            {
                "kind": self.kind,
                "id": str(r[self.id_column]),
                "record": r,
                "source": self.table,
                "lastRefreshedAt": result["lastRefreshedAt"],
                "lag": result["lag"],
                "capped": result["capped"],
            }
            for r in result["rows"]
        ]

    async def observe(self, id, who):
        data = await self.rows(who, id)
        raw = next(
            (
                r.get("result_state") or r.get("state")
                for r in data["rows"]
                if r.get("result_state") or r.get("state")
            ),
            None,
        )
        state = {
            "SUCCESS": "succeeded",
            "SUCCEEDED": "succeeded",
            "COMPLETED": "succeeded",
            "FAILED": "failed",
            "ERROR": "failed",
            "CANCELED": "cancelled",
            "CANCELLED": "cancelled",
            "TIMEDOUT": "failed",
        }.get(raw, "unobserved")
        return {
            "state": state,
            "result": data,
            "tier": "system-tables",
            "reason": data["lag"] if state == "unobserved" else "",
        }
