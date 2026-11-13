"""A fake agent that replays recorded ACP turns. Deterministic tests and demos without a model.

It speaks the same ACP v1 JSON-RPC dialect as opencode, on stdio and on HTTP, so the real
AcpAgentRuntime and HttpAcpAgentRuntime are exercised unmodified against it.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path

SCENARIOS_DIR = Path(__file__).parent / "scenarios"
#: Matches the orchestrator's FENCE_ENV: the folder a session may write to.
FENCE_ENV = "APP_WORKSPACE_FOLDER"


def load_scenario(name: str) -> dict:
    return json.loads((SCENARIOS_DIR / f"{name}.json").read_text())


class ScenarioAgent:
    """Turns a scenario into ACP messages for one session.

    A scenario is {"models": [...], "turn": {"updates": [...], "answer": "...", "usage": {...},
    "stopReason": "end_turn", "permission": {...}}}.
    """

    def __init__(self, scenario: dict | str, delay: float = 0.0) -> None:
        self.default = scenario
        self.delay = delay
        self._by_session: dict[str, dict] = {}
        self._prompted: dict[str, int] = {}
        self.mcp_urls: dict[str,str] = {}
        # The working folder this agent was started for. Scenarios name files with the placeholder
        # `/Users/you/…`, which is not a real path: the app opens what a tool reports, so every demo
        # turn navigated to `/Users/you/agent_scratch/taxi_hours`, the view 404'd, and the console
        # filled with a failed request in tests that are otherwise about the UI. Substituting the real
        # folder keeps each scenario's SHAPE (a notebook under the scratch folder) while making the
        # path one that exists.
        # Set by the orchestrator from the session's fenced folder. This is the authoritative answer
        # to "where do this scenario's files live"; `cwd` is the child's scratch dir, which is not a
        # workspace path at all.
        self._root = os.environ.get(FENCE_ENV, "").rstrip("/")

    def _real_path(self, path: str) -> str:
        """`/Users/you/agent_scratch/x` → `<this deployment's folder>/x`, when we know the folder.

        The placeholder already contains the scratch folder's own name, so the prefix to replace is
        `/Users/you/agent_scratch/`, not `/Users/you/`: substituting only the latter produced
        `<folder>/agent_scratch/agent_scratch/taxi_hours`, which is just as missing as the original.
        """
        if not self._root:
            return path
        if path.startswith("/Users/you/agent_scratch/"):
            return f"{self._root}/{path[len('/Users/you/agent_scratch/'):]}"
        if path.startswith("/Users/you/"):
            return f"{self._root}/{path[len('/Users/you/'):]}"
        return path

    def _localise(self, updates: list[dict]) -> list[dict]:
        """Rewrite placeholder paths in a scenario's tool arguments, leaving everything else alone."""
        if not self._root:
            return updates
        out: list[dict] = []
        for u in updates:
            raw = u.get("rawInput")
            if isinstance(raw, dict) and isinstance(raw.get("path"), str):
                u = {**u, "rawInput": {**raw, "path": self._real_path(raw["path"])}}
            out.append(u)
        return out

    def scenario_for(self, session_id: str) -> dict:
        if session_id in self._by_session:
            return self._by_session[session_id]
        if isinstance(self.default, dict):
            return self.default
        return load_scenario(self.default)

    def pick(self, session_id: str, prompt: str) -> None:
        """Demo mode: the prompt chooses the behaviour, so one server can show every state."""
        text = prompt.lower()
        explicit = re.search(r"\[\[scenario:(\w+)\]\]", text)
        if explicit:
            self._by_session[session_id] = load_scenario(explicit.group(1))
            return
        # A supervisor nudge ("Audit pass. Re-read the original task…") is not the user choosing a
        # behaviour: it is the app asking the same session to review itself. Treating it as a fresh
        # prompt re-picked the default scenario and OVERWROTE the one the user's own words had
        # selected — so `[[scenario:math]]` typeset a math answer and then reported "Revenue by
        # pickup hour", and the math e2e failed on a scene whose marker had worked perfectly. Once a
        # session has a scenario, only another explicit marker may change it.
        if session_id in self._by_session:
            return
        # Fallback for hand-typed prompts: ordered, most specific first.
        if any(w in text for w in ("document the tables", "inject", "canary", "support ticket")):
            name = "injection"
        elif any(w in text for w in ("investigate", "why did revenue", "failing job", "find the cause")):
            name = "blocked"
        elif any(w in text for w in ("recompute daily revenue", "create a job")):
            name = "slow"
        else:
            name = "notebook"
        self._by_session[session_id] = load_scenario(name)

    def handle(self, method: str, params: dict) -> tuple[dict | None, list[dict]]:
        """Returns (response result or None for notifications, notifications to emit)."""
        if method == "initialize":
            return (
                {
                    "protocolVersion": 1,
                    "agentCapabilities": {
                        "loadSession": True,
                        "mcpCapabilities": {"http": True},
                        "promptCapabilities": {"embeddedContext": True},
                        "sessionCapabilities": {"list": {}},
                    },
                    "agentInfo": {"name": "FakeAgent", "version": "1.0"},
                },
                [],
            )
        if method in ("session/new", "session/load", "session/resume"):
            self.mcp_urls['ses_fake_1']=next((v.get('url','') for v in params.get('mcpServers',[]) if v.get('type')=='http'),'')
            opts = ["fake/model-a", "fake/model-b"]
            return (
                {
                    "sessionId": "ses_fake_1",
                    "configOptions": [
                        {
                            "id": "model",
                            "name": "Model",
                            "category": "model",
                            "type": "select",
                            "currentValue": opts[0],
                            "options": [{"value": m, "name": m} for m in opts],
                        }
                    ],
                    "availableCommands": [{"name": "review", "description": "review the change"}],
                },
                [],
            )
        if method == "session/set_config_option":
            value = params.get("value")
            # mirror opencode: reject a union, accept a bare string
            if isinstance(value, dict):
                raise ValueError("Invalid params: expected a string")
            return (
                {
                    "configOptions": [
                        {
                            "id": "model",
                            "category": "model",
                            "type": "select",
                            "currentValue": value,
                            "options": [{"value": value, "name": value}],
                        }
                    ]
                },
                [
                    {
                        "method": "session/update",
                        "params": {
                            "sessionId": params.get("sessionId"),
                            "update": {"sessionUpdate": "config_option_update", "configId": "model"},
                        },
                    }
                ],
            )
        if method == "session/prompt":
            sid = params.get("sessionId", "")
            text = " ".join(b.get("text", "") for b in params.get("prompt", []) if isinstance(b, dict))
            if isinstance(self.default, str):
                self.pick(sid, text)
            turn = self.scenario_for(sid).get("turn", {})
            notes: list[dict] = []
            # Only the first prompt replays the tool activity. A supervisor nudge must produce the
            # answer alone, or the transcript shows every tool three times.
            prompted_before = self._prompted.get(sid, 0)
            self._prompted[sid] = prompted_before + 1
            updates = self._localise(turn.get("updates", [])) if prompted_before == 0 else []
            for u in updates:
                notes.append(
                    {
                        "method": "session/update",
                        "params": {"sessionId": params.get("sessionId"), "update": u},
                    }
                )
            answer = turn.get("answer", "")
            if answer:
                for chunk in _chunks(answer, 60):
                    notes.append(
                        {
                            "method": "session/update",
                            "params": {
                                "sessionId": params.get("sessionId"),
                                "update": {
                                    "sessionUpdate": "agent_message_chunk",
                                    "content": {"type": "text", "text": chunk},
                                },
                            },
                        }
                    )
            return (
                {
                    "stopReason": turn.get("stopReason", "end_turn"),
                    "usage": turn.get(
                        "usage",
                        {
                            "inputTokens": 1200,
                            "outputTokens": 180,
                            "cachedReadTokens": 900,
                            "totalTokens": 2280,
                        },
                    ),
                },
                notes,
            )
        if method == "session/cancel":
            return (
                None,
                [
                    {
                        "method": "session/update",
                        "params": {
                            "sessionId": params.get("sessionId"),
                            "update": {
                                "sessionUpdate": "state_update",
                                "state": "idle",
                                "stopReason": "cancelled",
                            },
                        },
                    }
                ],
            )
        if method == "session/list":
            return (
                {
                    "sessions": [
                        {
                            "sessionId": "ses_fake_1",
                            "cwd": "/tmp",
                            "title": "Fake",
                            "updatedAt": "2026-11-06T09:00:00Z",
                        }
                    ]
                },
                [],
            )
        raise KeyError(method)


def _chunks(text: str, size: int) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]


async def serve_stdio(scenario: dict | str, delay: float = 0.0) -> None:
    """Run a fake agent on stdin/stdout, exactly like `opencode acp`."""
    agent = ScenarioAgent(scenario, delay)
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), __import__("sys").stdin)
    out = __import__("sys").stdout

    def send(obj: dict) -> None:
        out.write(json.dumps(obj) + "\n")
        out.flush()

    permissions: dict[str, asyncio.Future] = {}
    active: dict[str, asyncio.Task] = {}

    async def respond(msg: dict) -> None:
        method, params = msg["method"], msg.get("params") or {}
        sid = params.get("sessionId", "")
        try:
            result, notes = agent.handle(method, params)
            if method=='session/prompt':
                turn=agent.scenario_for(sid).get('turn',{})
                if turn.get('question') and agent._prompted.get(sid,0)==1:
                    rid='question_'+str(msg['id']);future=asyncio.get_running_loop().create_future();permissions[rid]=future
                    send({'jsonrpc':'2.0','id':rid,'method':'elicitation/create','params':{'sessionId':sid,**turn['question']}})
                    try:decision=await future
                    finally:permissions.pop(rid,None)
                    notes=[{'method':'session/update','params':{'sessionId':sid,'update':{'sessionUpdate':'agent_message_chunk','content':{'type':'text','text':'Your response was '+decision.get('action','cancel')+'. No workspace changes were made.'}}}}]
                    result={'stopReason':'end_turn'}
                actions=turn.get('actions',[]) if agent._prompted.get(sid,0)==1 else turn.get('followupActions',[])
                if actions:
                    from .actions import run_actions
                    async def permit(cid,name,args,update):
                        rid='native_'+cid
                        future=asyncio.get_running_loop().create_future();permissions[rid]=future
                        options=[{'optionId':'once','kind':'allow_once','name':'Allow once'},{'optionId':'reject','kind':'reject_once','name':'Reject'}]
                        send({'jsonrpc':'2.0','id':rid,'method':'session/request_permission','params':{'sessionId':sid,
                            'toolCall':{'toolCallId':cid,'title':'db_'+name,'kind':'other','status':'pending','rawInput':{}},'options':options}})
                        update({'sessionUpdate':'tool_call_update','toolCallId':cid,'status':'in_progress','rawInput':args})
                        try:decision=await future
                        finally:permissions.pop(rid,None)
                        return decision.get('outcome',{}).get('optionId')=='once'
                    answer,denied=await run_actions(agent.mcp_urls[sid],sid,actions,
                        turn.get('answer','') if agent._prompted.get(sid,0)==1 else turn.get('followupAnswer',turn.get('answer','')),
                        agent._root,send,permit,str(msg['id']),{'operation':next(iter(__import__('re').findall(r'op_[0-9a-f]{20}',json.dumps(params))), '')})
                    notes=[]
                    if answer:send({'jsonrpc':'2.0','method':'session/update','params':{'sessionId':sid,'update':{'sessionUpdate':'agent_message_chunk','content':{'type':'text','text':answer}}}})
                    result={'stopReason':'end_turn','usage':{'inputTokens':150,'outputTokens':50}}
            if method == "session/prompt":
                permission = agent.scenario_for(sid).get("turn", {}).get("permission")
                if permission:
                    rid = f"permission_{msg['id']}"
                    future = asyncio.get_running_loop().create_future()
                    permissions[rid] = future
                    for note in notes:
                        if (note.get("params") or {}).get("update", {}).get("sessionUpdate") in ("tool_call", "tool_call_update"):
                            send({"jsonrpc": "2.0", **note})
                    notes = [n for n in notes if (n.get("params") or {}).get("update", {}).get("sessionUpdate") not in ("tool_call", "tool_call_update")]
                    send({"jsonrpc": "2.0", "id": rid, "method": "session/request_permission",
                          "params": {"sessionId": sid, **permission}})
                    try:
                        decision = await future
                    finally:
                        permissions.pop(rid, None)
                    selected = decision.get("outcome", {})
                    denied = next((o for o in permission.get("options", []) if o.get("optionId") == selected.get("optionId")), {}).get("kind", "").startswith("reject")
                    if denied:
                        send({"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": sid,
                              "update": {"sessionUpdate": "tool_call_update", "toolCallId": permission["toolCall"]["toolCallId"],
                                         "status": "failed", "rawOutput": {"error": "The user rejected permission"}}}})
                        notes, result = [], {"stopReason": "end_turn"}
                    elif selected.get("outcome") != "selected":
                        notes, result = [], {"stopReason": "cancelled"}
                    else:
                        send({"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": sid,
                              "update": {"sessionUpdate": "tool_call_update", "toolCallId": permission["toolCall"]["toolCallId"],
                                         "status": "completed", "content": [{"type": "content", "content": {"type": "text", "text": "Scripted permission check only; no workspace operation executed."}}]}}})
            for n in notes:
                if delay:
                    await asyncio.sleep(delay)
                send({"jsonrpc": "2.0", **n})
            if "id" in msg:
                send({"jsonrpc": "2.0", "id": msg["id"], "result": result or {}})
        except asyncio.CancelledError:
            if "id" in msg:
                send({"jsonrpc": "2.0", "id": msg["id"], "result": {"stopReason": "cancelled"}})
        except KeyError:
            send({"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32601, "message": "no method"}})
        except ValueError as exc:
            send({"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32602, "message": str(exc)}})

    try:
        while True:
            line = await reader.readline()
            if not line:
                return
            try:
                msg = json.loads(line.decode())
            except json.JSONDecodeError:
                continue
            if "method" not in msg:
                future = permissions.get(msg.get("id"))
                if future is not None and not future.done():
                    future.set_result(msg.get("result", {}))
                continue
            method, sid = msg["method"], (msg.get("params") or {}).get("sessionId", "")
            if method == "session/cancel":
                task = active.get(sid)
                if task and not task.done():
                    task.cancel()
            task = asyncio.create_task(respond(msg))
            if method == "session/prompt":
                active[sid] = task
    finally:
        for task in active.values():
            task.cancel()


if __name__ == "__main__":
    import sys

    name = sys.argv[1] if len(sys.argv) > 1 else "notebook"
    delay = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
    # Pass the *name*: ScenarioAgent then chooses the behaviour per session from the prompt, which
    # is what lets one demo server show every UI state. Pass "fixed:<name>" to pin one scenario.
    arg = name.split(":", 1)[1] if name.startswith("fixed:") else name
    scenario = load_scenario(arg) if name.startswith("fixed:") else arg
    asyncio.run(serve_stdio(scenario, delay))
