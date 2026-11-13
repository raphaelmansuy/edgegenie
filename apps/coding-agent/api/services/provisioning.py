"""Provisioning owns one part of the orchestrator lifecycle; it depends on domain values and ports."""

from __future__ import annotations

import base64
import json
import os
import tempfile

from ..domain.llm.agent_config import AgentConfig, session_rules
from ..domain.events import (
    Event,
    session_ready,
)
from ..domain.llm import ResolvedModel
from ..domain.redact import redact_labelled
from ..domain.session import (
    SessionStatus,
    Turn,
    updated,
)
from ..ports import SessionSpec


from .session_state import Live, TOOL_COUNT_CORE, FENCE_ENV


class Provisioning:
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
                {
                    "index": i + 1,
                    "turnId": pin["turnId"],
                    "model": pin["modelId"],
                    "provider": pin["providerId"],
                    "wire": pin["wire"],
                    "endpoint": pin["endpoint"],
                }
                for i, pin in enumerate(pins)
            ],
            "switchAtTurn": switch_turn,
        }

    async def _resolve(self, model: str, user_id: str, *, session_id: str) -> ResolvedModel:
        """One path from an id to a `ResolvedModel`. Falls back to a static resolution in demo mode."""
        if self._resolver is not None:
            resolved, _secret = await self._resolver.resolve(model, user_id=user_id, session_id=session_id)
            return resolved
        return self._static(model)

    def _static(self, model: str) -> ResolvedModel:
        """Demo and test mode: the seed row for this id, no credential, no database."""
        if self.static_resolve is None:
            raise RuntimeError("No static model resolver is configured")
        cfg = self.static_resolve(model, os.environ.get("DATABRICKS_HOST", ""))
        from ..domain.llm import Capability, ModelId
        from ..domain.llm.limits import Limits

        return ResolvedModel(
            id=ModelId.parse(model),
            provider=cfg.provider,
            wire=cfg.wire,
            endpoint=cfg.endpoint,
            base_url=cfg.base_url,
            limits=Limits(cfg.context, cfg.output),
            capability=Capability.TOOLS,
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
        cwd = live.agent_cwd or tempfile.mkdtemp(prefix=f"agent-{s.id[:8]}-", dir="/tmp")
        os.makedirs(cwd, exist_ok=True)
        live.agent_cwd = cwd
        live.workspace_folder = live.workspace_folder or s.folder

        if self.work and not self._demo:
            live.extra["workspace_preferences"] = await self.work.preferences.instructions(self.actor(s.id))
        # 1. The agent needs a provider config and its working rules, or it starts and never answers.
        #    The config names an environment VARIABLE; the value never touches the disk.
        try:
            self._write_config(live, cwd)
        except OSError:
            pass  # a read-only cwd is not fatal; the agent will report the failure

        # 2. The tool server, fenced to the workspace folder the user chose. It reads the user's
        #    token from a private file (not the agent's cwd) that every turn refreshes.
        if self.work:
            await self.work.prepare(s.id)
        user_token = live.extra.get("user_token") or os.environ.get("DATABRICKS_TOKEN", "")
        self._write_token(live, user_token, keep_in_app=bool(self.work))
        live.mcp_url = await self._tools.start(
            s.id, live.workspace_folder, s.schema, live.extra.get("token_file")
        )
        live.tools = (
            len(self.work.toolbox.catalogue(s.id)) if self.work else TOOL_COUNT_CORE if live.mcp_url else 0
        )

        # 3. The agent process itself. It authenticates as the USER, and it receives exactly one
        #    provider key: the selected one (S6).
        env = await self._child_env(live, user_token)
        # The folder the session may write to, so a reference agent's recorded file paths can name a
        # real one. `/Users/you/…` in a scenario is a placeholder; an agent that opened it 404'd and
        # filled the console with a failed request on every demo turn.
        if live.workspace_folder:
            env[FENCE_ENV] = live.workspace_folder
        spec = SessionSpec(
            session_id=s.id,
            cwd=cwd,
            model=s.model,
            mcp_url=live.mcp_url,
            env=env,
            agent_session_id=live.extra.get("agent_session_id", ""),
        )
        live.handle = await self._rt.start(spec)
        if self.work and self.work.sessions.mode(s.id) == "plan" and hasattr(self._rt, "set_mode"):
            await self._rt.set_mode(live.handle, "plan")
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
            session_ready(
                s.id,
                live.tools,
                live.handle.capabilities.agent,
                live.handle.capabilities.version,
                live.handle.capabilities.raw,
            )
        )

    def _write_config(self, live: Live, cwd: str) -> AgentConfig:
        """Write `opencode.json` + the working agreement for the resolved model."""
        resolved = live.resolved or self._static(live.state.session.model)
        cfg = AgentConfig.from_resolved(resolved, host=os.environ.get("DATABRICKS_HOST", ""))
        cfg.write(
            cwd,
            session_rules(live.workspace_folder, live.state.session.schema, live.state.session.id)
            + live.extra.get("workspace_preferences", ""),
            mode=self.work.sessions.mode(live.state.session.id) if self.work else None,
        )
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
            self._materialise(live, {})  # a switch away from a keyed provider drops its files
            return env
        if self._credentials is not None:
            child = await self._credentials.env_for(
                resolved,
                user_id=live.state.session.user_id,
                session_id=live.state.session.id,
                workspace_token=user_token,
            )
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
            for name in os.listdir(folder):  # drop the previous provider's files
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
    def _write_token(live: Live, token: str | None, *, keep_in_app: bool = False) -> None:
        """Keep the tool server's credential current. A forwarded user token lasts about an hour."""
        if not token:
            return
        live.extra["user_token"] = token
        try:
            segment = token.split(".")[1]
            expiry = json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))).get("exp")
            live.extra["token_expires_at"] = float(expiry) if expiry is not None else None
        except (IndexError, ValueError, TypeError):
            live.extra["token_expires_at"] = None
        if keep_in_app:
            return
        path = live.extra.get("token_file")
        if not path:
            folder = tempfile.mkdtemp(prefix="nbmcp-")  # mode 0700
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
        return {
            "current": live.state.session.model,
            "available": offered or allowed,
            "restartRequired": False,
        }

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
        restart = (
            current is None
            or current.provider is not resolved.provider
            or current.wire is not resolved.wire
        )
        if restart:
            if self.lazy_agents and live.handle is None:
                live.resolved = resolved
            else:
                await self._restart(live, resolved)
        else:
            agent_id = resolved.agent_id or resolved.endpoint
            if live.handle:
                try:
                    await self._rt.set_model(live.handle, agent_id)
                except Exception as exc:  # noqa: BLE001 - a refusal is a state, not a crash
                    from ..domain.llm import ProviderUnhealthy

                    raise ProviderUnhealthy(
                        f"the agent refused the switch: {redact_labelled(str(exc))[:300]}"
                    ) from exc
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
        env = await self._child_env(
            live, live.extra.get("user_token") or os.environ.get("DATABRICKS_TOKEN", "")
        )
        live.handle = await self._rt.start(
            SessionSpec(session_id=sid, cwd=cwd, model=resolved.id.value, mcp_url=live.mcp_url, env=env)
        )
        await self._emit(
            Event(
                sid,
                "session.ready",
                {
                    "switched": True,
                    "model": resolved.id.value,
                    "wire": resolved.wire.value,
                    "toolCount": live.tools,
                    "agent": live.handle.capabilities.agent,
                    "agentVersion": live.handle.capabilities.version,
                    "capabilities": live.handle.capabilities.raw,
                },
            )
        )

    async def _pin_turn(self, live: Live, turn: Turn) -> None:
        """Record which model this turn is about to use. Insert-once, so history is immutable."""
        if self._llm_store is None:
            return
        resolved = live.resolved or self._static(live.state.session.model)
        try:
            await self._llm_store.record_turn_model(
                {
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
                }
            )
        except Exception:  # noqa: BLE001 - recording provenance must not block a turn
            pass

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

        spec = None
        finder = self._llm_store
        if finder is not None:
            spec = await finder.find(resolved.id.value)
        if spec is None:
            return
        try:
            await self._health.note_turn(spec, error, turn_id=turn_id)
        except Exception:  # noqa: BLE001 - classification must never fail a turn
            pass
