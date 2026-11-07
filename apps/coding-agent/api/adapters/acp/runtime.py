"""The ACP agent runtime. The only module that knows a specific agent exists."""

from __future__ import annotations

import asyncio
import collections
import os
import re
import shlex
from collections.abc import AsyncIterator

from ...domain.events import Event
from ...ports import AgentAuthError, AgentCrashed, AgentError, Capabilities, RuntimeHandle, SessionSpec
from .jsonrpc import StdioChannel, TransportError
from .mapper import from_permission, from_update, model_options, turn_end_from_prompt_response

CLIENT_INFO = {"name": "databricks-coding-agents", "version": "0.1"}
# ACP has no "the model call failed" signal: when the endpoint errors, some agents log to stderr and
# never end the turn. Without this guard a turn hangs forever (observed with a 403 from the gateway).
IDLE_TURN_TIMEOUT = float(os.environ.get("APP_TURN_IDLE_TIMEOUT", "180"))


class AcpAgentRuntime:
    """Spawns `opencode acp` (or any ACP v1/v2 agent) and speaks the protocol."""

    def __init__(self, command: str = "opencode acp", extra_env: dict[str, str] | None = None) -> None:
        self._command = shlex.split(command)
        self._extra_env = extra_env or {}
        self._procs: dict[str, tuple[asyncio.subprocess.Process, StdioChannel]] = {}
        self._by_agent: dict[str, str] = {}  # agent session id -> our session id
        self._stderr: dict[str, collections.deque[str]] = {}
        self._stderr_tasks: dict[str, asyncio.Task] = {}
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
        # An unread stderr pipe fills its buffer and blocks the agent forever. That deadlocked a
        # real opencode session, with no error anywhere: the turn simply never produced an event.
        self._stderr[spec.session_id] = collections.deque(maxlen=200)
        if proc.stderr:
            self._stderr_tasks[spec.session_id] = asyncio.create_task(
                self._drain_stderr(spec.session_id, proc.stderr))
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
                    "mcpServers": [{"type": "http", "name": "db", "url": spec.mcp_url, "headers": []}],
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
        return RuntimeHandle(session_id=agent_sid, ours=spec.session_id, capabilities=caps,
                             models=models, current_model=current)

    async def _drain_stderr(self, session_id: str, stream: asyncio.StreamReader) -> None:
        """Keep the agent's stderr flowing and remember the tail, for diagnosis."""
        try:
            while True:
                line = await stream.readline()
                if not line:
                    return
                self._stderr[session_id].append(line.decode(errors="replace").rstrip())
        except (asyncio.CancelledError, ConnectionResetError):
            return

    def stderr_tail(self, session_id: str, lines: int = 6) -> str:
        """The single most useful error line from the agent's stderr.

        Model failures arrive as pretty-printed JSON plus log lines, so a raw tail shows a truncated
        object. Ranking, best first:
          1. a sentence that names a cause (limit, denied, quota, not enabled);
          2. an explicit `message: "..."` field (the longest one: nested objects have short ones);
          3. any ERROR line, cleaned of timestamps and ids;
          4. the last line.
        """
        rows = list(self._stderr.get(session_id, []))
        if not rows:
            return ""
        cause = re.compile(r"(limit|denied|quota|not enabled|unauthor|expired|invalid|forbidden)", re.I)
        named = [r.strip()[:300] for r in rows if cause.search(r)]
        if named:
            return max(named, key=len)
        msgs: list[str] = []
        for r in rows:
            m = re.search(r'message["\s:=]+"(.{15,400}?)"\s*[,}]?\s*$', r.strip())
            if m:
                msgs.append(m.group(1))
        if msgs:
            return max(msgs, key=len)
        errs = [r.strip()[:300] for r in rows if re.search(r"\b(ERROR|Error:)\b", r)]
        if errs:
            line = re.sub(r"^timestamp=\S+\s+(level=\S+\s+)?(run=\S+\s+)?", "", errs[-1])
            return line[:300]
        return rows[-1][:300]

    async def close(self, h: RuntimeHandle) -> None:
        ours = self._ours(h)
        t = self._stderr_tasks.pop(ours, None)
        if t:
            t.cancel()
        proc, ch = self._procs.pop(ours, (None, None))
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

        Three rules, each learned from a real hang:
        * both waits are created ONCE and reused. Re-creating `ends.get()` every iteration meant a
          cancelled waiter could swallow the end signal, and the turn never finished;
        * everything the agent already wrote is delivered before the end signal, because the final
          tool_call_update and the reasoning trace routinely arrive before the prompt response;
        * an idle guard reports a model failure instead of hanging (ACP has no error signal).
        """
        ch = self._channel(h)
        ours = self._ours(h)
        ends = self._turn_ends[ours]
        read: asyncio.Task | None = None
        fin: asyncio.Task | None = None
        end: tuple | None = None
        try:
            while True:
                read = read or asyncio.create_task(ch.next_notification())
                fin = fin or asyncio.create_task(ends.get())
                try:
                    done, _ = await asyncio.wait({read, fin}, timeout=IDLE_TURN_TIMEOUT,
                                                 return_when=asyncio.FIRST_COMPLETED)
                except asyncio.CancelledError:
                    raise
                if not done:
                    tail = self.stderr_tail(ours, 4)
                    yield (("error", f"the model or agent failed: {tail}") if tail
                           else ("error", f"the agent sent nothing for {IDLE_TURN_TIMEOUT:.0f}s"))
                    return
                if fin in done:
                    got = fin.result()
                    fin = None                     # consumed: a fresh waiter next iteration
                    end = ("end", got) if hasattr(got, "stop_reason") else got
                if read in done:
                    item = read.result()
                    read = None
                    if item.get("method") == "$/closed":
                        if end is not None:
                            yield end
                        else:
                            yield ("error", "the agent process ended")
                        return
                    if item.get("method") == "session/update":
                        update = (item.get("params") or {}).get("update") or {}
                        for ev in from_update(ours, self._turn_ids.get(ours), update):
                            yield ev
                        from .mapper import turn_end_from_state
                        state_end = turn_end_from_state(update)
                        if state_end:              # v2 agents end here instead
                            yield ("end", state_end)
                            return
                if end is not None:
                    for ev in await self._drain_tail(ch, ours):
                        yield ev
                    yield end
                    return
        finally:
            for t in (read, fin):
                if t is not None and not t.done():
                    t.cancel()

    async def _drain_tail(self, ch: StdioChannel, ours: str) -> list[Event]:
        """Everything the agent wrote just before its end signal.

        The agent writes the last text chunk and the prompt response as two lines; the reader can
        see the response first because both are already buffered. A single non-blocking sweep lost
        the tail of an answer (caught by a repeated test run, not by a single one), so this waits
        briefly for the pipe to go quiet instead of assuming it is empty.
        """
        import asyncio as _asyncio

        out: list[Event] = []
        quiet = 0.02
        limit = _asyncio.get_running_loop().time() + 0.5
        while _asyncio.get_running_loop().time() < limit:
            try:
                queued = ch.next_notification_nowait()
            except LookupError:
                await _asyncio.sleep(quiet)
                try:
                    queued = ch.next_notification_nowait()
                except LookupError:
                    break                      # the pipe stayed quiet: nothing more is coming
            if queued.get("method") != "session/update":
                continue
            update = (queued.get("params") or {}).get("update") or {}
            out.extend(from_update(ours, self._turn_ids.get(ours), update))
        return out

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
        """The key this process is stored under.

        `h.ours` is authoritative: it is the id we started the process with, and `_procs` is keyed
        by exactly that. The agent-id mapping is a fallback for a handle built before `ours` existed.

        This used to derive the key from the agent's own session id. That is not unique per process
        — the fake agent reports the same id for every instance — so three processes collapsed onto
        one key and `close()` could only find the last of them. Three archived sessions, two orphan
        processes, measured.
        """
        if h.ours and h.ours in self._procs:
            return h.ours
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
