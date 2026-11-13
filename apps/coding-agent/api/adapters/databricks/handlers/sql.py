"""SQL and saved Query assets reuse spec 013's service, validation, store and permission gates."""

import json
import time
from ....domain.asset import AssetContent, AssetRef, Plan, WorkError, digest
from ....domain.sqlquery import SqlActor, SqlError
from ....domain.policy.paths import inside
from ....domain.policy.sql import classify
from ....domain.policy.verdict import ActionClass


class StatementHandler:
    def __init__(self, service, resources=None):
        self.service = service
        self.resources = resources

    def sql_actor(self, who):
        return SqlActor(who.workspace, who.user_id, who.token, who.run_as)

    async def probe(self, who):
        capability = self.service.capabilities()
        await self.service.provider.warehouses(self.sql_actor(who))
        return {
            "read": True,
            "change": False,
            "run": capability["run"],
            "tier": "sql",
            "reason": "Statements run as you through the SQL editor service.",
        }

    def inside(self, ref, who):
        return True

    def requires_review(self, params):
        return classify(params.get("sql", "")).action is ActionClass.IRREVERSIBLE

    async def submit(self, ref, params, who, key):
        from ....domain.policy.sql import mutation_parameters

        mutation_parameters(
            params.get("sql", ""),
            params.get("parameters", []),
            schema=who.scope.schema or "",
            dialect=self.service.provider.dialect,
        )
        created = (
            await self.resources.creation_candidates(params.get("sql", ""), who) if self.resources else []
        )
        actor = self.sql_actor(who)
        warehouses = await self.service.provider.warehouses(actor)
        chosen = params.get("warehouse_id") or next(
            (w["id"] for w in warehouses if w.get("state") == "RUNNING"),
            warehouses[0]["id"] if warehouses else "",
        )
        if not chosen:
            raise WorkError("No accessible warehouse is available.", 422)
        draft = await self.service.draft(
            actor,
            {
                "text": "/* opengenie-operation:" + key + " */\n" + params.get("sql", ""),
                "name": "Agent statement " + key,
                "warehouseId": chosen,
                "originQueryId": params.get("originQueryId", ""),
            },
        )
        result = await self.service.run(
            actor,
            {
                "draftId": draft["id"],
                "version": draft["version"],
                "warehouseId": chosen,
                "parameters": params.get("parameters", []),
            },
            key,
            mutation_scope=who.scope.schema or "",
            created_tables=created,
        )
        return {
            "nativeId": result["id"],
            **(
                {"undoAvailable": False}
                if classify(params.get("sql", "")).action is not ActionClass.READ
                else {}
            ),
            "statementId": result.get("statementId", ""),
            "state": "running"
            if result.get("statementId")
            else "failed"
            if result["state"] == "failed"
            else "unknown",
            "reason": result.get("error", "")
            if result.get("statementId")
            else "SQL submission outcome is unknown. Lookup only; do not resubmit.",
            "tier": "sql",
        }

    async def observe(self, native, who):
        row = await self.service.observe(self.sql_actor(who), native)
        return {
            "state": {
                "canceled": "cancelled",
                "succeeded": "succeeded",
                "failed": "failed",
                "submission_unknown": "unknown",
                "outcome_unknown": "unknown",
                "reconciling": "unobserved",
            }.get(row["state"], "running"),
            "result": row.get("result", {}),
            "reason": row.get("error", ""),
            "statementId": row.get("statementId"),
            "stateVersion": row.get("version", 0),
        }

    async def lookup(self, key, who):
        return await self.service.lookup_operation(self.sql_actor(who), key)

    async def created_resources(self, native, who):
        row = await self.service.store.get(self.sql_actor(who).scope, "run", native)
        candidates = row.get("createdTableCandidates", [])
        return (
            await self.resources.created_resources(candidates, who) if self.resources and candidates else []
        )

    async def cancel(self, native, who):
        await self.service.observe(self.sql_actor(who), native, cancel=True)

    async def result_page(self, native, chunk, who):
        return await self.service.result_page(self.sql_actor(who), native, chunk)

    async def read(self, ref, who):
        row = await self.service.observe(self.sql_actor(who), ref.id)
        return AssetContent(ref, digest(row), json.dumps(row, ensure_ascii=False, indent=2), metadata=row)

    async def describe(self, ref, who):
        value = await self.read(ref, who)
        return {"asset": ref.to_dict(), "revision": value.revision, **value.metadata}

    async def find(self, query, who, limit):
        return (await self.service.history(self.sql_actor(who)))[:limit]


class QueryHandler:
    def __init__(self, service, kind="query", resources=None):
        self.service, self.kind = service, kind
        self.resources = resources

    def actor(self, who):
        return SqlActor(who.workspace, who.user_id, who.token, who.run_as)

    def inside(self, ref, who):
        return inside(ref.id, who.scope.folder) if ref.id.startswith("/") else True

    async def probe(self, who):
        await self.service.provider.list(self.actor(who), "", 1)
        c = self.service.capabilities()
        return {
            "read": True,
            "change": c["create"] and self.kind == "query",
            "run": c["run"],
            "tier": "api",
            "reason": "New Query copies only; native in-place update remains gated by spec 013.",
        }

    async def read(self, ref, who):
        row = await self.service.source(self.actor(who), self.kind, ref.id)
        return AssetContent(
            ref,
            str(row.get("version") or row.get("modifiedAt") or digest(row)),
            row.get("text", ""),
            "SQL",
            row,
        )

    async def describe(self, ref, who):
        value = await self.read(ref, who)
        return {"asset": ref.to_dict(), "revision": value.revision, **value.metadata}

    async def find(self, query, who, limit):
        if self.kind == "query-draft":
            actor = self.actor(who)
            rows = await self.service.store.list(actor.scope, "draft", limit=min(limit, 50))
            return [
                {"kind": self.kind, "id": row["id"], "name": row.get("name", "Untitled query")}
                for row in rows
                if query.casefold() in row.get("name", "").casefold()
            ]
        page = await self.service.provider.list(self.actor(who), "", min(limit, 100))
        return [r for r in page.get("items", []) if query.casefold() in r.get("name", "").casefold()]

    async def plan(self, ref, base, ops, who, *, content=None):
        if base:
            raise WorkError(
                "Native Query updates are gated. Create a reviewed copy inside your folder.", 422
            )
        if content is None:
            raise WorkError("New Query content is required.", 422)
        if not self.inside(ref, who):
            raise WorkError("Query destination is outside the working folder.", 403)
        return Plan(
            ref,
            "",
            "",
            content,
            [],
            "+ " + content[:65530],
            language="SQL",
            effect="create",
            undo_available=False,
        )

    async def apply(self, plan, who):
        actor = self.actor(who)
        folder, name = plan.ref.id.rsplit("/", 1)
        draft = await self.service.draft(actor, {"text": plan.after, "name": name})
        result = await self.service.create(
            actor,
            {"draftId": draft["id"], "version": draft["version"], "name": name, "parent": folder},
            digest([who.session_id, plan.ref.id, plan.after]),
        )
        if result["state"] != "created":
            raise RuntimeError("Query creation outcome needs reconciliation in SQL history.")
        row = result["query"]
        ref = AssetRef("query", row["id"])
        return AssetContent(ref, str(row.get("modifiedAt") or digest(row)), row.get("text", ""), "SQL", row)

    async def remove(self, ref, expect, who):
        if self.kind != "query":
            raise WorkError("Private draft cleanup is managed by its seven-day recovery policy.", 422)
        current = await self.read(ref, who)
        if current.revision != expect:
            raise WorkError("The Query changed after creation.", current=current.revision)
        parent = current.metadata.get("parent", "")
        name = current.metadata.get("name", "")
        if (
            current.metadata.get("owner") != who.run_as
            or not parent
            or not inside(parent.rstrip("/") + "/" + name, who.scope.folder)
        ):
            raise WorkError(
                "Cleanup refused: this Query moved outside the fence or its owner changed.", 403
            )
        await self.service.provider.delete(self.actor(who), ref.id)

    async def submit(self, ref, params, who, key):
        value = await self.read(ref, who)
        return await StatementHandler(self.service, self.resources).submit(
            ref,
            {
                **params,
                "sql": value.content,
                "originQueryId": ref.id
                if self.kind == "query"
                else value.metadata.get("originQueryId", ""),
            },
            who,
            key,
        )

    async def observe(self, native, who):
        return await StatementHandler(self.service).observe(native, who)

    async def created_resources(self, native, who):
        return await StatementHandler(self.service, self.resources).created_resources(native, who)

    async def lookup(self, key, who):
        return await self.service.lookup_operation(self.actor(who), key)

    async def cancel(self, native, who):
        return await StatementHandler(self.service).cancel(native, who)

    async def result_page(self, native, chunk, who):
        return await self.service.result_page(self.actor(who), native, chunk)
