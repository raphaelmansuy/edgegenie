"""Orchestration: owns session lifecycle and runs turns. Depends only on ports.

The supervisor decides; this module obeys. Every transition is written to the event store
BEFORE it is published, so a reconnecting browser can always fetch what it saw.

Three things this module owns that the spec is precise about:

* **resolution goes through one resolver** (C-3). `_provision` and `set_model` never derive an endpoint
  from an id; they ask `ModelResolver` for a `ResolvedModel`.
* **a turn's model is pinned before the prompt and never rewritten** (Axiom A5, C-8). A switch writes a
  row for the *next* turn; the running turn keeps what it started with.
* **a cross-provider switch restarts the child** (D5). A child's environment is fixed at spawn, so a
  second provider's key needs a new process; the session id, folder, transcript and tool server stay.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from ..adapters.acp.agent_config import AgentConfig, session_rules
from ..domain import supervisor
from ..domain.events import (
    Event,
    approval_decided,
    document_saved,
    evidence_proposed,
    session_created,
    session_ready,
    turn_auditing,
    turn_blocked,
    turn_completed,
    turn_ended,
    turn_started,
)
from ..domain.evidence import DEMO_MARKER, ToolCall, extract_requirements, is_read_only, says_no_tools
from ..domain.llm import ProviderKind, ResolvedModel, WireProtocol, clamp
from ..domain.redact import redact_labelled
from ..domain.scope import Scope, describe
from ..domain.session import (
    DomainError,
    Session,
    SessionState,
    SessionStatus,
    Turn,
    TurnStatus,
    title_from,
    updated,
)
from ..ports import AgentRuntime, RuntimeHandle, SessionSpec, ToolRegistry

MAX_TURNS = 200
TOOL_COUNT_CORE = 19


@dataclass
class Live:
    """Everything belonging to one running session. Rebuilt on restart; the store is truth."""

    state: SessionState
    #: The folder the agent may write to in the WORKSPACE (the fence), e.g. /Users/me/agent_scratch.
    #: Distinct from the agent process's local cwd; conflating them made the fence meaningless.
    workspace_folder: str = ""
    #: The agent process's own working directory on the local filesystem.
    agent_cwd: str = ""
    handle: RuntimeHandle | None = None
    mcp_url: str = ""
    tools: int = 0
    task: asyncio.Task | None = None
    cancel: bool = False
    extra: dict[str, Any] = field(default_factory=dict)
    #: Epoch seconds of the last activity (a turn, a stream connect, or creation). The reaper reads
    #: this; nothing else should. Without it a session is unreapable because "idle" is unknowable.
    last_seen: float = 0.0
    #: The resolved model this process was started with. A switch compares protocols against it.
    resolved: ResolvedModel | None = None

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
        self, runtime: AgentRuntime, tools: ToolRegistry, store, models, demo: bool = False,
        *, resolver=None, credentials=None, store_llm=None, health=None,
    ) -> None:
        self._rt = runtime
        self._tools = tools
        self._store = store
        self._models = models
        self._demo = demo
        self._resolver = resolver
        self._credentials = credentials
        self._llm_store = store_llm
        self._health = health
        self._live: dict[str, Live] = {}

    def attach_registry(self, registry) -> None:
        """Wire the registry after construction, so `build()` can hand it in either order."""
        if registry is None:
            return
        self._resolver = getattr(registry, "resolver", None) or self._resolver
        self._credentials = getattr(registry, "credentials", None) or self._credentials
        self._llm_store = getattr(registry, "store", None) or self._llm_store
        self._health = getattr(registry, "health", None) or self._health

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

    def touch(self, session_id: str) -> None:
        """Record activity. A turn, a stream connect, or an explicit read all count.

        Without this the reaper cannot tell an idle session from an abandoned one, which is why the
        server used to keep every agent process alive for its whole lifetime.
        """
        live = self._live.get(session_id)
        if live:
            live.last_seen = time.time()

    def watchers(self, session_id: str) -> int:
        """How many streams are attached. Non-zero means a human is looking right now."""
        return self._store.subscriber_count(session_id) if hasattr(self._store, "subscriber_count") else 0

    def idle_candidates(self, now: float) -> list[Any]:
        """Live sessions with the fields the reaper policy needs."""
        from ..domain.reaper import Candidate
        return [
            Candidate(session_id=sid, status=live.state.session.status.value,
                      last_seen=live.last_seen or 0.0, watchers=self.watchers(sid),
                      turns=len(live.state.turns))
            for sid, live in self._live.items()
        ]

    async def reap_idle(self, now: float | None = None) -> list[str]:
        """Archive sessions the policy says are finished with. Returns the ids reaped.

        This is what calls `archive()`. It existed but was never called, so every session a user
        opened held a subprocess for the life of the server.
        """
        from ..domain.reaper import Policy, reapable
        now = now if now is not None else time.time()
        policy = Policy()
        reaped: list[str] = []
        # The cap counts sessions still *open*, and archiving one must reduce that count — otherwise
        # a single pass reaps everything: the guard `live_count > keep_minimum` stayed true for every
        # candidate because nothing decremented it. Observed live with keep_minimum=2: all 8 archived.
        open_now = sum(1 for c in self.idle_candidates(now) if c.status != "archived")
        for c in self.idle_candidates(now):
            if reapable(c, now=now, live_count=open_now, policy=policy) is None:
                await self.archive(c.session_id)
                reaped.append(c.session_id)
                open_now -= 1
        return reaped

    def scope(self, session_id: str) -> Scope:
        s = self.get(session_id).state.session
        return Scope.for_session(s.id, s.folder, s.schema)

    def scope_description(self, session_id: str) -> dict:
        return describe(self.scope(session_id))

    async def model_facts(self, session_id: str) -> dict:
        """The inspector's model block: the resolved model plus which turn used which model (FR-10)."""
        live = self.get(session_id)
        pins: list[dict] = []
        if self._llm_store is not None:
            try:
                pins = await self._llm_store.turn_models(session_id)
            except Exception:  # noqa: BLE001 - a provenance read must not fail a session read
                pins = []
        switch_turn = None
        for index, pin in enumerate(pins[1:], start=1):
            if pin["modelId"] != pins[index - 1]["modelId"]:
                switch_turn = index + 1
                break
        return {
            "current": live.state.session.model,
            "resolved": live.resolved.to_dict() if live.resolved else None,
            "turns": [
                {"index": i + 1, "turnId": pin["turnId"], "model": pin["modelId"],
                 "provider": pin["providerId"], "wire": pin["wire"], "endpoint": pin["endpoint"]}
                for i, pin in enumerate(pins)
            ],
            "switchAtTurn": switch_turn,
        }

    # -- lifecycle ------------------------------------------------------------
    async def create(
        self,
        user_id: str,
        folder: str,
        model: str,
        schema: str | None,
        title: str = "New session",
        user_token: str | None = None,
    ) -> Session:
        resolved = await self._resolve(model, user_id, session_id="")
        sid = uuid4().hex[:16]
        session = Session(id=sid, user_id=user_id, folder=folder, schema=schema,
                          model=resolved.id.value, title=title, created_at=time.time())
        live = Live(state=SessionState(session=session), workspace_folder=folder,
                    last_seen=time.time(), resolved=resolved)
        # The user's forwarded token: the agent and the tool server act as this user, not as the app.
        live.extra["user_token"] = user_token
        self._live[sid] = live
        await self._store.append(session_created(sid, folder, resolved.id.value, schema))
        try:
            await self._provision(live)
        except Exception as exc:  # noqa: BLE001 - a failed provision is a visible state, not a crash
            live.state.session = live.state.session.transition(SessionStatus.FAILED)
            await self._store.append(Event(sid, "session.degraded", {"detail": str(exc)[:400]}))
            raise
        return live.state.session

    async def _resolve(self, model: str, user_id: str, *, session_id: str) -> ResolvedModel:
        """One path from an id to a `ResolvedModel`. Falls back to a static resolution in demo mode."""
        if self._resolver is not None:
            resolved, _secret = await self._resolver.resolve(model, user_id=user_id,
                                                            session_id=session_id)
            return resolved
        return self._static(model)

    @staticmethod
    def _static(model: str) -> ResolvedModel:
        """Demo and test mode: the seed row for this id, no credential, no database."""
        from ..services.model_registry import resolve_static as _resolve_static

        cfg = _resolve_static(model, os.environ.get("DATABRICKS_HOST", ""))
        from ..domain.llm import Capability, ModelId
        from ..domain.llm.limits import Limits

        return ResolvedModel(
            id=ModelId.parse(model), provider=cfg.provider, wire=cfg.wire,
            endpoint=cfg.endpoint, base_url=cfg.base_url,
            limits=Limits(cfg.context, cfg.output), capability=Capability.TOOLS,
        )

    async def _provision(self, live: Live) -> None:
        """Prepare everything a session needs, in the order each thing is needed.

        Two different paths matter here and were once conflated:
          * `workspace_folder` is the fence: a WORKSPACE path that the tool server enforces;
          * `agent_cwd` is a real LOCAL directory the agent process runs in.
        A workspace path cannot be a process cwd, and conflating them broke session creation.
        """
        s = live.state.session
        cwd = os.environ.get("APP_AGENT_CWD") or tempfile.mkdtemp(prefix=f"agent-{s.id[:8]}-")
        os.makedirs(cwd, exist_ok=True)
        live.agent_cwd = cwd
        live.workspace_folder = live.workspace_folder or s.folder

        # 1. The agent needs a provider config and its working rules, or it starts and never answers.
        #    The config names an environment VARIABLE; the value never touches the disk.
        try:
            self._write_config(live, cwd)
        except OSError:
            pass  # a read-only cwd is not fatal; the agent will report the failure

        # 2. The tool server, fenced to the workspace folder the user chose. It reads the user's
        #    token from a private file (not the agent's cwd) that every turn refreshes.
        user_token = live.extra.get("user_token") or os.environ.get("DATABRICKS_TOKEN", "")
        self._write_token(live, user_token)
        live.mcp_url = await self._tools.start(s.id, live.workspace_folder, s.schema,
                                               live.extra.get("token_file"))
        live.tools = TOOL_COUNT_CORE if live.mcp_url else 0

        # 3. The agent process itself. It authenticates as the USER, and it receives exactly one
        #    provider key: the selected one (S6).
        env = await self._child_env(live, user_token)
        spec = SessionSpec(session_id=s.id, cwd=cwd, model=s.model, mcp_url=live.mcp_url, env=env)
        live.handle = await self._rt.start(spec)
        # If the session was archived while this was in flight — a reaper pass, or the user closing
        # it — the process we just started has no session to serve and `archive()` already ran with
        # `live.handle` still None, so it could not close it. Close it here instead. Measured: nine
        # orphaned agents survived an archive because the reaper won this race.
        if live.state.session.status is SessionStatus.ARCHIVED:
            await self._rt.close(live.handle)
            live.handle = None
            return
        live.state.session = s.transition(SessionStatus.READY)
        live.state.session = updated(
            live.state.session,
            agent=live.handle.capabilities.agent,
            agent_version=live.handle.capabilities.version,
            tools=live.tools,
        )
        await self._store.append(
            session_ready(s.id, live.tools, live.handle.capabilities.agent,
                          live.handle.capabilities.version, live.handle.capabilities.raw))

    def _write_config(self, live: Live, cwd: str) -> AgentConfig:
        """Write `opencode.json` + the working agreement for the resolved model."""
        resolved = live.resolved or self._static(live.state.session.model)
        cfg = AgentConfig.from_resolved(resolved, host=os.environ.get("DATABRICKS_HOST", ""))
        cfg.write(cwd, session_rules(live.workspace_folder, live.state.session.schema,
                                     live.state.session.id))
        return cfg

    async def _child_env(self, live: Live, user_token: str) -> dict[str, str]:
        """The child's environment: the workspace token, plus **exactly one** provider key.

        Composing this through `CredentialService` is what makes "one key in one process" a property
        of the design rather than a habit: there is no code path here that adds a second one.
        """
        env: dict[str, str] = {}
        if user_token:
            env["DATABRICKS_TOKEN"] = user_token
        resolved = live.resolved
        # `env_var` is empty exactly when the model needs no provider key of its own: a Databricks
        # model is covered by the workspace token, and the demo provider has no endpoint at all.
        if resolved is None or not resolved.env_var:
            self._materialise(live, {})        # a switch away from a keyed provider drops its files
            return env
        if self._credentials is not None:
            child = await self._credentials.env_for(
                resolved, user_id=live.state.session.user_id, session_id=live.state.session.id,
                workspace_token=user_token)
            env.update(child.vars)
            env.update(self._materialise(live, child.files))
        return env

    @staticmethod
    def _materialise(live: Live, files: dict[str, str]) -> dict[str, str]:
        """Write each secret file the provider needs; return `{VARIABLE: path}`.

        One private directory per session (mode 0700), files 0600, removed on archive. A switch
        rewrites the files, so a previous provider's key never outlives its child. Nothing here is
        derived from the content, so a bad key cannot influence a path.
        """
        folder = live.extra.get("secret_dir")
        if files and not folder:
            folder = tempfile.mkdtemp(prefix="llmkey-")
            live.extra["secret_dir"] = folder
        if folder:
            for name in os.listdir(folder):               # drop the previous provider's files
                if name not in files:
                    os.unlink(os.path.join(folder, name))
        out: dict[str, str] = {}
        for var, content in files.items():
            path = os.path.join(folder, var.lower())
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as fh:
                fh.write(content)
            out[var] = path
        return out

    @staticmethod
    def _write_token(live: Live, token: str | None) -> None:
        """Keep the tool server's credential current. A forwarded user token lasts about an hour."""
        if not token:
            return
        path = live.extra.get("token_file")
        if not path:
            folder = tempfile.mkdtemp(prefix="nbmcp-")        # mode 0700
            path = os.path.join(folder, "token")
            live.extra["token_file"] = path
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(token)

    async def model_options(self, session_id: str) -> dict:
        live = self.get(session_id)
        allowed = [m["id"] for m in self._models.allowed(live.state.session.user_id)]
        # RB-11: never offer a catalogue entry this workspace cannot serve. The agent's own list is
        # authoritative for what it can switch to, but an empty list means "it advertises none" and
        # must not empty the picker.
        offered = [m for m in (live.handle.models if live.handle else []) if m in allowed]
        return {"current": live.state.session.model, "available": offered or allowed,
                "restartRequired": False}

    async def set_model(self, session_id: str, model: str) -> dict:
        """Switch the model for the **next** turn. The running turn is never retargeted (FR-9).

        Three cases (03 §Switching a model):
          * same provider and wire: ACP `set_config_option`, using the id the agent advertises;
          * different wire or provider: restart the child with a new config and a new environment,
            keeping the session id, folder, transcript and tool server;
          * ACP refuses: keep the old model, surface the provider's words, record nothing.
        """
        live = self.get(session_id)
        user_id = live.state.session.user_id
        resolved = await self._resolve(model, user_id, session_id=session_id)
        current = live.resolved
        restart = current is None or current.provider is not resolved.provider or current.wire is not resolved.wire
        if restart:
            await self._restart(live, resolved)
        else:
            agent_id = resolved.agent_id or resolved.endpoint
            if live.handle:
                try:
                    await self._rt.set_model(live.handle, agent_id)
                except Exception as exc:  # noqa: BLE001 - a refusal is a state, not a crash
                    from ..domain.llm import ProviderUnhealthy

                    raise ProviderUnhealthy(
                        f"the agent refused the switch: {redact_labelled(str(exc))[:300]}") from exc
            live.resolved = resolved
        live.state.session = updated(live.state.session, model=resolved.id.value)
        options = await self.model_options(session_id)
        return {**options, "restartRequired": restart}

    async def _restart(self, live: Live, resolved: ResolvedModel) -> None:
        """Drain the current turn, replace the child, keep everything else.

        Draining first is what stops a tool result being lost (E-19): `cancel` waits for the prompt
        task with a 10 s shield in the runtime, so an in-flight tool update is delivered and stored
        before the process goes away.
        """
        sid = live.state.session.id
        if live.handle is not None:
            if live.task and not live.task.done():
                try:
                    await self._rt.cancel(live.handle)
                except Exception:  # noqa: BLE001 - a cancel that fails must not block a switch
                    pass
            await self._rt.close(live.handle)
            live.handle = None
        live.resolved = resolved
        cwd = live.agent_cwd or tempfile.mkdtemp(prefix=f"agent-{sid[:8]}-")
        os.makedirs(cwd, exist_ok=True)
        live.agent_cwd = cwd
        self._write_config(live, cwd)
        env = await self._child_env(live, live.extra.get("user_token")
                                    or os.environ.get("DATABRICKS_TOKEN", ""))
        live.handle = await self._rt.start(
            SessionSpec(session_id=sid, cwd=cwd, model=resolved.id.value,
                        mcp_url=live.mcp_url, env=env))
        await self._store.append(Event(sid, "session.ready", {
            "switched": True, "model": resolved.id.value, "wire": resolved.wire.value,
            "toolCount": live.tools, "agent": live.handle.capabilities.agent,
            "agentVersion": live.handle.capabilities.version,
            "capabilities": live.handle.capabilities.raw,
        }))

    async def archive(self, session_id: str) -> None:
        live = self._live.get(session_id)
        if not live or live.state.session.status is SessionStatus.ARCHIVED:
            return
        if live.task and not live.task.done():
            live.cancel = True
            if live.handle:
                await self._rt.cancel(live.handle)
        live.state.session = live.state.session.transition(SessionStatus.ARCHIVED)
        live.cancel = True          # a provision still in flight must not finish
        if live.handle:
            await self._rt.close(live.handle)
        await self._tools.stop(session_id)
        token_file = live.extra.get("token_file")
        if token_file:       # only ever our own mkdtemp folder; never derive a path from nothing
            shutil.rmtree(os.path.dirname(token_file), ignore_errors=True)
        secret_dir = live.extra.get("secret_dir")
        if secret_dir:       # the provider key files; same rule: only our own mkdtemp folder
            shutil.rmtree(secret_dir, ignore_errors=True)
        await self._store.append(Event(session_id, "session.archived", {}))

    async def cancel(self, session_id: str) -> None:
        live = self.get(session_id)
        live.cancel = True
        if live.handle:
            await self._rt.cancel(live.handle)

    async def record_document_saved(self, session_id: str, path: str, size: int, *, by: str) -> None:
        """Put a human write into the session's event stream (spec 003 WR-4).

        The transcript and the audit are one record: a save that happened in the editor has to be
        visible where a turn is visible, with who did it. The session must exist; a caller that
        already saved should not fail because recording did not — the route decides that.
        """
        self.get(session_id)          # KeyError if there is no such session
        await self._store.append(document_saved(session_id, path, size, by=by))

    # -- turns ----------------------------------------------------------------
    async def submit(self, session_id: str, text: str, context: str = "",
                     attachments: list[dict] | None = None, user_token: str | None = None) -> Turn:
        live = self.get(session_id)
        if live.state.session.status is SessionStatus.ARCHIVED:
            raise DomainError("this session is archived")
        if len(live.state.turns) >= MAX_TURNS:
            raise DomainError(f"this session reached its limit of {MAX_TURNS} turns")
        self._write_token(live, user_token)
        running = live.state.running()
        text = DEMO_MARKER.sub(" ", text).strip()     # never store a demo hint as the user's words
        # A key pasted into a prompt is a user error the app must survive (S12/E-8): the stored
        # payload is redacted and labelled, and the turn continues.
        stored_text = redact_labelled(text)
        turn = live.state.new_turn(stored_text, context)
        if not live.state.turns[:-1] and live.state.session.title == "New session":
            live.state.session = updated(live.state.session, title=title_from(text))
        # The pin is written BEFORE the prompt and never updated (Axiom A5, C-8).
        await self._pin_turn(live, turn)
        await self._store.append(
            turn_started(session_id, turn.id, stored_text, live.state.session.model, attachments))
        if running is None:
            live.task = asyncio.create_task(self._run_turn(live, turn.id))
        return turn

    async def _pin_turn(self, live: Live, turn: Turn) -> None:
        """Record which model this turn is about to use. Insert-once, so history is immutable."""
        if self._llm_store is None:
            return
        resolved = live.resolved or self._static(live.state.session.model)
        try:
            await self._llm_store.record_turn_model({
                "turnId": turn.id,
                "sessionId": live.state.session.id,
                "modelId": resolved.id.value,
                "providerId": resolved.provider.value,
                "wire": resolved.wire.value,
                "endpoint": resolved.endpoint,
                "credentialRef": resolved.credential_ref,
                "limitEvidence": resolved.limits.evidence.value,
                "context": resolved.context,
                "output": resolved.output,
            })
        except Exception:  # noqa: BLE001 - recording provenance must not block a turn
            pass

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
            await self._rt.prompt_in_background(live.handle, turn.context + turn.prompt)  # type: ignore[arg-type]
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
            self._start_next(live)
            return
        if "error" in ended:
            await self._classify_failure(live, ended["error"], turn.id)
            self._finish(live, turn.finish(TurnStatus.FAILED, error=ended["error"][:400]))
            await self._store.append(turn_ended(sid, turn.id, "failed", ended["error"][:400]))
            live.state.session = live.state.session.transition(SessionStatus.BLOCKED)
            self._start_next(live)
            return

        requirements = extract_requirements(turn.prompt)
        decision = supervisor.decide(
            supervisor.State(
                requirements=requirements,
                read_only=is_read_only(requirements, bool(turn.context)) or says_no_tools(turn.prompt),
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
            # committed above, so _start_next sees no running turn
            await self._store.append(
                turn_completed(sid, turn.id, ended.get("stop", "end_turn"), usage, seconds)
            )
            live.state.session = live.state.session.transition(SessionStatus.READY)
            self._start_next(live)
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

    async def _classify_failure(self, live: Live, error: str, turn_id: str) -> None:
        """Name the failure, and let a cap rejection lower the stored cap (E-4).

        ACP has no structured provider error, so this consumes the one string the runtime produces.
        The classification is recorded as health with `source=turn`, which is what makes a failure
        between probes visible at all.
        """
        if self._health is None:
            return
        resolved = live.resolved
        if resolved is None:
            return
        from ..services.model_service import ModelService  # noqa: F401 - type clarity only

        spec = None
        finder = getattr(self._health, "_store", None)
        if finder is not None:
            spec = await finder.find(resolved.id.value)
        if spec is None:
            return
        try:
            await self._health.note_turn(spec, error, turn_id=turn_id)
        except Exception:  # noqa: BLE001 - classification must never fail a turn
            pass

    def _finish(self, live: Live, turn: Turn) -> None:
        live.state.update(turn)

    def _start_next(self, live: Live) -> None:
        """Run the next queued turn, if any.

        Called from inside the running turn's own task, so "is something running?" cannot be
        answered by `live.task` (that is this very task). The question that matters is whether any
        OTHER turn is already running.
        """
        nxt = next((t for t in live.state.turns if t.status is TurnStatus.QUEUED), None)
        if nxt is None:
            return
        # Every caller has already committed this turn's terminal status, so any RUNNING/AUDITING
        # turn here belongs to a different turn that is genuinely in flight.
        if any(t.status in (TurnStatus.RUNNING, TurnStatus.AUDITING) for t in live.state.turns):
            return
        # Schedule on the loop after this turn's own settle returns, so states are consistent.
        live.task = asyncio.get_running_loop().create_task(self._run_turn(live, nxt.id))

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
