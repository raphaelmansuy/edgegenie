"""Immutable event vocabulary shared by the domain, the store and the UI.

Every other module speaks this language. ACP shapes never escape adapters/acp/mapper.
Keep `EVENT_TYPES` and web/src/domain/events.ts in step: tests/unit checks they match.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

EventType = Literal[
    "session.created",
    "session.ready",
    "session.degraded",
    "session.archived",
    "turn.started",
    "turn.queued",
    "thought.delta",
    "message.delta",
    "tool_call.started",
    "tool_call.updated",
    "plan.updated",
    "approval.requested",
    "approval.decided",
    "evidence.proposed",
    "turn.auditing",
    "turn.completed",
    "turn.blocked",
    "turn.cancelled",
    "turn.interrupted",
    "turn.failed",
    "turn.retrying",
    "session.compacted",
    "usage.updated",
]

EVENT_TYPES: tuple[str, ...] = EventType.__args__  # type: ignore[attr-defined]


def now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class Event:
    session_id: str
    type: EventType
    payload: dict[str, Any] = field(default_factory=dict)
    turn_id: str | None = None
    actor: str = "app"
    seq: int = 0
    at: datetime = field(default_factory=now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "sessionId": self.session_id,
            "turnId": self.turn_id,
            "type": self.type,
            "actor": self.actor,
            "at": self.at.isoformat(),
            **self.payload,
        }


# --- constructors: one place per event shape, so payload keys cannot drift ---------


def session_created(sid: str, folder: str, model: str, schema: str | None) -> Event:
    return Event(sid, "session.created", {"folder": folder, "model": model, "schema": schema})


def session_ready(sid: str, tools: int, agent: str, version: str, capabilities: dict) -> Event:
    return Event(
        sid,
        "session.ready",
        {"toolCount": tools, "agent": agent, "agentVersion": version, "capabilities": capabilities},
    )


def turn_started(sid: str, tid: str, text: str, model: str) -> Event:
    return Event(sid, "turn.started", {"text": text, "model": model}, turn_id=tid, actor="user")


def thought(sid: str, tid: str, text: str) -> Event:
    return Event(sid, "thought.delta", {"text": text}, turn_id=tid, actor="agent")


def message(sid: str, tid: str, text: str) -> Event:
    return Event(sid, "message.delta", {"text": text}, turn_id=tid, actor="agent")


def tool_started(sid: str, tid: str, call_id: str, name: str, args: str, kind: str = "other") -> Event:
    return Event(
        sid,
        "tool_call.started",
        {"callId": call_id, "name": name, "args": args, "kind": kind, "status": "running"},
        turn_id=tid,
        actor="agent",
    )


def tool_updated(
    sid: str,
    tid: str,
    call_id: str,
    status: str,
    seconds: float | None = None,
    summary: str = "",
    error: str = "",
    args: str = "",
) -> Event:
    p: dict[str, Any] = {"callId": call_id, "status": status}
    if args:
        p["args"] = args
    if seconds is not None:
        p["seconds"] = round(seconds, 1)
    if summary:
        p["summary"] = summary
    if error:
        p["error"] = error
    return Event(sid, "tool_call.updated", p, turn_id=tid, actor="agent")


def approval_requested(
    sid: str,
    tid: str,
    approval_id: str,
    call_id: str,
    action: str,
    target: str,
    reason: str,
    blast: str,
    options: list[dict],
) -> Event:
    return Event(
        sid,
        "approval.requested",
        {
            "approvalId": approval_id,
            "callId": call_id,
            "action": action,
            "target": target,
            "reason": reason,
            "blastRadius": blast,
            "options": options,
        },
        turn_id=tid,
        actor="agent",
    )


def approval_decided(sid: str, tid: str, approval_id: str, outcome: str, decided_by: str) -> Event:
    return Event(
        sid,
        "approval.decided",
        {"approvalId": approval_id, "outcome": outcome},
        turn_id=tid,
        actor=decided_by,
    )


def evidence_proposed(sid: str, tid: str, rows: list[dict]) -> Event:
    return Event(sid, "evidence.proposed", {"rows": rows}, turn_id=tid, actor="supervisor")


def turn_auditing(sid: str, tid: str, pass_no: int, gaps: list[str]) -> Event:
    return Event(sid, "turn.auditing", {"pass": pass_no, "gaps": gaps}, turn_id=tid, actor="supervisor")


def turn_completed(sid: str, tid: str, stop_reason: str, usage: dict, seconds: float) -> Event:
    return Event(
        sid,
        "turn.completed",
        {"stopReason": stop_reason, "usage": usage, "seconds": round(seconds, 1)},
        turn_id=tid,
        actor="supervisor",
    )


def turn_blocked(sid: str, tid: str, reason: str, missing: list[str], attempted: list[dict]) -> Event:
    return Event(
        sid,
        "turn.blocked",
        {"reason": reason, "missing": missing, "attempted": attempted},
        turn_id=tid,
        actor="supervisor",
    )


def turn_ended(
    sid: str, tid: str, kind: Literal["cancelled", "interrupted", "failed"], detail: str = ""
) -> Event:
    t = {"cancelled": "turn.cancelled", "interrupted": "turn.interrupted", "failed": "turn.failed"}[kind]
    # `reason` is what the UI shows. A bare code, or an empty string, is the least useful state in
    # the product, so the reason is always populated and always carries the agent's own words.
    reason = detail.strip() or {
        "cancelled": "stopped at your request",
        "interrupted": "the agent process ended unexpectedly",
        "failed": "the agent failed without giving a reason",
    }[kind]
    return Event(sid, t, {"detail": detail, "reason": reason}, turn_id=tid, actor="app")  # type: ignore[arg-type]


def usage_updated(sid: str, tid: str, usage: dict) -> Event:
    return Event(sid, "usage.updated", {"usage": usage}, turn_id=tid, actor="agent")
