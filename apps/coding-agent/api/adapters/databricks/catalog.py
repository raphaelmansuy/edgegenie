"""Browse Unity Catalog with the user's token: catalogs -> schemas -> tables -> columns, plus a sample.

Unity Catalog is the permission boundary: this adapter only ever shows what the signed-in user's
token can see, and a denial is a PermissionError, not an empty list.
"""
from __future__ import annotations

import asyncio
import re
import time
from typing import Any

from .http import DbxHttp

_NAME = re.compile(r"^[\w\-]+$")
_FULL = re.compile(r"^[\w\-]+\.[\w\-]+\.[\w\-]+$")
PREVIEW_ROWS = 10

#: Bounds for name search. Unity Catalog has no metastore-wide search endpoint, so this walks
#: catalogs -> schemas -> tables; a user with a large metastore must not pay for an unbounded walk.
SEARCH_SCHEMAS = 24
SEARCH_TTL = 300
SEARCH_BUDGET = 3.5
SEARCH_CONCURRENCY = 8


def _check(name: str, label: str) -> str:
    if not _NAME.match(name or ""):
        raise ValueError(f"invalid {label}: {name!r}")
    return name


def _quote(full_name: str) -> str:
    """`catalog`.`schema`.`table`. The regex allows no backtick, so quoting cannot be escaped."""
    if not _FULL.match(full_name or ""):
        raise ValueError(f"invalid table name: {full_name!r}")
    return ".".join(f"`{p}`" for p in full_name.split("."))


class _Walk:
    """A table-name walk in progress: names arrive as schemas answer, so a search is useful meanwhile."""

    __slots__ = ("key", "at", "names", "done", "task")

    def __init__(self, key: str, at: float) -> None:
        self.key = key
        self.at = at
        self.names: list[str] = []
        self.done = False
        self.task: asyncio.Task | None = None


class CatalogBrowser:
    def __init__(self, host: str, token_provider, http: DbxHttp | None = None) -> None:
        self._http = http or DbxHttp(host, token_provider)
        #: One name walk per credential: the token is the permission boundary, so results cannot be shared.
        self._walks: dict[str, _Walk] = {}

    async def children(self, token: str | None, catalog: str = "", schema: str = "") -> list[dict[str, Any]]:
        """One level: catalogs, or the schemas of a catalog, or the tables of a schema."""
        if not catalog:
            d = await self._http.get("/api/2.1/unity-catalog/catalogs", token)
            rows = [{"kind": "catalog", "name": c["name"], "ref": c["name"], "comment": c.get("comment", "")}
                    for c in d.get("catalogs", [])]
        elif not schema:
            d = await self._http.get("/api/2.1/unity-catalog/schemas", token,
                                     {"catalog_name": _check(catalog, "catalog")})
            rows = [{"kind": "schema", "name": s["name"], "ref": f"{catalog}.{s['name']}",
                     "comment": s.get("comment", "")} for s in d.get("schemas", [])]
        else:
            d = await self._http.get("/api/2.1/unity-catalog/tables", token,
                                     {"catalog_name": _check(catalog, "catalog"),
                                      "schema_name": _check(schema, "schema"), "max_results": 200})
            rows = [{"kind": "table", "name": t["name"], "ref": t.get("full_name") or f"{catalog}.{schema}.{t['name']}",
                     "tableType": t.get("table_type", ""), "comment": t.get("comment", "")}
                    for t in d.get("tables", [])]
        return sorted(rows, key=lambda r: r["name"].lower())

    async def table(self, full_name: str, token: str | None) -> dict[str, Any]:
        _quote(full_name)
        t = await self._http.get(f"/api/2.1/unity-catalog/tables/{full_name}", token)
        cols = [{"name": c["name"], "type": c.get("type_text") or c.get("type_name", ""),
                 "nullable": c.get("nullable", True), "comment": c.get("comment", "")}
                for c in sorted(t.get("columns", []), key=lambda c: c.get("position", 0))]
        return {"fullName": t.get("full_name", full_name), "tableType": t.get("table_type", ""),
                "owner": t.get("owner", ""), "comment": t.get("comment", ""), "columns": cols,
                "format": t.get("data_source_format", ""), "updatedAt": t.get("updated_at"),
                "tableId": t.get("table_id", ""), "createdAt": t.get("created_at")}

    async def remove_table(self, full_name: str, token: str | None):
        _quote(full_name)
        await self._http.request("DELETE", f"/api/2.1/unity-catalog/tables/{full_name}", token)

    async def preview(self, full_name: str, token: str | None) -> dict[str, Any]:
        """The first rows, through the SQL Statement API on a running warehouse the user can use."""
        quoted = _quote(full_name)
        pick = await self._pick_warehouse(token, "run a preview")
        d = await self._http.post("/api/2.0/sql/statements", token, {
            "warehouse_id": pick["id"], "statement": f"SELECT * FROM {quoted} LIMIT {PREVIEW_ROWS}",
            "wait_timeout": "30s", "on_wait_timeout": "CANCEL", "row_limit": PREVIEW_ROWS,
        }, timeout=45.0)
        state = (d.get("status") or {}).get("state")
        if state != "SUCCEEDED":
            err = (d.get("status") or {}).get("error", {}).get("message", state)
            raise RuntimeError(f"preview {str(state).lower()}: {str(err)[:200]}")
        cols = [c["name"] for c in d.get("manifest", {}).get("schema", {}).get("columns", [])]
        return {"columns": cols, "rows": (d.get("result") or {}).get("data_array", []),
                "warehouse": pick.get("name", "")}

    async def _pick_warehouse(self, token: str | None, what: str) -> dict[str, Any]:
        """The warehouse to run on: a running one if there is one, else the first this user can see.

        Shared by the table preview and by cell execution. One definition, so the two cannot disagree
        about which warehouse a user's query lands on — and so `what` can name the user's action in
        the message when none exists.
        """
        wh = await self._http.get("/api/2.0/sql/warehouses", token)
        warehouses = wh.get("warehouses", [])
        pick = next((w for w in warehouses if w.get("state") == "RUNNING"), None) or (
            warehouses[0] if warehouses else None)
        if not pick:
            raise LookupError(f"no SQL warehouse is available to {what}")
        return pick

    async def run_sql(self, statement: str, token: str | None, *, limit: int = 200,
                      wait_seconds: float = 50.0, parameters: list[dict] | None = None) -> tuple[dict[str, Any], str]:
        """Run one SQL statement and return (raw response, warehouse name).

        The raw payload is returned rather than a decoded result so the *domain* decides what a
        result means (`cellrun.result_from_statement`). This adapter knows the API; it does not know
        what a user should be told about it.
        """
        pick = await self._pick_warehouse(token, "run this query")
        payload = await self._http.post("/api/2.0/sql/statements", token, {
            "warehouse_id": pick["id"], "statement": statement,
            "wait_timeout": f"{int(wait_seconds)}s", "on_wait_timeout": "CANCEL", "row_limit": limit,
            **({"parameters": parameters} if parameters is not None else {}),
        }, timeout=wait_seconds + 15)
        return payload, pick.get("name", "")

    async def pick_warehouse(self, token: str | None) -> dict[str, Any]:
        """The warehouse a cell runs on (a running one if there is one). `LookupError` when there is none."""
        return await self._pick_warehouse(token, "run this query")

    async def submit_statement(self, warehouse_id: str, statement: str, token: str | None, *,
                               limit: int, parameters: list[dict[str, str]] | None = None) -> dict[str, Any]:
        """Start one statement and return the raw response. It may already be finished.

        The adapter only knows the API. `CONTINUE` is deliberate: a statement still running after the
        short wait keeps running and is polled by id, instead of being cancelled at 50 seconds, which
        is the platform's longest synchronous wait and nobody's idea of a query limit.
        """
        body: dict[str, Any] = {
            "warehouse_id": warehouse_id, "statement": statement,
            "wait_timeout": "5s", "on_wait_timeout": "CONTINUE", "row_limit": limit,
        }
        if parameters:
            body["parameters"] = parameters   # named markers (`:name`); every value is a STRING, as a widget's is
        return await self._http.post("/api/2.0/sql/statements", token, body, timeout=30.0)

    async def statement(self, statement_id: str, token: str | None) -> dict[str, Any]:
        _check(statement_id, "statement id")
        return await self._http.get(f"/api/2.0/sql/statements/{statement_id}", token)

    async def cancel_statement(self, statement_id: str, token: str | None) -> None:
        _check(statement_id, "statement id")
        await self._http.post(f"/api/2.0/sql/statements/{statement_id}/cancel", token, {})

    async def table_names(self, token: str | None) -> list[str]:
        """Every table name this user can see, for name search.

        The walk (catalogs -> schemas -> tables) takes seconds on a real metastore, and Unity Catalog
        has no name-search endpoint, so it runs once and incrementally into a cache. One cache PER
        CREDENTIAL: in a deployed app the caller's token is the permission boundary, and a cache
        filled anonymously at startup showed every user nothing (seen on the deployed app).
        """
        await self._ensure_walk(token)
        return list(self._walk(token).names)

    def _walk(self, token: str | None) -> "_Walk":
        key = (token or "")[-24:] or "anonymous"
        found = self._walks.get(key)
        if found is None or found.at < time.monotonic() - SEARCH_TTL:
            found = _Walk(key=key, at=time.monotonic())
            self._walks[key] = found
            found.task = asyncio.create_task(self._run_walk(token, found))
        return found

    async def _ensure_walk(self, token: str | None) -> None:
        """Start the walk if it is not running, and never make the caller wait for all of it."""
        walk = self._walk(token)
        try:
            await asyncio.wait_for(asyncio.shield(walk.task), 0.4)
        except (TimeoutError, PermissionError, RuntimeError):
            pass

    async def _run_walk(self, token: str | None, walk: "_Walk") -> None:
        """One pass over every schema this user can see, a few requests at a time.

        Sequentially this is hundreds of round trips and a search never finishes; eight at a time
        turns it into a couple of seconds on a real metastore. Names land in `walk.names` as each
        schema answers, so a search during the walk still finds what has arrived.
        """
        try:
            cats = await self._http.get("/api/2.1/unity-catalog/catalogs", token)
        except (PermissionError, RuntimeError):
            walk.done = True
            return
        gate = asyncio.Semaphore(SEARCH_CONCURRENCY)

        async def tables_of(cat: str, schema: str) -> list[str]:
            async with gate:
                try:
                    t = await self._http.get("/api/2.1/unity-catalog/tables", token, {
                        "catalog_name": cat, "schema_name": schema, "max_results": 200})
                except (PermissionError, RuntimeError):
                    return []
                return [tab["full_name"] for tab in t.get("tables", []) if tab.get("full_name")]

        async def schemas_of(cat: str) -> list[tuple[str, str]]:
            async with gate:
                try:
                    s = await self._http.get("/api/2.1/unity-catalog/schemas", token, {"catalog_name": cat})
                except (PermissionError, RuntimeError):
                    return []
                return [(cat, sch["name"]) for sch in s.get("schemas", [])[:SEARCH_SCHEMAS]]

        # Both levels in parallel: catalogs -> schemas must not be a sequential loop, or a workspace
        # with three catalogs pays three seconds before the first table request is even sent.
        groups = await asyncio.gather(*(schemas_of(c.get("name", "")) for c in cats.get("catalogs", [])))
        tasks = [asyncio.create_task(tables_of(c, s)) for group in groups for c, s in group]
        for done in asyncio.as_completed(tasks):
            walk.names.extend(await done)
        walk.done = True

    async def find(self, token: str | None, needle: str, limit: int = 8) -> list[dict[str, Any]]:
        """Tables whose name contains `needle`, best match first.

        The walk is incremental, so this re-checks the cache while it fills and returns the moment
        something matches: a search never waits for the whole metastore, and never returns nothing
        just because the user typed before the cache was warm.
        """
        q = (needle or "").lower().strip()
        if len(q) < 2:
            return []
        walk = self._walk(token)
        deadline = time.monotonic() + SEARCH_BUDGET
        while True:
            hits = self._score(walk.names, q, limit)
            if hits or walk.done or time.monotonic() >= deadline:
                return hits
            await asyncio.sleep(0.1)

    def _score(self, names: list[str], q: str, limit: int) -> list[dict[str, Any]]:
        scored: list[tuple[float, str]] = []
        for n in list(names):
            low = n.lower()
            leaf = low.rsplit(".", 1)[-1]
            if q in low:
                # a match on the table's own name beats one on its catalog or schema
                scored.append((0 if q in leaf else 1, n))
            elif q in low.replace("_", ""):
                scored.append((1.5, n))
        scored.sort(key=lambda t: (t[0], len(t[1])))
        return [{"kind": "table", "name": n.rsplit(".", 1)[-1], "ref": n, "path": n}
                for _, n in scored[:limit]]

    async def close(self):
        closer=getattr(self._http,'close',None)
        if closer:await closer()
