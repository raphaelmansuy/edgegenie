"""ACP message -> our AgentEvent vocabulary.

Two dialects, one output:
  v1  the session/prompt RESPONSE carries stopReason + usage (what opencode 1.19.5 speaks)
  v2  the response only acknowledges insertion; an idle state_update carries the stop reason

Everything here is pure so it can be tested against recorded frames.
"""

from __future__ import annotations

from collections.abc import Iterable
from collections import Counter
import logging
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


def _tool_start(sid: str, tid: str | None, update: dict) -> list[Event]:
    args = _summarise(update.get("rawInput"))
    args = "" if args in ("{}", "[]", "null") else args
    event = tool_started(sid, tid or "", str(update.get("toolCallId", "")),
        str(update.get("name") or update.get("title") or update.get("kind") or "tool"),
        args, str(update.get("kind") or "other"))
    for key in ("locations", "rawInput"):
        if key in update:
            event.payload[key] = update[key]
    return [event]


def _tool_update(sid: str, tid: str | None, update: dict) -> list[Event]:
    raw = update.get("rawInput") or {}
    output = update.get("rawOutput") or {}
    err = _summarise(output.get("error"), 300) if isinstance(output, dict) else ""
    summary = _summarise(update.get("content") or (raw.get("summary") if isinstance(raw, dict) else ""), 200) if not err else ""
    shown = {k: v for k, v in raw.items() if k not in ("error", "summary", "tool")} if isinstance(raw, dict) else raw
    event = tool_updated(sid, tid or "", str(update.get("toolCallId", "")),
        str(update["status"]) if "status" in update else None, update.get("seconds"), summary,
        err, _summarise(shown, 160) if shown else "", _table_of(update.get("content")) if not err else None)
    proof = _proof_of(update.get("content"))
    if proof is not None:
        event.payload["proof"] = proof
    content = update.get("content") or []
    diffs = [c for c in content if isinstance(c, dict) and c.get("type") == "diff"] if isinstance(content, list) else []
    if diffs:
        event.payload["diffs"] = diffs
    for key in ("locations", "name", "title", "kind", "rawInput"):
        if key in update:
            event.payload[key] = update[key]
    return [event]


def _plan(sid: str, tid: str | None, update: dict) -> list[Event]:
    entries = [{"content": str(e.get("content", ""))[:200], "status": str(e.get("status", "pending")),
                "priority": str(e.get("priority", "medium"))}
               for e in update.get("entries") or [] if isinstance(e, dict) and e.get("content")]
    return [plan_updated(sid, tid or "", entries)] if entries else []


def _usage(sid: str, tid: str | None, update: dict) -> list[Event]:
    usage = {k: update[k] for k in ("used", "size", "cost") if k in update} or update.get("usage") or {}
    return [usage_updated(sid, tid or "", usage)] if usage else []


def _text(constructor):
    return lambda sid, tid, update: [constructor(sid, tid or "", _text_of(update.get("content")))]


def _event(event_type):
    return lambda sid, tid, update: [Event(sid, event_type,
        {k: v for k, v in update.items() if k != "sessionUpdate"}, turn_id=tid, actor="agent")]


MAPPERS = {
    "agent_thought_chunk": _text(thought), "agent_message_chunk": _text(message),
    "agent_message": _text(message), "agent_thought": _text(thought),
    "tool_call": _tool_start, "tool_call_update": _tool_update, "plan": _plan, "usage_update": _usage,
    "available_commands_update": _event("commands.updated"),
    "current_mode_update": _event("config.updated"), "config_option_update": _event("config.updated"),
    "session_info_update": _event("session.info"), "user_message_chunk": _event("agent.notice"),
    "notice": _event("agent.notice"), "compaction_update": _event("session.compacted"),
    "compaction_summary_chunk": _event("session.compacted"),
    "state_update": _event("session.info"),
}
UNKNOWN_UPDATES = Counter()


def from_update(sid: str, tid: str | None, update: dict) -> list[Event]:
    """Map known ACP updates. Missing optional fields stay absent; unknown kinds are counted."""
    kind = str(update.get("sessionUpdate", ""))
    mapper = MAPPERS.get(kind)
    if mapper:
        return mapper(sid, tid, update)
    # Bound adversarial unknown kinds, while retaining a total overflow count.
    key = kind if kind in UNKNOWN_UPDATES or len(UNKNOWN_UPDATES) < 128 else "<other>"
    UNKNOWN_UPDATES[key] += 1
    if UNKNOWN_UPDATES[key] == 1:
        logging.getLogger(__name__).warning("Unknown ACP update: %s", key)
    return []


def from_permission(sid: str, tid: str | None, params: dict, approval_id: str) -> Event:
    """session/request_permission -> approval.requested.

    The agent's option list is passed through unchanged; the UI maps `kind`
    (allow_once / allow_always / reject_once / reject_always) onto buttons.
    """
    call = params.get("toolCall") or {}
    raw = call.get("rawInput") or {}
    target = _summarise(next((raw[k] for k in ("path", "id", "full_name", "name", "sql")
                              if isinstance(raw, dict) and raw.get(k)), ""), 160)
    options = [{"optionId": o.get("optionId"), "kind": o.get("kind"), "name": o.get("name")}
               for o in params.get("options", [])]
    event = approval_requested(
        sid, tid or "", approval_id, str(call.get("toolCallId") or ""),
        action=str(call.get("name") or call.get("title") or "tool"),
        target=target or "Arguments unknown", reason="The agent requested permission for this tool call.",
        blast="", options=options,
    )
    event.payload["input"] = raw
    event.payload["argumentsKnown"] = bool(raw)
    return event



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
