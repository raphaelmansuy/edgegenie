"""Endpoints for the app's own tool servers, not for browsers. See `services/run_bridge.py`.

They are reachable only with a per-session key; the identity middleware lets `/internal/` through
because a loopback call has no forwarded user, and the key is the credential instead.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..domain import pyrun
from ..domain.notebook import parse_source

log = logging.getLogger("app.internal")
router = APIRouter(prefix="/internal")


class RunNotebookIn(BaseModel):
    session: str = Field(min_length=1, max_length=64)
    key: str = Field(min_length=1, max_length=128)
    #: The notebook in Databricks SOURCE format, exported by the tool with the USER's token.
    source: str = Field(min_length=1, max_length=2_000_000)
    language: str = Field(default="PYTHON", max_length=16)


def _authorised(request: Request, session: str, key: str):
    bridge = getattr(request.app.state, "run_bridge", None)
    if bridge is None or not bridge.verify(session, key):
        raise HTTPException(403, "not allowed")
    # A legacy grant must never authorize model-written code under the secret-bearing app identity.
    # The human Run button uses the separately authorized /api/python routes.
    raise HTTPException(
        403,
        "Agent code never runs as the app service principal. Run it in Databricks as yourself; "
        "a separate execution identity is not configured or qualified for this deployment.",
    )


@router.post("/run-notebook")
async def start(request: Request, body: RunNotebookIn) -> dict:
    runs = _authorised(request, body.session, body.key)
    cells = [pyrun.PyCell(c.index, "markdown" if c.kind == "markdown" else c.language, c.source)
             for c in parse_source(body.source, body.language)]
    if len(cells) > pyrun.MAX_CELLS:
        raise HTTPException(422, f"too many cells ({len(cells)}; the limit is {pyrun.MAX_CELLS})")
    started = await runs.start(f"session:{body.session}", cells, upto=None, show=None)
    return {**started, "cells": len(cells)}


@router.get("/run-notebook/{handle}")
async def poll(request: Request, handle: str, session: str, key: str) -> dict:
    runs = _authorised(request, session, key)
    try:
        return await runs.poll(f"session:{session}", handle)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
