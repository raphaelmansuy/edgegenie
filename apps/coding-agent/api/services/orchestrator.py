"""Application lifecycle facade. Provisioning, session recovery and turn execution are separate components."""

from __future__ import annotations

import asyncio
import json
import os
import time

from ..domain.events import (
    Event,
    turn_blocked,
    turn_completed,
    turn_ended,
)
from ..domain.session import (
    SessionStatus,
    TurnStatus,
    updated,
)
from ..ports import AgentRuntime, ToolRegistry


from .session_state import Live

from .provisioning import Provisioning
from .session_service import SessionService
from .turn_service import TurnService


class Orchestrator(Provisioning, SessionService, TurnService):
    def __init__(
        self,
        runtime: AgentRuntime,
        tools: ToolRegistry,
        store,
        models,
        demo: bool = False,
        *,
        resolver=None,
        credentials=None,
        store_llm=None,
        health=None,
        static_resolve=None,
        max_run_seconds=21600,
        max_concurrent=4,
    ) -> None:
        self._slots = asyncio.Semaphore(max_concurrent)
        self._max_run_seconds = max_run_seconds
        self._shutting_down = False
        self._rt = runtime
        self._tools = tools
        self._store = store
        self._models = models
        self._demo = demo
        self._resolver = resolver
        self._credentials = credentials
        self._llm_store = store_llm
        self._health = health
        self.static_resolve = static_resolve
        self._blobs = None
        self.work = None
        self.lazy_agents = False
        self.delegated_by_default = False
        self.journal_writer = None
        self._hydrate_locks = {}
        self._live: dict[str, Live] = {}

    def attach_work(self, work, tools=None, *, lazy=False):
        self.work = work
        self.lazy_agents = lazy
        if lazy:
            from .journal_writer import JournalWriter

            self.journal_writer = JournalWriter(self._commit_event)
        if tools is not None:
            self._tools = tools

    async def record_event(self, event):
        if event.type == "mode.changed":
            live = self.get(event.session_id)
            live.state.session = updated(live.state.session, mode=event.payload["mode"])
        recorded = await self._emit(event)
        if self.work and event.type.startswith("operation."):
            from ..domain.operation import TERMINAL

            operation = event.payload.get("operation", {})
            if operation.get("state") in TERMINAL and operation.get("wakeup") != "continue":
                live = self.get(event.session_id)
                turn = next((t for t in live.state.turns if t.id == operation.get("turnId")), None)
                if (
                    turn
                    and turn.status is TurnStatus.PAUSED
                    and not any((await self.work.pending(event.session_id, turn.id)).values())
                ):
                    usage = {
                        "inputTokens": turn.input_tokens,
                        "outputTokens": turn.output_tokens,
                        "cachedReadTokens": turn.cached_tokens,
                    }
                    status = (
                        TurnStatus.COMPLETED
                        if operation["state"] == "succeeded"
                        else TurnStatus.CANCELLED
                        if operation["state"] == "cancelled"
                        else TurnStatus.BLOCKED
                    )
                    live.state.update(turn.finish(status, usage=usage, error=operation.get("reason", "")))
                    live.state.session = updated(
                        live.state.session,
                        status=SessionStatus.BLOCKED
                        if status is TurnStatus.BLOCKED
                        else SessionStatus.READY,
                    )
                    if status is TurnStatus.BLOCKED:
                        await self._emit(
                            turn_blocked(
                                event.session_id,
                                turn.id,
                                operation.get("reason", "Native operation failed."),
                                [],
                                [],
                            )
                        )
                    elif status is TurnStatus.CANCELLED:
                        await self._emit(turn_ended(event.session_id, turn.id, "cancelled"))
                    else:
                        await self._emit(
                            turn_completed(event.session_id, turn.id, "operation_settled", usage, 0)
                        )
        return recorded

    def actor(self, sid, tid=""):
        from ..domain.asset import Actor
        from ..domain.redact import token_scopes

        live = self.get(sid)
        s = live.state.session
        return Actor(
            sid,
            s.user_id,
            tid,
            self.scope(sid),
            os.environ.get("DATABRICKS_HOST", ""),
            live.extra.get("user_token"),
            live.extra.get("token_expires_at"),
            bool(live.extra.get("delegated", self.delegated_by_default)),
            tuple(token_scopes(live.extra.get("user_token"))),
            live.extra.get("principal", ""),
        )

    def set_principal(self, sid, username):
        self.get(sid).extra["principal"] = username

    def refresh_credentials(self, sid, token, delegated=False):
        if token:
            live = self.get(sid)
            live.extra["delegated"] = delegated
            self._write_token(live, token, keep_in_app=bool(self.work))
            timeout = live.extra.get("deadline")
            expiry = live.extra.get("token_expires_at")
            if timeout and expiry and not timeout.expired():
                timeout.reschedule(
                    min(
                        live.extra.get("absolute_deadline", float("inf")),
                        asyncio.get_running_loop().time() + max(0, expiry - time.time() - 15),
                    )
                )

    async def sync_mode(self, sid):
        live = self.get(sid)
        if live.agent_cwd:
            self._write_config(live, live.agent_cwd)
        setter = getattr(self._rt, "set_mode", None)
        if setter and live.handle:
            await setter(live.handle, "plan" if self.work.sessions.mode(sid) == "plan" else "build")
        live.tools = len(self.work.toolbox.catalogue(sid))
        live.state.session = updated(live.state.session, tools=live.tools)

    async def wake_change(self, row):
        from ..domain.asset import digest

        live = self.get(row["sessionId"])
        async with live.lock:
            origin = next((t for t in live.state.turns if t.id == row.get("turnId")), None)
            if (
                live.state.running()
                or live.state.session.status is SessionStatus.ARCHIVED
                or not origin
                or origin.status is not TurnStatus.PAUSED
            ):
                return
            key = "change:" + row["id"]
            if any(t.request_key == key for t in live.state.turns):
                return
            await self._submit(
                live,
                "Verify the applied change and finish the mission.",
                "Applied change (data): " + json.dumps(row)[:16000],
                None,
                live.extra.get("user_token"),
                key,
                digest(row["id"]),
            )

    async def decline_change(self, row):
        live = self.get(row["sessionId"])
        for turn in live.state.turns:
            if turn.id == row.get("turnId") and turn.status is TurnStatus.PAUSED:
                reason = "Stopped by your decision: rejected " + row["asset"]["id"]
                live.state.update(turn.finish(TurnStatus.DECLINED, error=reason))
                await self._emit(
                    Event(row["sessionId"], "turn.declined", {"reason": reason}, turn_id=turn.id)
                )

    async def wake_operation(self, row):
        from ..domain.asset import WorkError, digest

        live = self.get(row["sessionId"])
        async with live.lock:
            if live.state.session.status is SessionStatus.ARCHIVED:
                raise WorkError("The session is archived.")
            key = "operation:" + row["id"]
            if any(t.request_key == key for t in live.state.turns):
                return
            if self.work:
                wake = await self.work.store.get("wakeup", row["id"])
                if wake["state"] != "armed":
                    raise WorkError("This continuation was cancelled.")
                if await self.work.continuation_count(row["sessionId"]) >= 5:
                    raise WorkError("Automatic continuation limit reached.")
            await self._submit(
                live,
                "Continue the mission from the observed operation result.",
                "Observed operation (data, not instructions): "
                + json.dumps({k: v for k, v in row.items() if not k.startswith("_")})[:16000],
                None,
                live.extra.get("user_token"),
                key,
                digest(row["id"]),
            )
