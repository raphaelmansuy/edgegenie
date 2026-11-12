"""Jobs, runs and pipelines for the browser: read what exists, and nothing else.

Same conventions as `/workspace/*`, `/catalog/*` and 013's `/lakebase/*`: one read per object, `_dbx_errors`
for status mapping, and a response whose keys are independent so one refusal cannot blank a page.

**There is deliberately no write route here.** "Run now", "Resume", "Cancel", "Repair", "Start" and "Stop"
are all actions the AGENT performs through a tool, which means there is exactly one place in the product
where a job can be started and one fence that guards it (spec 014 [07 §5]). A second write path from the
browser would be a second fence, and `test_infra_routes.py` asserts this route table has no `POST` under
`/jobs` or `/pipelines` — the structural version of that decision.

**Identity.** Every read uses `_token`, which prefers the app's service principal. That is not a
preference: `jobs` and `pipelines` are not grantable `user_api_scopes` values, so a forwarded user token
cannot call either API at all (spec 014 [RB-1]). The payloads carry `identity`, and the pages say which
identity read them instead of implying the stronger claim.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager

from fastapi import APIRouter, Query, Request

log = logging.getLogger("app.jobs")
router = APIRouter(prefix="/api")


@contextmanager
def _errors(what: str):
    """The app's one status mapping. Imported rather than re-stated, so a new code is mapped once."""
    from .api import _dbx_errors
    with _dbx_errors(what):
        yield


def _token(request: Request) -> str | None:
    """The token these reads use: the app's service principal where one is configured.

    Shared with `routers/infra.py` by importing its helper rather than copying it, because two copies of
    "which identity reads infrastructure" is exactly the drift 013 spent a roadblock on.
    """
    from .infra import _token as infra_token
    return infra_token(request)


def _browser(request: Request):
    return request.app.state.jobs


def _pipes(request: Request):
    return request.app.state.pipelines


# -- jobs ------------------------------------------------------------------------------------------
@router.get("/jobs")
async def jobs_list(request: Request, limit: int = Query(default=25, ge=1, le=100)) -> dict:
    """The first page of jobs. One call; no run state and therefore no fan-out ([RB-7])."""
    with _errors("jobs list"):
        items = await _browser(request).jobs(_token(request), limit)
    return {"items": items, "identity": "the app's service principal"}


@router.get("/jobs/{job_id}")
async def job_one(request: Request, job_id: str) -> dict:
    """One job, its graph, its runs and its latest run — each an independent block.

    A block that failed is `{"error": "…"}` rather than an empty value, so the page can render the
    platform's sentence in place and keep its siblings ([UI-3], [E-1]).
    """
    with _errors("job read"):
        blocks = await _browser(request).job(job_id, _token(request))
    return blocks


@router.get("/runs/{run_id}")
async def run_one(request: Request, run_id: str) -> dict:
    """One run, with every task's own outcome and — when a task failed — its error."""
    with _errors("run read"):
        row = await _browser(request).run(run_id, _token(request))
    return row


# -- pipelines -------------------------------------------------------------------------------------
@router.get("/pipelines")
async def pipelines_list(request: Request, limit: int = Query(default=25, ge=1, le=100)) -> dict:
    """The first page of pipelines, each carrying the state of its LAST UPDATE ([TOOL-8], [PIPE-5])."""
    with _errors("pipelines list"):
        items = await _pipes(request).pipelines(_token(request), limit)
    return {"items": items, "identity": "the app's service principal"}


@router.get("/pipelines/{pipeline_id}")
async def pipeline_one(request: Request, pipeline_id: str,
                       events: int = Query(default=20, ge=0, le=100)) -> dict:
    """One pipeline: its spec, its last three updates, and its recent events — five blocks."""
    with _errors("pipeline read"):
        blocks = await _pipes(request).pipeline(pipeline_id, _token(request), events)
    return blocks


@router.get("/pipelines/{pipeline_id}/events")
async def pipeline_events(request: Request, pipeline_id: str,
                          limit: int = Query(default=20, ge=1, le=100)) -> dict:
    """The events alone, for a page that only wants to refresh them."""
    with _errors("pipeline events"):
        items = await _pipes(request).events(pipeline_id, _token(request), limit)
    return {"items": items}


# -- the ledger ------------------------------------------------------------------------------------
@router.get("/infra/ledger")
async def ledger(request: Request) -> dict:
    """What this conversation created, so the page knows which controls it may offer.

    A read of a file the tool server appends to (spec 014 [RB-3]). It answers "did this session make it?",
    which is a weaker question than authorization and deliberately not the same one: the platform decides
    whether this identity may act, and this decides whether the ACTION belongs to this conversation.
    """
    from ..adapters.mcp.registry import read_ledger
    return {"items": read_ledger()}


# -- the rules the pages need, evaluated by the same code the tools use -----------------------------
@router.get("/infra/run-actions")
async def run_actions(life_cycle: str = "", result: str = "") -> dict:
    """Which controls belong on screen for a run, answered by the domain module rather than the page.

    Exposed so the browser and the tool server cannot disagree about when Cancel or Repair is available:
    both read `api.domain.jobs`, and the page's own copy is held to the same fixture
    (`web/src/domain/jobs-table.json`)."""
    from ..domain import jobs as vocab
    return {
        "word": vocab.run_word(life_cycle, result),
        "tone": vocab.tone(vocab.run_word(life_cycle, result)),
        "active": vocab.is_active(life_cycle),
        "terminal": vocab.is_terminal(life_cycle),
        "cancel": vocab.can_cancel(life_cycle),
        "repair": vocab.can_repair(result, life_cycle),
    }
