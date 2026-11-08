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
        if method == "session/new":
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

    while True:
        line = await reader.readline()
        if not line:
            return
        try:
            msg = json.loads(line.decode())
        except json.JSONDecodeError:
            continue
        method = msg.get("method")
        if not method:
            continue
        try:
            result, notes = agent.handle(method, msg.get("params") or {})
        except KeyError:
            send({"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32601, "message": "no method"}})
            continue
        except ValueError as exc:
            send({"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32602, "message": str(exc)}})
            continue
        if "id" in msg:
            send({"jsonrpc": "2.0", "id": msg["id"], "result": result or {}})
        for n in notes:
            if delay:
                await asyncio.sleep(delay)
            send({"jsonrpc": "2.0", **n})


if __name__ == "__main__":
    import sys

    name = sys.argv[1] if len(sys.argv) > 1 else "notebook"
    delay = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
    # Pass the *name*: ScenarioAgent then chooses the behaviour per session from the prompt, which
    # is what lets one demo server show every UI state. Pass "fixed:<name>" to pin one scenario.
    arg = name.split(":", 1)[1] if name.startswith("fixed:") else name
    scenario = load_scenario(arg) if name.startswith("fixed:") else arg
    asyncio.run(serve_stdio(scenario, delay))
