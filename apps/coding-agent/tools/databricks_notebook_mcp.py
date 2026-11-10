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

HOST = os.environ.get("DATABRICKS_HOST", "").strip().rstrip("/")
if HOST and not HOST.startswith(("http://", "https://")):
    HOST = "https://" + HOST          # Databricks Apps may provide a bare hostname
TOKEN = os.environ.get("DATABRICKS_TOKEN", "")
ALLOW_WRITES = os.environ.get("NBMCP_ALLOW_WRITES", "0") == "1"
MAX_CHARS = int(os.environ.get("NBMCP_MAX_CHARS", "6000"))
WAREHOUSE_ID = os.environ.get("NBMCP_WAREHOUSE_ID", "")

mcp = FastMCP("databricks-notebook-tools")

# Tool profile. A coding agent advertises every MCP tool on every request, so
# fewer, better tools beat many. `core` registers the ~20 tools the exam suite
# showed are actually needed; `full` also registers the rarely-used lookups.
PROFILE = os.environ.get("NBMCP_PROFILE", "full")
_CORE = {
    "dbx_whoami", "dbx_list_tables", "dbx_describe_table", "dbx_search_tables", "dbx_run_sql",
    "dbx_list_notebooks", "dbx_read_notebook", "dbx_grep_notebook", "dbx_write_notebook",
    "dbx_write_file", "dbx_run_notebook", "dbx_run_notebook_status", "dbx_create_job", "dbx_run_job", "dbx_job_run_status",
    "dbx_lakebase_create", "dbx_lakebase_status", "dbx_lakebase_sql", "dbx_lakebase_branch",
    "dbx_lakebase_database", "dbx_lakebase_role", "dbx_lakebase_tables",
    "dbx_create_app", "dbx_app_health", "dbx_skill",
}


def tool():
    def deco(fn):
        if PROFILE == "full" or fn.__name__ in _CORE:
            return mcp.tool()(fn)
        return fn
    return deco


# --------------------------------------------------------------------------
# plumbing
# --------------------------------------------------------------------------
def _token() -> str:
    """The credential, read at call time. A host app that acts for a user rewrites this file with
    the user's current token (they expire in about an hour); a plain PAT in the environment works too."""
    path = os.environ.get("NBMCP_TOKEN_FILE", "")
    if path:
        try:
            with open(path, encoding="utf-8") as fh:
                return fh.read().strip()
        except OSError:
            return ""
    return TOKEN


def _client() -> httpx.Client:
    token = _token()
    if not HOST or not token:
        raise RuntimeError(
            "the workspace connection is not available to this tool server: "
            "this is an app configuration problem, not something to retry or work around")
    def _refuse(response: httpx.Response) -> None:
        # A 401/403 will not change on retry. Say so, in words the model acts on, instead of an
        # httpx traceback it answers with another attempt.
        if response.status_code in (401, 403):
            raise PermissionError(
                f"permission denied by the workspace for {response.request.method} "
                f"{response.request.url.path}. The signed-in user or this app's authorization does not "
                "allow it. Do not retry; use another tool or report it.")

    return httpx.Client(
        event_hooks={"response": [_refuse]},
        base_url=HOST,
        headers={"Authorization": f"Bearer {token}"},
        timeout=120.0,
    )


def _trim(payload: Any) -> str:
    """Serialise and cap, so a wide catalog dump cannot blow the context."""
    text = json.dumps(payload, indent=2, default=str)
    if len(text) <= MAX_CHARS:
        return text
    return text[:MAX_CHARS] + f"\n... [truncated, {len(text)} chars total]"


def _retry(fn, *, idempotent: bool):
    """Retry transient failures. GETs retry on connection errors and 429/5xx.
    POSTs retry only on 429/503, where the request was provably not processed,
    so a retried runs/submit can never double-launch."""
    import time
    delay = 1.5
    for attempt in range(4):
        try:
            return fn()
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            retryable = code in (429, 503) or (idempotent and code in (500, 502, 504))
            if not retryable or attempt == 3:
                raise
        except (httpx.TransportError, ConnectionError, OSError):
            if not idempotent or attempt == 3:
                raise
        time.sleep(delay)
        delay *= 2


def _get(path: str, params: dict | None = None) -> Any:
    def go():
        with _client() as c:
            r = c.get(path, params=params)
            r.raise_for_status()
            return r.json()
    return _retry(go, idempotent=True)


def _post(path: str, body: dict | None = None) -> Any:
    def go():
        with _client() as c:
            r = c.post(path, json=body or {})
            if r.headers.get("content-type", "").startswith("application/json"):
                data = r.json()
            else:
                data = {"raw": r.text}
            r.raise_for_status()
            return data
    return _retry(go, idempotent=False)


def _patch(path: str, body: dict | None = None) -> Any:
    """A partial update. Idempotent by nature: the same body twice leaves the same state."""
    def go():
        with _client() as c:
            r = c.patch(path, json=body or {})
            if r.headers.get("content-type", "").startswith("application/json"):
                data = r.json()
            else:
                data = {"raw": r.text}
            r.raise_for_status()
            return data
    return _retry(go, idempotent=True)


def _need_writes() -> None:
    if not ALLOW_WRITES:
        raise PermissionError(
            "writes disabled; start the server with NBMCP_ALLOW_WRITES=1"
        )


# Write scope: even with writes enabled, the server only lets an agent mutate
# objects inside an allow-list. This is enforced here, not by the model.
#   NBMCP_WRITE_SCHEMAS  comma list of  catalog.schema   (SQL DDL/DML)
#   NBMCP_WRITE_PATHS    comma list of  /Workspace/... or /Users/... prefixes
WRITE_SCHEMAS = [s.strip().lower() for s in os.environ.get("NBMCP_WRITE_SCHEMAS", "").split(",") if s.strip()]
WRITE_PATHS = [p.strip() for p in os.environ.get("NBMCP_WRITE_PATHS", "").split(",") if p.strip()]

_ID = r"`?[A-Za-z_][\w-]*`?"
_NAME = rf"({_ID})(?:\.({_ID}))?(?:\.({_ID}))?"
# Write *targets* only: sources of a CTAS (FROM/JOIN) are reads and stay free.
_TARGETS = re.compile(
    r"(?i)\b(?:"
    r"create\s+(?:or\s+replace\s+)?(?:temp(?:orary)?\s+)?(?:external\s+)?(?:table|view|materialized\s+view|streaming\s+table|schema|volume|function)"
    r"(?:\s+if\s+not\s+exists)?"
    r"|insert\s+(?:into|overwrite)(?:\s+table)?"
    r"|merge\s+into|update|delete\s+from|truncate\s+table|copy\s+into"
    r"|drop\s+(?:table|view|schema|volume|function)(?:\s+if\s+exists)?"
    r"|alter\s+(?:table|view|schema)"
    r"|comment\s+on\s+(?:table|schema|column)"
    r"|optimize|vacuum"
    r")\s+" + _NAME
)


def _check_sql_scope(sql: str) -> str | None:
    """Return an error string if any write target is outside the write scope."""
    if not WRITE_SCHEMAS:
        return None
    targets = _TARGETS.findall(sql)
    if not targets:
        return "write blocked: could not identify a write target; use plain CREATE/INSERT/MERGE/ALTER statements"
    for a, b, c in targets:
        parts = [x.strip("`").lower() for x in (a, b, c) if x]
        if len(parts) == 2 and f"{parts[0]}.{parts[1]}" in WRITE_SCHEMAS:
            continue  # schema-level target e.g. CREATE SCHEMA cat.sch
        if len(parts) == 3 and f"{parts[0]}.{parts[1]}" in WRITE_SCHEMAS:
            continue
        # COMMENT ON COLUMN cat.sch.tbl.col is matched as 3 parts, still fine.
        return (f"write blocked: target {'.'.join(parts)} is not inside allowed schemas "
                f"{WRITE_SCHEMAS}; use fully qualified catalog.schema.name")
    return None


JOB_PREFIX = os.environ.get("NBMCP_WRITE_JOB_PREFIX", "")
INSTANCE_PREFIX = os.environ.get("NBMCP_WRITE_INSTANCE_PREFIX", "")
#: The app prefix is its own variable. Before spec 013 `dbx_create_app` compared app names to
#: INSTANCE_PREFIX, which passed only because the two strings happen to be equal — a fence that
#: worked by coincidence ([F3], [E-6]).
APP_PREFIX = os.environ.get("NBMCP_WRITE_APP_PREFIX", "")


def _check_prefix(kind: str, name: str, prefix: str) -> None:
    if prefix and not name.startswith(prefix):
        raise PermissionError(f"write blocked: {kind} name must start with '{prefix}' (got '{name}')")


def _check_path_scope(path: str) -> None:
    """Refuse a path outside the session's folder — and refuse a `..` escape inside it.

    A prefix test alone accepts `/fence/../elsewhere/x`, because the STRING starts with the fence.
    The app's own `scope.check_path` normalises and rejects `..` (spec 013 [F4], [E-27]); this is the
    tool server's half of the same rule, and before it was added the two disagreed on exactly that
    case. `tests/test_tools_fence.py` holds both sides to one table.
    """
    normalised = path.replace("\\", "/")
    while "//" in normalised:
        normalised = normalised.replace("//", "/")
    if ".." in normalised.split("/"):
        raise PermissionError(f"write blocked: {path} contains '..' and is not a real location "
                              f"inside {WRITE_PATHS}")
    if WRITE_PATHS and not any(normalised.startswith(p) for p in WRITE_PATHS):
        raise PermissionError(f"write blocked: {path} outside allowed paths {WRITE_PATHS}")


# --------------------------------------------------------------------------
# identity & catalog
# --------------------------------------------------------------------------
@tool()
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


@tool()
def dbx_list_catalogs() -> str:
    """List Unity Catalog catalogs visible to the caller."""
    data = _get("/api/2.1/unity-catalog/catalogs")
    return _trim(
        [
            {"name": c.get("name"), "type": c.get("catalog_type"), "comment": c.get("comment")}
            for c in data.get("catalogs", [])
        ]
    )


@tool()
def dbx_list_schemas(catalog: str) -> str:
    """List schemas in a catalog."""
    data = _get("/api/2.1/unity-catalog/schemas", {"catalog_name": catalog})
    return _trim(
        [{"name": s.get("name"), "comment": s.get("comment")} for s in data.get("schemas", [])]
    )


@tool()
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


@tool()
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


@tool()
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


@tool()
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


@tool()
def dbx_grants(securable_type: str, full_name: str) -> str:
    """List Unity Catalog grants on an object (catalog/schema/table/volume)."""
    return _trim(_get(f"/api/2.1/unity-catalog/permissions/{securable_type}/{full_name}"))


# --------------------------------------------------------------------------
# SQL
# --------------------------------------------------------------------------
@tool()
def dbx_run_sql(sql: str, warehouse_id: str = "", limit: int = 100) -> str:
    """Execute SQL on a SQL warehouse and return rows.

    Read-only by convention: statements that are not SELECT/SHOW/DESCRIBE are
    rejected unless NBMCP_ALLOW_WRITES=1. Uses the Statements API (synchronous
    wait, so the agent does not have to poll).
    """
    head = sql.strip().split(None, 1)[0].upper() if sql.strip() else ""
    if head not in ("SELECT", "SHOW", "DESCRIBE", "DESC", "WITH", "EXPLAIN") and not ALLOW_WRITES:
        return json.dumps({"error": f"statement type {head} blocked (read-only server)"})
    if head not in ("SELECT", "SHOW", "DESCRIBE", "DESC", "EXPLAIN"):
        # WITH ... SELECT is read-only, but WITH ... INSERT is not; scope-check
        # anything that is not an obvious read.
        is_read = head == "WITH" and not re.search(r"(?i)\b(insert|merge|update|delete)\b", sql)
        if not is_read:
            err = _check_sql_scope(sql)
            if err:
                return json.dumps({"error": err})
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


@tool()
def dbx_sample_rows(full_name: str, n: int = 5) -> str:
    """Return n sample rows from a table (read-only)."""
    return dbx_run_sql(f"SELECT * FROM {full_name} LIMIT {int(n)}")


# --------------------------------------------------------------------------
# workspace files / notebooks
# --------------------------------------------------------------------------
@tool()
def dbx_list_notebooks(path: str = "/") -> str:
    """List a workspace directory (notebooks, files, directories, repos)."""
    data = _get("/api/2.0/workspace/list", {"path": path})
    return _trim(
        [
            {"type": o.get("object_type"), "path": o.get("path"), "id": o.get("object_id")}
            for o in data.get("objects", [])
        ]
    )


@tool()
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


@tool()
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


def _cells_to_source(cells: list[dict], language: str) -> str:
    """Assemble Databricks SOURCE format from [{type: markdown|code|sql, source: str|[str]}]."""
    bodies = []
    for c in cells:
        kind = (c.get("type") or c.get("cell_type") or "code").lower()
        src = c.get("source", "")
        if isinstance(src, list):                      # ipynb style: list of lines
            src = "".join(src)
        src = src.rstrip("\n")
        if kind in ("markdown", "md"):
            body = "\n".join("# MAGIC " + ln if ln else "# MAGIC" for ln in ("%md\n" + src).split("\n"))
        elif kind == "sql":
            body = "\n".join("# MAGIC " + ln if ln else "# MAGIC" for ln in ("%sql\n" + src).split("\n"))
        else:
            body = src
        bodies.append(body)
    return "# Databricks notebook source\n\n" + "\n\n# COMMAND ----------\n\n".join(bodies) + "\n"


def _maybe_ipynb(source: str) -> list[dict] | None:
    """Models often emit Jupyter JSON. Accept it instead of writing it verbatim as one cell."""
    t = source.lstrip()
    if not t or t[0] not in "[{":
        return None
    try:
        data = json.loads(t)
    except Exception:  # noqa: BLE001
        return None
    cells = data.get("cells") if isinstance(data, dict) else data
    if isinstance(cells, list) and cells and all(isinstance(c, dict) and ("source" in c) for c in cells):
        return cells
    return None


_BARE_MAGIC = re.compile(r"^\s*%(md|sql|sh|python|scala|r)\b[ \t]*\n?", re.I)


def _normalise_source(source: str) -> str:
    """Be liberal in what we accept: a cell whose first line is a bare `%md` /
    `%sql` is rewritten to the `# MAGIC` form Databricks SOURCE format needs."""
    parts = re.split(r"\n# COMMAND ----------\n", source)
    fixed = []
    for part in parts:
        m = _BARE_MAGIC.match(part.lstrip("\n"))
        if m and "# MAGIC" not in part.split("\n", 2)[0]:
            body = part.lstrip("\n")[m.end():]
            lang = m.group(1).lower()
            lines = [f"# MAGIC %{lang}"] + [("# MAGIC " + ln) if ln.strip() else "# MAGIC" for ln in body.rstrip("\n").split("\n")]
            part = "\n".join(lines)
        fixed.append(part)
    return "\n# COMMAND ----------\n".join(fixed)


@tool()
def dbx_write_notebook(path: str, cells: list[dict] | None = None, source: str = "", language: str = "PYTHON",
                       overwrite: bool = True, cells_json: str = "") -> str:
    """Create or overwrite a notebook.

    PREFERRED: pass `cells`, a list of objects, which guarantees correct notebook
    structure (do not stringify it):
      cells=[{"type": "markdown", "source": "# Title\\nWhy this notebook exists"},
             {"type": "code",     "source": "df = spark.table('a.b.c')\\ndisplay(df)"},
             {"type": "sql",      "source": "SELECT 1"}]
    Or pass `source` as plain Python, splitting cells with '# COMMAND ----------'
    lines (a cell starting with a bare %md / %sql is fixed up for you). Jupyter-style
    JSON in `source` is converted. The reply says how many markdown/code cells were
    written: check it matches your intent. Requires NBMCP_ALLOW_WRITES=1 and a path
    inside the allowed paths.
    """
    _need_writes()
    _check_path_scope(path)
    if cells is None and cells_json.strip():
        try:
            cells = json.loads(cells_json)
        except Exception as e:  # noqa: BLE001
            return _trim({"error": f"cells_json is not valid JSON ({e}). Pass `cells` as a native list of "
                                   "{type, source} objects instead of a JSON string."})
    converted = False
    if cells is None:
        cells = _maybe_ipynb(source)
        converted = cells is not None
    if cells is not None:
        source = _cells_to_source(cells, language)
    else:
        source = _normalise_source(source)
        if not source.startswith("# Databricks notebook source"):
            source = "# Databricks notebook source\n" + source
    body = {
        "path": path,
        "format": "SOURCE",
        "language": language,
        "content": base64.b64encode(source.encode()).decode(),
        "overwrite": overwrite,
    }
    _post("/api/2.0/workspace/mkdirs", {"path": path.rsplit("/", 1)[0]})
    r = _post("/api/2.0/workspace/import", body)
    n_cells = source.count("\n# COMMAND ----------\n") + 1
    n_md = source.count("# MAGIC %md")
    out = {"path": path, "object_id": r.get("object_id"), "cells": n_cells, "markdown_cells": n_md,
           "code_cells": n_cells - n_md}
    if converted:
        out["note"] = "converted from Jupyter-style JSON"
    if n_md == 0:
        out["warning"] = "0 markdown cells. If the task asks for narrative/documentation, add markdown cells."
    return _trim(out)


# --------------------------------------------------------------------------
# jobs / pipelines
# --------------------------------------------------------------------------
@tool()
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


def _task_outputs(run: dict) -> list[dict]:
    """Per-task state + notebook exit value + error text. The exit value and the
    error are what an agent needs to decide its next step, so return them."""
    out = []
    for t in run.get("tasks", []) or []:
        st = t.get("state") or {}
        item = {"task_key": t.get("task_key"), "state": st.get("life_cycle_state"),
                "result": st.get("result_state"), "message": st.get("state_message") or None}
        if st.get("life_cycle_state") == "TERMINATED":
            try:
                o = _get("/api/2.1/jobs/runs/get-output", {"run_id": t["run_id"]})
                nb = o.get("notebook_output") or {}
                if nb.get("result") is not None:
                    item["exit_value"] = nb["result"][:2000]
                if o.get("error"):
                    item["error"] = str(o["error"])[:1200]
                if o.get("error_trace"):
                    item["error_trace_tail"] = str(o["error_trace"])[-1200:]
            except Exception as e:  # noqa: BLE001
                item["output_error"] = str(e)[:200]
        out.append(item)
    return out


def _wait_run(run_id: int, wait_seconds: int) -> dict:
    import time
    t0 = time.time()
    while True:
        d = _get("/api/2.1/jobs/runs/get", {"run_id": run_id})
        if (d.get("state") or {}).get("life_cycle_state") in ("TERMINATED", "SKIPPED", "INTERNAL_ERROR"):
            return d
        if time.time() - t0 >= wait_seconds:
            return d
        time.sleep(5)


def _run_summary(run_id: int, d: dict) -> str:
    state = d.get("state") or {}
    finished = state.get("life_cycle_state") in ("TERMINATED", "SKIPPED", "INTERNAL_ERROR")
    payload = {"run_id": run_id, "life_cycle": state.get("life_cycle_state"),
               "result": state.get("result_state"), "message": state.get("state_message") or None,
               "finished": finished, "tasks": _task_outputs(d) if finished else
               [{"task_key": t.get("task_key"), "state": (t.get("state") or {}).get("life_cycle_state")}
                for t in d.get("tasks", []) or []]}
    if not finished:
        payload["hint"] = "still running: call dbx_job_run_status(run_id) again to wait/poll"
    elif state.get("result_state") == "SUCCESS" and not any("exit_value" in t for t in payload["tasks"]):
        payload["note"] = ("run succeeded but no task returned an exit value: the notebook never called "
                           "dbutils.notebook.exit(...). If the task required one, the notebook is incomplete.")
    return _trim(payload)


RUN_URL = os.environ.get("NBMCP_RUN_URL", "")
RUN_SESSION = os.environ.get("NBMCP_RUN_SESSION", "")
RUN_KEY = os.environ.get("NBMCP_RUN_KEY", "")


def _app_call(method: str, url: str, **kw: Any) -> dict:
    """One call to the host app's run endpoint (loopback). Its refusals are sentences meant for the agent."""
    try:
        r = httpx.request(method, url, timeout=30.0, **kw)
    except httpx.HTTPError as e:
        raise RuntimeError(f"the app's run service is not reachable ({type(e).__name__}); "
                           "tell the user to run the notebook in Databricks") from None
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail")
        except ValueError:
            detail = None
        raise PermissionError(str(detail or f"the app refused the run ({r.status_code})")) if r.status_code == 403 \
            else RuntimeError(str(detail or f"the app could not run it ({r.status_code})"))
    return r.json()


def _run_via_app(path: str, wait_seconds: int) -> str:
    """Run the notebook on serverless compute AS THE APP and wait a little for it.

    The notebook is read with the USER's token (so the user's own access decides what is read) and sent
    to the app, which runs its Python cells in order in one namespace and returns each cell's printed
    output, last value and tables. It runs as the app's service principal, not as the user: the result
    says so, and the agent must say so too.
    """
    exported = _get("/api/2.0/workspace/export", {"path": path, "format": "SOURCE"})
    source = base64.b64decode(exported.get("content") or "").decode(errors="replace")
    started = _app_call("POST", RUN_URL, json={"session": RUN_SESSION, "key": RUN_KEY, "source": source,
                                               "language": str(exported.get("language") or "PYTHON")})
    if not started.get("handle"):
        return _trim({"finished": True, "ran_as": "the app", "results": started.get("refused", {})})
    return _poll_app_run(started["handle"], wait_seconds)


def _poll_app_run(handle: str, wait_seconds: int) -> str:
    import time
    t0 = time.time()
    while True:
        d = _app_call("GET", f"{RUN_URL}/{handle}", params={"session": RUN_SESSION, "key": RUN_KEY})
        if d.get("state") == "done" or time.time() - t0 >= min(wait_seconds, 55):
            break
        time.sleep(3)
    if d.get("state") != "done":
        return _trim({"finished": False, "handle": handle, "stage": d.get("stage"),
                      "hint": f"still running as the app: call dbx_run_notebook_status('{handle}') to wait"})
    cells = []
    for index, r in sorted(((int(k), v) for k, v in (d.get("results") or {}).items())):
        item = {"cell": index + 1, "state": r.get("state")}
        if r.get("output"):
            item["output"] = r["output"][:3000]
        if r.get("rows") is not None and r.get("columns"):
            item["table"] = {"columns": r["columns"], "rows": r["rows"][:20], "total_rows": r.get("totalRows")}
        if r.get("error"):
            item["error"] = r["error"][:1500]
        cells.append(item)
    ok = all(c["state"] == "succeeded" for c in cells)
    return _trim({"finished": True, "result": "SUCCESS" if ok else "FAILED", "seconds": d.get("seconds"),
                  "ran_as": "the app's service principal on serverless compute (not as the user)",
                  "cells": cells})


@tool()
def dbx_run_notebook_status(handle: str, wait_seconds: int = 45) -> str:
    """Wait for (or read) a notebook run that dbx_run_notebook left running as the app.

    Pass the `handle` it returned. Same output as dbx_run_notebook: each Python cell's printed output,
    last value and tables, or the error. Call again if it says finished=false.
    """
    if not RUN_URL:
        return _trim({"error": "this server has no app run service; use dbx_job_run_status with a run_id"})
    return _poll_app_run(handle, wait_seconds)


@tool()
def dbx_run_notebook(path: str, parameters_json: str = "{}", wait_seconds: int = 45) -> str:
    """Run a notebook ONCE on serverless compute and wait for the result.

    Returns the state, the dbutils.notebook.exit() value and, on failure, the
    error and the tail of the stack trace. If it is still running after
    wait_seconds you get finished=false and a run_id to poll with
    dbx_job_run_status.

    In a deployed Databricks App the user's token cannot submit runs; then the notebook is run by the
    app itself as its own service principal (only for administrators). The result says `ran_as`, and
    you must tell the user it did not run as them. If finished=false, call dbx_run_notebook_status(handle).

    Kept short on purpose: a tool that blocks for minutes produces no ACP events, so the turn looks
    dead and the app's idle guard fires. Poll instead.
    """
    _need_writes()
    _check_path_scope(path)
    task: dict = {"task_key": "t", "notebook_task": {"notebook_path": path}}
    params = json.loads(parameters_json or "{}")
    if params:
        task["notebook_task"]["base_parameters"] = {k: str(v) for k, v in params.items()}
    try:
        run_id = _post("/api/2.1/jobs/runs/submit", {"run_name": "nbmcp-run", "tasks": [task]})["run_id"]
    except PermissionError:
        # A Databricks App's user authorization has no jobs scope, so the user's token cannot submit a
        # run. When the host app offers to run it itself (as the app, for administrators), ask it to.
        if RUN_URL:
            return _run_via_app(path, wait_seconds)
        raise
    summary = _run_summary(run_id, _wait_run(run_id, wait_seconds))
    # On failure, hand back the tables the notebook reads and their real columns: a failed run is
    # exactly when the agent needs the truth, and making it guess again wastes a whole turn.
    if '"result": "FAILED"' in summary or '"life_cycle": "INTERNAL_ERROR"' in summary:
        try:
            import re as _re
            source = ""
            exported = _get("/api/2.0/workspace/export", {"path": path, "format": "SOURCE"})
            import base64 as _b64
            source = _b64.b64decode(exported.get("content") or "").decode(errors="replace")
            tables = sorted(set(_re.findall(r"\b(?:from|join)\s+([\w.]+)", source, _re.I)))[:3]
            hints = []
            for t in tables:
                if t.count(".") == 2:
                    cols = _get(f"/api/2.1/unity-catalog/tables/{t}").get("columns") or []
                    hints.append({"table": t, "columns": [c.get("name") for c in cols]})
            if hints:
                summary += ("\n\nSCHEMA HINT (the notebook failed; these are the real columns):\n"
                            + json.dumps(hints, indent=1)
                            + "\nFix the code using exactly these names, then run it again.")
        except Exception:  # noqa: BLE001 - a hint is a bonus, never a reason to fail the tool
            pass
    return summary


@tool()
def dbx_create_job(name: str, tasks: list[dict] | None = None, cron: str = "", timezone: str = "UTC",
                   max_retries: int = 0, tasks_json: str = "") -> str:
    """Create a Databricks Job whose tasks are notebooks, on serverless compute.

    `tasks` is a list of objects (native list, not a string), in any order:
      [{"task_key": "silver", "notebook_path": "/Users/me/x/silver", "depends_on": []},
       {"task_key": "gold",   "notebook_path": "/Users/me/x/gold",   "depends_on": ["silver"]}]
    cron is an optional Quartz expression ("0 0 6 * * ?"). The job name must
    start with the allowed prefix. Returns job_id; run it with dbx_run_job.
    """
    _need_writes()
    _check_prefix("job", name, JOB_PREFIX)
    if tasks is None and tasks_json.strip():
        try:
            tasks = json.loads(tasks_json)
        except Exception as e:  # noqa: BLE001
            return _trim({"error": f"tasks_json is not valid JSON ({e}). Pass `tasks` as a native list."})
    if not tasks:
        return _trim({"error": "no tasks given"})
    built = []
    for t in tasks:
        _check_path_scope(t["notebook_path"])
        item: dict = {"task_key": t["task_key"], "notebook_task": {"notebook_path": t["notebook_path"]}}
        if t.get("depends_on"):
            item["depends_on"] = [{"task_key": k} for k in t["depends_on"]]
        if max_retries:
            item["max_retries"] = max_retries
        built.append(item)
    tasks = built
    body: dict = {"name": name, "tasks": tasks}
    if cron:
        body["schedule"] = {"quartz_cron_expression": cron, "timezone_id": timezone, "pause_status": "PAUSED"}
    data = _post("/api/2.1/jobs/create", body)
    return _trim({"job_id": data.get("job_id"), "name": name, "tasks": [t["task_key"] for t in tasks],
                  "schedule": "created PAUSED" if cron else None,
                  "next": "call dbx_run_job(job_id, wait_seconds=300) to run it"})


@tool()
def dbx_run_job(job_id: int, wait_seconds: int = 45) -> str:
    """Trigger a job run. With wait_seconds > 0 wait for it and return per-task
    results (exit values, errors). Requires NBMCP_ALLOW_WRITES=1."""
    _need_writes()
    job = _get("/api/2.1/jobs/get", {"job_id": job_id})
    _check_prefix("job", (job.get("settings") or {}).get("name", ""), JOB_PREFIX)
    run_id = _post("/api/2.1/jobs/run-now", {"job_id": job_id})["run_id"]
    if wait_seconds > 0:
        return _run_summary(run_id, _wait_run(run_id, wait_seconds))
    return _trim({"run_id": run_id, "hint": "poll with dbx_job_run_status(run_id)"})


@tool()
def dbx_job_run_status(run_id: int, wait_seconds: int = 0) -> str:
    """State of a run, plus per-task exit values and error text once finished.
    wait_seconds > 0 blocks until it finishes or the time is up."""
    return _run_summary(run_id, _wait_run(run_id, wait_seconds) if wait_seconds else
                        _get("/api/2.1/jobs/runs/get", {"run_id": run_id}))


@tool()
def dbx_list_pipelines(limit: int = 25) -> str:
    """List Lakeflow Spark Declarative Pipelines."""
    data = _get("/api/2.0/pipelines", {"max_results": limit})
    return _trim(
        [{"pipeline_id": p.get("pipeline_id"), "name": p.get("name"),
          "state": p.get("state"), "catalog": p.get("catalog")}
         for p in data.get("statuses", data.get("pipelines", []))]
    )


@tool()
def dbx_list_warehouses() -> str:
    """List SQL warehouses and their state."""
    data = _get("/api/2.0/sql/warehouses")
    return _trim(
        [{"id": w.get("id"), "name": w.get("name"), "state": w.get("state"),
          "size": w.get("cluster_size"), "type": w.get("warehouse_type")}
         for w in data.get("warehouses", [])]
    )


# --------------------------------------------------------------------------
# workspace files, Lakebase, Apps
# --------------------------------------------------------------------------
@tool()
def dbx_write_file(path: str, content: str, overwrite: bool = True) -> str:
    """Write a plain workspace FILE (app.py, app.yaml, requirements.txt, .md ...),
    not a notebook. Parent folders are created. Path must be in the allowed paths."""
    _need_writes()
    _check_path_scope(path)
    _post("/api/2.0/workspace/mkdirs", {"path": path.rsplit("/", 1)[0]})
    _post("/api/2.0/workspace/import", {"path": path, "format": "AUTO", "overwrite": overwrite,
                                        "content": base64.b64encode(content.encode()).decode()})
    info = _get("/api/2.0/workspace/get-status", {"path": path})
    return _trim({"path": path, "object_type": info.get("object_type"), "bytes": len(content.encode())})


@tool()
def dbx_lakebase_create(name: str, capacity: str = "CU_1", wait_seconds: int = 45,
                        min_cu: float = 0, max_cu: float = 0) -> str:
    """Create a Lakebase Autoscaling project and wait until it is ready.

    A project is the container: it arrives with a `production` branch and a `primary` read-write
    compute. Idempotent — if it exists, its state is returned. The name must start with the session's
    allowed prefix and is the project id, so it must be lowercase letters, digits and hyphens.

    `capacity` is the Provisioned spelling and is accepted for compatibility: `CU_1` means 1 CU. Pass
    `min_cu`/`max_cu` for an autoscaling range (max − min ≤ 16, max ≤ 64; scale-to-zero needs max ≤ 32).

    Returns the project path, its `production` branch and the `next` call, because a model should copy
    an identity it was just given rather than remember one (spec 013 [LB-2], [LB-4]).
    """
    _need_writes()
    _check_prefix("instance", name, INSTANCE_PREFIX)
    problem = _capacity_problem(min_cu, max_cu)
    if problem:
        return _trim({"error": problem,
                      "hint": "reduce the maximum to min + 16, or use a fixed size, then call again"})
    project = _lakebase_project(name)
    if not re.match(r"^[a-z][a-z0-9-]{1,62}$", name):
        return _trim({"error": f"a Lakebase project id must be lowercase letters, digits and hyphens, "
                               f"starting with a letter; got {name!r}",
                      "hint": "lowercase the name and replace underscores with hyphens, then call again"})
    import time
    body: dict = {"project_id": name, "spec": {"display_name": name}}
    if min_cu or max_cu:
        body["spec"]["default_endpoint_settings"] = {
            "autoscaling_limit_min_cu": float(min_cu or 0.5),
            "autoscaling_limit_max_cu": float(max_cu or max(min_cu, 1.0)),
        }
    try:
        d = _get(f"/api/2.0/postgres/{project}")
    except httpx.HTTPStatusError as e:
        if e.response.status_code != 404:
            raise
        d = _post("/api/2.0/postgres/projects", body)
    t0 = time.time()
    while True:
        d = _get(f"/api/2.0/postgres/{project}")
        state = (d.get("status") or {}).get("state") or d.get("state") or ""
        if state in ("READY", "AVAILABLE", "ACTIVE") or time.time() - t0 > wait_seconds:
            break
        time.sleep(6)
    state = (d.get("status") or {}).get("state") or d.get("state") or ""
    ready = state in ("READY", "AVAILABLE", "ACTIVE")
    branch = _lakebase_endpoint(project, "production", "primary")
    return _trim({
        "project": project, "name": name, "state": state, "ready": ready,
        "branch": f"{project}/branches/production", "endpoint": branch,
        "next": None if ready else f"call dbx_lakebase_status('{name}') to wait for READY",
        "next_when_ready": f"call dbx_lakebase_branch(project='{project}', branch='agent-<your session>')",
    })


def _capacity_problem(min_cu: float, max_cu: float) -> str | None:
    """The platform's autoscaling rules, checked here so the answer names the rule (spec 013 [LB-4])."""
    lo, hi = float(min_cu or 0), float(max_cu or 0)
    if not lo and not hi:
        return None
    lo = lo or 0.5
    hi = hi or lo
    if lo < 0.5:
        return f"the minimum is 0.5 CU; got {lo}"
    if hi > 64:
        return f"the maximum is 64 CU; got {hi}"
    if hi < lo:
        return f"the maximum ({hi}) is below the minimum ({lo})"
    if hi - lo > 16:
        return (f"max − min must not exceed 16 CU; {hi} − {lo} = {hi - lo}. "
                f"Choose a maximum of at most {lo + 16}")
    return None


@tool()
def dbx_lakebase_status(name: str) -> str:
    """State of a Lakebase project: readiness, its branches, and its project id."""
    project = _lakebase_project(name)
    d = _get(f"/api/2.0/postgres/{project}")
    branches = _get(f"/api/2.0/postgres/{project}/branches").get("branches", [])
    return _trim({
        "project": project,
        "state": (d.get("status") or {}).get("state") or d.get("state") or "",
        "pgVersion": (d.get("status") or {}).get("pg_version") or (d.get("spec") or {}).get("pg_version"),
        "displayName": (d.get("status") or {}).get("display_name") or (d.get("spec") or {}).get("display_name"),
        "branches": [b.get("name", "").rsplit("/", 1)[-1] for b in branches],
    })


@tool()
def dbx_lakebase_list(limit: int = 50) -> str:
    """List the Lakebase projects this user can see."""
    data = _get("/api/2.0/postgres/projects", {"page_size": limit})
    return _trim([{"project": p.get("name"),
                   "displayName": (p.get("status") or {}).get("display_name")}
                  for p in data.get("projects", [])])


@tool()
def dbx_lakebase_branch(project: str, branch: str = "", from_branch: str = "production",
                        wait_seconds: int = 30) -> str:
    """Create a branch in a project, or list the branches when `branch` is empty.

    A branch is a copy-on-write copy: schema, data and roles at the moment it is created, isolated
    afterwards. Use one branch per session so a scaffold never writes to `production`
    (spec 013 [LB-2], [E-16]).
    """
    _need_writes()
    p = _lakebase_project(project)
    _check_prefix("instance", p.rsplit("/", 1)[-1], INSTANCE_PREFIX)
    if not branch:
        data = _get(f"/api/2.0/postgres/{p}/branches")
        return _trim([{"branch": b.get("name")} for b in data.get("branches", [])])
    if not re.match(r"^[a-z][a-z0-9-]{1,62}$", branch):
        return _trim({"error": f"a branch id must be lowercase letters, digits and hyphens; got {branch!r}"})
    body = {"branch_id": branch, "spec": {"source_branch": f"{p}/branches/{from_branch or 'production'}"}}
    try:
        _post(f"/api/2.0/postgres/{p}/branches", body)
    except httpx.HTTPStatusError as e:
        if e.response.status_code != 409:
            raise
    import time
    t0 = time.time()
    while True:
        d = _get(f"/api/2.0/postgres/{p}/branches/{branch}")
        state = (d.get("status") or {}).get("state") or ""
        if state in ("READY", "AVAILABLE", "ACTIVE") or time.time() - t0 > wait_seconds:
            break
        time.sleep(4)
    return _trim({"branch": f"{p}/branches/{branch}", "from": from_branch, "state": state,
                  "next": f"call dbx_lakebase_sql(project='{p.rsplit('/', 1)[-1]}', "
                          f"branch='{branch}', sql='CREATE SCHEMA IF NOT EXISTS app')"})


@tool()
def dbx_lakebase_database(project: str, branch: str = "production", database: str = "") -> str:
    """Create a database in a branch, or list the branch's databases when `database` is empty.

    Most work needs none: every branch arrives with `databricks_postgres`, and a schema inside it is
    cheaper than a database.
    """
    _need_writes()
    p = _lakebase_project(project)
    _check_prefix("instance", p.rsplit("/", 1)[-1], INSTANCE_PREFIX)
    if not database:
        data = _get(f"/api/2.0/postgres/{p}/branches/{branch}/databases")
        return _trim([{"database": d.get("name")} for d in data.get("databases", [])])
    _pg_identifier(database, "database")
    try:
        d = _post(f"/api/2.0/postgres/{p}/branches/{branch}/databases",
                  {"database_id": database, "spec": {}})
    except httpx.HTTPStatusError as e:
        if e.response.status_code != 409:
            raise
        d = _get(f"/api/2.0/postgres/{p}/branches/{branch}/databases/{database}")
    return _trim({"database": d.get("name") or f"{p}/branches/{branch}/databases/{database}",
                  "next": f"call dbx_lakebase_sql(project='{p.rsplit('/', 1)[-1]}', "
                          f"branch='{branch}', database='{database}', sql='SELECT 1')"})


@tool()
def dbx_lakebase_role(project: str, branch: str = "production", role: str = "") -> str:
    """List the Postgres roles on a branch, or read one by name.

    An app's role is created by the PLATFORM when its `postgres` resource is attached: the role name is
    the service principal's client id. So a scaffold does not create that role — it attaches the
    resource and then reads the role back here to prove it exists (spec 013 [RB-4], [SCF-1] step 4).
    """
    p = _lakebase_project(project)
    data = _get(f"/api/2.0/postgres/{p}/branches/{branch}/roles")
    roles = data.get("roles", [])
    rows = [{"role": r.get("name", "").rsplit("/", 1)[-1],
             "identity": (r.get("spec") or {}).get("postgres_role") or (r.get("status") or {}).get("postgres_role"),
             "type": (r.get("spec") or {}).get("identity_type")} for r in roles]
    if role:
        rows = [r for r in rows if r["role"] == role or r["identity"] == role]
        if not rows:
            return _trim({"found": False, "role": role, "roles": rows,
                          "hint": "attach the app's postgres resource first; the platform creates the role"})
    return _trim({"found": bool(rows), "roles": rows})


@tool()
def dbx_lakebase_compute(project: str, branch: str = "production", endpoint: str = "primary",
                         min_cu: float = 0, max_cu: float = 0) -> str:
    """Read a branch's compute, or set its autoscaling range.

    Reading returns the endpoint type, the range, the host and whether the compute is suspended.
    Setting validates the platform's rules first: max − min ≤ 16, max ≤ 64, min ≥ 0.5
    (spec 013 [LB-4]).
    """
    p = _lakebase_project(project)
    path = f"/api/2.0/postgres/{p}/branches/{branch}/endpoints/{endpoint or 'primary'}"
    if min_cu or max_cu:
        _need_writes()
        problem = _capacity_problem(min_cu, max_cu)
        if problem:
            return _trim({"error": problem})
        _patch(path, {"spec": {"autoscaling_limit_min_cu": float(min_cu or 0.5),
                               "autoscaling_limit_max_cu": float(max_cu)}})
    d = _get(path)
    status = d.get("status") or {}
    return _trim({
        "endpoint": d.get("name") or path,
        "type": status.get("endpoint_type"),
        "state": status.get("current_state"),
        "host": (status.get("hosts") or {}).get("host", ""),
        "minCu": status.get("autoscaling_limit_min_cu"),
        "maxCu": status.get("autoscaling_limit_max_cu"),
        "lastActive": status.get("last_active_time"),
    })


def _lakebase_endpoint(project: str, branch: str = "production", endpoint: str = "primary") -> str:
    """The read-write endpoint's resource path. The one place that builds this string.

    Lakebase addresses a compute as `projects/{p}/branches/{b}/endpoints/{e}`. Every credential and
    every connection names one, because a token minted for an endpoint is what authorises the
    connection: there is no "instance" to name any more (spec 013 [LB-1], [RB-6]).
    """
    p = _lakebase_project(project)
    b = branch or "production"
    if b.startswith("projects/"):
        b = b.rsplit("/", 1)[-1]
    return f"{p}/branches/{b}/endpoints/{endpoint or 'primary'}"


def _lakebase_project(name: str) -> str:
    """`pg_tickets` and `projects/pg_tickets` are one object (spec 013 [LB-5])."""
    n = (name or "").strip().strip("/")
    return n if n.startswith("projects/") else f"projects/{n}"


def _pg_identifier(value: str, what: str) -> str:
    """An identifier that needs escaping is not an identifier (spec 013 [E-19]).

    The connection string is assembled by the driver from these values, and the SQL may interpolate
    them. Refusing a quote or a semicolon here is cheaper and stricter than escaping downstream.
    """
    import re as _re
    if not _re.match(r"^[A-Za-z_][A-Za-z0-9_$]*$", value or ""):
        raise ValueError(
            f"{what} must be a plain Postgres identifier (letters, digits, underscore; no quotes, "
            f"spaces or semicolons); got {value!r}")
    return value


def _lakebase_token(endpoint: str) -> str:
    """Mint a credential for one endpoint. Never cached: a cached token is a credential on disk."""
    import uuid
    return _post("/api/2.0/postgres/credentials",
                 {"endpoint": endpoint, "request_id": str(uuid.uuid4())}).get("token", "")


def _lakebase_connect(endpoint: str, database: str, user: str):
    """One connection, for one statement batch, closed by the caller.

    `psycopg` v3 is what this app already ships (`requirements.txt`); `psycopg2` was imported here and
    declared nowhere, which is why the card's first data step raised ModuleNotFoundError
    (spec 013 [F1]). The token is minted per call by design: the tool runs SQL the agent wrote.
    """
    import psycopg
    d = _get(endpoint)
    host = ((d.get("status") or {}).get("hosts") or {}).get("host", "")
    if not host:
        raise RuntimeError(
            f"{endpoint} has no host yet; the compute is still starting. A connection resumes a "
            "suspended compute, so call again in a few seconds.")
    token = _lakebase_token(endpoint)
    if not token:
        raise RuntimeError("the workspace returned no Lakebase credential for this endpoint")
    return psycopg.connect(host=host, port=5432, dbname=_pg_identifier(database, "database"),
                           user=user, password=token, sslmode="require", connect_timeout=20)


@tool()
def dbx_lakebase_sql(project: str, sql: str, branch: str = "production",
                     database: str = "databricks_postgres", limit: int = 100) -> str:
    """Run SQL on a Lakebase database using a short-lived credential.

    `project` is the id or the full path ("pg_tickets" or "projects/pg_tickets"). `branch` names which
    branch the SQL runs on; the read-write compute of THAT branch is used, so a scaffold writes to its
    own branch and never to `production` (spec 013 [LB-3], [E-16]).

    Multiple statements are allowed. Returns rows for a query, or the row count for a write.
    """
    _need_writes()
    _check_prefix("instance", project, INSTANCE_PREFIX)
    endpoint = _lakebase_endpoint(project, branch)
    me = _get("/api/2.0/preview/scim/v2/Me").get("userName")
    conn = None
    try:
        conn = _lakebase_connect(endpoint, database, me)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(sql)
        if cur.description:
            cols = [c.name for c in cur.description]
            rows = cur.fetchall()
            return _trim({"columns": cols, "rows": [[str(v) for v in r] for r in rows[:limit]],
                          "row_count": len(rows), "branch": _branch_name(endpoint),
                          "database": database})
        return _trim({"ok": True, "rowcount": cur.rowcount, "branch": _branch_name(endpoint),
                      "database": database})
    except Exception as e:  # noqa: BLE001 - a driver error is a fact the agent must read, not a crash
        return _trim({"error": str(e)[:600], "branch": _branch_name(endpoint)})
    finally:
        if conn is not None:
            conn.close()


def _branch_name(endpoint: str) -> str:
    """`projects/p/branches/b/endpoints/e` -> `b`. Used only to report which branch ran."""
    parts = endpoint.split("/")
    return parts[parts.index("branches") + 1] if "branches" in parts else ""


@tool()
def dbx_lakebase_tables(project: str, branch: str = "production", schema: str = "public",
                        database: str = "databricks_postgres", limit: int = 50) -> str:
    """Tables in a schema of a Lakebase database, with a row count for each.

    The count is bounded: a table that takes longer than 5 s reports `>= 1000` rather than 0, because
    "could not count" and "empty" are different facts and a page must not confuse them
    (spec 013 [E-18]). At most `limit` tables are listed; `truncated` says whether more exist.
    """
    _need_writes()
    endpoint = _lakebase_endpoint(project, branch)
    me = _get("/api/2.0/preview/scim/v2/Me").get("userName")
    _pg_identifier(schema, "schema")
    _pg_identifier(database, "database")
    conn = None
    try:
        conn = _lakebase_connect(endpoint, database, me)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = %s AND table_type = 'BASE TABLE' "
            "ORDER BY table_name LIMIT %s", (schema, limit + 1))
        names = [r[0] for r in cur.fetchall()]
        truncated = len(names) > limit
        names = names[:limit]
        rows = []
        for name in names:
            safe = name.replace('"', '""')
            try:
                cur.execute('SET LOCAL statement_timeout = 5000')
                cur.execute(f'SELECT count(*) FROM "{schema}"."{safe}"')
                rows.append({"table": name, "rows": cur.fetchone()[0]})
            except Exception:  # noqa: BLE001 - a slow table is a bound, not a failure
                conn.rollback()
                rows.append({"table": name, "rows": ">= 1000", "note": "count timed out"})
        return _trim({"schema": schema, "database": database, "branch": _branch_name(endpoint),
                      "tables": rows, "truncated": truncated})
    except Exception as e:  # noqa: BLE001
        return _trim({"error": str(e)[:600], "branch": _branch_name(endpoint)})
    finally:
        if conn is not None:
            conn.close()


@tool()
def dbx_create_app(name: str, source_code_path: str = "", project: str = "", branch: str = "",
                   database: str = "databricks_postgres", scopes: list[str] | None = None,
                   wait_seconds: int = 90) -> str:
    """Create (and deploy) a Databricks App, optionally wired to a Lakebase database.

    Pass `project` and `branch` when the app should read the database: that becomes a `postgres`
    RESOURCE, which is what makes the platform inject PGHOST/PGDATABASE/PGUSER/PGSSLMODE and create
    the app's Postgres role. An app created without it starts and cannot connect — the defect this
    signature exists to remove (spec 013 [AP-1], [F6]).

    The name must start with this session's app prefix. The platform's answer is returned verbatim,
    including refusals: quote it, and never claim a deployment you did not observe running.
    """
    _need_writes()
    if not re.match(r"^[a-z0-9][a-z0-9-]{0,28}[a-z0-9]$", name):
        return _trim({"error": f"an app name is 2–30 lowercase letters, digits and hyphens, starting and "
                               f"ending with a letter or digit; got {name!r}",
                      "hint": "lowercase the name and replace underscores with hyphens, then call again"})
    _check_prefix("app", name, APP_PREFIX)
    if source_code_path:
        _check_path_scope(source_code_path)
    resources: list[dict] = []
    if project:
        if not branch:
            return _trim({"error": "a postgres resource needs a branch; pass branch='<your session branch>'",
                          "hint": "do not use 'production': create a branch for this session first"})
        p = _lakebase_project(project)
        resources.append({"name": "postgres", "postgres": {
            "branch": f"{p}/branches/{branch}",
            "database": f"{p}/branches/{branch}/databases/{database}",
            "permission": "CAN_CONNECT_AND_CREATE",
        }})
    body: dict = {"name": name}
    if resources:
        body["resources"] = resources
        body["user_api_scopes"] = scopes or ["postgres"]
    elif scopes:
        body["user_api_scopes"] = scopes
    with _client() as c:
        r = c.post("/api/2.0/apps", json=body)
        if not r.is_success:
            return _trim({"created": False, "http_status": r.status_code,
                          "platform_error": r.text[:800],
                          "do_not_retry": "a refusal will not change on a second identical call; "
                                          "report this text to the user"})
        app = r.json()
        out: dict = {"created": True, "app": app.get("name"), "url": app.get("url"),
                     "servicePrincipal": app.get("service_principal_client_id"),
                     "resources": [x.get("name") for x in (app.get("resources") or [])]}
        if source_code_path:
            dep = c.post(f"/api/2.0/apps/{name}/deployments",
                         json={"source_code_path": source_code_path})
            out["deploy_http_status"] = dep.status_code
            if not dep.is_success:
                out["platform_error"] = dep.text[:600]
                out["verified"] = False
                return _trim(out)
            out["verified"], out["state"] = _wait_app(c, name, wait_seconds)
        else:
            out["verified"], out["state"] = _wait_app(c, name, wait_seconds)
        out["next"] = (f"call dbx_app_health(app='{name}') to prove it answers"
                       if out["verified"] else
                       f"read the logs at {out.get('url') or ''}/logz, then fix and redeploy")
        return _trim(out)


def _wait_app(c, name: str, wait_seconds: int) -> tuple[bool, str]:
    """Poll until the app is RUNNING. `verified` is what was OBSERVED, never what was requested.

    `SUCCEEDED` on a deployment means the process started, not that it is running your code — the
    distinction this repository learned the expensive way (spec 013 [AP-3]).
    """
    import time
    t0 = time.time()
    state = ""
    while time.time() - t0 <= min(wait_seconds, 120):
        try:
            d = c.get(f"/api/2.0/apps/{name}").json()
        except Exception:  # noqa: BLE001 - a read failure is not a deployment verdict
            time.sleep(3)
            continue
        state = ((d.get("app_status") or {}).get("state")
                 or (d.get("active_deployment") or {}).get("status", {}).get("state", ""))
        if state == "RUNNING":
            return True, state
        if state in ("CRASHED", "ERROR", "FAILED"):
            return False, state
        time.sleep(3)
    return False, state or "UNKNOWN"


@tool()
def dbx_app_health(app: str, wait_seconds: int = 15) -> str:
    """Fetch a Databricks App's URL and report the status code and the time it took.

    This is the proof that an app works (spec 013 [AP-4]). A first request after the app scaled to
    zero is slow and is reported as `starting`, not `down`: an app that is waking is healthy
    (spec 013 [E-14]).
    """
    d = _get(f"/api/2.0/apps/{app}")
    url = d.get("url") or ""
    if url and not url.startswith("http"):
        url = "https://" + url
    if not url:
        return _trim({"app": app, "state": "no-url", "detail": "the platform has not assigned a URL yet"})
    import time
    t0 = time.time()
    try:
        with httpx.Client(timeout=min(wait_seconds, 30), follow_redirects=True) as c:
            r = c.get(url)
        ms = int((time.time() - t0) * 1000)
        if r.status_code < 500:
            state = "running"
        else:
            state = "failing"
        return _trim({"app": app, "url": url, "status": r.status_code, "ms": ms, "state": state,
                      "logs": f"{url}/logz"})
    except httpx.TimeoutException:
        return _trim({"app": app, "url": url, "state": "starting",
                      "detail": f"no response in {wait_seconds}s: a cold start, or a hung process",
                      "logs": f"{url}/logz"})
    except httpx.HTTPError as e:
        return _trim({"app": app, "url": url, "state": "unreachable", "detail": type(e).__name__,
                      "logs": f"{url}/logz"})


# --------------------------------------------------------------------------
# skills (progressive disclosure: the index is cheap, a skill is read on demand)
# --------------------------------------------------------------------------
SKILLS_DIR = os.environ.get("NBMCP_SKILLS_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills"))


@tool()
def dbx_skill(name: str = "") -> str:
    """Read a how-to skill. Call with no name to list the skills (one line each),
    then call with a name BEFORE starting that kind of task. Skills hold exact
    formats and workspace-specific facts that are easy to get wrong from memory."""
    import glob
    paths = sorted(glob.glob(os.path.join(SKILLS_DIR, "*.md")))
    index = {}
    for p in paths:
        stem = os.path.splitext(os.path.basename(p))[0]
        with open(p) as f:
            first = f.readline().strip().lstrip("# ").strip()
        index[stem] = first
    if not name:
        return _trim({"skills": index, "usage": "dbx_skill(name='<skill>')"})
    if name not in index:
        return _trim({"error": f"unknown skill '{name}'", "skills": index})
    with open(os.path.join(SKILLS_DIR, name + ".md")) as f:
        return f.read()


if __name__ == "__main__":
    transport = os.environ.get("NBMCP_TRANSPORT", "stdio")
    if transport == "http":
        mcp.settings.port = int(os.environ.get("NBMCP_PORT", "8799"))
        mcp.settings.host = os.environ.get("NBMCP_HOST", "127.0.0.1")
        mcp.run(transport="streamable-http")
    else:
        mcp.run()
