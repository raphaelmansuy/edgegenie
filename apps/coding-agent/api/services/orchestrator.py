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
import base64
import contextlib
import dataclasses
import copy
import json
import logging
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
from ..domain.llm import ResolvedModel
from ..domain.redact import redact_labelled, redact_value
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
#: How many tools the `core` profile advertises, for the UI's "N tools" badge. It is NOT the authority
#: on the budget: `NBMCP_PROFILE=core` selects the set, and `tests/test_tools_fence.py` holds it to 28
#: (spec 014 [TOOL-1]). This number is a label that must match, and a test asserts it does.
TOOL_COUNT_CORE = 28
#: The folder the agent may write to, handed to the child so it can name real paths. A reference
#: agent's scenarios record `/Users/you/…` as a placeholder; without this it reported a path that
#: does not exist and every demo turn opened a 404.
FENCE_ENV = "APP_WORKSPACE_FOLDER"
#: Where each session's ledger of created pipelines lives. Beside the blob store, because it has the same
#: durability requirement: a session that resumes must still be able to stop what it made (spec 014
#: [RB-3]). The app owns the directory; the tool server only appends to its own file.
LEDGER_ENV = "APP_SESSION_LEDGER_DIR"


@dataclass
class Live:
    """Everything belonging to one running session. Rebuilt on restart; the store is truth."""

    state: SessionState
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
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
        *, resolver=None, credentials=None, store_llm=None, health=None, max_run_seconds=21600, max_concurrent=4,
    ) -> None:
        self._slots = asyncio.Semaphore(max_concurrent)
        self._max_run_seconds = max_run_seconds
        self._shutting_down = False
        self._rt = runtime
        self._tools = tools
        self._store = store
        self._models = models
        self._demo = demo
        self._resolver = resolver
        self._credentials = credentials
        self._llm_store = store_llm
        self._health = health
        self._blobs = None
        self._live: dict[str, Live] = {}

    def _snapshot(self, live: Live) -> dict:
        # A whitelist: never serialize extra, a forwarded token, secret file, or provider key.
        return {
            "version": 1,
            "session": dataclasses.asdict(live.state.session),
            "turns": [dataclasses.asdict(t) for t in live.state.turns],
            "calls": copy.deepcopy(live.state.calls),
            "agentCwd": live.agent_cwd,
            "agentSessionId": live.handle.session_id if live.handle else live.extra.get("agent_session_id", ""),
            "lastSeen": live.last_seen,
            "approvals": copy.deepcopy(live.extra.get("approvals", {})),
        }

    async def _emit(self, event: Event) -> Event:
        live = self.get(event.session_id)
        safe = dataclasses.replace(event, payload=redact_value(event.payload))
        return await self._store.commit(safe, redact_value(self._snapshot(live)))

    async def restore(self) -> None:
        """Restore committed state, never replay a potentially non-idempotent tool operation."""
        for row in await self._store.snapshots():
            if not row:
                continue
            if row.get("version") != 1:
                raise RuntimeError("unsupported session snapshot version")
            s = Session(**{**row["session"], "status": SessionStatus(row["session"]["status"])})
            turns = [Turn(**{**t, "status": TurnStatus(t["status"])}) for t in row["turns"]]
            live = Live(SessionState(s, turns, row.get("calls", {})), workspace_folder=s.folder,
                        agent_cwd=row.get("agentCwd", ""), last_seen=row.get("lastSeen", 0))
            live.extra["agent_session_id"] = row.get("agentSessionId", "")
            self._live[s.id] = live
            if s.status is SessionStatus.ARCHIVED:
                continue
            # Permissions belong to the dead transport. They must be requested afresh after load.
            for aid in row.get("approvals", {}):
                await self._emit(approval_decided(s.id, None, aid, "expired", "server"))
            interrupted = []
            for t in turns:
                if t.status in (TurnStatus.RUNNING, TurnStatus.AUDITING, TurnStatus.QUEUED):
                    live.state.update(t.finish(TurnStatus.INTERRUPTED, error="Server restarted; review saved progress before continuing."))
                    interrupted.append(t)
            live.state.session = updated(s, status=SessionStatus.BLOCKED, requires_resume=True)
            for t in interrupted:
                await self._emit(turn_ended(s.id, t.id, "interrupted",
                    "Server restarted. Saved progress is available; no operation was automatically repeated."))
            await self._emit(Event(s.id, "session.recovery_required", {"requiresResume": True}))

    async def shutdown(self) -> None:
        self._shutting_down = True
        for live in self._live.values():
            if live.task and not live.task.done():
                live.task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await live.task
            if live.handle:
                await self._rt.close(live.handle)
                live.handle = None
            await self._tools.stop(live.state.session.id)
            # Private credentials are disposable; the journal is not.
            for key in ("token_file", "secret_dir"):
                path = live.extra.pop(key, "")
                if path:
                    shutil.rmtree(os.path.dirname(path) if key == "token_file" else path, ignore_errors=True)

    async def resume(self, session_id: str, user_token: str | None = None) -> Session:
        live = self.get(session_id)
        async with live.lock:
            if not live.state.session.requires_resume:
                return live.state.session
            if live.state.session.status is SessionStatus.ARCHIVED:
                raise DomainError("this session is archived")
            if live.task and not live.task.done():
                raise DomainError("a turn is still running")
            live.extra["user_token"] = user_token
            live.resolved = await self._resolve(live.state.session.model, live.state.session.user_id,
                                                session_id=session_id)
            live.state.session = updated(live.state.session, status=SessionStatus.PROVISIONING)
            try:
                await self._provision(live)
            except Exception:
                live.state.session = updated(live.state.session, status=SessionStatus.BLOCKED, requires_resume=True)
                await self._tools.stop(session_id)
                await self._emit(Event(session_id, "session.recovery_required", {"requiresResume": True}))
                raise
            return live.state.session

    def agent_stderr(self, session_id: str) -> str:
        """The agent's own last words, for a turn that ended without an answer.

        `blocked` with no cause is the worst failure this app can show: the user sees a stopped turn and
        nothing else. The runtime captures stderr and ranks the most useful line; nothing read it.
        """
        live = self._live.get(session_id)
        if live is None or live.handle is None:
            return ""
        tail = getattr(self._rt, "stderr_tail", None)
        return tail(session_id, 3) if callable(tail) else ""

    def attach_blobs(self, blobs) -> None:
        """Wire the blob stage after construction, the same way the registry is wired.

        The orchestrator reads image bytes here rather than in the agent: the store already decided who may
        see this row, and the bytes must not travel through the prompt as text (spec 009 [D7]).
        """
        self._blobs = blobs

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
        """The user's conversations, newest first. An archived one is the user's "delete": it stays in
        memory for the audit trail but is no longer something to list, or the delete control would
        succeed and the row would still be there."""
        return sorted(
            (live.state.session for live in self._live.values()
             if live.state.session.user_id == user_id
             and live.state.session.status is not SessionStatus.ARCHIVED),
            key=lambda s: s.id,
            reverse=True,
        )

    def activity(self, session_id: str) -> dict:
        live = self.get(session_id)
        last = live.state.turns[-1] if live.state.turns else None
        approvals = live.extra.get("approvals", {})
        return {"persistence": "durable" if self._store.durable else "memory",
                "state": "needs_attention" if live.state.session.requires_resume else
                         "waiting_for_approval" if approvals else
                         "running" if live.state.running() else last.status.value if last else "ready",
                "queued": sum(t.status is TurnStatus.QUEUED for t in live.state.turns),
                "pendingApprovals": len(approvals),
                "maxRunSeconds": self._max_run_seconds}

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
                if self._store.durable:
                    live = self.get(c.session_id)
                    if live.state.session.requires_resume:
                        continue
                    if live.handle:
                        live.extra["agent_session_id"] = live.handle.session_id
                        await self._rt.close(live.handle)
                        live.handle = None
                    await self._tools.stop(c.session_id)
                    live.state.session = updated(live.state.session, requires_resume=True)
                    await self._emit(Event(c.session_id, "session.recovery_required", {"requiresResume": True}))
                else:
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
        await self._emit(session_created(sid, folder, resolved.id.value, schema))
        try:
            await self._provision(live)
        except Exception as exc:  # noqa: BLE001 - a failed provision is a visible state, not a crash
            live.state.session = live.state.session.transition(SessionStatus.FAILED)
            await self._emit(Event(sid, "session.degraded", {"detail": str(exc)[:400]}))
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
            # The capability travels with the resolution. Without it, this fallback path built a config
            # that told opencode the model was text-only — so the agent stripped the image and the model
            # answered "Can't see the image" while the catalogue claimed it could. Measured.
            sees_images=bool(getattr(cfg, "sees_images", False)),
        )

    async def _provision(self, live: Live) -> None:
        """Prepare everything a session needs, in the order each thing is needed.

        Two different paths matter here and were once conflated:
          * `workspace_folder` is the fence: a WORKSPACE path that the tool server enforces;
          * `agent_cwd` is a real LOCAL directory the agent process runs in.
        A workspace path cannot be a process cwd, and conflating them broke session creation.
        """
        s = live.state.session
        cwd = live.agent_cwd or os.environ.get("APP_AGENT_CWD") or tempfile.mkdtemp(prefix=f"agent-{s.id[:8]}-")
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
        ledger_dir = os.environ.get(LEDGER_ENV) or os.path.join(tempfile.gettempdir(),
                                                               "agent-ledgers")
        live.mcp_url = await self._tools.start(s.id, live.workspace_folder, s.schema,
                                               live.extra.get("token_file"),
                                               live.extra.get("sp_token_file"),
                                               ledger_dir)
        live.tools = TOOL_COUNT_CORE if live.mcp_url else 0

        # 3. The agent process itself. It authenticates as the USER, and it receives exactly one
        #    provider key: the selected one (S6).
        env = await self._child_env(live, user_token)
        # The folder the session may write to, so a reference agent's recorded file paths can name a
        # real one. `/Users/you/…` in a scenario is a placeholder; an agent that opened it 404'd and
        # filled the console with a failed request on every demo turn.
        if live.workspace_folder:
            env[FENCE_ENV] = live.workspace_folder
        spec = SessionSpec(session_id=s.id, cwd=cwd, model=s.model, mcp_url=live.mcp_url, env=env,
                           agent_session_id=live.extra.get("agent_session_id", ""))
        live.handle = await self._rt.start(spec)
        # If the session was archived while this was in flight — a reaper pass, or the user closing
        # it — the process we just started has no session to serve and `archive()` already ran with
        # `live.handle` still None, so it could not close it. Close it here instead. Measured: nine
        # orphaned agents survived an archive because the reaper won this race.
        if live.state.session.status is SessionStatus.ARCHIVED:
            await self._rt.close(live.handle)
            live.handle = None
            return
        live.state.session = updated(s.transition(SessionStatus.READY), requires_resume=False)
        live.state.session = updated(
            live.state.session,
            agent=live.handle.capabilities.agent,
            agent_version=live.handle.capabilities.version,
            tools=live.tools,
        )
        await self._emit(
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

    def _write_token(self, live: Live, token: str | None) -> None:
        """Keep the tool server's credentials current. A forwarded user token lasts about an hour.

        An instance method, not a static one, because it also writes the app's own service-principal
        token: `postgres` cannot be called as the user (spec 013 [RB-10]), so the Lakebase tools need
        a second credential beside the user's.
        """
        if not token:
            return
        live.extra["user_token"] = token
        try:
            segment = token.split(".")[1]
            expiry = json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))).get("exp")
            live.extra["token_expires_at"] = float(expiry) if expiry is not None else None
        except (IndexError, ValueError, TypeError):
            live.extra["token_expires_at"] = None
        path = live.extra.get("token_file")
        if not path:
            folder = tempfile.mkdtemp(prefix="nbmcp-")        # mode 0700
            path = os.path.join(folder, "token")
            live.extra["token_file"] = path
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(token)

        # A SECOND token, for the one API the user's token can never call.
        #
        # `[RB-10]`: `postgres` is "always bound to the SP, not OBO", so `/api/2.0/postgres` refuses a
        # forwarded user token however many scopes the app declares. The tool server's Lakebase tools
        # therefore need the app's own identity, and they read it from this file. Written beside the
        # user token, same 0600 file, and only when this process HAS a service principal — on a laptop
        # there is none and the tools fall back to the user token as before.
        sp = getattr(self, "_sp_token", None)
        if sp is not None and sp.available():
            try:
                sp_path = os.path.join(os.path.dirname(path), "sp-token")
                fd = os.open(sp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "w") as fh:
                    fh.write(sp.get())
                live.extra["sp_token_file"] = sp_path
            except Exception as exc:      # noqa: BLE001 - the tools degrade to the user token, as on a laptop
                # Degrading is correct; degrading SILENTLY is not. A missing token file makes every
                # `/api/2.0/postgres` call answer 403, which reads as a permissions problem on the
                # user's project — three layers away from this line. `warning`, not `debug`, so the
                # app's own log answers "why is the Data tab refused" in one line.
                logging.getLogger("app.session").warning(
                    "no service-principal token for this session's tool server: %s", exc)
        elif sp is not None:
            logging.getLogger("app.session").debug(
                "this process has no service principal; Lakebase tools use the user token")

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
        await self._emit(Event(session_id, "session.checkpoint", {}))
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
        await self._emit(Event(sid, "session.ready", {
            "switched": True, "model": resolved.id.value, "wire": resolved.wire.value,
            "toolCount": live.tools, "agent": live.handle.capabilities.agent,
            "agentVersion": live.handle.capabilities.version,
            "capabilities": live.handle.capabilities.raw,
        }))

    async def archive(self, session_id: str) -> None:
        live = self._live.get(session_id)
        if not live or live.state.session.status is SessionStatus.ARCHIVED:
            return
        await self.cancel(session_id)
        if live.task and not live.task.done():
            with contextlib.suppress(asyncio.CancelledError):
                await live.task
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
        await self._emit(Event(session_id, "session.archived", {}))

    async def cancel(self, session_id: str) -> None:
        live = self.get(session_id)
        async with live.lock:
            # Stop means the entire accepted queue stops. It must not launch another write next.
            live.cancel = True
            live.extra["stopping"] = True
            for turn in list(live.state.turns):
                if turn.status is TurnStatus.QUEUED:
                    live.state.update(turn.finish(TurnStatus.CANCELLED))
                    await self._emit(turn_ended(session_id, turn.id, "cancelled"))
            for aid in list(live.extra.get("approvals", {})):
                del live.extra["approvals"][aid]
                await self._emit(approval_decided(session_id, None, aid, "cancelled", "user"))
            if live.handle:
                await self._rt.cancel(live.handle)
            if live.task and not live.task.done():
                try:
                    await asyncio.wait_for(asyncio.shield(live.task), 2)
                except TimeoutError:
                    live.task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await live.task
                    if live.handle:
                        live.extra["agent_session_id"] = live.handle.session_id
                        await self._rt.close(live.handle)
                        live.handle = None
                    for active in list(live.state.turns):
                        if active.status in (TurnStatus.RUNNING, TurnStatus.AUDITING):
                            live.state.update(active.finish(TurnStatus.CANCELLED))
                            await self._emit(turn_ended(session_id, active.id, "cancelled"))
                    live.state.session = updated(live.state.session, status=SessionStatus.BLOCKED, requires_resume=True)
                    await self._emit(Event(session_id, "session.recovery_required", {"requiresResume": True}))
            if not live.task or live.task.done():
                live.cancel = False
                live.extra["stopping"] = False

    async def record_document_saved(self, session_id: str, path: str, size: int, *, by: str) -> None:
        """Put a human write into the session's event stream (spec 003 WR-4).

        The transcript and the audit are one record: a save that happened in the editor has to be
        visible where a turn is visible, with who did it. The session must exist; a caller that
        already saved should not fail because recording did not — the route decides that.
        """
        self.get(session_id)          # KeyError if there is no such session
        await self._emit(document_saved(session_id, path, size, by=by))

    # -- turns ----------------------------------------------------------------
    async def submit(self, session_id: str, text: str, context: str = "",
                     attachments: list[dict] | None = None, user_token: str | None = None,
                     request_key: str = "", request_hash: str = "") -> Turn:
        live = self.get(session_id)
        async with live.lock:
            if request_key:
                previous = next((t for t in live.state.turns if t.request_key == request_key), None)
                if previous:
                    if previous.request_hash != request_hash:
                        raise DomainError("this retry key was already used for another message")
                    return previous
            return await self._submit(live, text, context, attachments, user_token, request_key, request_hash)

    async def _submit(self, live: Live, text: str, context: str, attachments, user_token,
                      request_key: str, request_hash: str) -> Turn:
        session_id = live.state.session.id
        if live.state.session.status is SessionStatus.ARCHIVED:
            raise DomainError("this session is archived")
        if live.state.session.requires_resume:
            raise DomainError("restore this session before sending a new message")
        if live.state.session.status not in (SessionStatus.READY, SessionStatus.STREAMING, SessionStatus.BLOCKED):
            raise DomainError("this session is not ready")
        if len(live.state.turns) >= MAX_TURNS:
            raise DomainError(f"this session reached its limit of {MAX_TURNS} turns")
        if live.extra.get("stopping"):
            raise DomainError("the agent is stopping; wait before sending another message")
        self._write_token(live, user_token)
        live.cancel = False
        running = live.state.running()
        asked = text
        text = DEMO_MARKER.sub(" ", text).strip()     # never store a demo hint as the user's words
        # A key pasted into a prompt is a user error the app must survive (S12/E-8): the stored
        # payload is redacted and labelled, and the turn continues.
        stored_text = redact_labelled(text)
        # The reference agent still needs the hint: it is how one demo server plays every behaviour.
        # It goes in `context`, which is sent but is not the user's words — stripping it from `prompt`
        # alone had quietly stopped the start cards from choosing (the "investigate a number" card
        # answered with a notebook).
        hint = DEMO_MARKER.search(asked) if self._demo else None
        turn = live.state.new_turn(
            stored_text,
            f"{context} {hint.group(0).strip()}" if hint else context,
            # References, not content: the transcript renders these chips on reload, and a blob is one id.
            [{"kind": a.get("kind", ""), "ref": a.get("ref", ""), "name": a.get("name", "")}
             for a in (attachments or [])],
        )
        turn = updated(turn, request_key=request_key, request_hash=request_hash,
                       context=redact_labelled(turn.context))
        live.state.update(turn)
        if not live.state.turns[:-1] and live.state.session.title == "New session":
            live.state.session = updated(live.state.session, title=title_from(stored_text))
        # The pin is written BEFORE the prompt and never updated (Axiom A5, C-8).
        await self._pin_turn(live, turn)
        # The accepted prompt, retry receipt, and queue entry are one commit before HTTP 202.
        try:
            await self._emit(turn_started(session_id, turn.id, stored_text, live.state.session.model, attachments))
        except Exception:
            live.state.turns.remove(turn)
            raise
        if running is not None:
            await self._emit(Event(session_id, "turn.queued", {}, turn_id=turn.id))
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

    async def _interrupt_pending(self, live: Live, reason: str) -> None:
        for queued in list(live.state.turns):
            if queued.status is TurnStatus.QUEUED:
                live.state.update(queued.finish(TurnStatus.INTERRUPTED, error=reason))
                await self._emit(turn_ended(live.state.session.id, queued.id, "interrupted", reason))

    async def _run_turn(self, live: Live, turn_id: str) -> None:
        if next(t for t in live.state.turns if t.id == turn_id).status is TurnStatus.CANCELLED:
            live.cancel = False
            live.extra["stopping"] = False
            return
        try:
            async with self._slots:
                expiry = live.extra.get("token_expires_at")
                budget = min(self._max_run_seconds, max(0, expiry - time.time() - 15)) if expiry else self._max_run_seconds
                async with asyncio.timeout(budget):
                    await self._execute_turn(live, turn_id)
        except TimeoutError:
            live.cancel = True
            if live.handle:
                await self._rt.close(live.handle)
                live.extra["agent_session_id"] = live.handle.session_id
                live.handle = None
            turn = next(t for t in live.state.turns if t.id == turn_id)
            live.state.update(turn.finish(TurnStatus.INTERRUPTED, error="The runtime or delegated credential limit was reached."))
            live.state.session = updated(live.state.session, status=SessionStatus.BLOCKED, requires_resume=True)
            await self._emit(turn_ended(live.state.session.id, turn_id, "interrupted", "The runtime or delegated credential limit was reached. Restore with a fresh sign-in and review progress before continuing."))
            await self._interrupt_pending(live, "Queued work was not started because the preceding turn was interrupted.")
            await self._emit(Event(live.state.session.id, "session.recovery_required", {"requiresResume": True}))
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.getLogger("app.runner").exception("session journal or worker failed; closing agent")
            if live.handle:
                live.extra["agent_session_id"] = live.handle.session_id
                await self._rt.close(live.handle)
                live.handle = None
            live.state.session = updated(live.state.session, status=SessionStatus.BLOCKED, requires_resume=True)

    async def _execute_turn(self, live: Live, turn_id: str) -> None:
        sid = live.state.session.id
        candidate = next(t for t in live.state.turns if t.id == turn_id)
        if candidate.status is TurnStatus.CANCELLED or live.state.session.status is SessionStatus.ARCHIVED:
            live.cancel = False
            live.extra["stopping"] = False
            return
        turn = live.state.claim(turn_id)
        live.state.session = live.state.session.transition(SessionStatus.STREAMING)
        self._rt.set_turn(sid, turn.id)
        live.state.calls.clear()  # evidence is scoped to THIS turn
        await self._emit(Event(sid, "turn.retrying", {}, turn_id=turn.id))
        started = time.time()
        parts: list[str] = []
        ended: dict = {"error": "no result"}
        usage: dict = {}
        try:
            # Bind the blobs to this turn BEFORE the prompt: refcount is what protects them from the
            # sweeper, and until this was called every attached blob had refcount 0 — so a transcript chip
            # would survive 24 hours and then point at bytes that no longer existed ([AFC-8], [BLB-3]).
            # It is also where a blob uploaded before a session existed adopts the session.
            await self._bind_blobs(live, turn)
            images = await self._images_for(live, turn)
            await self._rt.prompt_in_background(  # type: ignore[attr-defined]
                live.handle, turn.context + turn.prompt, images)
            ended, usage, new_text = await self._drain(live)
            parts.append(new_text)
            if live.cancel:
                ended = {"stop": "cancelled"}
        except Exception as exc:  # noqa: BLE001 - a runtime failure must not escape
            ended = {"error": str(exc)[:400]}
        await self._settle(live, turn, "".join(parts), ended, usage, time.time() - started)

    async def _bind_blobs(self, live: Live, turn) -> None:
        """Record that this turn references these blobs. Best-effort: never fail a turn over bookkeeping."""
        if self._blobs is None or not turn.attachments:
            return
        for att in turn.attachments:
            if att.get("kind") != "blob":
                continue
            ref = att.get("ref") or ""
            try:
                await self._blobs.store.mark_attached(
                    ref, turn.id, att.get("name") or "", live.state.session.id)
            except Exception:  # noqa: BLE001 - provenance must not block a turn
                pass

    async def _images_for(self, live: Live, turn) -> list[dict]:
        """The image attachments this turn carries, as ACP image blocks.

        Only images: everything else is already text in `render()`, and sending a CSV twice would double
        the prompt for no benefit. A blob that has gone missing is skipped here and was already reported to
        the model by `render()` as unavailable, so this adds nothing to say.
        """
        if self._blobs is None or not turn.attachments:
            return []
        out: list[dict] = []
        for att in turn.attachments:
            if att.get("kind") != "blob":
                continue
            try:
                row = await self._blobs.store.meta(att.get("ref", ""), live.state.session.user_id)
                if not str(row.mime).startswith("image/"):
                    continue
                raw = await self._blobs.store.bytes_for(att["ref"], live.state.session.user_id)
            except (LookupError, KeyError):
                continue
            out.append({
                "data": base64.b64encode(raw).decode(),
                "mimeType": row.mime,
                "name": att.get("name") or row.original_name,
            })
        return out

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
            if item.type == "approval.requested":
                live.extra.setdefault("approvals", {})[item.payload["approvalId"]] = item.payload
            await self._emit(item)
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
            live.extra["stopping"] = False
            self._finish(live, turn.finish(TurnStatus.CANCELLED))
            live.state.session = live.state.session.transition(SessionStatus.READY)
            await self._emit(turn_ended(sid, turn.id, "cancelled"))
            self._start_next(live)
            return
        if "error" in ended:
            await self._classify_failure(live, ended["error"], turn.id)
            self._finish(live, turn.finish(TurnStatus.FAILED, error=ended["error"][:400]))
            live.state.session = live.state.session.transition(SessionStatus.BLOCKED)
            if live.handle:
                live.extra["agent_session_id"] = live.handle.session_id
                await self._rt.close(live.handle)
                live.handle = None
            live.state.session = updated(live.state.session, requires_resume=True)
            await self._emit(turn_ended(sid, turn.id, "failed", ended["error"][:400]))
            await self._emit(Event(sid, "session.recovery_required", {"requiresResume": True}))
            await self._interrupt_pending(live, "Queued work was not started because the preceding turn failed.")
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
            await self._emit(turn_auditing(sid, turn.id, audits + 1, list(decision.missing)))
            await self._nudge(live, turn, decision.message, answer, continuations, audits + 1)
            return
        if decision.evidence:  # recorded once, with the outcome, never per audit pass
            await self._emit(evidence_proposed(sid, turn.id, list(decision.evidence)))
        if decision.verdict is supervisor.Verdict.DONE:
            self._finish(live, turn.finish(TurnStatus.COMPLETED, ended.get("stop", "end_turn"), usage))
            live.state.session = live.state.session.transition(SessionStatus.READY)
            # committed above, so _start_next sees no running turn
            await self._emit(
                turn_completed(sid, turn.id, ended.get("stop", "end_turn"), usage, seconds)
            )
            self._start_next(live)
            return
        self._finish(live, turn.finish(TurnStatus.BLOCKED, error=decision.message))
        attempted = [
            {"tool": c["name"], "status": c.get("status", ""), "summary": c.get("summary", "")}
            for c in live.state.calls.values()
        ][:8]
        live.state.session = live.state.session.transition(SessionStatus.BLOCKED)
        await self._emit(
            turn_blocked(sid, turn.id, decision.message, list(decision.missing), attempted)
        )
        await self._interrupt_pending(live, "Queued work was not started because the preceding turn needs attention.")

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
        if self._shutting_down or live.cancel or live.state.session.requires_resume or live.state.session.status is SessionStatus.ARCHIVED:
            return
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
        async with live.lock:
            pending = live.extra.get("approvals", {})
            request = pending.get(approval_id)
            if request is None or live.handle is None:
                raise DomainError("this approval expired or was already decided")
            # Match the selected option to the kind offered by the agent, server-side.
            offered = request.get("options", [])
            expected = {"allow_once": "allow_once", "allow_session": "allow_always"}.get(outcome)
            selected = next((o for o in offered if o.get("optionId") == option_id
                             and o.get("kind") == expected), None) if expected else None
            if outcome != "deny" and selected is None:
                raise DomainError("the selected permission option was not offered")
            del pending[approval_id]
            turn = live.state.running()
            await self._emit(approval_decided(session_id, turn.id if turn else None,
                                               approval_id, outcome, user_id))
            await self._rt.respond_permission(live.handle, approval_id,
                                               selected["optionId"] if selected else None)
