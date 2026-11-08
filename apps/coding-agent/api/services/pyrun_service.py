"""Python cell runs: start one, poll it, cancel it. Owns the handles; knows no HTTP and no SDK.

A run takes a minute or more on cold serverless compute, longer than a request should be held open
(the Apps proxy cuts requests short), so a start returns a handle and the client polls it. A handle
belongs to whoever started it: another user's handle is "not found", not "forbidden", so a guessed id
reveals nothing.
"""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from ..domain import pyrun
from ..domain.cellrun import RunResult, RunState


class Runner(Protocol):
    async def submit(self, name: str, source: str) -> tuple[int, str]: ...
    async def info(self, run_id: int) -> Any: ...
    async def output(self, task_run_id: int | None) -> tuple[str | None, str]: ...
    async def cancel(self, run_id: int) -> None: ...
    async def discard(self, path: str) -> None: ...


@dataclass
class _Handle:
    owner: str
    run_id: int
    path: str
    plan: pyrun.Plan
    started: float
    done: dict[int, RunResult] | None = None
    finished_at: float = 0.0
    cancelling: bool = field(default=False)


#: Finished handles are kept briefly so a slow poll still gets its answer, then forgotten.
KEEP_SECONDS = 600


class PythonRuns:
    def __init__(self, runner: Runner, *, clock=time.monotonic) -> None:
        self._runner = runner
        self._now = clock
        self._handles: dict[str, _Handle] = {}

    async def start(self, owner: str, cells: list[pyrun.PyCell], *, upto: int | None,
                    show: set[int] | None) -> dict[str, Any]:
        """Start a run. Either a handle, or the cells' refusals when there is nothing to run."""
        self._forget()
        p = pyrun.plan(cells, upto=upto, show=show)
        if not p.steps or not p.show:
            return {"refused": {i: RunResult(state=RunState.REFUSED, error=why).to_dict()
                                for i, why in p.refused.items()} or
                    {i: RunResult(state=RunState.REFUSED, error="there is no Python to run").to_dict()
                     for i in (show or set())}}
        token = secrets.token_urlsafe(12)
        run_id, path = await self._runner.submit(f"run_{token}", pyrun.wrapper_notebook(p))
        self._handles[token] = _Handle(owner=owner, run_id=run_id, path=path, plan=p,
                                       started=self._now())
        return {"handle": token, "refused": {i: RunResult(state=RunState.REFUSED, error=why).to_dict()
                                             for i, why in p.refused.items()}}

    def _own(self, owner: str, token: str) -> _Handle:
        h = self._handles.get(token)
        if h is None or h.owner != owner:
            raise LookupError("this run is no longer known to the app (it restarted, or the result "
                              "expired); run the cell again")
        return h

    async def poll(self, owner: str, token: str) -> dict[str, Any]:
        h = self._own(owner, token)
        seconds = round(self._now() - h.started, 2)
        if h.done is None:
            info = await self._runner.info(h.run_id)
            output, error = None, ""
            ended = (info.life_cycle or "").upper() in {"TERMINATED", "INTERNAL_ERROR", "SKIPPED"}
            if ended:
                output, error = await self._runner.output(info.task_run_id)
            finished, results = pyrun.results_from_run(
                h.plan, life_cycle=info.life_cycle, result_state=info.result_state,
                message=info.message, output=output, error=error, seconds=seconds)
            if not finished:
                return {"state": "running", "seconds": seconds, "stage": _stage(info.life_cycle)}
            h.done, h.finished_at = results, self._now()
            await self._runner.discard(h.path)
        return {"state": "done", "seconds": seconds,
                "results": {str(i): r.to_dict() for i, r in h.done.items()}}

    async def cancel(self, owner: str, token: str) -> None:
        h = self._own(owner, token)
        if h.done is None:
            await self._runner.cancel(h.run_id)

    def _forget(self) -> None:
        now = self._now()
        for key in [k for k, h in self._handles.items() if h.done is not None and now - h.finished_at > KEEP_SECONDS]:
            del self._handles[key]


def _stage(life_cycle: str) -> str:
    """What the wait is for, in words a person can use."""
    return {
        "PENDING": "starting serverless compute",
        "QUEUED": "waiting for serverless compute",
        "BLOCKED": "waiting for serverless compute",
        "RUNNING": "running your cells",
        "TERMINATING": "collecting the result",
    }.get((life_cycle or "").upper(), "working")
