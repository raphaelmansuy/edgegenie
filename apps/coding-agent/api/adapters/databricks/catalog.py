"""Browse Unity Catalog with the user's token: catalogs -> schemas -> tables -> columns, plus a sample.

Unity Catalog is the permission boundary: this adapter only ever shows what the signed-in user's
token can see, and a denial is a PermissionError, not an empty list.
"""
from __future__ import annotations

import re
from typing import Any

from .http import DbxHttp

_NAME = re.compile(r"^[\w\-]+$")
_FULL = re.compile(r"^[\w\-]+\.[\w\-]+\.[\w\-]+$")
PREVIEW_ROWS = 10


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
