"""Native Query and Statement adapters share the existing user-authenticated HTTP transport."""

from __future__ import annotations

from ...domain.sqlquery import SqlError, native_id
from .http import DbxHttp

try:
    from sqlglot.dialects.databricks import Databricks as SqlDialect
except ImportError:
    SqlDialect = None


class DatabricksQueries:
    demo = False
    dialect = SqlDialect

    def __init__(self, http: DbxHttp, create_enabled=False):
        self.http, self.create_enabled = http, create_enabled

    async def list(self, actor, cursor, size):
        data = await self.http.get(
            "/api/2.0/sql/queries",
            actor.token,
            {"page_size": size, **({"page_token": cursor} if cursor else {})},
        )
        return {
            "items": [self.normalize(q, False) for q in data.get("results", [])],
            "nextCursor": data.get("next_page_token", ""),
        }

    @staticmethod
    def normalize(q, content=True):
        text = q.get("query_text", "")
        truncated = len(text.encode()) > 200 * 1024
        if truncated:
            text = text.encode()[: 200 * 1024].decode("utf-8", "ignore")
        return {
            "id": native_id(q["id"]),
            "name": q.get("display_name") or "Untitled query",
            "description": q.get("description", "")[:4000],
            "owner": q.get("owner_user_name", ""),
            "modifiedAt": q.get("update_time", ""),
            "warehouseId": q.get("warehouse_id", ""),
            "catalog": q.get("catalog", ""),
            "schema": q.get("schema", ""),
            **(
                {"text": text, "truncated": truncated, "nativeParameters": q.get("parameters", [])}
                if content
                else {}
            ),
        }

    async def get(self, actor, query_id):
        q = await self.http.get(f"/api/2.0/sql/queries/{native_id(query_id)}", actor.token)
        if q.get("lifecycle_state") == "TRASHED":
            raise LookupError("Query is unavailable")
        result = self.normalize(q)
        # Do not infer CAN RUN from GET. Until effective permission lookup is qualified, fail closed.
        result["canRun"] = False
        result["runReason"] = (
            "Saved-query execution requires a verified native permission mapping. Open in Databricks or author a new independent draft."
        )
        return result

    async def create(self, actor, query):
        if not self.create_enabled:
            raise SqlError(
                "CAPABILITY_DISABLED",
                "Native Query creation has not been qualified for this deployment.",
                409,
            )
        result = await self.http.post(
            "/api/2.0/sql/queries",
            actor.token,
            {
                "query": {
                    "display_name": query["name"],
                    "query_text": query["text"],
                    "parent_path": query["parent"],
                    "warehouse_id": query["warehouseId"],
                    "run_as_mode": "VIEWER",
                    **({"catalog": query["catalog"]} if query.get("catalog") else {}),
                    **({"schema": query["schema"]} if query.get("schema") else {}),
                }
            },
        )
        return self.normalize(result)

    async def warehouses(self, actor):
        data = await self.http.get("/api/2.0/sql/warehouses", actor.token)
        return [
            {"id": w["id"], "name": w.get("name", w["id"]), "state": w.get("state", "UNKNOWN")}
            for w in data.get("warehouses", [])
        ]

    async def submit(self, actor, payload):
        return await self.http.post("/api/2.0/sql/statements", actor.token, payload)

    async def status(self, actor, statement_id):
        return await self.http.get(f"/api/2.0/sql/statements/{native_id(statement_id)}", actor.token)

    async def cancel(self, actor, statement_id):
        await self.http.post(f"/api/2.0/sql/statements/{native_id(statement_id)}/cancel", actor.token)


class DemoQueries:
    """Persisted deterministic provider for the local full-stack demo; never touches Databricks."""

    demo = True
    dialect = SqlDialect

    def __init__(self, store):
        self.store = store

    async def list(self, actor, cursor, size):
        await self._seed(actor)
        rows = await self.store.list(actor.scope, "native", limit=50)
        offset = int(cursor or 0)
        return {
            "items": [{k: v for k, v in q.items() if k != "text"} for q in rows[offset : offset + size]],
            "nextCursor": str(offset + size) if offset + size < len(rows) else "",
        }

    async def _seed(self, actor):
        import time

        seeds = [
            (
                "01",
                "Revenue overview",
                "A small, reproducible result to explore the SQL workspace.",
                "SELECT 'North America' AS region, 128400 AS revenue\nUNION ALL SELECT 'Europe', 96350\nUNION ALL SELECT 'Asia Pacific', 78200",
            ),
            (
                "02",
                "Parameter playground",
                "Try a typed named parameter without changing the source.",
                "SELECT :region AS region, 42 AS orders, NULL AS note",
            ),
            (
                "03",
                "Warehouse health",
                "A simple query for checking execution and cancellation.",
                "SELECT 'Connected' AS status, 1 AS warehouse_count",
            ),
        ]
        for suffix, name, description, text in seeds:
            qid = "00000000-0000-4000-8000-0000000000" + suffix
            try:
                await self.store.get(actor.scope, "native", qid)
            except SqlError:
                await self.store.put(
                    actor.scope,
                    "native",
                    qid,
                    {
                        "id": qid,
                        "name": name,
                        "description": description,
                        "text": text,
                        "owner": actor.user,
                        "warehouseId": "demo-warehouse",
                        "catalog": "",
                        "schema": "",
                        "modifiedAt": "2026-11-12T09:30:00Z",
                        "createdAt": time.time() - int(suffix),
                        "canRun": True,
                    },
                )

    async def get(self, actor, query_id):
        await self._seed(actor)
        return await self.store.get(actor.scope, "native", native_id(query_id))

    async def create(self, actor, query):
        import time
        from uuid import uuid4

        qid = str(uuid4())
        return await self.store.put(
            actor.scope,
            "native",
            qid,
            {
                **query,
                "id": qid,
                "owner": actor.user,
                "description": "Created in your SQL workspace",
                "canRun": True,
                "modifiedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "createdAt": time.time(),
            },
        )

    async def warehouses(self, actor):
        return [{"id": "demo-warehouse", "name": "Analytics warehouse", "state": "RUNNING"}]

    async def submit(self, actor, payload):
        import sqlite3
        import time
        from uuid import uuid4

        sid = str(uuid4())
        try:
            with sqlite3.connect(":memory:") as db:
                cursor = db.execute(
                    payload["statement"], {p["name"]: p["value"] for p in payload.get("parameters", [])}
                )
                columns = [{"name": c[0], "type_text": "STRING"} for c in cursor.description or []]
                rows = [[None if v is None else str(v) for v in row] for row in cursor.fetchmany(1001)]
            result = {
                "manifest": {
                    "schema": {"columns": columns},
                    "truncated": len(rows) > 1000,
                    "total_row_count": min(len(rows), 1000),
                },
                "result": {"data_array": rows[:1000]},
            }
        except sqlite3.Error:
            result = {
                "status": {
                    "state": "FAILED",
                    "error": {
                        "message": "The demo engine could not execute this syntax. Use a table-free query; the live provider uses Databricks SQL."
                    },
                }
            }
        await self.store.put(
            actor.scope,
            "statement",
            sid,
            {"id": sid, "createdAt": time.time(), "result": result, "canceled": False},
        )
        return {"statement_id": sid, "status": {"state": "PENDING"}}

    async def status(self, actor, statement_id):
        import time

        row = await self.store.get(actor.scope, "statement", statement_id)
        if row["canceled"]:
            return {"status": {"state": "CANCELED"}}
        elapsed = time.time() - row["createdAt"]
        if elapsed < 3:
            return {"status": {"state": "PENDING" if elapsed < 1 else "RUNNING"}}
        return {"status": {"state": "SUCCEEDED"}, **row["result"]}

    async def cancel(self, actor, statement_id):
        row = await self.store.get(actor.scope, "statement", statement_id)
        import time

        if time.time() - row["createdAt"] < 3:
            await self.store.put(
                actor.scope, "statement", statement_id, {**row, "canceled": True}, row["version"]
            )
