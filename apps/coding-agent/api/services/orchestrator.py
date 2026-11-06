"""Orchestration: owns session lifecycle and runs turns. Depends only on ports.

The supervisor decides; this module obeys. Every transition is written to the event store
BEFORE it is published, so a reconnecting browser can always fetch what it saw.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from ..domain import supervisor
from ..domain.events import (
    Event,
    approval_decided,
    evidence_proposed,
    session_created,
    session_ready,
    turn_auditing,
    turn_blocked,
    turn_completed,
    turn_ended,
    turn_started,
)
from ..domain.evidence import ToolCall, extract_requirements
from ..domain.scope import Scope, describe
from ..domain.session import (
    DomainError,
    Session,
    SessionState,
    SessionStatus,
    Turn,
    TurnStatus,
    updated,
)
from ..ports import AgentRuntime, RuntimeHandle, SessionSpec, ToolRegistry

MAX_TURNS = 200
TOOL_COUNT_CORE = 19


@dataclass
class Live:
    """Everything belonging to one running session. Rebuilt on restart; the store is truth."""

    state: SessionState
    handle: RuntimeHandle | None = None
    mcp_url: str = ""
    tools: int = 0
    task: asyncio.Task | None = None
    cancel: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def record(self, call_id: str, name: str, status: str, summary: str = "", args: str = "") -> None:
        c = self.state.calls.setdefault(call_id, {"name": name, "status": "running"})
        if name:
            c["name"] = name
        c["status"] = status
        if summary:
            c["summary"] = summary
        if args:
            c["args"] = args

    def tool_calls(self) -> list[ToolCall]:
        return [
            ToolCall(
                call_id=cid,
                name=c.get("name", ""),
                status=c.get("status", ""),
                summary=c.get("summary", ""),
            )
            for cid, c in self.state.calls.items()
        ]


class Orchestrator:
    def __init__(
        self, runtime: AgentRuntime, tools: ToolRegistry, store, models, demo: bool = False
    ) -> None:
        self._rt = runtime
        self._tools = tools
        self._store = store
        self._models = models
        self._demo = demo
        self._live: dict[str, Live] = {}

    # -- queries --------------------------------------------------------------
    def get(self, session_id: str) -> Live:
        try:
            return self._live[session_id]
        except KeyError:
            raise KeyError(session_id) from None

    def sessions_for(self, user_id: str) -> list[Session]:
        return sorted(
            (live.state.session for live in self._live.values() if live.state.session.user_id == user_id),
            key=lambda s: s.id,
            reverse=True,
        )

    def scope(self, session_id: str) -> Scope:
        s = self.get(session_id).state.session
        return Scope.for_session(s.id, s.folder, s.schema)

    def scope_description(self, session_id: str) -> dict:
        return describe(self.scope(session_id))

    # -- lifecycle ------------------------------------------------------------
    async def create(
        self, user_id: str, folder: str, model: str, schema: str | None, title: str = "New session"
    ) -> Session:
        self._models.check(user_id, model)
        sid = uuid4().hex[:16]
        session = Session(id=sid, user_id=user_id, folder=folder, schema=schema, model=model, title=title)
        live = Live(state=SessionState(session=session))
        self._live[sid] = live
        await self._store.append(session_created(sid, folder, model, schema))
        try:
            await self._provision(live)
        except Exception as exc:  # noqa: BLE001 - a failed provision is a visible state, not a crash
            live.state.session = live.state.session.transition(SessionStatus.FAILED)
            await self._store.append(Event(sid, "session.degraded", {"detail": str(exc)[:400]}))
            raise
        return live.state.session

    async def _provision(self, live: Live) -> None:
        s = live.state.session
        live.mcp_url = await self._tools.start(s.id, s.folder, s.schema)
        live.tools = TOOL_COUNT_CORE if live.mcp_url else 0
        spec = SessionSpec(session_id=s.id, cwd=s.folder, model=s.model, mcp_url=live.mcp_url)
        live.handle = await self._rt.start(spec)
        live.state.session = s.transition(SessionStatus.READY)
        live.state.session = updated(
            live.state.session,
            agent=live.handle.capabilities.agent,
            agent_version=live.handle.capabilities.version,
            tools=live.tools,
        )
        await self._store.append(
            session_ready(
                s.id,
                live.tools,
                live.handle.capabilities.agent,
                live.handle.capabilities.version,
                live.handle.capabilities.raw,
            )
        )

    async def model_options(self, session_id: str) -> dict:
        live = self.get(session_id)
        allowed = [m["id"] for m in self._models.allowed(live.state.session.user_id)]
        # RB-11: never offer a catalogue entry this workspace cannot serve.
        offered = [m for m in (live.handle.models if live.handle else []) if m in allowed]
        return {"current": live.state.session.model, "available": offered or allowed}

    async def set_model(self, session_id: str, model: str) -> dict:
        live = self.get(session_id)
        self._models.check(live.state.session.user_id, model)
        if live.handle:
            await self._rt.set_model(live.handle, model)
        live.state.session = updated(live.state.session, model=model)
        return await self.model_options(session_id)

    async def archive(self, session_id: str) -> None:
        live = self._live.get(session_id)
        if not live or live.state.session.status is SessionStatus.ARCHIVED:
            return
        if live.task and not live.task.done():
            live.cancel = True
            if live.handle:
                await self._rt.cancel(live.handle)
        live.state.session = live.state.session.transition(SessionStatus.ARCHIVED)
        if live.handle:
            await self._rt.close(live.handle)
        await self._tools.stop(session_id)
        await self._store.append(Event(session_id, "session.archived", {}))

    async def cancel(self, session_id: str) -> None:
        live = self.get(session_id)
        live.cancel = True
        if live.handle:
            await self._rt.cancel(live.handle)

    # -- turns ----------------------------------------------------------------
    async def submit(self, session_id: str, text: str) -> Turn:
        live = self.get(session_id)
        if live.state.session.status is SessionStatus.ARCHIVED:
            raise DomainError("this session is archived")
        if len(live.state.turns) >= MAX_TURNS:
            raise DomainError(f"this session reached its limit of {MAX_TURNS} turns")
        running = live.state.running()
        turn = live.state.new_turn(text)
        await self._store.append(turn_started(session_id, turn.id, text, live.state.session.model))
        if running is None:
            live.task = asyncio.create_task(self._run_turn(live, turn.id))
        return turn

    async def _run_turn(self, live: Live, turn_id: str) -> None:
        sid = live.state.session.id
        turn = live.state.claim(turn_id)
        live.state.session = live.state.session.transition(SessionStatus.STREAMING)
        self._rt.set_turn(sid, turn.id)
        started = time.time()
        parts: list[str] = []
        ended: dict = {"error": "no result"}
        usage: dict = {}
        try:
            await self._rt.prompt_in_background(live.handle, turn.prompt)  # type: ignore[arg-type]
            ended, usage, new_text = await self._drain(live)
            parts.append(new_text)
            if live.cancel:
                ended = {"stop": "cancelled"}
        except Exception as exc:  # noqa: BLE001 - a runtime failure must not escape
            ended = {"error": str(exc)[:400]}
        await self._settle(live, turn, "".join(parts), ended, usage, time.time() - started)

    async def _drain(self, live: Live) -> tuple[dict, dict, str]:
        """Consume one turn's events. Returns (end, usage, answer text)."""
        assert live.handle
        ended: dict = {"error": "no result"}
        usage: dict = {}
        parts: list[str] = []
        async for item in self._rt.events(live.handle):
            if live.cancel:  # set by /cancel while this turn was streaming
                ended = {"stop": "cancelled"}
                break
            if live.cancel:
                ended = {"stop": "cancelled"}
                break
            if isinstance(item, tuple):
                kind, value = item
                if kind == "end":
                    ended, usage = {"stop": value.stop_reason}, value.usage
                else:
                    ended = {"error": str(value)}
                break
            await self._store.append(item)
            if item.type == "message.delta":
                parts.append(item.payload.get("text", ""))
            elif item.type == "tool_call.started":
                live.record(item.payload["callId"], item.payload["name"], "running")
            elif item.type == "tool_call.updated":
                live.record(
                    item.payload["callId"],
                    "",
                    item.payload["status"],
                    item.payload.get("summary", ""),
                    item.payload.get("args", ""),
                )
        return ended, usage, "".join(parts)

    async def _settle(
        self,
        live: Live,
        turn: Turn,
        answer: str,
        ended: dict,
        usage: dict,
        seconds: float,
        continuations: int = 0,
        audits: int = 0,
    ) -> None:
        sid = live.state.session.id
        if live.cancel or ended.get("stop") == "cancelled":
            live.cancel = False
            self._finish(live, turn.finish(TurnStatus.CANCELLED))
            await self._store.append(turn_ended(sid, turn.id, "cancelled"))
            live.state.session = live.state.session.transition(SessionStatus.READY)
            return
        if "error" in ended:
            self._finish(live, turn.finish(TurnStatus.FAILED, error=ended["error"][:400]))
            await self._store.append(turn_ended(sid, turn.id, "failed", ended["error"][:400]))
            live.state.session = live.state.session.transition(SessionStatus.BLOCKED)
            return

        decision = supervisor.decide(
            supervisor.State(
                requirements=extract_requirements(turn.prompt),
                calls=live.tool_calls(),
                answer=answer,
                continuations=continuations,
                audits=audits,
            )
        )

        if decision.verdict is supervisor.Verdict.CONTINUE:
            await self._nudge(live, turn, decision.message, answer, continuations + 1, audits)
            return
        if decision.verdict is supervisor.Verdict.AUDIT:
            live.state.update(updated(turn, status=TurnStatus.AUDITING))
            await self._store.append(turn_auditing(sid, turn.id, audits + 1, list(decision.missing)))
            await self._nudge(live, turn, decision.message, answer, continuations, audits + 1)
            return
        if decision.evidence:  # recorded once, with the outcome, never per audit pass
            await self._store.append(evidence_proposed(sid, turn.id, list(decision.evidence)))
        if decision.verdict is supervisor.Verdict.DONE:
            self._finish(live, turn.finish(TurnStatus.COMPLETED, ended.get("stop", "end_turn"), usage))
            await self._store.append(
                turn_completed(sid, turn.id, ended.get("stop", "end_turn"), usage, seconds)
            )
            live.state.session = live.state.session.transition(SessionStatus.READY)
            return
        self._finish(live, turn.finish(TurnStatus.BLOCKED, error=decision.message))
        attempted = [
            {"tool": c["name"], "status": c.get("status", ""), "summary": c.get("summary", "")}
            for c in live.state.calls.values()
        ][:8]
        await self._store.append(
            turn_blocked(sid, turn.id, decision.message, list(decision.missing), attempted)
        )
        live.state.session = live.state.session.transition(SessionStatus.BLOCKED)

    def _finish(self, live: Live, turn: Turn) -> None:
        live.state.update(turn)

    async def _nudge(
        self, live: Live, turn: Turn, prompt: str, previous: str, continuations: int, audits: int
    ) -> None:
        assert live.handle
        started = time.time()
        try:
            await self._rt.prompt_in_background(live.handle, prompt)
            ended, usage, text = await self._drain(live)
        except Exception as exc:  # noqa: BLE001
            ended, usage, text = {"error": str(exc)[:400]}, {}, ""
        await self._settle(
            live,
            turn,
            (previous + "\n" + text).strip(),
            ended,
            usage,
            time.time() - started,
            continuations,
            audits,
        )

    # -- approvals ------------------------------------------------------------
    async def approve(
        self, session_id: str, approval_id: str, outcome: str, option_id: str | None, user_id: str
    ) -> None:
        live = self.get(session_id)
        if live.handle:
            await self._rt.respond_permission(
                live.handle, option_id or approval_id, option_id if outcome != "deny" else None
            )
        turn = live.state.running()
        await self._store.append(
            approval_decided(session_id, turn.id if turn else None, approval_id, outcome, user_id)
        )
