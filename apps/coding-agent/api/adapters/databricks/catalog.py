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
SEARCH_BUDGET = 6.0


def _check(name: str, label: str) -> str:
    if not _NAME.match(name or ""):
        raise ValueError(f"invalid {label}: {name!r}")
    return name


def _quote(full_name: str) -> str:
    """`catalog`.`schema`.`table`. The regex allows no backtick, so quoting cannot be escaped."""
    if not _FULL.match(full_name or ""):
        raise ValueError(f"invalid table name: {full_name!r}")
    return ".".join(f"`{p}`" for p in full_name.split("."))


class CatalogBrowser:
    def __init__(self, host: str, token_provider, http: DbxHttp | None = None) -> None:
        self._http = http or DbxHttp(host, token_provider)
        #: (when, token tail, table names) — the walk is expensive, the answer is stable enough.
        self._names: tuple[float, str, list[str]] | None = None

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
                "format": t.get("data_source_format", ""), "updatedAt": t.get("updated_at")}

    async def preview(self, full_name: str, token: str | None) -> dict[str, Any]:
        """The first rows, through the SQL Statement API on a running warehouse the user can use."""
        quoted = _quote(full_name)
        wh = await self._http.get("/api/2.0/sql/warehouses", token)
        warehouses = wh.get("warehouses", [])
        pick = next((w for w in warehouses if w.get("state") == "RUNNING"), None) or (
            warehouses[0] if warehouses else None)
        if not pick:
            raise LookupError("no SQL warehouse is available to run a preview")
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

    async def table_names(self, token: str | None) -> list[str]:
        """Every table name this user can see, for name search. Cached for a few minutes."""
        tail = (token or "")[-12:]
        if self._names and self._names[0] > time.monotonic() - SEARCH_TTL and self._names[1] == tail:
            return self._names[2]
        names: list[str] = []
        cats = await self._http.get("/api/2.1/unity-catalog/catalogs", token)
        for c in cats.get("catalogs", []):
            cat = c.get("name", "")
            try:
                sch = await self._http.get("/api/2.1/unity-catalog/schemas", token, {"catalog_name": cat})
            except (PermissionError, RuntimeError):
                continue
            for s in sch.get("schemas", [])[:SEARCH_SCHEMAS]:
                try:
                    t = await self._http.get("/api/2.1/unity-catalog/tables", token, {
                        "catalog_name": cat, "schema_name": s.get("name", ""), "max_results": 200})
                except (PermissionError, RuntimeError):
                    continue
                names.extend(tab.get("full_name", "") for tab in t.get("tables", []) if tab.get("full_name"))
        self._names = (time.monotonic(), tail, names)
        return names

    async def find(self, token: str | None, needle: str, limit: int = 8) -> list[dict[str, Any]]:
        """Tables and columns whose name contains `needle`, best match first, within a time budget."""
        q = (needle or "").lower().strip()
        if len(q) < 2:
            return []
        try:
            names = await asyncio.wait_for(self.table_names(token), SEARCH_BUDGET)
        except (TimeoutError, PermissionError, RuntimeError):
            return []
        scored: list[tuple[float, str]] = []
        for n in names:
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
