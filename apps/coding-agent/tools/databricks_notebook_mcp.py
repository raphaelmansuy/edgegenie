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
    "dbx_write_file", "dbx_run_notebook", "dbx_create_job", "dbx_run_job", "dbx_job_run_status",
    "dbx_lakebase_create", "dbx_lakebase_status", "dbx_lakebase_sql", "dbx_create_app", "dbx_skill",
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


def _check_prefix(kind: str, name: str, prefix: str) -> None:
    if prefix and not name.startswith(prefix):
        raise PermissionError(f"write blocked: {kind} name must start with '{prefix}' (got '{name}')")


def _check_path_scope(path: str) -> None:
    if WRITE_PATHS and not any(path.startswith(p) for p in WRITE_PATHS):
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


@tool()
def dbx_run_notebook(path: str, parameters_json: str = "{}", wait_seconds: int = 45) -> str:
    """Run a notebook ONCE on serverless compute and wait for the result.

    Returns the state, the dbutils.notebook.exit() value and, on failure, the
    error and the tail of the stack trace. If it is still running after
    wait_seconds you get finished=false and a run_id to poll with
    dbx_job_run_status.

    Kept short on purpose: a tool that blocks for minutes produces no ACP events, so the turn looks
    dead and the app's idle guard fires. Poll instead.
    """
    _need_writes()
    _check_path_scope(path)
    task: dict = {"task_key": "t", "notebook_task": {"notebook_path": path}}
    params = json.loads(parameters_json or "{}")
    if params:
        task["notebook_task"]["base_parameters"] = {k: str(v) for k, v in params.items()}
    run_id = _post("/api/2.1/jobs/runs/submit", {"run_name": "nbmcp-run", "tasks": [task]})["run_id"]
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
def dbx_lakebase_create(name: str, capacity: str = "CU_1", wait_seconds: int = 45) -> str:
    """Create a Lakebase (managed Postgres) instance and wait until AVAILABLE.
    Idempotent: if it exists, returns its state. Name must start with the allowed prefix."""
    _need_writes()
    _check_prefix("instance", name, INSTANCE_PREFIX)
    import time
    try:
        _get(f"/api/2.0/database/instances/{name}")
    except httpx.HTTPStatusError:
        _post("/api/2.0/database/instances", {"name": name, "capacity": capacity})
    t0 = time.time()
    while True:
        d = _get(f"/api/2.0/database/instances/{name}")
        if d.get("state") == "AVAILABLE" or time.time() - t0 > wait_seconds:
            break
        time.sleep(8)
    return _trim({"name": name, "state": d.get("state"), "capacity": d.get("capacity"),
                  "host": d.get("read_write_dns"), "database": "databricks_postgres",
                  "hint": None if d.get("state") == "AVAILABLE" else "not AVAILABLE yet: call dbx_lakebase_status"})


@tool()
def dbx_lakebase_status(name: str) -> str:
    """State, host and capacity of a Lakebase instance."""
    d = _get(f"/api/2.0/database/instances/{name}")
    return _trim({"name": name, "state": d.get("state"), "capacity": d.get("capacity"),
                  "host": d.get("read_write_dns"), "database": "databricks_postgres"})


@tool()
def dbx_lakebase_sql(instance: str, sql: str, database: str = "databricks_postgres", limit: int = 100) -> str:
    """Run SQL on a Lakebase (Postgres) instance using a short-lived credential.
    Multiple statements allowed. Returns rows for queries, or the row count."""
    _need_writes()
    _check_prefix("instance", instance, INSTANCE_PREFIX)
    import uuid
    import psycopg2
    d = _get(f"/api/2.0/database/instances/{instance}")
    cred = _post("/api/2.0/database/credentials", {"request_id": str(uuid.uuid4()), "instance_names": [instance]})
    me = _get("/api/2.0/preview/scim/v2/Me").get("userName")
    conn = psycopg2.connect(host=d["read_write_dns"], port=5432, dbname=database, user=me,
                            password=cred["token"], sslmode="require", connect_timeout=20)
    conn.autocommit = True
    try:
        cur = conn.cursor()
        cur.execute(sql)
        if cur.description:
            cols = [c.name for c in cur.description]
            rows = cur.fetchall()
            return _trim({"columns": cols, "rows": [[str(v) for v in r] for r in rows[:limit]], "row_count": len(rows)})
        return _trim({"ok": True, "rowcount": cur.rowcount})
    except Exception as e:  # noqa: BLE001
        return _trim({"error": str(e)[:600]})
    finally:
        conn.close()


@tool()
def dbx_create_app(name: str, source_code_path: str = "") -> str:
    """Try to create (and deploy) a Databricks App. Returns the platform's answer
    verbatim, including refusals (some workspaces require a Git repository for
    Apps). Report that text to the user exactly; never claim a deploy that failed."""
    _need_writes()
    _check_prefix("app", name, INSTANCE_PREFIX)
    if source_code_path:
        _check_path_scope(source_code_path)
    with _client() as c:
        r = c.post("/api/2.0/apps", json={"name": name})
        if not r.is_success:
            return _trim({"created": False, "http_status": r.status_code, "platform_error": r.text[:800]})
        app = r.json()
        if source_code_path:
            dep = c.post(f"/api/2.0/apps/{name}/deployments", json={"source_code_path": source_code_path})
            return _trim({"created": True, "app": app.get("name"), "url": app.get("url"),
                          "deploy_http_status": dep.status_code, "deploy": dep.text[:600]})
        return _trim({"created": True, "app": app.get("name"), "url": app.get("url")})


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
