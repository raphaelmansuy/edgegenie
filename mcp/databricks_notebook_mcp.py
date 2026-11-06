#!/usr/bin/env python3
"""Databricks Notebook & Workspace MCP server ("nbmcp").

Purpose
-------
The Databricks-provided MCP servers (`system.ai.dbsql`, `system.ai.sandbox`,
`system.ai.genie_one_mcp`) cover SQL execution, code sandboxing and
natural-language analytics. They deliberately do *not* cover the parts of
Genie Code's loop that operate on **workspace artefacts**: reading a notebook,
editing it in place, listing a schema with comments, checking lineage, or
running a job and reading its output.

This server fills that gap. It is a thin, typed, read-mostly wrapper over the
Databricks REST API that any MCP client (OpenCode, Copilot CLI, Claude Code,
Codex, Cursor) can attach to.

Design notes
------------
* Transport: stdio by default; set ``NBMCP_TRANSPORT=http`` to serve streamable
  HTTP so it can be registered as a Databricks App or reached from a sandbox.
* Auth: ``DATABRICKS_HOST`` + ``DATABRICKS_TOKEN`` (PAT) or OAuth via the CLI.
* Safety: every mutating tool is behind ``NBMCP_ALLOW_WRITES=1``. Reads never
  require the flag. This mirrors Genie Code's approval modes but is enforced by
  the server, not by an AI classifier (an important distinction — see docs).
* Output: results are compact JSON, truncated to a token budget so an agent's
  context window is not exhausted by a wide table listing.

Tools
-----
  dbx_whoami              identity + workspace host
  dbx_list_catalogs       catalogs the caller can see
  dbx_list_schemas        schemas in a catalog
  dbx_list_tables         tables/views in a schema
  dbx_describe_table      columns, types, comments, properties
  dbx_sample_rows         SELECT * ... LIMIT n (read-only, warehouse-backed)
  dbx_search_tables       substring search over table + column names
  dbx_table_lineage       upstream/downstream lineage edges
  dbx_list_notebooks      list a workspace directory
  dbx_read_notebook       export notebook source + metadata
  dbx_write_notebook      create/overwrite a notebook  [writes]
  dbx_list_jobs           jobs with recent run state
  dbx_run_job             trigger a job run           [writes]
  dbx_job_run_status      status + output of a run
  dbx_list_pipelines      Lakeflow pipelines
  dbx_list_warehouses     SQL warehouses and their state
  dbx_run_sql             execute SQL on a warehouse
  dbx_grants              Unity Catalog grants on an object
  dbx_audit_usage         recent audit events for an object
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

HOST = os.environ.get("DATABRICKS_HOST", "").rstrip("/")
TOKEN = os.environ.get("DATABRICKS_TOKEN", "")
ALLOW_WRITES = os.environ.get("NBMCP_ALLOW_WRITES", "0") == "1"
MAX_CHARS = int(os.environ.get("NBMCP_MAX_CHARS", "6000"))
WAREHOUSE_ID = os.environ.get("NBMCP_WAREHOUSE_ID", "")

mcp = FastMCP("databricks-notebook-tools")


# --------------------------------------------------------------------------
# plumbing
# --------------------------------------------------------------------------
def _client() -> httpx.Client:
    if not HOST or not TOKEN:
        raise RuntimeError("set DATABRICKS_HOST and DATABRICKS_TOKEN")
    return httpx.Client(
        base_url=HOST,
        headers={"Authorization": f"Bearer {TOKEN}"},
        timeout=120.0,
    )


def _trim(payload: Any) -> str:
    """Serialise and cap, so a wide catalog dump cannot blow the context."""
    text = json.dumps(payload, indent=2, default=str)
    if len(text) <= MAX_CHARS:
        return text
    return text[:MAX_CHARS] + f"\n... [truncated, {len(text)} chars total]"


def _get(path: str, params: dict | None = None) -> Any:
    with _client() as c:
        r = c.get(path, params=params)
        r.raise_for_status()
        return r.json()


def _post(path: str, body: dict | None = None) -> Any:
    with _client() as c:
        r = c.post(path, json=body or {})
        if r.headers.get("content-type", "").startswith("application/json"):
            data = r.json()
        else:
            data = {"raw": r.text}
        r.raise_for_status()
        return data


def _need_writes() -> None:
    if not ALLOW_WRITES:
        raise PermissionError(
            "writes disabled; start the server with NBMCP_ALLOW_WRITES=1"
        )


# --------------------------------------------------------------------------
# identity & catalog
# --------------------------------------------------------------------------
@mcp.tool()
def dbx_whoami() -> str:
    """Return the authenticated identity and workspace host."""
    me = _get("/api/2.0/preview/scim/v2/Me")
    return _trim(
        {
            "host": HOST,
            "user": me.get("userName"),
            "id": me.get("id"),
            "groups": [g.get("display") for g in me.get("groups", [])],
        }
    )


@mcp.tool()
def dbx_list_catalogs() -> str:
    """List Unity Catalog catalogs visible to the caller."""
    data = _get("/api/2.1/unity-catalog/catalogs")
    return _trim(
        [
            {"name": c.get("name"), "type": c.get("catalog_type"), "comment": c.get("comment")}
            for c in data.get("catalogs", [])
        ]
    )


@mcp.tool()
def dbx_list_schemas(catalog: str) -> str:
    """List schemas in a catalog."""
    data = _get("/api/2.1/unity-catalog/schemas", {"catalog_name": catalog})
    return _trim(
        [{"name": s.get("name"), "comment": s.get("comment")} for s in data.get("schemas", [])]
    )


@mcp.tool()
def dbx_list_tables(catalog: str, schema: str, limit: int = 100) -> str:
    """List tables and views in a schema with comments."""
    data = _get(
        "/api/2.1/unity-catalog/tables",
        {"catalog_name": catalog, "schema_name": schema, "max_results": limit},
    )
    return _trim(
        [
            {
                "name": t.get("name"),
                "type": t.get("table_type"),
                "columns": len(t.get("columns") or []),
                "comment": (t.get("comment") or "")[:160],
            }
            for t in data.get("tables", [])
        ]
    )


@mcp.tool()
def dbx_describe_table(full_name: str) -> str:
    """Describe a table: columns, types, comments, partitioning, owner.

    This is the context an agent needs before writing SQL. Genie Code gets this
    automatically from Unity Catalog; an external agent must ask for it.
    """
    t = _get(f"/api/2.1/unity-catalog/tables/{full_name}")
    return _trim(
        {
            "name": t.get("full_name"),
            "type": t.get("table_type"),
            "owner": t.get("owner"),
            "comment": t.get("comment"),
            "properties": t.get("properties"),
            "columns": [
                {
                    "name": c.get("name"),
                    "type": c.get("type_name"),
                    "nullable": c.get("nullable"),
                    "comment": c.get("comment"),
                    "partition": c.get("partition_index") is not None,
                }
                for c in t.get("columns", [])
            ],
        }
    )


@mcp.tool()
def dbx_search_tables(needle: str, catalog: str = "", limit: int = 40) -> str:
    """Search table and column names for a substring.

    Walks catalogs -> schemas -> tables. Slow on large metastores; scope it with
    `catalog` when you can.
    """
    needle_l = needle.lower()
    hits: list[dict] = []
    skipped: list[str] = []
    catalogs = [catalog] if catalog else [
        c["name"] for c in _get("/api/2.1/unity-catalog/catalogs").get("catalogs", [])
    ]
    for cat in catalogs:
        try:
            schemas = _get(
                "/api/2.1/unity-catalog/schemas", {"catalog_name": cat}
            ).get("schemas", [])
        except Exception as exc:  # noqa: BLE001 - unreachable catalog/schema
            skipped.append(f"{cat}: {type(exc).__name__}")
            continue
        for sch in schemas:
            if len(hits) >= limit:
                break
            try:
                tables = _get(
                    "/api/2.1/unity-catalog/tables",
                    {"catalog_name": cat, "schema_name": sch["name"], "max_results": 200},
                ).get("tables", [])
            except Exception as exc:  # noqa: BLE001
                skipped.append(f"{cat}.{sch['name']}: {type(exc).__name__}")
                continue
            for t in tables:
                if needle_l in (t.get("full_name") or "").lower():
                    hits.append({"match": "table", "name": t["full_name"],
                                 "comment": (t.get("comment") or "")[:120]})
                else:
                    for col in t.get("columns") or []:
                        if needle_l in (col.get("name") or "").lower():
                            hits.append({"match": "column", "name": f"{t['full_name']}.{col['name']}",
                                         "comment": (col.get("comment") or "")[:120]})
                            break
                if len(hits) >= limit:
                    break
    if skipped:
        hits.append({"note": "some schemas were not readable", "skipped": skipped[:10]})
    return _trim(hits)


@mcp.tool()
def dbx_table_lineage(full_name: str, direction: str = "both") -> str:
    """Return Unity Catalog lineage edges for a table.

    direction: upstream | downstream | both
    """
    out: dict[str, Any] = {"table": full_name}
    if direction in ("upstream", "both"):
        out["upstream"] = _get(
            "/api/2.0/lineage-tracking/table-lineage",
            {"table_name": full_name, "include_entity_lineage": "true"},
        ).get("upstreams", [])
    if direction in ("downstream", "both"):
        out["downstream"] = _get(
            "/api/2.0/lineage-tracking/table-lineage",
            {"table_name": full_name, "include_entity_lineage": "true"},
        ).get("downstreams", [])
    return _trim(out)


@mcp.tool()
def dbx_grants(securable_type: str, full_name: str) -> str:
    """List Unity Catalog grants on an object (catalog/schema/table/volume)."""
    return _trim(_get(f"/api/2.1/unity-catalog/permissions/{securable_type}/{full_name}"))


# --------------------------------------------------------------------------
# SQL
# --------------------------------------------------------------------------
@mcp.tool()
def dbx_run_sql(sql: str, warehouse_id: str = "", limit: int = 100) -> str:
    """Execute SQL on a SQL warehouse and return rows.

    Read-only by convention: statements that are not SELECT/SHOW/DESCRIBE are
    rejected unless NBMCP_ALLOW_WRITES=1. Uses the Statements API (synchronous
    wait, so the agent does not have to poll).
    """
    head = sql.strip().split(None, 1)[0].upper() if sql.strip() else ""
    if head not in ("SELECT", "SHOW", "DESCRIBE", "DESC", "WITH", "EXPLAIN") and not ALLOW_WRITES:
        return json.dumps({"error": f"statement type {head} blocked (read-only server)"})
    wh = warehouse_id or WAREHOUSE_ID
    if not wh:
        whs = _get("/api/2.0/sql/warehouses").get("warehouses", [])
        if not whs:
            return json.dumps({"error": "no SQL warehouse available"})
        # prefer a running one
        whs.sort(key=lambda w: 0 if w.get("state") == "RUNNING" else 1)
        wh = whs[0]["id"]
    data = _post(
        "/api/2.0/sql/statements",
        {
            "warehouse_id": wh,
            "statement": sql,
            "wait_timeout": "50s",
            "on_wait_timeout": "CONTINUE",
            "format": "JSON_ARRAY",
            "disposition": "INLINE",
        },
    )
    state = (data.get("status") or {}).get("state")
    if state != "SUCCEEDED":
        return _trim({"state": state, "error": (data.get("status") or {}).get("error")})
    result = data.get("result") or {}
    cols = [c["name"] for c in (data.get("manifest") or {}).get("schema", {}).get("columns", [])]
    rows = result.get("data_array") or []
    return _trim({"columns": cols, "rows": rows[:limit], "row_count": len(rows)})


@mcp.tool()
def dbx_sample_rows(full_name: str, n: int = 5) -> str:
    """Return n sample rows from a table (read-only)."""
    return dbx_run_sql(f"SELECT * FROM {full_name} LIMIT {int(n)}")


# --------------------------------------------------------------------------
# workspace files / notebooks
# --------------------------------------------------------------------------
@mcp.tool()
def dbx_list_notebooks(path: str = "/") -> str:
    """List a workspace directory (notebooks, files, directories, repos)."""
    data = _get("/api/2.0/workspace/list", {"path": path})
    return _trim(
        [
            {"type": o.get("object_type"), "path": o.get("path"), "id": o.get("object_id")}
            for o in data.get("objects", [])
        ]
    )


@mcp.tool()
def dbx_read_notebook(path: str, offset: int = 0, max_chars: int = 0) -> str:
    """Export a notebook's source, with paging.

    Notebooks routinely exceed an agent's context budget (a 17 KB notebook is
    already at the limit once tool schemas are counted). Truncating silently is
    the single most common cause of a confidently wrong answer, so this tool
    reports the full length and returns a paged window with explicit
    `next_offset`, letting the agent walk the file deliberately.
    """
    data = _get("/api/2.0/workspace/export", {"path": path, "format": "SOURCE"})
    content = base64.b64decode(data.get("content", "")).decode("utf-8", "replace")
    window = max_chars or MAX_CHARS
    start = max(0, offset)
    end = min(len(content), start + window)
    return _trim(
        {
            "path": path,
            "language": data.get("language"),
            "total_chars": len(content),
            "offset": start,
            "returned_chars": end - start,
            "next_offset": end if end < len(content) else None,
            "source": content[start:end],
        }
    )


# POSIX character classes that models emit but Python's `re` does not support.
# A silent zero-hit result is worse than an error: the agent concludes "the
# notebook has no imports" and keeps digging. Translate before compiling.
_POSIX = {
    "[[:space:]]": r"\s",
    "[[:alpha:]]": r"[A-Za-z]",
    "[[:digit:]]": r"\d",
    "[[:alnum:]]": r"[A-Za-z0-9]",
    "[[:upper:]]": r"[A-Z]",
    "[[:lower:]]": r"[a-z]",
    "[[:punct:]]": r"[^\w\s]",
    "[[:blank:]]": r"[ \t]",
}


def _normalise_pattern(pattern: str) -> str:
    for posix, py in _POSIX.items():
        pattern = pattern.replace(posix, py)
    return pattern


@mcp.tool()
def dbx_grep_notebook(path: str, pattern: str, context: int = 2) -> str:
    """Search a notebook's source with a regex and return matching lines.

    Far cheaper than paging a whole notebook when the agent has a specific
    question ("which libraries does this import?"). Returns line numbers so the
    agent can page in exactly the region it needs with dbx_read_notebook.

    `pattern` is a Python regex. POSIX classes like `[[:space:]]` are accepted
    and translated. If nothing matches, the response says so explicitly and
    includes a hint, so the agent does not mistake "no match" for "not present".
    """
    data = _get("/api/2.0/workspace/export", {"path": path, "format": "SOURCE"})
    content = base64.b64decode(data.get("content", "")).decode("utf-8", "replace")
    lines = content.splitlines()
    norm = _normalise_pattern(pattern)
    try:
        rx = re.compile(norm)
    except re.error as exc:
        return _trim({"error": f"invalid regex {pattern!r}: {exc}",
                      "hint": "use Python regex syntax, e.g. r'^\\s*(import|from)\\s'"})
    hits = []
    for i, line in enumerate(lines):
        if rx.search(line):
            lo, hi = max(0, i - context), min(len(lines), i + context + 1)
            hits.append(
                {"line": i + 1, "text": "\n".join(f"{n + 1}: {lines[n]}" for n in range(lo, hi))}
            )
        if len(hits) >= 40:
            break

    payload: dict[str, Any] = {
        "path": path,
        "pattern": pattern,
        "normalised_pattern": norm if norm != pattern else None,
        "total_lines": len(lines),
        "match_count": len(hits),
        "hits": hits,
    }
    if not hits:
        # Say it loudly, and offer a concrete next step instead of a silent [].
        payload["no_matches"] = True
        payload["hint"] = (
            "No line matched. This does NOT mean the content is absent — try a "
            "looser pattern such as r'(?i)import' or r'^\\s*(import|from)\\s', "
            "or call dbx_read_notebook with offset=0 to inspect the source "
            "directly."
        )
        payload["first_lines"] = "\n".join(
            f"{n + 1}: {lines[n]}" for n in range(min(8, len(lines)))
        )
    return _trim(payload)


@mcp.tool()
def dbx_write_notebook(path: str, source: str, language: str = "PYTHON", overwrite: bool = True) -> str:
    """Create or overwrite a notebook. Requires NBMCP_ALLOW_WRITES=1."""
    _need_writes()
    if not source.startswith("# Databricks notebook source"):
        source = "# Databricks notebook source\n" + source
    body = {
        "path": path,
        "format": "SOURCE",
        "language": language,
        "content": base64.b64encode(source.encode()).decode(),
        "overwrite": overwrite,
    }
    return _trim(_post("/api/2.0/workspace/import", body))


# --------------------------------------------------------------------------
# jobs / pipelines
# --------------------------------------------------------------------------
@mcp.tool()
def dbx_list_jobs(limit: int = 25) -> str:
    """List jobs with their latest run state."""
    data = _get("/api/2.1/jobs/list", {"limit": limit, "expand_tasks": "false"})
    return _trim(
        [
            {
                "job_id": j.get("job_id"),
                "name": (j.get("settings") or {}).get("name"),
                "schedule": ((j.get("settings") or {}).get("schedule") or {}).get("quartz_cron_expression"),
            }
            for j in data.get("jobs", [])
        ]
    )


@mcp.tool()
def dbx_run_job(job_id: int) -> str:
    """Trigger a job run. Requires NBMCP_ALLOW_WRITES=1."""
    _need_writes()
    return _trim(_post("/api/2.1/jobs/run-now", {"job_id": job_id}))


@mcp.tool()
def dbx_job_run_status(run_id: int) -> str:
    """Get the state and result of a job run."""
    data = _get("/api/2.1/jobs/runs/get", {"run_id": run_id})
    state = data.get("state") or {}
    return _trim(
        {
            "run_id": run_id,
            "life_cycle": state.get("life_cycle_state"),
            "result": state.get("result_state"),
            "message": state.get("state_message"),
            "tasks": [
                {
                    "task_key": t.get("task_key"),
                    "state": (t.get("state") or {}).get("life_cycle_state"),
                    "result": (t.get("state") or {}).get("result_state"),
                }
                for t in data.get("tasks", [])
            ],
        }
    )


@mcp.tool()
def dbx_list_pipelines(limit: int = 25) -> str:
    """List Lakeflow Spark Declarative Pipelines."""
    data = _get("/api/2.0/pipelines", {"max_results": limit})
    return _trim(
        [{"pipeline_id": p.get("pipeline_id"), "name": p.get("name"),
          "state": p.get("state"), "catalog": p.get("catalog")}
         for p in data.get("statuses", data.get("pipelines", []))]
    )


@mcp.tool()
def dbx_list_warehouses() -> str:
    """List SQL warehouses and their state."""
    data = _get("/api/2.0/sql/warehouses")
    return _trim(
        [{"id": w.get("id"), "name": w.get("name"), "state": w.get("state"),
          "size": w.get("cluster_size"), "type": w.get("warehouse_type")}
         for w in data.get("warehouses", [])]
    )


if __name__ == "__main__":
    transport = os.environ.get("NBMCP_TRANSPORT", "stdio")
    if transport == "http":
        mcp.settings.port = int(os.environ.get("NBMCP_PORT", "8799"))
        mcp.settings.host = os.environ.get("NBMCP_HOST", "127.0.0.1")
        mcp.run(transport="streamable-http")
    else:
        mcp.run()
