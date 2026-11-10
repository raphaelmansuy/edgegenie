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
# fewer, better tools beat many. `core` registers the tools a session actually needs; `full` also
# registers the rarely-used lookups.
#
# THE BUDGET IS 28, AND IT IS A BUDGET (spec 014 [TOOL-1]). Before spec 014 it was 25 and a test asserted
# equality. The raise is a recorded decision, not a drift: three Lakebase scaffold calls left (each is
# named by `skills/lakebase-postgres.md`, so still discoverable through `dbx_skill`), and one tool was
# added for jobs and five for pipelines. `07 §6` of spec 014 carries the arithmetic and the two merges
# that were considered and rejected. Every member must be reachable from a page or a skill.
PROFILE = os.environ.get("NBMCP_PROFILE", "full")
_CORE = {
    "dbx_whoami", "dbx_list_tables", "dbx_describe_table", "dbx_search_tables", "dbx_run_sql",
    "dbx_list_notebooks", "dbx_read_notebook", "dbx_grep_notebook", "dbx_write_notebook",
    "dbx_write_file", "dbx_run_notebook", "dbx_run_notebook_status", "dbx_skill",
    # jobs (spec 014). `dbx_list_jobs` was missing until 014: an agent could create a job and never
    # enumerate one, which is [F6].
    "dbx_list_jobs", "dbx_create_job", "dbx_run_job", "dbx_job_run_status", "dbx_job_failure_context",
    # pipelines (spec 014). There was one read-only pipeline tool before; a pipeline could not be built.
    "dbx_create_pipeline", "dbx_pipeline_status", "dbx_start_pipeline", "dbx_stop_pipeline",
    # Lakebase (spec 013). The scaffold trio left `core` in 014 and stays registered in `full`.
    "dbx_lakebase_create", "dbx_lakebase_status", "dbx_lakebase_branch", "dbx_lakebase_sql",
    "dbx_create_app", "dbx_app_health",
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


def _sp_token() -> str:
    """The APP'S SERVICE PRINCIPAL token, for the one API that cannot be called as the user.

    `[RB-10]`: `postgres` is "always bound to the SP, not OBO", so a user's forwarded token never
    carries it and every `/api/2.0/postgres` call 403s no matter what scope the app declares. The
    host app writes a second token file for exactly this; when it is absent (a laptop) the user
    token is returned so behaviour is unchanged outside a deployment.
    """
    path = os.environ.get("NBMCP_SP_TOKEN_FILE", "")
    if path:
        try:
            with open(path, encoding="utf-8") as fh:
                sp = fh.read().strip()
            if sp:
                return sp
        except OSError:
            pass
    return _token()


def _sp_client() -> httpx.Client:
    """An HTTP client authenticated as the service principal. Same refusal contract as `_client`.

    EVERY call under `/api/2.0/postgres` must go through this and never through `_client`. The rule is
    the platform's, not ours (spec 013 [RB-10]):

        `postgres` — Lakebase (always bound to the SP, not OBO)

    A forwarded user token therefore never carries it, so `_get`/`_post`/`_patch` against a Postgres
    path answer 403 for every user no matter which scopes the app declares. That is measured, not
    inferred: on the deployed app the same human's PAT read `projects/coding-agent-llm` with a 200
    while the tool reported 403 for it.

    The three helpers below exist so that "which identity" is a property of the PATH'S API rather than
    of the call site — a call site is what got it wrong.
    """
    token = _sp_token()
    if not HOST or not token:
        raise RuntimeError(
            "the workspace connection is not available to this tool server: "
            "this is an app configuration problem, not something to retry or work around")
    return httpx.Client(
        event_hooks={"response": [_refuse_response]},
        base_url=HOST,
        headers={"Authorization": f"Bearer {token}"},
        timeout=120.0,
    )


def _has_sp() -> bool:
    """True when a real service-principal token file is present (a deployment, not a laptop).

    `_sp_token()` falls back to the user token so that a laptop keeps working; this predicate is how a
    caller says *which* case it is in, without reading the file a second time.
    """
    path = os.environ.get("NBMCP_SP_TOKEN_FILE", "")
    if not path:
        return False
    try:
        with open(path, encoding="utf-8") as fh:
            return bool(fh.read().strip())
    except OSError:
        return False


def _refuse_response(response: httpx.Response) -> None:
    """Turn a 401/403 on a service-principal call into a sentence the model can act on.

    **The distinction that matters.** A 403 on `/api/2.0/postgres` almost never means "your permissions
    are wrong". It means one of two things, and conflating them sent a live investigation down a
    three-tool dead end:

    * the call carried a **user** token, which can never carry `postgres` ([RB-10]) — a product defect;
    * the call carried the **SP** token and the SP genuinely lacks the permission — a grant to make.

    Both used to print "permission denied by the workspace … the signed-in user or this app's
    authorization does not allow it", which reads as *the user needs a grant* and invites an agent to
    retry, re-authenticate, or blame an id. So this hook names the identity that was used, states that
    retrying cannot help, and — for the user-token case — says it is a defect in this tool server
    rather than something the caller can fix.
    """
    if response.status_code not in (401, 403):
        return
    used_sp = _has_sp()
    path = response.request.url.path
    identity = (
        "the app's service principal" if used_sp
        else "the signed-in user's token, and this API cannot be called with a user token"
    )
    raise PermissionError(
        f"permission denied by the workspace for {response.request.method} {path}. "
        f"The request was made as {identity}. "
        + ("" if used_sp else
           "That is a defect in this tool server, not something to work around: /api/2.0/postgres is "
           "always bound to the service principal. Report it and stop. Do not call this tool again. ")
        + "A retry with the same identity will fail identically."
    )


def _get_sp(path: str, params: dict | None = None) -> Any:
    """A GET as the service principal, for the Postgres API ([RB-10])."""
    def go():
        with _sp_client() as c:
            r = c.get(path, params=params)
            r.raise_for_status()
            return r.json()
    return _retry(go, idempotent=True)


def _post_sp(path: str, body: dict | None = None) -> Any:
    def go():
        with _sp_client() as c:
            r = c.post(path, json=body or {})
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") \
                else {"raw": r.text}
            r.raise_for_status()
            return data
    return _retry(go, idempotent=False)


def _patch_sp(path: str, body: dict | None = None) -> Any:
    """A partial update as the service principal. Idempotent: the same body twice leaves one state.

    Postgres has no `_patch` path that may use the user token, so there is no user-token twin here.
    """
    def go():
        with _sp_client() as c:
            r = c.patch(path, json=body or {})
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") \
                else {"raw": r.text}
            r.raise_for_status()
            return data
    return _retry(go, idempotent=True)


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

#: How this process reaches the host app's run service, and — since spec 014 — the identity half of an
#: idempotency token (see `_idempotency_token`). Defined HERE rather than beside the run helpers below,
#: because a module constant read at call time is fine and one read at import time below its user is not:
#: the first draft placed these 130 lines later and `dbx_list_jobs` referenced `RUN_SESSION` before it
#: existed, which is a NameError only on the path that uses it.
RUN_URL = os.environ.get("NBMCP_RUN_URL", "")
RUN_SESSION = os.environ.get("NBMCP_RUN_SESSION", "")
RUN_KEY = os.environ.get("NBMCP_RUN_KEY", "")


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
#: Imported by path, not `import job_graph`: the tool server is spawned as a script
#: (`python3 tools/databricks_notebook_mcp.py`), so `tools/` is `sys.path[0]` and a plain import would
#: work — but it would also work by ACCIDENT of how the process was launched, and a test that imports
#: this module by path would get a second copy. One loader, used by this file and by `api/domain/jobs.py`
#: (spec 014 [RB-5]).
def _graph_module():
    """`tools/job_graph.py` — the validation and levelling rules, shared with the app."""
    global _GRAPH
    try:
        return _GRAPH
    except NameError:
        pass
    import importlib.util
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "job_graph.py")
    spec = importlib.util.spec_from_file_location("job_graph", path)
    _GRAPH = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_GRAPH)
    return _GRAPH


def _idempotency_token(job_id: int, purpose: str) -> str:
    """A stable token per (session, job, purpose), so two identical runs make ONE run.

    `run-now` accepts `idempotency_token`: "If a run with the provided token already exists, the request
    does not create a new run but returns the run ID of the existing run." Without it, a retried call — or
    a double click — starts a second run of a job that bills per minute (spec 014 [TOOL-5], [E-5]).

    The session id makes two conversations independent: a user re-running "yesterday's" job in a new
    conversation should get a new run, and should not be handed the run from the first one.
    """
    import hashlib
    session = RUN_SESSION or "local"
    raw = f"{session}:{job_id}:{purpose}".encode()
    return hashlib.sha256(raw).hexdigest()[:40]


@tool()
def dbx_list_jobs(limit: int = 25, include_runs: bool = True) -> str:
    """List jobs, each with its latest run's state when `include_runs`.

    The Jobs API's list payload carries NO run state (spec 014 [F6]) — the docstring used to claim it did
    — so the state comes from one `runs/list?limit=1` per job. `include_runs=False` skips that, for a
    caller that only wants names.

    `runsUnread` names the jobs whose run state could not be read, so "no runs" and "not read" are never
    the same answer (spec 014 [E-9]).
    """
    data = _get("/api/2.2/jobs/list", {"limit": min(max(limit, 1), 100), "expand_tasks": "false"})
    rows = []
    unread = []
    for j in data.get("jobs", []):
        settings = j.get("settings") or {}
        schedule = settings.get("schedule") or {}
        row = {
            "job_id": j.get("job_id"),
            "name": settings.get("name"),
            "schedule": {
                "cron": schedule.get("quartz_cron_expression"),
                "timezone": schedule.get("timezone_id"),
                "paused": (schedule.get("pause_status") or "").upper() == "PAUSED",
            } if schedule else None,
            "owner": settings.get("run_as_user_name") or j.get("creator_user_name"),
        }
        if include_runs and row["job_id"]:
            try:
                runs = _get("/api/2.2/jobs/runs/list",
                            {"job_id": row["job_id"], "limit": 1}).get("runs") or []
                if runs:
                    state = runs[0].get("state") or {}
                    row["lastRun"] = {
                        "run_id": runs[0].get("run_id"),
                        "life_cycle": state.get("life_cycle_state"),
                        "result": state.get("result_state"),
                        "start_time": runs[0].get("start_time"),
                        "end_time": runs[0].get("end_time"),
                    }
                else:
                    row["lastRun"] = None
            except Exception as e:  # noqa: BLE001 - one unreadable job is not a failed list
                unread.append(row["job_id"])
                row["lastRun"] = None
        rows.append(row)
    return _trim(rows if not unread else {"jobs": rows, "runsUnread": unread})


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
                o = _get("/api/2.2/jobs/runs/get-output", {"run_id": t["run_id"]})
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
        d = _get("/api/2.2/jobs/runs/get", {"run_id": run_id})
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
        run_id = _post("/api/2.2/jobs/runs/submit", {"run_name": "nbmcp-run", "tasks": [task]})["run_id"]
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
                   max_retries: int = 0, tasks_json: str = "", timeout_seconds: int = 0,
                   performance_target: str = "STANDARD") -> str:
    """Create a Databricks Job whose tasks are notebooks, on serverless compute, via Jobs API 2.2.

    `tasks` is a list of objects (native list, not a string), in any order:
      [{"task_key": "silver", "notebook_path": "/Users/me/x/silver", "depends_on": []},
       {"task_key": "gold",   "notebook_path": "/Users/me/x/gold",   "depends_on": ["silver"]}]

    A task may carry `timeout_seconds` and `max_retries` of its own, and exactly one task type:
    `notebook_path`, `python_file`, `sql_file`, `pipeline_id` or `job_id`.

    The graph is validated HERE, before any HTTP call: unique keys, known dependencies, exactly one type
    per task, no cycle. A malformed graph returns every problem in one sentence and creates NOTHING —
    the platform's own `400` for the same graph says less and arrives after a round trip (spec 014
    [TOOL-3], [F3]).

    `cron` is an optional Quartz expression ("0 0 6 * * ?") and the schedule is created PAUSED, so an
    agent cannot start a recurring cost without the user resuming it ([JOB-4]).

    Queueing is on explicitly (2.2's default made visible) so a run requested while the job is busy is
    queued instead of skipped ([TOOL-2], [E-6]).
    """
    _need_writes()
    _check_prefix("job", name, JOB_PREFIX)
    if tasks is None and tasks_json.strip():
        try:
            tasks = json.loads(tasks_json)
        except Exception as e:  # noqa: BLE001
            return _trim({"error": f"tasks_json is not valid JSON ({e}). Pass `tasks` as a native list."})
    if not isinstance(tasks, list):
        return _trim({"error": "tasks must be a list of objects, not "
                               f"{type(tasks).__name__}; each task is "
                               "{'task_key': ..., 'notebook_path': ...}"})

    graph = _graph_module()
    found = graph.problems(tasks)
    if found:
        # Every problem, one sentence, ZERO calls made. `nothing_was_created` is the half that stops a
        # model from reporting a job that does not exist (spec 014 [E-3]).
        return _trim({"error": "; ".join(found), "nothing_was_created": True,
                      "hint": "fix every problem named above and call again; nothing was sent to Databricks"})

    built = [_task_body(t, max_retries) for t in tasks]

    body: dict = {
        "name": name,
        "tasks": built,
        "queue": {"enabled": True},
        "performance_target": performance_target if performance_target in
        ("PERFORMANCE_OPTIMIZED", "STANDARD", "COST_OPTIMIZED") else "STANDARD",
    }
    if timeout_seconds:
        body["timeout_seconds"] = int(timeout_seconds)
    if cron:
        body["schedule"] = {"quartz_cron_expression": cron, "timezone_id": timezone,
                            "pause_status": "PAUSED"}
    try:
        data = _post("/api/2.2/jobs/create", body)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 400:
            return _trim({"created": False, "http_status": 400,
                          "platform_error": e.response.text[:800], "nothing_was_created": True,
                          "hint": "the platform refused the settings; report this text, do not retry"})
        raise
    return _trim({
        "job_id": data.get("job_id"), "name": name,
        "tasks": [t["task_key"] for t in built],
        "levels": graph.levels(tasks),
        "summary": graph.describe(tasks),
        "schedule": ({"cron": cron, "timezone": timezone, "pauseStatus": "PAUSED"} if cron else None),
        "queueing": "on",
        "next": (f"call dbx_run_job(job_id={data.get('job_id')}, purpose='first-run') to run it once"
                 if not cron else
                 f"the schedule is PAUSED; call dbx_run_job(job_id={data.get('job_id')}) to prove it "
                 "works now, and tell the user nothing runs on a schedule until they resume it"),
    })


#: How one task type becomes the platform's task body. ONE table, so a new type is a row and the two
#: maps the first draft used (a key and an inner field, kept in step by hand) cannot drift. `None` as the
#: inner field means the id IS the inner value; `notebook_path` is the nested common case.
_TASK_BODY: dict[str, tuple[str, str | None]] = {
    "notebook_path": ("notebook_task", "notebook_path"),
    "python_file": ("spark_python_task", "python_file"),
    "sql_file": ("sql_task", "file"),
    "pipeline_id": ("pipeline_task", "pipeline_id"),
    "job_id": ("run_job_task", "job_id"),
}


def _task_body(task: dict, default_retries: int) -> dict:
    """One task as the Jobs API 2.2 wants it. `task` has already passed `job_graph.problems()`.

    The shape is `{task_key, <one task type field>, depends_on[], max_retries?, timeout_seconds?}`. The
    task type is looked up, never guessed: `problems()` guarantees exactly one is present.
    """
    kind = next(k for k in _TASK_BODY if task.get(k))
    field, inner = _TASK_BODY[kind]
    value = task[kind]
    if kind in ("notebook_path", "python_file", "sql_file"):
        _check_path_scope(value)             # the fence, on the write targets only
    item: dict = {
        "task_key": task["task_key"],
        field: {inner: value} if inner else value,
    }
    if task.get("depends_on"):
        item["depends_on"] = [{"task_key": k} for k in task["depends_on"]]
    retries = task.get("max_retries", default_retries)
    if retries:
        item["max_retries"] = int(retries)
    if task.get("timeout_seconds"):
        item["timeout_seconds"] = int(task["timeout_seconds"])
    return item


@tool()
def dbx_run_job(job_id: int, wait_seconds: int = 45, purpose: str = "run") -> str:
    """Trigger a job run and, with wait_seconds > 0, return per-task results. Requires writes.

    **Idempotent.** The run carries an `idempotency_token` derived from (session, job, `purpose`), so
    calling twice with the same purpose returns the SAME run instead of starting a second one that bills
    (spec 014 [TOOL-5], [F2]). Use a different `purpose` for a deliberate re-run after a fix, e.g.
    `"retry-after-fix"`.

    The job is re-read and its NAME re-checked against this session's prefix before anything is
    triggered: the fence is re-applied to the object the platform returned, not to the id in the
    arguments ([TOOL-4]).
    """
    _need_writes()
    job = _get("/api/2.2/jobs/get", {"job_id": job_id})
    _check_prefix("job", (job.get("settings") or {}).get("name", ""), JOB_PREFIX)

    token = _idempotency_token(job_id, purpose)
    # Read the newest run BEFORE the call, so the result can say whether this call created one or re-used
    # one. The platform does not tell us: it answers with a run id either way.
    before = _newest_run_id(job_id)
    run_id = _post("/api/2.2/jobs/run-now",
                   {"job_id": job_id, "idempotency_token": token})["run_id"]
    reused = before is not None and run_id == before

    if wait_seconds > 0:
        summary = _run_summary(run_id, _wait_run(run_id, wait_seconds))
        return summary if not reused else _annotate(summary, {"reused": True, "purpose": purpose})
    return _trim({"run_id": run_id, "reused": reused, "purpose": purpose,
                  "job_id": job_id,
                  "hint": "poll with dbx_job_run_status(run_id)"})


def _newest_run_id(job_id: int) -> int | None:
    """The most recent run of a job, or None. One call, `limit=1`; a failure here is not a failure to run."""
    try:
        runs = _get("/api/2.2/jobs/runs/list", {"job_id": job_id, "limit": 1}).get("runs") or []
        return runs[0].get("run_id") if runs else None
    except Exception:  # noqa: BLE001 - the annotation is a courtesy, never a reason to fail
        return None


def _annotate(summary_json: str, extra: dict) -> str:
    """One string with a few keys added. A summary is JSON, so this re-parses rather than concatenating:
    a model reading two JSON documents in one string guesses which is true."""
    try:
        data = json.loads(summary_json)
    except (ValueError, TypeError):
        return summary_json
    if not isinstance(data, dict):
        return summary_json
    data.update(extra)
    return _trim(data)


@tool()
def dbx_job_failure_context(job_id: int) -> str:
    """Why a job's last run failed — assembled from three calls, in one answer.

    Returns the failing task, its error and the tail of its trace, the tables that task's notebook reads
    with their REAL columns, and the last successful run's duration.

    This exists because "why did my job fail?" is the most common question after a job turn, and a model
    left to assemble it makes three calls and has three chances to conclude "the job is broken" when the
    truth is "the column was renamed" (spec 014 [06 §7]). The schema hint is the same trick
    `dbx_run_notebook` already uses on a failed run: read the tables the code names, and hand back the
    columns that actually exist.
    """
    job = _get("/api/2.2/jobs/get", {"job_id": job_id})
    settings = job.get("settings") or {}
    name = settings.get("name", "")
    # NO prefix fence here, deliberately: this tool only READS, and inspecting a job you may not run is
    # not a write. `dbx_lakebase_branch` already draws this line between listing and creating, and a model
    # asked "why did this fail?" about a colleague's job must be able to answer (spec 014 [E-2]).

    runs = _get("/api/2.2/jobs/runs/list", {"job_id": job_id, "limit": 10}).get("runs") or []
    failed = next((r for r in runs
                   if (r.get("state") or {}).get("result_state") in ("FAILED", "TIMEDOUT")), None)
    last_ok = next((r for r in runs
                    if (r.get("state") or {}).get("result_state") == "SUCCESS"), None)
    if failed is None:
        return _trim({"job_id": job_id, "name": name, "failed": False,
                      "note": ("no failed run in the last 10" if runs else "this job has never run"),
                      "lastSuccess": _run_brief(last_ok) if last_ok else None})

    detail = _get("/api/2.2/jobs/runs/get", {"run_id": failed["run_id"]})
    tasks = _task_outputs(detail)
    broken = next((t for t in tasks if t.get("result") in ("FAILED", "TIMEDOUT")), None) \
        or (tasks[0] if tasks else None)

    hints = _schema_hints(settings, broken.get("task_key") if broken else "")
    return _trim({
        "job_id": job_id, "name": name, "failed": True,
        "run_id": failed.get("run_id"),
        "when": failed.get("start_time"),
        "failingTask": broken,
        "lastSuccess": _run_brief(last_ok) if last_ok else None,
        "tables": hints,
        "next": ("fix the code using exactly these column names, then call "
                 "dbx_run_job(job_id, purpose='retry-after-fix') — a NEW purpose, so the re-run is a new "
                 "run rather than the re-use of the failed one"),
    })


def _run_brief(run: dict) -> dict:
    state = run.get("state") or {}
    return {"run_id": run.get("run_id"), "result": state.get("result_state"),
            "start_time": run.get("start_time"), "end_time": run.get("end_time")}


def _schema_hints(settings: dict, task_key: str) -> list[dict]:
    """The tables the failing task's notebook reads, with their real columns.

    A notebook task names a path; the notebook is exported and scanned for `from`/`join` targets. This is
    the same approach `dbx_run_notebook` uses, and it is bounded: at most three tables, and any failure
    yields an empty list rather than a worse error.
    """
    path = ""
    for task in settings.get("tasks") or []:
        if task.get("task_key") == task_key:
            path = (task.get("notebook_task") or {}).get("notebook_path") or ""
            break
    if not path:
        return []
    try:
        import base64 as _b64
        exported = _get("/api/2.0/workspace/export", {"path": path, "format": "SOURCE"})
        source = _b64.b64decode(exported.get("content") or "").decode(errors="replace")
    except Exception:  # noqa: BLE001 - a hint is a bonus, never a reason to fail
        return []
    tables = sorted(set(re.findall(r"\b(?:from|join)\s+([\w.]+)", source, re.I)))[:3]
    out = []
    for table in tables:
        if table.count(".") != 2:
            continue
        try:
            columns = _get(f"/api/2.1/unity-catalog/tables/{table}").get("columns") or []
            out.append({"table": table, "columns": [c.get("name") for c in columns]})
        except Exception:  # noqa: BLE001
            continue
    return out


@tool()
def dbx_job_run_status(run_id: int, wait_seconds: int = 0) -> str:
    """State of a run, plus per-task exit values and error text once finished.
    wait_seconds > 0 blocks until it finishes or the time is up.

    `life_cycle` and `result` are separate on purpose: a run that failed is `TERMINATED` + `FAILED`, and
    `TERMINATED` alone is not a verdict (spec 014 [E-10])."""
    return _run_summary(run_id, _wait_run(run_id, wait_seconds) if wait_seconds else
                        _get("/api/2.2/jobs/runs/get", {"run_id": run_id}))


@tool()
def dbx_list_pipelines(limit: int = 25) -> str:
    """List Lakeflow Spark Declarative Pipelines, each with its LAST UPDATE's state.

    The list payload's `state` is the PIPELINE's state, and `IDLE` means both "never run" and "the last
    update failed" — so it cannot answer "did the last run work?" (spec 014 [F5], [TOOL-8]). Each row
    therefore carries `lastUpdate` from the pipeline's own `latest_updates`, and `null` when it has never
    been updated.
    """
    data = _get("/api/2.0/pipelines", {"max_results": min(max(limit, 1), 100)})
    rows = []
    for p in data.get("statuses", data.get("pipelines", [])):
        updates = p.get("latest_updates") or []
        latest = updates[0] if updates else None
        rows.append({
            "pipeline_id": p.get("pipeline_id"),
            "name": p.get("name"),
            "state": p.get("state"),
            "lastUpdate": ({"update_id": latest.get("update_id"), "state": latest.get("state"),
                            "creation_time": latest.get("creation_time")} if latest else None),
            "catalog": p.get("catalog"),
            "creator": p.get("creator_user_name"),
        })
    return _trim(rows)


# ---------------------------------------------------------------------------------------------
# pipelines: the ledger fence
# ---------------------------------------------------------------------------------------------
#: The ledger of pipelines THIS session created. A pipeline id is a platform UUID with no session prefix,
#: so a prefix rule cannot exist; the honest rule is "did this conversation make it?" (spec 014 [TOOL-6],
#: [RB-3]). It lives in a FILE the host app owns and passes by path, because the tool server is a
#: subprocess that dies with the session and 010's durable sessions make a restart routine.
LEDGER = os.environ.get("NBMCP_SESSION_LEDGER", "")


def _ledger_read() -> list[dict]:
    """Every object this session created, newest last. A missing or unreadable file is an empty ledger:
    a fence that fails closed on a corrupt file would refuse work the user can see they did."""
    if not LEDGER:
        return []
    try:
        with open(LEDGER, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]
    except (OSError, ValueError):
        return []


def _ledger_add(kind: str, identifier: str, name: str) -> None:
    """Append one object. Best effort by design: the ledger is a fence input, and failing a CREATE because
    the fence could not be recorded would refuse the work rather than protect it. The caller is told."""
    if not LEDGER:
        return
    import time
    try:
        os.makedirs(os.path.dirname(LEDGER) or ".", exist_ok=True)
        with open(LEDGER, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"kind": kind, "id": identifier, "name": name,
                                 "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}) + "\n")
    except OSError:
        pass


def _ledger_has(kind: str, identifier: str) -> bool:
    return any(row.get("kind") == kind and str(row.get("id")) == str(identifier)
               for row in _ledger_read())


def _pipeline_fence(identifier: str) -> None:
    """Refuse a pipeline this session did not create, in words that say what that means.

    Not "permission denied": a permission is something an admin can grant, and no grant makes a pipeline
    this conversation's. The distinction is what stops a user being sent to the wrong person (spec 014
    [TOOL-6], [E-2]).
    """
    _check_prefix("pipeline", identifier, PIPELINE_PREFIX)
    if PIPELINE_PREFIX:
        return                      # a prefix IS a fence, when one is configured
    if _ledger_has("pipeline", identifier):
        return
    known = [row.get("name") for row in _ledger_read() if row.get("kind") == "pipeline"]
    raise PermissionError(
        f"write blocked: pipeline {identifier} was not created in this conversation. "
        f"This session created {len(known)}"
        + (f" ({', '.join(str(k) for k in known[:5])})" if known else "")
        + ". A pipeline someone else owns is changed in Databricks; open it there.")


PIPELINE_PREFIX = os.environ.get("NBMCP_WRITE_PIPELINE_PREFIX", "")


def _pipeline_body_module():
    """`tools/pipeline_body.py` — the shape rules, shared with the tests. Loaded by path, like the graph."""
    global _PIPE_BODY
    try:
        return _PIPE_BODY
    except NameError:
        pass
    import importlib.util
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pipeline_body.py")
    spec = importlib.util.spec_from_file_location("pipeline_body", path)
    _PIPE_BODY = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_PIPE_BODY)
    return _PIPE_BODY


@tool()
def dbx_create_pipeline(name: str, notebooks: list[str] | None = None, files: list[str] | None = None,
                        catalog: str = "", schema: str = "", edition: str = "ADVANCED",
                        channel: str = "CURRENT", continuous: bool = False,
                        development: bool = False) -> str:
    """Create a Lakeflow Spark Declarative Pipeline on serverless compute, with its id recorded.

    A pipeline is NOT a job. Use one when the user says pipeline, declarative, streaming table,
    expectation, or medallion; a job orchestrates notebooks and has no lineage graph. The `etl-pipelines`
    skill is the decision table.

    `notebooks` / `files` are the paths `dbx_write_notebook` / `dbx_write_file` returned — inside this
    session's folder. `catalog` and `schema` are required (a serverless pipeline always publishes to Unity
    Catalog), and `edition` defaults ADVANCED because expectations need it.

    The pipeline is created but NOT started: call dbx_start_pipeline(validate_only=True) to check the code
    for free, then dbx_start_pipeline() to run it.
    """
    _need_writes()
    pipes = _pipeline_body_module()
    _check_prefix("pipeline", name, PIPELINE_PREFIX)
    try:
        body = pipes.build(name=name, notebooks=notebooks, files=files, catalog=catalog, schema=schema,
                           edition=edition, channel=channel, continuous=continuous,
                           development=development, check_path=_check_path_scope)
    except pipes.PipelineProblem as e:
        return _trim({"error": str(e), "nothing_was_created": True})
    try:
        data = _post("/api/2.0/pipelines", body)
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (400, 403):
            return _trim({"created": False, "http_status": e.response.status_code,
                          "platform_error": e.response.text[:800], "nothing_was_created": True,
                          "hint": _serverless_hint(e.response.text),
                          "do_not_retry": "this refusal will not change on a second identical call"})
        raise
    identifier = data.get("pipeline_id") or ""
    _ledger_add("pipeline", identifier, name)
    return _trim({
        "created": True, "pipeline_id": identifier, "name": name, "state": data.get("state"),
        "libraries": pipes.describe_libraries(body),
        "catalog": body.get("catalog"), "schema": body.get("schema"),
        "serverless": True, "edition": body.get("edition"),
        "next": (f"call dbx_start_pipeline(pipeline_id='{identifier}', validate_only=True) to check the "
                 "code without materialising anything, then call it again with no validate_only to run it"),
    })


def _serverless_hint(platform_text: str) -> str:
    """Name the three workspace properties a serverless pipeline needs, when the refusal is about them.

    A `400` saying "serverless is not enabled" does not tell a user which of three settings to change.
    Saying so once, here, is cheaper than a user discovering it in three tabs (spec 014 [RB-8], [E-4]).
    """
    lowered = (platform_text or "").lower()
    if "serverless" in lowered or "edition" in lowered or "catalog" in lowered:
        return ("a serverless pipeline needs: Unity Catalog enabled, the ADVANCED edition, and the "
                "serverless terms accepted in this region. Check the workspace's serverless settings, "
                "or build a classic pipeline in Databricks and open it here")
    return "report this text to the user; do not retry"


@tool()
def dbx_pipeline_status(pipeline_id: str, include_events: bool = True, events: int = 20) -> str:
    """A pipeline, its last three updates, and (by default) its recent events — one call, one object.

    The `state` here is the PIPELINE's; the answer to "did the last run work?" is `lastUpdate.state`,
    which is `COMPLETED`, `FAILED` or absent when the pipeline has never updated (spec 014 [PIPE-5]).
    """
    pipes = _pipeline_body_module()
    identifier = _pipeline_id(pipeline_id)
    detail = _get(f"/api/2.0/pipelines/{identifier}")
    spec = detail.get("spec") or {}
    updates = _get(f"/api/2.0/pipelines/{identifier}/updates",
                   {"max_results": 3}).get("updates") or []
    latest = updates[0] if updates else None
    out: dict = {
        "pipeline_id": identifier,
        "name": spec.get("name"),
        "state": detail.get("state"),
        "lastUpdate": ({"update_id": latest.get("update_id"), "state": latest.get("state"),
                        "creation_time": latest.get("creation_time"),
                        "full_refresh": latest.get("full_refresh")} if latest else None),
        "updates": [{"update_id": u.get("update_id"), "state": u.get("state"),
                     "creation_time": u.get("creation_time")} for u in updates],
        "libraries": pipes.describe_libraries(spec),
        "catalog": spec.get("catalog"),
        "schema": spec.get("schema"),
        "serverless": spec.get("serverless"),
        "edition": spec.get("edition"),
        "channel": spec.get("channel"),
        "continuous": spec.get("continuous"),
        "activeUpdate": next((u.get("update_id") for u in updates
                              if (u.get("state") or "").upper() in
                              ("QUEUED", "WAITING_FOR_RESOURCES", "INITIALIZING", "RESETTING",
                               "CREATING_FLOW", "RUNNING")), None),
    }
    if include_events:
        out["events"] = _pipeline_events(identifier, events)
        failed = (latest or {}).get("state") == "FAILED"
        if failed:
            first_error = next((e for e in out["events"]
                                if (e.get("level") or "").upper() == "ERROR"), None)
            out["failureDetail"] = first_error.get("message") if first_error else (
                "the platform reported a FAILED update with no ERROR event")
    return _trim(out)


def _pipeline_events(identifier: str, limit: int = 20) -> list[dict]:
    """Recent events, errors and warnings first.

    A model reading 200 INFO lines spends its context on nothing, so the filter is applied server-side
    and the order puts the thing that went wrong first (spec 014 [06 §7], [PIPE-6]).
    """
    try:
        data = _get(f"/api/2.0/pipelines/{identifier}/events",
                    {"max_results": min(max(limit, 1), 100),
                     "filter": "level in ('ERROR', 'WARN')"})
        events_list = data.get("events") or []
    except httpx.HTTPStatusError:
        return []
    rank = {"ERROR": 0, "WARN": 1, "INFO": 2}
    rows = [{"level": (e.get("level") or "").upper(), "message": (e.get("message") or "")[:400],
             "timestamp": e.get("timestamp"),
             "stack_trace": (e.get("details") or {}).get("stack_trace")}
            for e in events_list]
    rows.sort(key=lambda r: rank.get(r["level"], 9))
    return rows


@tool()
def dbx_start_pipeline(pipeline_id: str, full_refresh: bool = False, validate_only: bool = False,
                       refresh_selection: list[str] | None = None,
                       full_refresh_selection: list[str] | None = None,
                       wait_seconds: int = 0) -> str:
    """Start an update of a pipeline this session created.

    Three modes, each with its own cost, and the caller must choose:
      * `validate_only=True` — checks the code, materialises NOTHING, is free;
      * (neither)            — incremental: re-reads only new data;
      * `full_refresh=True`  — resets every table and re-reads every source. Expensive.

    If the pipeline is already being updated the platform refuses, and the refusal names the active update
    so the user can watch it instead of retrying (spec 014 [E-7]).
    """
    _need_writes()
    pipes = _pipeline_body_module()
    identifier = _pipeline_id(pipeline_id)
    _pipeline_fence(identifier)
    try:
        body = pipes.start_body(full_refresh=full_refresh, validate_only=validate_only,
                                refresh_selection=refresh_selection,
                                full_refresh_selection=full_refresh_selection)
    except pipes.PipelineProblem as e:
        return _trim({"error": str(e), "nothing_was_started": True})
    try:
        data = _post(f"/api/2.0/pipelines/{identifier}/updates", body)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 400:
            active = _active_update(identifier)
            return _trim({"started": False, "http_status": 400,
                          "platform_error": e.response.text[:600],
                          "activeUpdate": active,
                          "hint": (f"update {active} is already running; watch it with "
                                   "dbx_pipeline_status" if active else
                                   "the platform refused the update; report this text")})
        raise
    update_id = data.get("update_id")
    out: dict = {"started": True, "pipeline_id": identifier, "update_id": update_id,
                 "mode": ("validated only" if validate_only else
                          "full refresh" if full_refresh else "incremental")}
    if wait_seconds > 0:
        out.update(_wait_update(identifier, update_id, wait_seconds))
    else:
        out["hint"] = (f"call dbx_start_pipeline(pipeline_id='{identifier}', wait_seconds=120) to watch "
                       "it, or dbx_pipeline_status to read the result")
    return _trim(out)


def _active_update(identifier: str) -> str | None:
    try:
        updates = _get(f"/api/2.0/pipelines/{identifier}/updates",
                       {"max_results": 3}).get("updates") or []
    except httpx.HTTPStatusError:
        return None
    for u in updates:
        if (u.get("state") or "").upper() in ("QUEUED", "WAITING_FOR_RESOURCES", "INITIALIZING",
                                              "RESETTING", "CREATING_FLOW", "RUNNING"):
            return u.get("update_id")
    return None


def _wait_update(identifier: str, update_id: str | None, wait_seconds: int) -> dict:
    """Poll an update until it is terminal or the time is up. A `validate_only` update finishes fast."""
    import time
    t0 = time.time()
    state = ""
    while True:
        try:
            d = _get(f"/api/2.0/pipelines/{identifier}/updates/{update_id}")
        except httpx.HTTPStatusError:
            return {"waiting": False, "note": "the update could not be read; check dbx_pipeline_status"}
        state = ((d.get("update") or {}).get("state") or d.get("state") or "").upper()
        if state in ("COMPLETED", "FAILED", "CANCELED") or time.time() - t0 >= wait_seconds:
            break
        time.sleep(4)
    return {"updateState": state or "unknown",
            "finished": state in ("COMPLETED", "FAILED", "CANCELED")}


@tool()
def dbx_stop_pipeline(pipeline_id: str) -> str:
    """Stop the active update of a pipeline this session created.

    Refused when nothing is active, with the reason: a Stop that always succeeds teaches a user that the
    button did something (spec 014 [PIPE-4]).
    """
    _need_writes()
    identifier = _pipeline_id(pipeline_id)
    _pipeline_fence(identifier)
    active = _active_update(identifier)
    if not active:
        return _trim({"stopped": False, "reason": "no update is active on this pipeline",
                      "hint": "nothing to stop; dbx_pipeline_status shows its last update"})
    try:
        _post(f"/api/2.0/pipelines/{identifier}/updates/{active}/cancel", {})
    except httpx.HTTPStatusError as e:
        return _trim({"stopped": False, "update_id": active, "http_status": e.status_code,
                      "platform_error": e.response.text[:600]})
    return _trim({"stopped": True, "update_id": active,
                  "note": "cancellation is asynchronous: the update may still be running for a moment",
                  "hint": f"call dbx_pipeline_status(pipeline_id='{identifier}') to see it finish"})


@tool()
def dbx_pipeline_edit(pipeline_id: str, name: str = "", notebooks: list[str] | None = None,
                      files: list[str] | None = None) -> str:
    """Replace a pipeline's libraries (and optionally its name) with a new list.

    An edit REPLACES the library list, so a file that is dropped stops being part of the pipeline and its
    tables stop being maintained. The removed paths are named in the result, so a removal cannot happen
    silently (spec 014 [E-18]).
    """
    _need_writes()
    pipes = _pipeline_body_module()
    identifier = _pipeline_id(pipeline_id)
    _pipeline_fence(identifier)
    current = _get(f"/api/2.0/pipelines/{identifier}")
    spec = current.get("spec") or {}
    try:
        body = pipes.build(name=name or spec.get("name") or "",
                           notebooks=notebooks, files=files,
                           catalog=spec.get("catalog") or "",
                           schema=spec.get("schema") or "",
                           serverless=bool(spec.get("serverless", True)),
                           edition=spec.get("edition") or "ADVANCED",
                           channel=spec.get("channel") or "CURRENT",
                           continuous=bool(spec.get("continuous")),
                           development=bool(spec.get("development")),
                           check_path=_check_path_scope)
    except pipes.PipelineProblem as e:
        return _trim({"error": str(e), "nothing_was_changed": True})
    body["id"] = identifier
    try:
        _put(f"/api/2.0/pipelines/{identifier}", body)
    except httpx.HTTPStatusError as e:
        return _trim({"updated": False, "http_status": e.status_code,
                      "platform_error": e.response.text[:600]})
    removed = pipes.removed_libraries(spec, body)
    return _trim({"updated": True, "pipeline_id": identifier,
                  "libraries": pipes.describe_libraries(body),
                  "removed": removed,
                  "warning": (f"{len(removed)} library path(s) removed from the pipeline; their tables "
                              "will no longer be maintained" if removed else None),
                  "next": "start an update to apply the new code" if removed else
                          "call dbx_start_pipeline(validate_only=True) to check the new code"})


def _pipeline_id(value: str) -> str:
    """A pipeline id as the platform spells it. A NAME is refused with the alternative, because a 404 for
    a name reads as a permission problem (spec 014 [E-17], the class 013's [RB-12] recorded)."""
    text = (value or "").strip()
    if not text:
        raise ValueError(
            "a pipeline is named by its id, for example 'f0e1c4a2-…-9a2b'. "
            "Call dbx_list_pipelines to find the id.")
    looks_uuid = len(text) == 36 and text.count("-") == 4 and all(
        c in "0123456789abcdef-" for c in text.lower())
    if not looks_uuid and not _ledger_has("pipeline", text):
        import re as _re
        if not _re.match(r"^[A-Za-z0-9-]+$", text):
            raise ValueError(f"{text!r} is not a pipeline id")
        if "-" not in text:
            raise ValueError(
                f"{text!r} looks like a pipeline NAME; a pipeline is identified by its UUID. "
                "Call dbx_list_pipelines to find the id.")
    return text


def _put(path: str, body: dict) -> Any:
    """A full replacement. Idempotent: the same body twice leaves one state."""
    def go():
        with _client() as c:
            r = c.put(path, json=body)
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") \
                else {"raw": r.text}
            r.raise_for_status()
            return data
    return _retry(go, idempotent=True)


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
        d = _get_sp(f"/api/2.0/postgres/{project}")
    except httpx.HTTPStatusError as e:
        if e.response.status_code != 404:
            raise
        d = _post_sp("/api/2.0/postgres/projects", body)
    t0 = time.time()
    # MEASURED: a PROJECT has no state field, so polling one always waited the full timeout and then
    # reported ready=false for a project that was fine. Readiness belongs to the default BRANCH, whose
    # status carries `current_state` (spec 013 [RB-12]).
    state = ""
    while True:
        branches = _get_sp(f"/api/2.0/postgres/{project}/branches").get("branches", [])
        default = next((b for b in branches if (b.get("status") or {}).get("default")), None)
        state = ((default or {}).get("status") or {}).get("current_state") or ""
        if state in ("READY", "AVAILABLE", "ACTIVE") or time.time() - t0 > wait_seconds:
            break
        time.sleep(6)
    ready = state in ("READY", "AVAILABLE", "ACTIVE")
    branch = _lakebase_endpoint(project, "production", "primary")
    return _trim({
        "project": project, "name": name, "defaultBranchState": state, "ready": ready,
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
    """State of a Lakebase project: its branches, their computes, and whether anything is suspended.

    `name` is the project ID (`coding-agent-llm`), never a display name. A display name can contain
    spaces and a word like "dev", and a 404 for a guessed id reads as a permission problem — which is
    what happened when an agent turned `coding-agent-llm dev` into `coding-agent-llm-dev` and was told
    "permission denied" (spec 013 [RB-12]). Call dbx_lakebase_list first if you are unsure.
    """
    project = _lakebase_project(name)
    try:
        d = _get_sp(f"/api/2.0/postgres/{project}")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            try:
                known = [p.get("name", "").rsplit("/", 1)[-1]
                         for p in _get_sp("/api/2.0/postgres/projects").get("projects", [])]
            except Exception:  # noqa: BLE001 - the hint is a courtesy
                known = []
            return _trim({
                "error": f"no Lakebase project with id {project!r}",
                "not_a_permission_problem": True,
                "knownProjectIds": known,
                "hint": "pass one of knownProjectIds. A display name is not an id; call "
                        "dbx_lakebase_list to see both.",
            })
        raise
    status = d.get("status") or {}
    branches = _get_sp(f"/api/2.0/postgres/{project}/branches").get("branches", [])

    observed = []
    for b in branches:
        bstatus = b.get("status") or {}
        bid = (b.get("name") or "").rsplit("/", 1)[-1]
        eps = _get_sp(f"/api/2.0/postgres/{project}/branches/{bid}/endpoints").get("endpoints", [])
        computes = []
        for e in eps:
            est = e.get("status") or {}
            lo, hi = est.get("autoscaling_limit_min_cu"), est.get("autoscaling_limit_max_cu")
            spread = round((hi - lo), 2) if (lo is not None and hi is not None) else None
            computes.append({
                "endpoint": (e.get("name") or "").rsplit("/", 1)[-1],
                "type": (est.get("endpoint_type") or "").replace("ENDPOINT_TYPE_", "").lower(),
                # MEASURED: a compute's state is `current_state`, and a suspended compute reports
                # SUSPENDED/IDLE here rather than a separate flag.
                "state": est.get("current_state"),
                "suspended": (est.get("current_state") or "").upper() in ("SUSPENDED", "IDLE"),
                "disabled": est.get("disabled"),
                "min_cu": lo, "max_cu": hi, "spread_cu": spread,
                "range_legal": (spread is not None and spread <= 16
                                and (lo or 0) >= 0.5 and (hi or 0) <= 64),
                "last_active": est.get("last_active_time"),
                "host": (est.get("hosts") or {}).get("host", ""),
            })
        observed.append({
            "branch": bid,
            # MEASURED: `current_state` and `default`, not `state` and `is_default`.
            "state": bstatus.get("current_state"),
            "is_default": bool(bstatus.get("default")),
            "protected": bool(bstatus.get("is_protected")),
            "computes": computes,
        })

    return _trim({
        "project": project,
        "displayName": status.get("display_name"),
        "pgVersion": status.get("pg_version"),
        "owner": status.get("owner"),
        # A project has no state of its own; readiness is per branch and per compute. Saying so is
        # more useful than emitting an empty string.
        "note": "a project has no state field; readiness is reported per branch and per compute",
        "branches": observed,
        "anythingSuspended": any(c["suspended"] for b in observed for c in b["computes"]),
        "everyRangeLegal": all(c["range_legal"] for b in observed for c in b["computes"]) if observed else None,
    })


@tool()
def dbx_lakebase_list(limit: int = 50) -> str:
    """List the Lakebase projects this user can see."""
    data = _get_sp("/api/2.0/postgres/projects", {"page_size": limit})
    return _trim([{"project": p.get("name"),
                   "displayName": (p.get("status") or {}).get("display_name")}
                  for p in data.get("projects", [])])


@tool()
def dbx_lakebase_branch(project: str, branch: str = "", from_branch: str = "production",
                        wait_seconds: int = 30) -> str:
    """Create a branch in a project, or list its branches when `branch` is empty.

    A branch is a copy-on-write copy: schema, data and roles at the moment it is created, isolated
    afterwards. Use one branch per session so a scaffold never writes to `production`
    (spec 013 [LB-2], [E-16]).

    LISTING is a read and works on any project you can see — inspecting infrastructure is not creating
    it. CREATING must name a project inside this session's prefix, and a refusal says so plainly
    rather than looking like a permission problem on a remote object (spec 013 [RB-12]).
    """
    p = _lakebase_project(project)
    if not branch:
        data = _get_sp(f"/api/2.0/postgres/{p}/branches")
        return _trim([{
            "branch": (b.get("name") or "").rsplit("/", 1)[-1],
            "state": (b.get("status") or {}).get("current_state"),
            "is_default": bool((b.get("status") or {}).get("default")),
        } for b in data.get("branches", [])])

    _need_writes()
    _check_prefix("instance", p.rsplit("/", 1)[-1], INSTANCE_PREFIX)
    if not re.match(r"^[a-z][a-z0-9-]{1,62}$", branch):
        return _trim({"error": f"a branch id must be lowercase letters, digits and hyphens; got {branch!r}"})
    body = {"branch_id": branch,
            "spec": {"source_branch": f"{p}/branches/{from_branch or 'production'}"}}
    try:
        _post_sp(f"/api/2.0/postgres/{p}/branches", body)
    except httpx.HTTPStatusError as e:
        if e.response.status_code != 409:      # already exists is the idempotent case
            raise
    import time
    t0 = time.time()
    # MEASURED: a branch reports `current_state`, not `state`.
    state = ""
    while True:
        d = _get_sp(f"/api/2.0/postgres/{p}/branches/{branch}")
        state = (d.get("status") or {}).get("current_state") or ""
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
        data = _get_sp(f"/api/2.0/postgres/{p}/branches/{branch}/databases")
        return _trim([{"database": d.get("name")} for d in data.get("databases", [])])
    _pg_identifier(database, "database")
    try:
        d = _post_sp(f"/api/2.0/postgres/{p}/branches/{branch}/databases",
                  {"database_id": database, "spec": {}})
    except httpx.HTTPStatusError as e:
        if e.response.status_code != 409:
            raise
        d = _get_sp(f"/api/2.0/postgres/{p}/branches/{branch}/databases/{database}")
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
    data = _get_sp(f"/api/2.0/postgres/{p}/branches/{branch}/roles")
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
        _patch_sp(path, {"spec": {"autoscaling_limit_min_cu": float(min_cu or 0.5),
                                  "autoscaling_limit_max_cu": float(max_cu)}})
    d = _get_sp(path)
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
    """Mint a credential for one endpoint. Never cached: a cached credential is a credential on disk."""
    import uuid
    return _post_sp("/api/2.0/postgres/credentials",
                 {"endpoint": endpoint, "request_id": str(uuid.uuid4())}).get("token", "")


def _lakebase_connect_user(project: str, branch: str, wanted: str) -> str:
    """The Postgres username to connect as, taken from the branch's ROLES.

    The `postgres_role` field is on a role's `status`, not on the endpoint: an earlier version read it
    from the endpoint, got `""`, and every connection failed (spec 013 [RB-11]).

    **Which role, when a branch has several.** The credential and the role must belong to the same
    identity, because a Lakebase credential "may only be used by the identity that minted it"
    ([RB-11] part 2). The credential is minted with the SERVICE PRINCIPAL token, so the connection must
    be the service principal's role. Picking `roles[0]` was therefore wrong in the one deployment that
    has two roles, and it failed in the most confusing way available: the management calls succeeded and
    the connection reported `OAuth: User is not authorized`.

    Order of preference, the same rule `adapters/databricks/lakebase.py::_connect_role` implements:

    1. the app's own service principal, when this process has one (`DATABRICKS_CLIENT_ID`);
    2. the caller's identity, when the caller has a role (a laptop, or a hand-provisioned branch);
    3. the only role, when the branch has exactly one — unambiguous, so it cannot be the wrong one.

    Anything else is a refusal that names the roles, because silently picking one would read another
    identity's objects.
    """
    p = _lakebase_project(project)
    data = _get_sp(f"/api/2.0/postgres/{p}/branches/{branch or 'production'}/roles")
    identities = [((r.get("status") or {}).get("postgres_role")
                   or (r.get("spec") or {}).get("postgres_role") or "")
                  for r in data.get("roles", [])]
    identities = [i for i in identities if i]

    # 1. The identity the credential was minted by, when this process has one.
    client_id = os.environ.get("DATABRICKS_CLIENT_ID", "")
    if _has_sp() and client_id and client_id in identities:
        return client_id
    # 2. The caller, when the caller has a role of their own.
    if wanted and wanted in identities:
        return wanted
    # 3. The only role: nothing to choose, so nothing to choose wrongly.
    if len(identities) == 1:
        return identities[0]
    if not identities:
        raise RuntimeError(
            f"no Postgres role on branch {branch or 'production'}; attach a database resource to the "
            "app (the platform creates the role) or create one with dbx_lakebase_role")
    raise RuntimeError(
        f"this branch has {len(identities)} roles and none matches this app's identity "
        f"({', '.join(identities)}); a credential may only be used by the identity that minted it, so "
        "connecting as another one fails with 'User is not authorized'. Attach the app's postgres "
        "resource so the platform creates its role")


def _lakebase_connect(endpoint: str, database: str, user: str):
    """One connection, for one statement batch, closed by the caller.

    `psycopg` v3 is what this app already ships (`requirements.txt`); `psycopg2` was imported here and
    declared nowhere, which is why the card's first data step raised ModuleNotFoundError
    (spec 013 [F1]). The token is minted per call by design: the tool runs SQL the agent wrote.
    """
    import psycopg
    d = _get_sp(endpoint)
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
    # Connect as a role that EXISTS on this branch. The Postgres username is on a role object,
    # not on the endpoint, and the signed-in identity matches a role only when it was granted
    # (spec 013 [RB-11]).
    me = _lakebase_connect_user(project, branch, _get("/api/2.0/preview/scim/v2/Me").get("userName"))
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
    me = _lakebase_connect_user(project, branch, _get("/api/2.0/preview/scim/v2/Me").get("userName"))
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
