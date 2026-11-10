"""Lakebase projects, branches and databases, as the signed-in user sees them.

One class, one call per method, no aggregation. `[06 §5]` decided that: a project page fans out to
four reads so one slow call cannot hide four fast facts, and so a partial failure is visible instead
of looking like an empty result.

Every method takes the **user's** token, and every error goes through `DbxHttp`, so a denial is a
`PermissionError` (with `ScopeMissing` distinguishing "the app lacks a scope" from "you lack access")
and a missing object is a `LookupError`. That inheritance is why the pages need no error-mapping code
of their own (spec 013 [UI-6], [RB-2]).
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from ...domain import lakebase
from .http import DbxHttp

BASE = "/api/2.0/postgres"
#: A project page makes four calls. Longer than this and the page is stale anyway.
TTL_SECONDS = 60


class _Cache:
    """Per-token, per-path, TTL. Keyed by the credential because the token is the permission
    boundary: no user's results may answer another's request — the bug `CatalogBrowser` already
    fixed for its table-name walk (spec 013 [E-28])."""

    def __init__(self, ttl: float = TTL_SECONDS) -> None:
        self._ttl = ttl
        self._rows: dict[tuple[int, str], tuple[float, Any]] = {}

    def get(self, token: str | None, key: str):
        hit = self._rows.get((hash(token or ""), key))
        if hit and time.monotonic() - hit[0] < self._ttl:
            return hit[1]
        return None

    def put(self, token: str | None, key: str, value: Any) -> Any:
        self._rows[(hash(token or ""), key)] = (time.monotonic(), value)
        return value

    def invalidate(self, token: str | None, prefix: str = "") -> None:
        mark = hash(token or "")
        for key in [k for k in self._rows if k[0] == mark and k[1].startswith(prefix)]:
            self._rows.pop(key, None)


class LakebaseBrowser:
    def __init__(self, host: str, token_provider, http: DbxHttp | None = None) -> None:
        self._http = http or DbxHttp(host, token_provider)
        self._cache = _Cache()

    # -- reads -------------------------------------------------------------------------------
    async def projects(self, token: str | None, limit: int = 100) -> list[dict[str, Any]]:
        """Every project the user can see. ONE call: the rail lists them on every load ([06 §6.1])."""
        data = await self._http.get(f"{BASE}/projects", token, {"page_size": limit})
        return [self._project_row(p) for p in data.get("projects", [])]

    async def project(self, ref: str, token: str | None) -> dict[str, Any]:
        key = f"project:{ref}"
        if (hit := self._cache.get(token, key)) is not None:
            return hit
        data = await self._http.get(f"{BASE}/{lakebase.project_ref(ref)}", token)
        spec = data.get("spec") or {}
        status = data.get("status") or {}
        row = {
            **self._project_row(data),
            "displayName": status.get("display_name") or spec.get("display_name") or "",
            "pgVersion": status.get("pg_version") or spec.get("pg_version"),
            "historyRetention": status.get("history_retention_duration"),
            "defaultBranch": (spec.get("default_branch") or "").rsplit("/", 1)[-1] or "production",
        }
        return self._cache.put(token, key, row)

    async def branches(self, ref: str, token: str | None) -> list[dict[str, Any]]:
        key = f"branches:{ref}"
        if (hit := self._cache.get(token, key)) is not None:
            return hit
        data = await self._http.get(f"{BASE}/{lakebase.project_ref(ref)}/branches", token)
        project = lakebase.project_ref(ref)
        rows = [{
            "ref": b.get("name") or "",
            "name": lakebase.branch_id(b.get("name") or ""),
            "isDefault": lakebase.branch_id(b.get("name") or "") == "production",
            "state": lakebase.state_word((b.get("status") or {}).get("state") or ""),
            "project": project,
        } for b in data.get("branches", [])]
        return self._cache.put(token, key, rows)

    async def databases(self, ref: str, branch: str, token: str | None) -> list[dict[str, Any]]:
        path = lakebase.branch_ref(ref, branch)
        data = await self._http.get(f"{BASE}/{path}/databases", token)
        return [{"ref": d.get("name") or "", "name": (d.get("name") or "").rsplit("/", 1)[-1]}
                for d in data.get("databases", [])]

    async def endpoints(self, ref: str, branch: str, token: str | None) -> list[dict[str, Any]]:
        path = lakebase.branch_ref(ref, branch)
        data = await self._http.get(f"{BASE}/{path}/endpoints", token)
        rows = []
        for e in data.get("endpoints", []):
            status = e.get("status") or {}
            rng = lakebase.range_from(e)
            rows.append({
                "ref": e.get("name") or "",
                "name": (e.get("name") or "").rsplit("/", 1)[-1] or "primary",
                "type": status.get("endpoint_type") or "",
                "state": lakebase.state_word(status.get("current_state") or ""),
                "suspended": lakebase.is_suspended(status.get("current_state") or ""),
                "host": (status.get("hosts") or {}).get("host", ""),
                "minCu": rng.min_cu,
                "maxCu": rng.max_cu,
                "range": rng.describe(),
                "rangeValid": rng.valid,
                "lastActive": status.get("last_active_time") or "",
            })
        return rows

    async def roles(self, ref: str, branch: str, token: str | None) -> list[dict[str, Any]]:
        path = lakebase.branch_ref(ref, branch)
        data = await self._http.get(f"{BASE}/{path}/roles", token)
        return [{
            "ref": r.get("name") or "",
            "name": (r.get("name") or "").rsplit("/", 1)[-1],
            "identity": (r.get("spec") or {}).get("postgres_role") or "",
            "type": (r.get("spec") or {}).get("identity_type") or "",
        } for r in data.get("roles", [])]

    async def credential(self, endpoint: str, token: str | None) -> dict[str, Any]:
        """A token for one endpoint. Never cached: a cached credential is a credential at rest."""
        import uuid
        return await self._http.post(f"{BASE}/credentials", token,
                                     {"endpoint": endpoint, "request_id": str(uuid.uuid4())},
                                     timeout=30)

    async def tables(self, ref: str, branch: str, database: str, schema: str,
                     token: str | None) -> dict[str, Any]:
        """Table names in one schema, capped at 50, with `truncated` telling the truth.

        The one read that needs a database connection rather than a management call. The two
        management reads happen here (async), then the connection runs in a worker thread because the
        driver is synchronous — the same shape `services/model_registry` uses for its pool
        (spec 013 [06 §6.3], [E-19]).
        """
        problem = (lakebase.check_identifier(database, "database")
                   or lakebase.check_identifier(schema, "schema"))
        if problem:
            raise ValueError(problem)
        endpoint = lakebase.endpoint_ref(ref, branch)
        meta = await self._http.get(f"{BASE}/{endpoint}", token)
        status = meta.get("status") or {}
        host = (status.get("hosts") or {}).get("host", "")
        if not host:
            raise RuntimeError(f"{endpoint} has no host yet: the compute is starting. Try again shortly.")
        credential = await self.credential(endpoint, token)
        password = credential.get("token") or ""
        if not password:
            raise RuntimeError("the workspace returned no Lakebase credential for this endpoint")
        user = status.get("postgres_role") or ""

        def run() -> list[tuple]:
            import psycopg
            with psycopg.connect(host=host, port=5432, dbname=database, user=user,
                                 password=password, sslmode="require",
                                 connect_timeout=20) as conn:
                conn.autocommit = True
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = %s AND table_type = 'BASE TABLE' "
                        "ORDER BY table_name LIMIT 51", (schema,))
                    return cur.fetchall()

        rows = await asyncio.to_thread(run)
        names = [r[0] for r in rows]
        return {"schema": schema, "database": database, "branch": lakebase.branch_id(branch),
                "tables": names[:50], "truncated": len(names) > 50}

    def invalidate(self, token: str | None, ref: str = "") -> None:
        self._cache.invalidate(token, ref)

    # -- shape ---------------------------------------------------------------------------------
    @staticmethod
    def _project_row(p: dict) -> dict[str, Any]:
        spec = p.get("spec") or {}
        status = p.get("status") or {}
        name = p.get("name") or ""
        state = status.get("state") or p.get("state") or ""
        return {
            "ref": name,
            "name": lakebase.project_id(name),
            "displayName": status.get("display_name") or spec.get("display_name") or lakebase.project_id(name),
            "state": lakebase.state_word(state),
            "stateRaw": state,
            "ready": lakebase.is_ready(state),
        }


async def page_blocks(token: str | None, ref: str, branch: str, browser: LakebaseBrowser) -> dict[str, Any]:
    """The independent reads a project page needs, each with its OWN outcome.

    `return_exceptions=True` is the whole point: one failing read must not blank the others
    (spec 013 [UI-3], [E-11]). The keys are the page's blocks."""
    results = await asyncio.gather(
        browser.project(ref, token),
        browser.branches(ref, token),
        browser.databases(ref, branch, token),
        browser.endpoints(ref, branch, token),
        return_exceptions=True,
    )
    keys = ("project", "branches", "databases", "compute")
    out: dict[str, Any] = {}
    for key, value in zip(keys, results):
        if isinstance(value, BaseException):
            out[key] = {"error": _sentence(value)}
        else:
            out[key] = value
    return out


def _sentence(exc: BaseException) -> str:
    """A refusal keeps its own words; anything else gets the platform's message."""
    return str(exc) or exc.__class__.__name__
