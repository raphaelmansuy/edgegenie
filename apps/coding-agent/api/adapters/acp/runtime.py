"""The ACP agent runtime. The only module that knows a specific agent exists."""

from __future__ import annotations

import asyncio
import os
import shlex
from collections.abc import AsyncIterator

from ...domain.events import Event
from ...ports import AgentAuthError, AgentCrashed, AgentError, Capabilities, RuntimeHandle, SessionSpec
from .jsonrpc import StdioChannel, TransportError
from .mapper import from_permission, from_update, model_options, turn_end_from_prompt_response

CLIENT_INFO = {"name": "databricks-coding-agents", "version": "0.1"}


class AcpAgentRuntime:
    """Spawns `opencode acp` (or any ACP v1/v2 agent) and speaks the protocol."""

    def __init__(self, command: str = "opencode acp", extra_env: dict[str, str] | None = None) -> None:
        self._command = shlex.split(command)
        self._extra_env = extra_env or {}
        self._procs: dict[str, tuple[asyncio.subprocess.Process, StdioChannel]] = {}
        self._by_agent: dict[str, str] = {}  # agent session id -> our session id
        self._capabilities: dict[str, Capabilities] = {}
        self._turn_ends: dict[str, asyncio.Queue] = {}
        self._turn_ids: dict[str, str] = {}
        self._permission_waiters: dict[str, asyncio.Future] = {}
        self._approval_seq = 0
        self._prompt_tasks: dict[str, asyncio.Task] = {}
        self._pending_permissions: dict[str, tuple[str, dict]] = {}

    # -- lifecycle ------------------------------------------------------------
    async def start(self, spec: SessionSpec) -> RuntimeHandle:
        env = {**os.environ, **self._extra_env, **spec.env}
        env.setdefault("NODE_NO_WARNINGS", "1")
        # A missing working directory makes subprocess raise FileNotFoundError for the *binary*,
        # which is a misleading error. Create it, and say so clearly if we cannot.
        try:
            os.makedirs(spec.cwd, exist_ok=True)
        except OSError as exc:
            raise AgentCrashed(f"cannot use working directory {spec.cwd}: {exc}") from exc
        try:
            proc = await asyncio.create_subprocess_exec(
                *self._command,
                cwd=spec.cwd,
                env=env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=16 * 1024 * 1024,
            )
        except FileNotFoundError as exc:
            raise AgentCrashed(
                f"agent binary not found: {self._command[0]} (or its working directory "
                f"{spec.cwd} is unusable): {exc}"
            ) from exc
        assert proc.stdin and proc.stdout
        ch = StdioChannel(proc.stdout, proc.stdin)
        self._procs[spec.session_id] = (proc, ch)
        self._turn_ends[spec.session_id] = asyncio.Queue()

        ch.on_request("session/request_permission", lambda p: self._on_permission(spec.session_id, p))

        try:
            init = await ch.request(
                "initialize",
                {
                    "protocolVersion": 1,
                    "clientCapabilities": {
                        "fs": {"readTextFile": True, "writeTextFile": True},
                        "terminal": False,
                    },
                    "clientInfo": CLIENT_INFO,
                },
                timeout=60,
            )
        except TransportError as exc:
            await self.close_silently(spec.session_id)
            raise AgentCrashed(str(exc)) from exc

        caps = Capabilities(
            protocol_version=int(init.get("protocolVersion") or 1),
            agent=str((init.get("agentInfo") or {}).get("name", "agent")),
            version=str((init.get("agentInfo") or {}).get("version", "")),
            load_session=bool((init.get("agentCapabilities") or {}).get("loadSession")),
            raw=init.get("agentCapabilities") or {},
        )
        self._capabilities[spec.session_id] = caps

        try:
            new = await ch.request(
                "session/new",
                {
                    "cwd": spec.cwd,
                    "mcpServers": [{"type": "http", "name": "dbx", "url": spec.mcp_url, "headers": []}],
                },
                timeout=90,
            )
        except TransportError as exc:
            await self.close_silently(spec.session_id)
            msg = str(exc)
            if "auth_required" in msg or "-32000" in msg:
                raise AgentAuthError(msg) from exc
            raise AgentCrashed(msg) from exc

        models, current = model_options(new)
        agent_sid = str(new.get("sessionId", ""))
        self._by_agent[agent_sid] = spec.session_id
        return RuntimeHandle(session_id=agent_sid, capabilities=caps, models=models, current_model=current)

    async def close(self, h: RuntimeHandle) -> None:
        proc, ch = self._procs.pop(self._ours(h), (None, None))
        if ch:
            await ch.close()
        if proc and proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), 5)
            except TimeoutError:
                proc.kill()

    async def close_silently(self, session_id: str) -> None:
        proc, ch = self._procs.pop(session_id, (None, None))
        if ch:
            await ch.close()
        if proc and proc.returncode is None:
            proc.kill()

    # -- turns ----------------------------------------------------------------
    async def prompt(self, h: RuntimeHandle, text: str) -> dict:
        ch = self._channel(h)
        # opencode accepts prompt as a request; the response carries the stop reason in v1.
        task = asyncio.create_task(
            ch.request(
                "session/prompt",
                {"sessionId": h.session_id, "prompt": [{"type": "text", "text": text}]},
                timeout=None,
            )
        )
        self._prompt_tasks[self._ours(h)] = task
        try:
            result = await task
        except TransportError as exc:
            raise AgentCrashed(str(exc)) from exc
        finally:
            self._prompt_tasks.pop(self._ours(h), None)
        end = turn_end_from_prompt_response(result)
        await self._turn_ends[self._ours(h)].put(end)
        return result

    async def prompt_in_background(self, h: RuntimeHandle, text: str) -> None:
        """Same as prompt, but does not wait: completion arrives through events()."""
        ch = self._channel(h)
        task = asyncio.create_task(
            ch.request(
                "session/prompt",
                {"sessionId": h.session_id, "prompt": [{"type": "text", "text": text}]},
                timeout=None,
            )
        )
        self._prompt_tasks[self._ours(h)] = task
        ours = self._ours(h)
        task.add_done_callback(lambda t: self._prompt_done(ours, t))

    def _prompt_done(self, session_id: str, task: asyncio.Task) -> None:
        self._prompt_tasks.pop(session_id, None)
        q = self._turn_ends.get(session_id)
        if q is None:
            return
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            q.put_nowait(("error", str(exc)))
            return
        q.put_nowait(turn_end_from_prompt_response(task.result()))

    async def cancel(self, h: RuntimeHandle) -> None:
        ch = self._channel(h)
        ch.notify("session/cancel", {"sessionId": h.session_id})
        task = self._prompt_tasks.get(self._ours(h))
        if task and not task.done():
            try:
                await asyncio.wait_for(asyncio.shield(task), 10)
            except (TimeoutError, asyncio.CancelledError):
                pass

    async def set_model(self, h: RuntimeHandle, model: str) -> None:
        ch = self._channel(h)
        # Verified: opencode rejects the documented union value and accepts a bare string.
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
                raise AgentError(str(first)) from first

    async def respond_permission(self, h: RuntimeHandle, request_id: str, option_id: str | None) -> None:
        fut = self._permission_waiters.pop(request_id, None)
        if fut and not fut.done():
            fut.set_result(option_id)

    # -- events ---------------------------------------------------------------
    async def events(self, h: RuntimeHandle) -> AsyncIterator[Event | tuple]:
        """Yields domain Events, then exactly one ("end", TurnEnd) or ("error", str).

        Two ordering rules, both learned from real failures:
        * a notification read is started once and reused, because cancelling a pending
          queue.get() silently discards the item it was about to return;
        * everything the agent already wrote is delivered before the end signal, because the
          final tool_call_update (and the whole reasoning trace) can arrive first.
        """
        ch = self._channel(h)
        ends = self._turn_ends[self._ours(h)]
        read: asyncio.Task | None = None
        end: tuple | None = None
        try:
            while True:
                if read is None:
                    read = asyncio.create_task(ch.next_notification())
                fin = asyncio.create_task(ends.get())
                done, _ = await asyncio.wait({read, fin}, return_when=asyncio.FIRST_COMPLETED)
                if fin in done:
                    got = fin.result()
                    end = ("end", got) if hasattr(got, "stop_reason") else got
                if read in done:
                    item = read.result()
                    read = None
                    if item.get("method") == "$/closed" and end is None:
                        yield ("error", "the agent process ended")
                        return
                    if item.get("method") == "session/update":
                        update = (item.get("params") or {}).get("update") or {}
                        ours = self._ours(h)
                        for ev in from_update(ours, self._turn_ids.get(ours), update):
                            yield ev
                        from .mapper import turn_end_from_state

                        state_end = turn_end_from_state(update)
                        if state_end:
                            yield ("end", state_end)
                            return
                if end is not None:
                    # deliver anything the agent already wrote, then finish
                    while True:
                        try:
                            queued = ch.next_notification_nowait()
                        except LookupError:
                            break
                        if queued.get("method") != "session/update":
                            continue
                        update = (queued.get("params") or {}).get("update") or {}
                        ours = self._ours(h)
                        for ev in from_update(ours, self._turn_ids.get(ours), update):
                            yield ev
                    yield end
                    return
        finally:
            if read is not None and not read.done():
                read.cancel()

    def pending_approval(self) -> tuple[str, str, dict] | None:
        """(approval_id, session_id, params) of a permission request waiting for a human."""
        for aid, (sid, params) in list(self._pending_permissions.items()):
            if aid in self._permission_waiters:
                return aid, sid, params
        return None

    def take_permission_event(self, session_id: str, turn_id: str) -> Event | None:
        """Called by the runner when it notices a pending request, to build approval.requested."""
        found = self.pending_approval()
        if not found:
            return None
        aid, sid, params = found
        if sid != session_id:
            return None
        return from_permission(sid, turn_id, params, aid)

    def set_turn(self, session_id: str, turn_id: str) -> None:
        """Tell the adapter which turn subsequent updates belong to."""
        self._turn_ids[session_id] = turn_id

    # -- internals ------------------------------------------------------------
    def _ours(self, h: RuntimeHandle) -> str:
        """Our session id for a handle (the handle carries the agent's own session id)."""
        return self._by_agent.get(h.session_id, h.session_id)

    def _channel(self, h: RuntimeHandle) -> StdioChannel:
        ch = self._procs.get(self._ours(h), (None, None))[1]
        if ch is None or ch.closed:
            raise AgentCrashed("agent process is not running")
        return ch

    async def _on_permission(self, session_id: str, params: dict) -> dict:
        self._approval_seq += 1
        approval_id = f"ap_{self._approval_seq}"
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._permission_waiters[approval_id] = fut
        self._pending_permissions[approval_id] = (session_id, params)
        option_id = await fut
        if option_id is None:
            return {"outcome": {"outcome": "cancelled"}}
        return {"outcome": {"outcome": "selected", "optionId": option_id}}
