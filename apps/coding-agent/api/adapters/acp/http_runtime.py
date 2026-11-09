"""HTTP client for ACP agents that expose a streamable-HTTP endpoint (instead of stdio).

This adapter requires a separate ACP-over-HTTP service. `opencode serve` is a REST/OpenAPI
server, not this transport. This adapter lets the app host a compatible agent
without a child process, which matters when the app runtime forbids spawning (RB-03/RB-04).

It implements the same AgentRuntime port as AcpAgentRuntime, so nothing else changes.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

import httpx

from ...domain.events import Event
from .blocks import prompt_blocks
from ...ports import AgentAuthError, AgentCrashed, Capabilities, RuntimeHandle, SessionSpec
from .mapper import from_update, model_options, turn_end_from_prompt_response, turn_end_from_state

HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


class HttpChannel:
    def __init__(self, base_url: str, timeout: float = 600) -> None:
        self._url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout, headers=HEADERS)
        self._id = 0
        self._queue: asyncio.Queue[dict | None] = asyncio.Queue(maxsize=10_000)
        self._tasks: set[asyncio.Task] = set()

    async def request(self, method: str, params: dict, timeout: float | None = 30) -> dict:
        self._id += 1
        body = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}
        try:
            r = await self._client.post(
                self._url, json=body, timeout=timeout if timeout else httpx.Timeout(None)
            )
        except httpx.HTTPError as exc:
            raise TransportError(str(exc)) from exc
        payload = self._parse_body(r)
        if "error" in payload:
            raise TransportError(f"{method}: {json.dumps(payload['error'])[:300]}")
        return payload.get("result", {})

    async def stream(self, method: str, params: dict) -> None:
        """Fire a request whose progress arrives as server-sent notifications."""
        self._id += 1
        body = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}
        task = asyncio.create_task(self._consume(body))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _consume(self, body: dict) -> None:
        try:
            async with self._client.stream("POST", self._url, json=body, timeout=httpx.Timeout(None)) as r:
                async for line in r.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    try:
                        msg = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue
                    if "id" in msg and ("result" in msg or "error" in msg):
                        await self._queue.put({"$response": msg})
                    elif "method" in msg:
                        await self._queue.put(msg)
        except httpx.HTTPError as exc:
            await self._queue.put({"$error": str(exc)})
        finally:
            await self._queue.put(None)

    def _parse_body(self, r: httpx.Response) -> dict:
        text = r.text.strip()
        if text.startswith("{"):
            return r.json()
        for line in text.splitlines():
            if line.startswith("data:"):
                try:
                    return json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue
        raise TransportError(f"unexpected response: {text[:200]}")

    async def next(self) -> dict | None:
        return await self._queue.get()

    async def close(self) -> None:
        for t in list(self._tasks):
            t.cancel()
        await self._client.aclose()


class TransportError(Exception):
    pass


class HttpAcpAgentRuntime:
    """Same contract as AcpAgentRuntime, over HTTP."""

    def __init__(self, base_url: str | None = None) -> None:
        self._base = base_url
        self._channels: dict[str, HttpChannel] = {}
        self._turn_ids: dict[str, str] = {}

    async def start(self, spec: SessionSpec) -> RuntimeHandle:
        if spec.agent_session_id:
            raise AgentCrashed("session recovery is supported by the stdio ACP adapter; select APP_AGENT_MODE=stdio")
        url = self._base or spec.mcp_url.replace("/mcp", "")
        ch = HttpChannel(url)
        self._channels[spec.session_id] = ch
        try:
            init = await ch.request(
                "initialize",
                {
                    "protocolVersion": 1,
                    "clientCapabilities": {
                        "fs": {"readTextFile": True, "writeTextFile": True},
                        "terminal": False,
                    },
                    "clientInfo": {"name": "databricks-coding-agents", "version": "0.1"},
                },
                timeout=60,
            )
        except TransportError as exc:
            await ch.close()
            raise AgentCrashed(str(exc)) from exc
        caps = Capabilities(
            protocol_version=int(init.get("protocolVersion") or 1),
            agent=str((init.get("agentInfo") or {}).get("name", "agent")),
            version=str((init.get("agentInfo") or {}).get("version", "")),
            raw=init.get("agentCapabilities") or {},
        )
        try:
            new = await ch.request(
                "session/new",
                {
                    "cwd": spec.cwd,
                    "mcpServers": [{"type": "http", "name": "db", "url": spec.mcp_url, "headers": []}],
                },
                timeout=90,
            )
        except TransportError as exc:
            await ch.close()
            if "auth_required" in str(exc) or "-32000" in str(exc):
                raise AgentAuthError(str(exc)) from exc
            raise AgentCrashed(str(exc)) from exc
        models, current = model_options(new)
        return RuntimeHandle(
            session_id=str(new.get("sessionId", "")),
            capabilities=caps,
            models=models,
            current_model=current,
        )

    async def prompt(self, h: RuntimeHandle, text: str, images: list[dict] | None = None) -> dict:
        ch = self._channels[h.session_id]
        await ch.stream(
            "session/prompt",
            {"sessionId": h.session_id,
             "prompt": prompt_blocks(text, images, self._capabilities.get(h.session_id))},
        )
        return {}

    async def prompt_in_background(self, h: RuntimeHandle, text: str,
                                   images: list[dict] | None = None) -> None:
        await self.prompt(h, text, images)

    async def cancel(self, h: RuntimeHandle) -> None:
        ch = self._channels[h.session_id]
        await ch.request("session/cancel", {"sessionId": h.session_id}, timeout=10)

    async def set_model(self, h: RuntimeHandle, model: str) -> None:
        ch = self._channels[h.session_id]
        try:
            await ch.request(
                "session/set_config_option",
                {"sessionId": h.session_id, "configId": "model", "value": model},
                timeout=30,
            )
        except TransportError as first:
            try:
                await ch.request(
                    "session/set_config_option",
                    {
                        "sessionId": h.session_id,
                        "configId": "model",
                        "value": {"type": "id", "value": model},
                    },
                    timeout=30,
                )
            except TransportError:
                raise AgentCrashed(str(first)) from first

    async def respond_permission(self, h: RuntimeHandle, request_id: str, option_id: str | None) -> None:
        ch = self._channels[h.session_id]
        result = (
            {"outcome": {"outcome": "cancelled"}}
            if option_id is None
            else {"outcome": {"outcome": "selected", "optionId": option_id}}
        )
        await ch.request(
            "session/respond_permission",
            {"sessionId": h.session_id, "requestId": request_id, "result": result},
            timeout=30,
        )

    async def events(self, h: RuntimeHandle) -> AsyncIterator[Event | tuple]:
        ch = self._channels[h.session_id]
        while True:
            msg = await ch.next()
            if msg is None:
                yield ("error", "stream ended")
                return
            if "$error" in msg:
                yield ("error", msg["$error"])
                return
            if "$response" in msg:
                r = msg["$response"]
                if "error" in r:
                    yield ("error", json.dumps(r["error"])[:300])
                    return
                end = turn_end_from_prompt_response(r.get("result", {}))
                yield ("end", end)
                return
            update = (msg.get("params") or {}).get("update") or {}
            tid = self._turn_ids.get(h.session_id)
            for ev in from_update(h.session_id, tid, update):
                yield ev
            if update.get("sessionUpdate") == "state_update" and update.get("state") == "idle":
                end = turn_end_from_state(update)
                if end:
                    yield ("end", end)
                    return

    def set_turn(self, session_id: str, turn_id: str) -> None:
        self._turn_ids[session_id] = turn_id

    async def close(self, h: RuntimeHandle) -> None:
        ch = self._channels.pop(h.session_id, None)
        if ch:
            await ch.close()
