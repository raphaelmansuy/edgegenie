"""SQL cell runs: start one, poll it, cancel it. Owns the handles; knows no HTTP route and no SDK.

A SQL statement can run for minutes, longer than one request should be held open (the Apps proxy cuts
requests short), so a start returns a handle and the client polls it, exactly as Python cells do
(`pyrun_service`). A cell may hold several statements (`select 1; select 2`): they run in order on one
warehouse, the first failure stops the rest, and the last statement's result is the cell's.

A run belongs to whoever started it: another user's handle is "not found", not "forbidden", so a
guessed id reveals nothing. It runs with the *user's* token, which is held in memory for the length of
the run and never stored.
"""
from __future__ import annotations

import asyncio
import dataclasses
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from ..domain import cellrun
from ..domain.cellrun import RunResult, RunState

#: A finished handle is kept briefly so a slow poll still gets its answer, then forgotten.
KEEP_SECONDS = 600
POLL_SECONDS = 1.0
_LIVE = {"PENDING", "QUEUED", "RUNNING"}


class StatementApi(Protocol):
    async def pick_warehouse(self, token: str | None) -> dict[str, Any]: ...
    async def submit_statement(self, warehouse_id: str, statement: str, token: str | None, *,
                               limit: int, parameters: list[dict[str, str]] | None = None) -> dict[str, Any]: ...
    async def statement(self, statement_id: str, token: str | None) -> dict[str, Any]: ...
    async def cancel_statement(self, statement_id: str, token: str | None) -> None: ...


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class _Handle:
    owner: str
    started: float
    statements: list[str]
    params: dict[str, str] = field(default_factory=dict)
    warehouse: str = ""
    index: int = 0
    statement_id: str = ""
    cancelled: bool = False
    done: RunResult | None = None
    finished_at: float = 0.0
    task: asyncio.Task | None = field(default=None, repr=False)


class SqlRuns:
    def __init__(self, api: StatementApi, *, clock=time.monotonic, wall=_utc_now,
                 poll_seconds: float = POLL_SECONDS, limit_seconds: float = cellrun.MAX_RUN_SECONDS) -> None:
        self._api = api
        self._now = clock
        self._wall = wall
        self._poll = poll_seconds
        self._limit = limit_seconds
        self._handles: dict[str, _Handle] = {}

    async def start(self, owner: str, token: str | None, language: str, source: str,
                    params: dict[str, str] | None = None) -> dict[str, Any]:
        """Either `{"handle": ...}` to poll, or `{"result": ...}` when the answer is already known
        (a refusal, or the warehouse could not be reached)."""
        self._forget()
        ok, why = cellrun.is_runnable(language, source)
        if not ok:
            return {"result": cellrun.refused(why).to_dict()}
        statements = cellrun.split_statements(cellrun.sql_statement(source))
        if not statements:
            return {"result": cellrun.refused("this cell has no SQL statement to run").to_dict()}
        try:
            warehouse = await self._api.pick_warehouse(token)
        except (PermissionError, LookupError) as exc:
            return {"result": cellrun.refused(str(exc)).to_dict()}
        except RuntimeError as exc:
            return {"result": self._stamp(owner, RunResult(state=RunState.FAILED,
                                                           error=str(exc)[:cellrun.MAX_ERROR_CHARS])).to_dict()}
        handle = secrets.token_urlsafe(12)
        h = _Handle(owner=owner, started=self._now(), statements=statements, params=dict(params or {}),
                    warehouse=warehouse.get("name", ""))
        self._handles[handle] = h
        h.task = asyncio.create_task(self._drive(h, token, warehouse.get("id", "")))
        return {"handle": handle}

    def _own(self, owner: str, handle: str) -> _Handle:
        h = self._handles.get(handle)
        if h is None or h.owner != owner:
            raise LookupError("this run is no longer known to the app (it restarted, or the result "
                              "expired); run the cell again")
        return h

    async def poll(self, owner: str, handle: str) -> dict[str, Any]:
        h = self._own(owner, handle)
        seconds = round(self._now() - h.started, 2)
        if h.done is None:
            many = len(h.statements) > 1
            stage = (f"running statement {h.index + 1} of {len(h.statements)}" if many else "running")
            return {"state": "running", "seconds": seconds,
                    "stage": f"{stage} on {h.warehouse}" if h.warehouse else stage}
        return {"state": "done", "seconds": seconds, "result": h.done.to_dict()}

    async def cancel(self, owner: str, handle: str, token: str | None = None) -> None:
        h = self._own(owner, handle)
        if h.done is not None:
            return
        h.cancelled = True
        if h.statement_id:
            try:
                await self._api.cancel_statement(h.statement_id, token)
            except Exception:  # noqa: BLE001 - the flag already stops the loop; a cancel that fails is not news
                pass

    # -- the run itself ---------------------------------------------------------------------------

    def _stamp(self, owner: str, result: RunResult, warehouse: str = "") -> RunResult:
        return dataclasses.replace(result, warehouse=warehouse or result.warehouse,
                                   finished_at=self._wall(), ran_by=owner)

    async def _drive(self, h: _Handle, token: str | None, warehouse_id: str) -> None:
        total = len(h.statements)
        final: RunResult | None = None
        try:
            for n, statement in enumerate(h.statements):
                h.index = n
                if h.cancelled:
                    final = RunResult(state=RunState.CANCELLED, error="cancelled before it finished")
                    break
                # Only the parameters this statement uses are sent: a value for a name it does not use is noise,
                # and a name it uses with no value is left for the warehouse to report, in its own words.
                bound = [{"name": name, "value": h.params[name]} for name in cellrun.sql_params(statement)
                         if name in h.params]
                extra = {"parameters": bound} if bound else {}
                payload = await self._api.submit_statement(
                    warehouse_id, statement, token, limit=cellrun.MAX_ROWS, **extra)
                h.statement_id = str(payload.get("statement_id") or "")
                payload.setdefault("statement", statement)
                while str((payload.get("status") or {}).get("state") or "").upper() in _LIVE:
                    if h.cancelled:
                        break
                    if self._now() - h.started > self._limit:
                        await self._cancel_quietly(h.statement_id, token)
                        break
                    await asyncio.sleep(self._poll)
                    payload = await self._api.statement(h.statement_id, token)
                    payload.setdefault("statement", statement)
                waited = round(self._now() - h.started, 2)
                if h.cancelled:
                    final = RunResult(state=RunState.CANCELLED, seconds=waited, statement=statement,
                                      error="cancelled before it finished")
                    break
                final = cellrun.result_from_statement(payload, waited=waited)
                if final.state is not RunState.SUCCEEDED:
                    if total > 1:
                        final = dataclasses.replace(
                            final, error=f"statement {n + 1} of {total}: {final.error}" if final.error
                            else f"statement {n + 1} of {total} did not finish")
                    break
        except (PermissionError, LookupError) as exc:
            final = cellrun.refused(str(exc))
        except Exception as exc:  # noqa: BLE001 - a run must always end in a result, never a silent task death
            final = RunResult(state=RunState.FAILED, seconds=round(self._now() - h.started, 2),
                              error=str(exc)[:cellrun.MAX_ERROR_CHARS] or "the run failed without a message")
        h.done = self._stamp(h.owner, final or RunResult(state=RunState.FAILED, error="nothing ran"),
                             h.warehouse)
        h.finished_at = self._now()

    async def _cancel_quietly(self, statement_id: str, token: str | None) -> None:
        try:
            await self._api.cancel_statement(statement_id, token)
        except Exception:  # noqa: BLE001
            pass

    def _forget(self) -> None:
        now = self._now()
        for key in [k for k, h in self._handles.items()
                    if h.done is not None and now - h.finished_at > KEEP_SECONDS]:
            del self._handles[key]
