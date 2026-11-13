"""The ACP agent runtime. The only module that knows a specific agent exists."""

from __future__ import annotations

import asyncio
import collections
import os
import re
import shlex
from uuid import uuid4
from collections.abc import AsyncIterator

from ...domain.events import Event
from ...ports import AgentAuthError, AgentCrashed, AgentError, Capabilities, RuntimeHandle, SessionSpec
from ..child_env import child_env
from .blocks import prompt_blocks
from .jsonrpc import StdioChannel, TransportError
from .mapper import from_permission, from_update, model_options, turn_end_from_prompt_response

CLIENT_INFO = {"name": "databricks-coding-agents", "version": "0.1"}
# ACP has no "the model call failed" signal: when the endpoint errors, some agents log to stderr and
# never end the turn. Without this guard a turn hangs forever (observed with a 403 from the gateway).
IDLE_TURN_TIMEOUT = float(os.environ.get("APP_TURN_IDLE_TIMEOUT", "180"))


class AcpAgentRuntime:
    """Spawns an ACP v1 agent. v2 is a different lifecycle and is not negotiated here."""

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
        self._tool_frames: dict[str, dict[str, dict]] = {}
        self._call_turns: dict[str, dict[str, str]] = {}
        self._prompt_tasks: dict[str, asyncio.Task] = {}
        self._questions = {}
        self._agent_sessions = {}
        self._pending_permissions: dict[str, tuple[str, dict]] = {}

    # -- lifecycle ------------------------------------------------------------
    async def start(self, spec: SessionSpec) -> RuntimeHandle:
        env = child_env({**self._extra_env, **spec.env}, home=os.path.join(spec.cwd, ".home"))
        env.setdefault("NODE_NO_WARNINGS", "1")
        env["OPENCODE_DISABLE_AUTOUPDATE"] = "1"
        from pathlib import Path
        # Agent discovery walks ancestors. None may silently contribute instructions or skills.
        for ancestor in Path(spec.cwd).resolve().parents:
            for candidate in ("AGENTS.md", "CLAUDE.md", ".opencode", ".assistant/skills", ".agents/skills"):
                if (ancestor / candidate).exists():
                    raise AgentCrashed(f"Agent folder has inherited instructions or skills at {ancestor / candidate}")
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
        ch.on_request("elicitation/create", lambda p: self._on_question(spec.session_id,p))

        try:
            init = await ch.request(
                "initialize",
                {
                    "protocolVersion": 1,
                    "clientCapabilities": {
                        "fs": {"readTextFile": False, "writeTextFile": False},
                        "terminal": False,
                        "elicitation": {"form": {}},
                        "session": {"notices": {}, "compaction": {}},
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
            # Measured on opencode 1.18.19: `promptCapabilities: {embeddedContext: true, image: true}`.
            # Reading it is what lets the wire carry pixels when the agent can take them.
            images=bool(((init.get("agentCapabilities") or {}).get("promptCapabilities") or {}).get("image")),
            embedded_context=bool(((init.get("agentCapabilities") or {}).get("promptCapabilities") or {})
                                  .get("embeddedContext")),
            raw=init.get("agentCapabilities") or {},
        )
        if caps.protocol_version != 1:
            await self.close_silently(spec.session_id)
            raise AgentCrashed("unsupported ACP version: this runtime requires ACP v1")
        if caps.agent.lower() == "opencode" and caps.version not in {"1.18.19"}:
            await self.close_silently(spec.session_id)
            raise AgentCrashed(f"Unsupported opencode version {caps.version}; supported: 1.18.19")
        if spec.mcp_url and not (caps.raw.get("mcpCapabilities") or {}).get("http"):
            await self.close_silently(spec.session_id)
            raise AgentCrashed("The agent cannot reach tools: mcpCapabilities.http was not advertised")
        can_resume = "resume" in (caps.raw.get("sessionCapabilities") or {})
        if spec.agent_session_id and not (caps.load_session or can_resume):
            await self.close_silently(spec.session_id)
            raise AgentCrashed("this agent cannot restore sessions; loadSession was not advertised")
        self._capabilities[spec.session_id] = caps

        ch.discard_session_history(bool(spec.agent_session_id))
        try:
            new = await ch.request(
                ("session/resume" if can_resume else "session/load") if spec.agent_session_id else "session/new",
                {
                    **({"sessionId": spec.agent_session_id} if spec.agent_session_id else {}),
                    "cwd": spec.cwd,
                    "mcpServers": ([{"type": "http", "name": "db", "url": spec.mcp_url, "headers": []}]
                                   if spec.mcp_url else []),
                },
                timeout=90,
            )
        except TransportError as exc:
            await self.close_silently(spec.session_id)
            msg = str(exc)
            if "auth_required" in msg or "-32000" in msg:
                raise AgentAuthError(msg) from exc
            raise AgentCrashed(msg) from exc

        ch.discard_session_history(False)
        models, current = model_options(new)
        # session/load replays history. It is already in our journal: consume it before the next
        # prompt, or yesterday's tool results would be attributed to today's turn.
        if spec.agent_session_id:
            while True:
                try:
                    ch.next_notification_nowait()
                except LookupError:
                    break
        agent_sid = spec.agent_session_id or str(new.get("sessionId", ""))
        if not agent_sid:
            await self.close_silently(spec.session_id)
            raise AgentCrashed("the agent returned no session id")
        self._by_agent[agent_sid] = spec.session_id
        self._agent_sessions[spec.session_id] = agent_sid
        # Setup can carry the initial command catalogue before any update notification exists.
        if "availableCommands" in new:
            await ch.enqueue_notification({"method": "session/update", "params": {"update": {
                "sessionUpdate": "available_commands_update", "availableCommands": new["availableCommands"]}}})
        return RuntimeHandle(session_id=agent_sid, ours=spec.session_id, capabilities=caps,
                             models=models, current_model=current)

    async def _drain_stderr(self, session_id: str, stream: asyncio.StreamReader) -> None:
        """Keep the agent's stderr flowing and remember the tail, for diagnosis."""
        try:
            pending = ""
            while chunk := await stream.read(16384):
                lines = (pending + chunk.decode(errors="replace")).split("\n")
                pending = lines.pop()[-4096:]
                rows = self._stderr.get(session_id)
                if rows is not None:
                    rows.extend(line[-4096:].rstrip() for line in lines)
            if pending and session_id in self._stderr:
                self._stderr[session_id].append(pending)
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
        self._cancel_permissions(ours)
        task = self._prompt_tasks.pop(ours, None)
        if task and not task.done():
            task.cancel()
        t = self._stderr_tasks.pop(ours, None)
        if t:
            t.cancel()
        proc, ch = self._procs.pop(ours, (None, None))
        if ch:
            await ch.close()
        self._forget(ours)
        if proc and proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), 5)
            except TimeoutError:
                proc.kill()
                await proc.wait()

    async def close_silently(self, session_id: str) -> None:
        self._cancel_permissions(session_id)
        task = self._stderr_tasks.pop(session_id, None)
        if task:
            task.cancel()
        proc, ch = self._procs.pop(session_id, (None, None))
        if ch:
            await ch.close()
        self._forget(session_id)
        if proc and proc.returncode is None:
            proc.kill()
            await proc.wait()

    def _forget(self, sid: str) -> None:
        for qid,pending in list(self._questions.items()):
            if pending[0]==sid:self._questions.pop(qid,None)
        task = self._prompt_tasks.pop(sid, None)
        if task and not task.done():
            task.cancel()
        for mapping in (self._capabilities, self._turn_ends, self._turn_ids, self._stderr, self._tool_frames, self._call_turns, self._agent_sessions):
            mapping.pop(sid, None)
        for agent_id, ours in list(self._by_agent.items()):
            if ours == sid:
                del self._by_agent[agent_id]

    # -- turns ----------------------------------------------------------------
    def _blocks(self, h: RuntimeHandle, text: str, images: list[dict] | None) -> list[dict]:
        """The prompt array, built by the one function that knows ACP's capability rule.

        The capability is looked up by `_ours(h)` — the id WE started the process with — not by
        `h.session_id`, which is the AGENT's own id. `_capabilities` is keyed by ours, so the wrong key
        returned None and every image was silently replaced by the "omitted" text: the model was told it
        could not see a picture that was never sent, and answered exactly that. Measured: the image
        reduced the prompt by 1,990 tokens instead of adding any, because only a sentence travelled.
        """
        return prompt_blocks(text, images, self._capabilities.get(self._key(h)))

    def _key(self, h: RuntimeHandle) -> str:
        """The key this session's facts are stored under.

        `h.ours` is OUR id — the one `_capabilities` and `_procs` are keyed by — and it is authoritative
        when present. `_ours()` adds a fallback that consults `_procs`, which is right for process
        bookkeeping and wrong for a pure capability lookup: a handle with no live process yet would miss.
        So the capability path asks the handle directly.
        """
        return h.ours or self._by_agent.get(h.session_id, h.session_id)

    async def prompt(self, h: RuntimeHandle, text: str, images: list[dict] | None = None) -> dict:
        ch = self._channel(h)
        # opencode accepts prompt as a request; the response carries the stop reason in v1.
        task = asyncio.create_task(
            ch.request(
                "session/prompt",
                {"sessionId": h.session_id, "prompt": self._blocks(h, text, images)},
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

    async def prompt_in_background(self, h: RuntimeHandle, text: str,
                                   images: list[dict] | None = None) -> None:
        """Same as prompt, but does not wait: completion arrives through events()."""
        ch = self._channel(h)
        task = asyncio.create_task(
            ch.request(
                "session/prompt",
                {"sessionId": h.session_id, "prompt": self._blocks(h, text, images)},
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
        self._cancel_permissions(self._ours(h))
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

    async def set_mode(self,h,mode):
        await self._channel(h).request('session/set_config_option',{'sessionId':h.session_id,'configId':'mode','value':mode},timeout=30)

    async def respond_permission(self, h: RuntimeHandle, request_id: str, option_id: str | None) -> None:
        pending = self._pending_permissions.get(request_id)
        if not pending or pending[0] != self._ours(h):
            raise AgentError("permission is no longer pending for this session")
        if option_id is not None and not any(o.get("optionId") == option_id
                                            for o in pending[1].get("options", [])):
            raise AgentError("permission option was not offered")
        fut = self._permission_waiters.get(request_id)
        if fut and not fut.done():
            fut.set_result(option_id)

    async def fail_permission(self, h: RuntimeHandle, request_id: str, reason: str) -> None:
        pending = self._pending_permissions.get(request_id)
        if not pending or pending[0] != self._ours(h):
            raise AgentError("permission is no longer pending for this session")
        future = self._permission_waiters.get(request_id)
        if future and not future.done():
            future.set_exception(ValueError(reason[:300]))

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
                    done, _ = await asyncio.wait({read, fin}, timeout=(90 if any(f.get("status") in ("pending", "in_progress", "running")
                        for f in self._tool_frames.get(ours, {}).values()) else IDLE_TURN_TIMEOUT),
                                                 return_when=asyncio.FIRST_COMPLETED)
                except asyncio.CancelledError:
                    raise
                if not done:
                    if any(sid == ours for sid, _ in self._pending_permissions.values()) or any(q[0]==ours for q in self._questions.values()):
                        continue  # waiting for a person is not an unresponsive model
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
                    if item.get("method") == "opengenie/question":
                        yield Event(ours,"question.requested",item["params"],turn_id=self._turn_ids.get(ours),actor="agent")
                    if item.get("method") == "opengenie/permission":
                        params = item["params"]
                        request = params["request"]
                        call = request.get("toolCall") or {}
                        frame = self._tool_frames.get(ours, {}).get(call.get("toolCallId"), {})
                        request = {**request, "toolCall": {**call, **frame}}
                        yield from_permission(ours, self._turn_ids.get(ours), request, params["approvalId"])
                    if item.get("method") == "session/update":
                        update = (item.get("params") or {}).get("update") or {}
                        if not self._remember_tool(ours, update):
                            continue
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
            if self._remember_tool(ours, update):
                out.extend(from_update(ours, self._turn_ids.get(ours), update))
        return out

    def _remember_tool(self, sid: str, update: dict) -> bool:
        cid = update.get("toolCallId")
        if cid:
            epoch = self._turn_ids.get(sid, "")
            calls = self._call_turns.setdefault(sid, {})
            if cid in calls and calls[cid] != epoch:
                return False
            calls[cid] = epoch
            # Bound retained attribution ids. They exist to reject late notifications.
            if len(calls) > 4096:
                del calls[next(iter(calls))]
            frames = self._tool_frames.setdefault(sid, {})
            frames[cid] = {**frames.get(cid, {}), **update}
        return True

    def set_turn(self, session_id: str, turn_id: str) -> None:
        """Tell the adapter which turn subsequent updates belong to."""
        self._turn_ids[session_id] = turn_id
        self._tool_frames[session_id] = {}

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
        approval_id = f"ap_{uuid4().hex}"
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._permission_waiters[approval_id] = fut
        self._pending_permissions[approval_id] = (session_id, params)
        ch = self._procs[session_id][1]
        await ch.enqueue_notification({"method": "opengenie/permission", "params": {
            "approvalId": approval_id, "request": params}})
        try:
            option_id = await fut
            if option_id is None:
                return {"outcome": {"outcome": "cancelled"}}
            return {"outcome": {"outcome": "selected", "optionId": option_id}}
        finally:
            self._permission_waiters.pop(approval_id, None)
            self._pending_permissions.pop(approval_id, None)

    def _cancel_permissions(self, session_id: str) -> None:
        for qid,(sid,future,schema) in list(self._questions.items()):
            if sid==session_id and not future.done():future.set_result({"action":"cancel"})
        for aid, (sid, _) in list(self._pending_permissions.items()):
            if sid == session_id:
                fut = self._permission_waiters.get(aid)
                if fut and not fut.done():
                    fut.set_result(None)

    async def _on_question(self,sid,params):
        from ...domain.question import validate_schema
        if params.get('mode')!='form':raise ValueError('Only advertised form elicitation is supported')
        if self._agent_sessions.get(sid)!=params.get('sessionId'):raise ValueError('Question does not belong to this connection')
        schema=validate_schema(params.get('requestedSchema',{}))
        qid='question_'+uuid4().hex
        future=asyncio.get_running_loop().create_future()
        self._questions[qid]=(sid,future,schema)
        await self._procs[sid][1].enqueue_notification({'method':'opengenie/question','params':{'id':qid,'message':str(params.get('message',''))[:2000],'schema':schema,'state':'pending','agent':self._capabilities[sid].agent}})
        try:return await future
        finally:self._questions.pop(qid,None)

    async def respond_question(self,h,qid,action,content):
        from ...domain.question import validate_content
        pending=self._questions.get(qid)
        if not pending or pending[0]!=self._ours(h) or pending[1].done():raise AgentError('This question is no longer pending')
        if action not in ('accept','decline','cancel'):raise ValueError('Choose accept, decline or cancel')
        result={'action':action}
        if action=='accept':result['content']=validate_content(pending[2],content)
        pending[1].set_result(result)
