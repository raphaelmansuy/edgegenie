"""One application path for SQL assets, private context and durable execution intent."""

from __future__ import annotations

import asyncio
import time
from uuid import uuid4

from ..domain import sqlpolicy
from ..domain.sqlquery import (
    TERMINAL,
    QueryProvider,
    QueryStore,
    SqlError,
    digest,
    native_id,
    selected_source,
)


class SqlService:
    def __init__(
        self, provider: QueryProvider, store: QueryStore, *, create_enabled=False, run_enabled=False
    ):
        self.provider, self.store = provider, store
        self.create_enabled = create_enabled or provider.demo
        self.run_enabled = run_enabled or provider.demo
        self._poll_slots = asyncio.Semaphore(4)

    def capabilities(self):
        recovery = self.store.durable or self.provider.demo
        return {
            "demo": self.provider.demo,
            "read": True,
            "create": self.create_enabled,
            "run": self.run_enabled and sqlpolicy.available() and recovery,
            "update": False,
            "durable": self.store.durable,
            "reason": "" if recovery else "Configure a persistent SQL journal before enabling execution.",
            "createReason": "Native creation is gated until deployment interoperability is verified.",
        }

    async def draft(self, actor, body, draft_id=None):
        text = body.get("text", "")
        selected_source(text, None)
        if draft_id:
            old = await self.store.get(actor.scope, "draft", draft_id)
            if body.get("version") != old["version"]:
                raise SqlError(
                    "CONFLICT", "This draft changed in another tab. Recover a separate copy.", 409
                )
        else:
            old = {"id": str(uuid4()), "createdAt": time.time()}
        origin = old.get("originQueryId") or body.get("originQueryId", "")
        if origin:
            origin = native_id(origin)
            await self.provider.get(actor, origin)
        return await self.store.put(
            actor.scope,
            "draft",
            old["id"],
            {
                **old,
                "text": text,
                "name": body.get("name", "Untitled query")[:200],
                "originQueryId": origin,
                "hash": digest(text),
                "warehouseId": body.get("warehouseId", ""),
                "catalog": body.get("catalog", ""),
                "schema": body.get("schema", ""),
                "updatedAt": time.time(),
            },
            old.get("version"),
        )

    async def source(self, actor, kind, ref):
        if kind == "query":
            return await self.provider.get(actor, native_id(ref))
        if kind == "query-draft":
            row = await self.store.get(actor.scope, "draft", native_id(ref))
            if time.time() - row.get("updatedAt", row["createdAt"]) > 7 * 86400:
                raise SqlError("NOT_FOUND", "This draft recovery has expired.", 404)
            return row
        raise SqlError("INVALID_REFERENCE", "Choose a query or private query draft.")

    async def create(self, actor, body, key):
        if not self.create_enabled:
            raise SqlError("CAPABILITY_DISABLED", self.capabilities()["createReason"], 409)
        draft = await self.source(actor, "query-draft", body["draftId"])
        if draft["version"] != body["version"]:
            raise SqlError(
                "CONFLICT", "The draft changed. Review the latest text before creating a Query.", 409
            )
        name, parent = body["name"].strip(), body["parent"].rstrip("/")
        if (
            not name
            or len(name) > 200
            or not parent.startswith("/")
            or ".." in parent.split("/")
            or parent in {"/", "/Users", "/Shared", "/Workspace"}
        ):
            raise SqlError(
                "INVALID_DESTINATION", "Enter a query name and a workspace folder, not a workspace root."
            )
        query = {k: draft.get(k, "") for k in ("text", "warehouseId", "catalog", "schema")}
        query.update(name=name, parent=parent)
        row, fresh = await self.store.reserve(
            actor.scope,
            "create:" + key,
            digest(query),
            {
                "id": str(uuid4()),
                "operationKind": "create",
                "state": "submitting",
                "createdAt": time.time(),
                "query": query,
            },
        )
        if fresh:
            try:
                result = await self.provider.create(actor, query)
                row = await self.store.put(
                    actor.scope,
                    "create",
                    row["id"],
                    {**row, "state": "created_unverified", "queryId": result["id"]},
                    row["version"],
                )
            except (PermissionError, LookupError, SqlError):
                await self.store.put(
                    actor.scope, "create", row["id"], {**row, "state": "failed"}, row["version"]
                )
                raise
            except Exception:
                row = await self.store.put(
                    actor.scope, "create", row["id"], {**row, "state": "create_unknown"}, row["version"]
                )
        if row.get("queryId"):
            try:
                result = await self.provider.get(actor, row["queryId"])
                return {"state": "created", "query": result, "operationId": row["id"]}
            except Exception:
                return {"state": "created_unverified", "queryId": row["queryId"], "operationId": row["id"]}
        return {"state": row["state"], "operationId": row["id"]}

    async def run(self, actor, body, key):
        if not self.capabilities()["run"]:
            raise SqlError(
                "CAPABILITY_DISABLED",
                "SQL execution is not enabled or its parser/durable journal is unavailable.",
                409,
            )
        draft = await self.source(actor, "query-draft", body["draftId"])
        if draft["version"] != body["version"]:
            raise SqlError("CONFLICT", "The source changed. Review it before running.", 409)
        if draft.get("originQueryId"):
            asset = await self.provider.get(actor, draft["originQueryId"])
            if not asset.get("canRun"):
                raise SqlError(
                    "ACCESS_DENIED", asset.get("runReason", "You cannot run the source Query."), 403
                )
        statement = selected_source(draft["text"], body.get("selection"))
        parameters = sqlpolicy.validate(
            statement, body.get("parameters", []), dialect=self.provider.dialect
        )
        warehouse = body["warehouseId"]
        warehouses = await self.provider.warehouses(actor)
        if not any(w["id"] == warehouse for w in warehouses):
            raise SqlError(
                "ACCESS_DENIED",
                "Choose an accessible SQL warehouse; the selected warehouse is unavailable.",
                403,
            )
        payload = {
            "statement": statement,
            "warehouse_id": warehouse,
            "wait_timeout": "0s",
            "format": "JSON_ARRAY",
            "disposition": "INLINE",
            "row_limit": 1000,
            "byte_limit": 4194304,
            "parameters": parameters,
            **({"catalog": body["catalog"]} if body.get("catalog") else {}),
            **({"schema": body["schema"]} if body.get("schema") else {}),
        }
        row, fresh = await self.store.reserve(
            actor.scope,
            "run:" + key,
            digest(payload),
            {
                "id": str(uuid4()),
                "state": "submitting",
                "createdAt": time.time(),
                "name": draft["name"],
                "sourceRef": draft.get("originQueryId") or draft["id"],
                "sourceVersion": draft["version"],
                "text": statement,
                "sourceHash": digest(statement),
                "warehouseId": warehouse,
                "catalog": body.get("catalog", ""),
                "schema": body.get("schema", ""),
                "parameterNames": [p["name"] for p in parameters],
                "inputHash": digest(payload),
                "cancelRequested": False,
            },
        )
        if fresh:
            try:
                response = await self.provider.submit(actor, payload)
                sid = response.get("statement_id")
                if not sid:
                    raise RuntimeError("missing statement handle")
                row = await self.store.put(
                    actor.scope,
                    "run",
                    row["id"],
                    {**row, "statementId": sid, "state": "pending"},
                    row["version"],
                )
            except (PermissionError, LookupError):
                row = await self.store.put(
                    actor.scope,
                    "run",
                    row["id"],
                    {**row, "state": "failed", "error": "The warehouse refused execution."},
                    row["version"],
                )
            except Exception:
                row = await self.store.put(
                    actor.scope, "run", row["id"], {**row, "state": "submission_unknown"}, row["version"]
                )
        return self.public(row)

    @staticmethod
    def public(row):
        result = {k: v for k, v in row.items() if k not in {"parameterValues", "query"}}
        if time.time() - row["createdAt"] > 7 * 86400:
            result.pop("text", None)
        return result

    async def acknowledge(self, actor, run_id):
        row = await self.store.get(actor.scope, "run", native_id(run_id))
        if row.get("statementId") or row["state"] not in {"submission_unknown", "submitting"}:
            raise SqlError(
                "CONFLICT",
                "Only an unresolved submission without a statement handle can be acknowledged.",
                409,
            )
        return self.public(
            await self.store.put(
                actor.scope,
                "run",
                run_id,
                {**row, "state": "outcome_unknown", "acknowledgedAt": time.time()},
                row["version"],
            )
        )

    async def observe(self, actor, run_id, cancel=False):
        row = await self.store.get(actor.scope, "run", native_id(run_id))
        sid = row.get("statementId")
        if not sid:
            if row["state"] == "submitting":
                row = {**row, "state": "submission_unknown"}
            return self.public(row)
        cancel = (
            cancel
            or row.get("cancelRequested", False)
            or (time.time() - row["createdAt"] >= 900 and row["state"] not in TERMINAL)
        )
        if cancel and row["state"] not in TERMINAL:
            if not row["cancelRequested"]:
                row = await self.store.put(
                    actor.scope,
                    "run",
                    run_id,
                    {**row, "cancelRequested": True, "state": "cancel_requested"},
                    row["version"],
                )
            try:
                await self.provider.cancel(actor, sid)
            except PermissionError:
                raise
            except Exception:
                return self.public(row)
        async with self._poll_slots:
            response = await self.provider.status(actor, sid)
        state = (response.get("status") or {}).get("state", "UNKNOWN")
        normalized = {
            "PENDING": "pending",
            "RUNNING": "running",
            "SUCCEEDED": "succeeded",
            "CLOSED": "succeeded",
            "FAILED": "failed",
            "CANCELED": "canceled",
        }.get(state, "reconciling")
        current = await self.store.get(actor.scope, "run", run_id)
        if current["state"] in TERMINAL:
            normalized = current["state"]
        next_row = {
            **current,
            "state": normalized,
            "resultExpired": current.get("resultExpired", False) or state == "CLOSED",
        }
        if normalized in TERMINAL:
            next_row["finishedAt"] = current.get("finishedAt", time.time())
        if state == "FAILED":
            # Upstream messages may echo SQL or bindings. Do not log or persist them verbatim.
            next_row["error"] = (
                "The SQL warehouse could not execute this query. Review its syntax and data permissions."
            )
        try:
            row = await self.store.put(actor.scope, "run", run_id, next_row, current["version"])
        except SqlError as exc:
            if exc.code != "CONFLICT":
                raise
            row = await self.store.get(actor.scope, "run", run_id)
        result = self.public(row)
        if state == "SUCCEEDED" and result["state"] == "succeeded":
            manifest = response.get("manifest") or {}
            columns = (manifest.get("schema") or {}).get("columns", [])
            rows = (response.get("result") or {}).get("data_array", [])
            if any(len(r) != len(columns) for r in rows):
                raise SqlError("UPSTREAM_PROTOCOL", "Result rows do not match the returned schema.", 502)
            result["result"] = {
                "columns": columns[:200],
                "rows": [r[:200] for r in rows[:1000]],
                "truncated": bool(
                    manifest.get("truncated")
                    or len(columns) > 200
                    or len(rows) > 1000
                    or (response.get("result") or {}).get("next_chunk_index") is not None
                ),
                "rowCount": len(rows[:1000]),
                "totalRows": manifest.get("total_row_count"),
            }
        return result

    async def history(self, actor):
        rows = await self.store.list(actor.scope, "run")
        return [{k: v for k, v in row.items() if k not in {"text", "parameterNames"}} for row in rows]
