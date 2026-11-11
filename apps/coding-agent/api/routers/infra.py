"""Lakebase and Databricks Apps for the browser: read what exists, and prove an app answers.

Same conventions as `/workspace/*` and `/catalog/*`: the user's token on every call, `_dbx_errors`
for status mapping, one read per object (spec 013 [07 §4]).

There is deliberately **no aggregate overview route**. A project page fans out to four reads, each
with its own outcome, so one slow or denied call cannot hide the other three (spec 013 [06 §5]).
"""
from __future__ import annotations

import logging
from contextlib import contextmanager

from fastapi import APIRouter, Query, Request

from ..adapters.databricks.apps import apps_using
from ..domain import lakebase

log = logging.getLogger("app.infra")
router = APIRouter(prefix="/api")


# -- shared plumbing: one definition, used by both groups ---------------------------------------
def _token(request: Request) -> str | None:
    """The token the INFRASTRUCTURE calls use: the app's service principal, not the user's.

    This replaced `_user_token` because the platform will not put these permissions in a user token.
    `postgres` is "always bound to the SP, not OBO" and Lakebase resources "cannot run OBO, even under
    `--auth-mode obo`" (spec 013 [RB-10]). Declaring the scope made it *effective* on the app and
    changed nothing in the forwarded token, so every call 403'd and no sign-in could help.

    The consequence, stated so it is not a surprise: these two panes show what the APP may see, not
    what the viewer may see. That is the correct model for a management surface — a Databricks App's
    own service principal is the thing that owns the infrastructure it created — and it is why the
    page says so instead of blaming the user's sign-in.
    """
    from .api import _user_token
    source = getattr(request.app.state, "sp_token", None)
    if source is not None and source.available():
        try:
            return source.get()
        except Exception:  # noqa: BLE001 - fall through to the user token and let the API refuse
            pass
    # Local development has no injected service principal, so the configured token is the identity —
    # the same one the agent's tool server uses there.
    return _user_token(request)


@contextmanager
def _errors(what: str):
    from .api import _dbx_errors
    with _dbx_errors(what):
        yield


def _lakebase(request: Request):
    return request.app.state.lakebase


def _apps(request: Request):
    return request.app.state.apps


# -- Lakebase -----------------------------------------------------------------------------------
@router.get("/lakebase/projects")
async def lakebase_projects(request: Request, limit: int = Query(default=100, ge=1, le=200)) -> dict:
    """Every Lakebase project the user can see. One call, for the rail and the palette."""
    with _errors("lakebase projects"):
        items = await _lakebase(request).projects(_token(request), limit)
    return {"items": items}


@router.get("/lakebase/projects/{ref:path}/branches")
async def lakebase_branches(request: Request, ref: str) -> dict:
    """Lazy: the tree and the page ask for branches only when a project is opened."""
    with _errors("lakebase branches"):
        items = await _lakebase(request).branches(ref, _token(request))
    return {"items": items}


@router.get("/lakebase/projects/{ref:path}/databases")
async def lakebase_databases(request: Request, ref: str, branch: str = "production") -> dict:
    """`branch` is a query parameter, not a path segment: a branch ref contains slashes, and a path
    segment with slashes needs double encoding — the class of bug `route.ts` already fought."""
    with _errors("lakebase databases"):
        items = await _lakebase(request).databases(ref, branch, _token(request))
    return {"items": items}


@router.get("/lakebase/projects/{ref:path}/compute")
async def lakebase_compute(request: Request, ref: str, branch: str = "production") -> dict:
    """The branch's computes, each with its autoscaling range and the rule evaluated."""
    with _errors("lakebase compute"):
        items = await _lakebase(request).endpoints(ref, branch, _token(request))
    return {"items": items}


@router.get("/lakebase/projects/{ref:path}/roles")
async def lakebase_roles(request: Request, ref: str, branch: str = "production") -> dict:
    with _errors("lakebase roles"):
        items = await _lakebase(request).roles(ref, branch, _token(request))
    return {"items": items}


@router.get("/lakebase/projects/{ref:path}/tables")
async def lakebase_tables(request: Request, ref: str, branch: str = "production",
                          database: str = "databricks_postgres", schema: str = "public") -> dict:
    """Table names in one schema, capped at 50 with `truncated` telling the truth ([06 §6.3])."""
    with _errors("lakebase tables"):
        found = await _lakebase(request).tables(ref, branch, database, schema, _token(request))
    return found


@router.get("/lakebase/projects/{ref:path}")
async def lakebase_project(request: Request, ref: str, branch: str = "production") -> dict:
    """The project, and the three reads a page needs beside it — each independent.

    The response is `{project, branches, databases, compute}`, and any key may instead be
    `{"error": "…"}`. That shape is the contract the page renders ([UI-3], [E-11])."""
    from ..adapters.databricks.lakebase import page_blocks
    with _errors("lakebase project"):
        blocks = await page_blocks(_token(request), ref, branch, _lakebase(request))
    return blocks


@router.post("/lakebase/projects/{ref:path}/refresh")
async def lakebase_refresh(request: Request, ref: str) -> dict:
    """Drop the cache for one project. A manual refresh must never be served a stale object."""
    _lakebase(request).invalidate(_token(request), ref)
    return {"refreshed": True}


# -- Apps ----------------------------------------------------------------------------------------
@router.get("/apps")
async def apps_list(request: Request, lakebase: str = "") -> dict:
    """The apps the user can see; `?lakebase=<project>` narrows to the ones using that project.

    Narrowing happens over the LIST payload, so it costs one call either way ([06 §6.2])."""
    with _errors("apps list"):
        items = await _apps(request).apps(_token(request))
    if lakebase:
        items = apps_using(items, lakebase)
    return {"items": items}


@router.get("/apps/{name}")
async def apps_one(request: Request, name: str, health: bool = True) -> dict:
    """One app, its resources, and (by default) a health check that is the proof it works."""
    with _errors("app read"):
        row = await _apps(request).app(name, _token(request))
    if health and row.get("url"):
        try:
            row["health"] = await _apps(request).health(row["url"])
        except Exception as exc:  # noqa: BLE001 - the app's state is still worth showing
            row["health"] = {"state": "unknown", "detail": str(exc)[:200]}
    return row


@router.get("/apps/{name}/health")
async def apps_health(request: Request, name: str, fresh: bool = False) -> dict:
    with _errors("app health"):
        row = await _apps(request).app(name, _token(request))
        if fresh:
            _apps(request).forget(row.get("url") or "")
        return await _apps(request).health(row.get("url") or "")


# -- the two rules the UI needs, exposed so the two runtimes agree ------------------------------
@router.get("/infra/capacity-check")
async def capacity_check(min_cu: float = 0, max_cu: float = 0, scale_to_zero: bool = False) -> dict:
    """The autoscaling rule, evaluated by the same code the tool server checks before it calls.

    Exposed so the settings form can say *why* a range is refused before the platform does."""
    rng = lakebase.Range(min_cu or lakebase.MIN_CU, max_cu or lakebase.MIN_CU, scale_to_zero)
    return {"valid": rng.valid, "problem": rng.problem, "describe": rng.describe()}
