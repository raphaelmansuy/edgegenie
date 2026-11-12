"""ACP message -> our AgentEvent vocabulary.

Two dialects, one output:
  v1  the session/prompt RESPONSE carries stopReason + usage (what opencode 1.19.5 speaks)
  v2  the response only acknowledges insertion; an idle state_update carries the stop reason

Everything here is pure so it can be tested against recorded frames.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from ...domain.events import (
    Event,
    approval_requested,
    message,
    plan_updated,
    thought,
    tool_started,
    tool_updated,
    usage_updated,
)


@dataclass(frozen=True, slots=True)
class TurnEnd:
    stop_reason: str
    usage: dict


def _text_of(content: Any) -> str:
    """The text inside an ACP content value: a block, a list of blocks, a `{"type":"content"}` wrapper,
    or any of those serialised as a string (a tool error often arrives that way)."""
    if isinstance(content, str):
        t = content.strip()
        if t[:2] in ("[{", '{"'):
            try:
                inner = _text_of(__import__("json").loads(t))
            except ValueError:
                return ""
            return inner
        return ""
    if isinstance(content, dict):
        if content.get("type") == "text":
            return _text_of(content.get("text", "")) or content.get("text", "")
        if content.get("type") == "content":
            return _text_of(content.get("content"))
        return ""
    if isinstance(content, list):
        return "".join(_text_of(c) for c in content)
    return ""


def _summarise(value: Any, limit: int = 140) -> str:
    """Human-readable one-liner for a tool's input or output. Text blocks are unwrapped, not JSON-encoded."""
    import json

    if value is None:
        return ""
    text = _text_of(value)
    if text:
        value = text
    if isinstance(value, str):
        s = value
    else:
        try:
            s = json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            s = str(value)
    s = " ".join(s.split())
    return s[:limit]


MAX_COLS, MAX_ROWS = 24, 60


def _proof_of(content: Any) -> dict | None:
    import json

    try:
        data = json.loads(_text_of(content))
    except (ValueError, TypeError):
        data = content if isinstance(content, dict) else {}
    proof = data.get("proof") if isinstance(data, dict) else None
    if not isinstance(proof, dict) or proof.get("kind") not in {"sql-query", "sql-run"}:
        return None
    # Copy only receipt metadata, never source, bindings, arbitrary tool text or result rows.
    keys = {"kind", "action", "draftId", "version", "sourceHash", "state", "runId",
            "statementId", "warehouseId", "resultAvailable", "rowCount", "cancelRequested"}
    return {k: v for k, v in proof.items() if k in keys and isinstance(v, (str, int, bool))}


def _table_of(content: Any) -> dict | None:
    """A tool result that is a query answer (`{"columns": [...], "rows": [[...]]}`) becomes a grid.

    Only this shape is promoted: the same JSON with other keys is prose for the model, not a table.
    Values are capped and stringified so one wide cell cannot bloat the event stream.
    """
    import json

    text = _text_of(content)
    if not text or not text.lstrip().startswith(("{", "[")):
        return None
    try:
        d = json.loads(text)
    except ValueError:
        return None
    if not isinstance(d, dict) or not isinstance(d.get("columns"), list) or not isinstance(d.get("rows"), list):
        return None
    columns = [str(c)[:60] for c in d["columns"][:MAX_COLS]]
    if not columns or not all(isinstance(r, list) for r in d["rows"][:MAX_ROWS]):
        return None
    rows = [["" if v is None else str(v)[:200] for v in r[:MAX_COLS]] for r in d["rows"][:MAX_ROWS]]
    return {"columns": columns, "rows": rows,
            "truncated": len(d["rows"]) > MAX_ROWS or len(d["columns"]) > MAX_COLS}


def from_update(sid: str, tid: str | None, update: dict) -> list[Event]:
    """Map one session/update's `update` object into zero or more events."""
    kind = update.get("sessionUpdate")
    if kind == "agent_thought_chunk":
        return [thought(sid, tid or "", _text_of(update.get("content")))]
    if kind == "agent_message_chunk":
        return [message(sid, tid or "", _text_of(update.get("content")))]
    if kind in ("agent_message", "agent_thought"):
        return [message(sid, tid or "", _text_of(update.get("content")))] if update.get("content") else []
    if kind == "tool_call":
        # opencode sends the arguments on the follow-up tool_call_update, not here, so an empty
        # rawInput must render as no arguments rather than as "{}".
        args = _summarise(update.get("rawInput"))
        args = "" if args in ("{}", "[]", "null") else args
        return [
            tool_started(
                sid,
                tid or "",
                str(update.get("toolCallId", "")),
                str(update.get("title") or update.get("kind") or "tool"),
                args,
                str(update.get("kind") or "other"),
            )
        ]
    if kind == "tool_call_update":
        status = str(update.get("status") or "running")
        raw = update.get("rawInput") or {}
        err = _summarise(raw.get("error"), 300) if isinstance(raw, dict) else ""
        summary = _summarise(update.get("content") or raw.get("summary"), 200) if not err else ""
        # The arguments of a call are useful whatever its status: show them, minus the noise keys.
        shown = (
            {k: v for k, v in raw.items() if k not in ("error", "summary", "tool")}
            if isinstance(raw, dict)
            else raw
        )
        args = _summarise(shown, 160) if shown else ""
        return [
            tool_updated(
                sid,
                tid or "",
                str(update.get("toolCallId", "")),
                status,
                update.get("seconds"),
                summary,
                err,
                args,
                _table_of(update.get("content")) if not err else None,
                _proof_of(update.get("content")) if not err else None,
            )
        ]
    if kind == "plan":
        # ACP: {"entries": [{"content", "priority", "status": pending|in_progress|completed}]}.
        entries = [
            {"content": str(e.get("content", ""))[:200], "status": str(e.get("status", "pending")),
             "priority": str(e.get("priority", "medium"))}
            for e in update.get("entries") or [] if isinstance(e, dict) and e.get("content")
        ]
        return [plan_updated(sid, tid or "", entries)] if entries else []
    if kind == "usage_update":
        u = update.get("usage") or {}
        return [usage_updated(sid, tid or "", u)] if u else []
    return []


def from_permission(sid: str, tid: str | None, params: dict, approval_id: str) -> Event:
    """session/request_permission -> approval.requested.

    The agent's option list is passed through unchanged; the UI maps `kind`
    (allow_once / allow_always / reject_once / reject_always) onto buttons.
    """
    subject = params.get("subject") or {}
    target = _summarise(subject.get("path") or subject.get("target") or params.get("title", ""), 160)
    options = [
        {"optionId": o.get("optionId"), "kind": o.get("kind"), "name": o.get("name")}
        for o in params.get("options", [])
    ]
    return approval_requested(
        sid,
        tid or "",
        approval_id,
        str(subject.get("toolCallId") or ""),
        action=str(subject.get("action") or "write"),
        target=target or "an object",
        reason=str(params.get("description") or params.get("title") or "the agent asked for permission"),
        blast=_summarise(subject.get("blastRadius") or "", 200),
        options=options,
    )


def turn_end_from_prompt_response(result: dict) -> TurnEnd:
    """v1: the prompt response is the completion signal."""
    return TurnEnd(stop_reason=str(result.get("stopReason") or "end_turn"), usage=result.get("usage") or {})


def turn_end_from_state(update: dict) -> TurnEnd | None:
    """v2: completion is an idle state_update."""
    if update.get("sessionUpdate") == "state_update" and update.get("state") == "idle":
        return TurnEnd(
            stop_reason=str(update.get("stopReason") or "end_turn"), usage=update.get("usage") or {}
        )
    return None


def model_options(session_new_result: dict) -> tuple[list[str], str]:
    """Read the model selector the agent advertises. Empty when it advertises none."""
    for opt in session_new_result.get("configOptions") or []:
        if opt.get("category") == "model" or opt.get("id") == "model":
            values = [o.get("value") for o in opt.get("options") or [] if o.get("value")]
            return values, str(opt.get("currentValue") or "")
    return [], ""


def chunks(events: Iterable[Event]) -> list[Event]:
    return [e for e in events if e is not None]
