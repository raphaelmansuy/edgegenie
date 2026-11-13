"""SessionService owns one part of the orchestrator lifecycle; it depends on domain values and ports."""

from __future__ import annotations

import asyncio
import logging
import contextlib
import dataclasses
import copy
import os
import shutil
import time
from typing import Any
from pathlib import Path
from uuid import uuid4

from ..domain.events import (
    Event,
    session_compacted,
    approval_decided,
    document_saved,
    session_created,
    session_ready,
    turn_ended,
)
from ..domain import compaction
from ..domain.redact import redact_value
from ..domain.scope import Scope, describe
from ..domain.session import (
    DomainError,
    Session,
    SessionState,
    SessionStatus,
    Turn,
    TurnStatus,
    updated,
)


from .session_state import Live


class SessionService:
    def _snapshot(self, live: Live) -> dict:
        # A whitelist: never serialize extra, a forwarded token, secret file, or provider key.
        return {
            "version": 1,
            "session": dataclasses.asdict(live.state.session),
            "turns": [dataclasses.asdict(t) for t in live.state.turns],
            "calls": copy.deepcopy(live.state.calls),
            "agentCwd": live.agent_cwd,
            "agentSessionId": live.handle.session_id
            if live.handle
            else live.extra.get("agent_session_id", ""),
            "lastSeen": live.last_seen,
            "questions": copy.deepcopy(live.extra.get("questions", {})),
            "approvals": copy.deepcopy(live.extra.get("approvals", {})),
        }

    async def _emit(self, event: Event) -> Event:
        if self.journal_writer:
            return await self.journal_writer.emit(event)
        return await self._commit_event(event)

    async def _commit_event(self, event: Event, snapshot=True) -> Event:
        live = self.get(event.session_id)
        safe = dataclasses.replace(event, payload=redact_value(event.payload))
        saved = redact_value(self._snapshot(live)) if snapshot else None
        if snapshot and self.work:
            return await self.work.commit_transition(self._store, safe, saved, live.state)
        return await self._store.commit(safe, saved)

    async def restore(self) -> None:
        """Restore committed state, never replay a potentially non-idempotent tool operation."""
        if self.lazy_agents:
            return
        for row in await self._store.snapshots():
            await self._restore_row(row)

    def loaded(self, sid):
        return sid in self._live

    async def ensure_owned(self, sid, user):
        async with self._hydrate_locks.setdefault(sid, asyncio.Lock()):
            if sid not in self._live:
                row = await self._store.snapshot(sid)
                if row.get("session", {}).get("user_id") != user:
                    raise KeyError(sid)
                await self._restore_row(row, lazy=True)
            return self.owned(sid, user)

    async def _restore_row(self, row, *, lazy=False):
        if not row:
            return
        if row.get("version") != 1:
            raise RuntimeError("unsupported session snapshot version")
        s = Session(**{**row["session"], "status": SessionStatus(row["session"]["status"])})
        turns = [Turn(**{**t, "status": TurnStatus(t["status"])}) for t in row["turns"]]
        live = Live(
            SessionState(s, turns, row.get("calls", {})),
            workspace_folder=s.folder,
            agent_cwd=row.get("agentCwd", ""),
            last_seen=row.get("lastSeen", 0),
        )
        live.extra["agent_session_id"] = row.get("agentSessionId", "")
        self._live[s.id] = live
        if s.status is SessionStatus.ARCHIVED:
            return
        for qid, question in row.get("questions", {}).items():
            live.extra.setdefault("questions", {})[qid] = {**question, "state": "expired"}
            await self._emit(Event(s.id, "question.decided", {"id": qid, "state": "expired"}))
        if lazy and not any(
            t.status in (TurnStatus.RUNNING, TurnStatus.AUDITING, TurnStatus.QUEUED) for t in turns
        ):
            return
        # Permissions belong to the dead transport. They must be requested afresh after load.
        for aid in row.get("approvals", {}):
            await self._emit(approval_decided(s.id, None, aid, "expired", "server"))
        interrupted = []
        for t in turns:
            if t.status in (TurnStatus.RUNNING, TurnStatus.AUDITING, TurnStatus.QUEUED):
                live.state.update(
                    t.finish(
                        TurnStatus.INTERRUPTED,
                        error="Server restarted; review saved progress before continuing.",
                    )
                )
                interrupted.append(t)
        live.state.session = updated(s, status=SessionStatus.BLOCKED, requires_resume=True)
        for t in interrupted:
            await self._emit(
                turn_ended(
                    s.id,
                    t.id,
                    "interrupted",
                    "Server restarted. Saved progress is available; no operation was automatically repeated.",
                )
            )
        await self._emit(Event(s.id, "session.recovery_required", {"requiresResume": True}))

    async def shutdown(self) -> None:
        self._shutting_down = True
        if self.journal_writer:
            await self.journal_writer.close()
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
                    shutil.rmtree(
                        os.path.dirname(path) if key == "token_file" else path, ignore_errors=True
                    )

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
            live.resolved = await self._resolve(
                live.state.session.model, live.state.session.user_id, session_id=session_id
            )
            live.state.session = updated(live.state.session, status=SessionStatus.PROVISIONING)
            try:
                await self._provision(live)
            except Exception:
                live.state.session = updated(
                    live.state.session, status=SessionStatus.BLOCKED, requires_resume=True
                )
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

    def get(self, session_id: str) -> Live:
        try:
            return self._live[session_id]
        except KeyError:
            raise KeyError(session_id) from None

    def owned(self, session_id: str, user_id: str) -> Live:
        live = self.get(session_id)
        if live.state.session.user_id != user_id:
            raise KeyError(session_id)
        return live

    def sessions_for(self, user_id: str) -> list[Session]:
        """The user's conversations, newest first. An archived one is the user's "delete": it stays in
        memory for the audit trail but is no longer something to list, or the delete control would
        succeed and the row would still be there."""
        return sorted(
            (
                live.state.session
                for live in self._live.values()
                if live.state.session.user_id == user_id
                and live.state.session.status is not SessionStatus.ARCHIVED
            ),
            key=lambda s: s.id,
            reverse=True,
        )

    def activity(self, session_id: str) -> dict:
        live = self.get(session_id)
        last = live.state.turns[-1] if live.state.turns else None
        approvals = live.extra.get("approvals", {})
        return {
            "persistence": "durable" if self._store.durable else "memory",
            "state": "needs_attention"
            if live.state.session.requires_resume
            else "waiting_for_approval"
            if approvals
            else "running"
            if live.state.running()
            else last.status.value
            if last
            else "ready",
            "queued": sum(t.status is TurnStatus.QUEUED for t in live.state.turns),
            "pendingApprovals": len(approvals),
            "maxRunSeconds": self._max_run_seconds,
        }

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
            Candidate(
                session_id=sid,
                status=live.state.session.status.value,
                last_seen=live.last_seen or 0.0,
                watchers=self.watchers(sid),
                turns=len(live.state.turns),
            )
            for sid, live in self._live.items()
        ]

    async def reap_idle(self, now: float | None = None, policy=None) -> list[str]:
        """Archive sessions the policy says are finished with. Returns the ids reaped.

        This is what calls `archive()`. It existed but was never called, so every session a user
        opened held a subprocess for the life of the server.

        `policy` is injectable for the same reason `reapable` takes one: the default keeps eight
        sessions, so a test with one session can never reap anything and a test of "does reaping
        work" passes while reaping nothing.

        **The decision is re-checked under the session's lock.** `idle_candidates` reads a snapshot,
        and everything after it awaits: a `submit` that lands in that gap would start a turn on a
        session this pass has already decided to tear down, and the teardown would cancel it. So the
        lock a submission takes is the lock a reap takes, and the candidate is re-read inside it. A
        session that became busy in the gap is skipped rather than archived.
        """
        from ..domain.reaper import Policy, reapable
        now = now if now is not None else time.time()
        policy = policy or Policy()
        reaped: list[str] = []
        # The cap counts sessions still *open*, and archiving one must reduce that count — otherwise
        # a single pass reaps everything: the guard `live_count > keep_minimum` stayed true for every
        # candidate because nothing decremented it. Observed live with keep_minimum=2: all 8 archived.
        open_now = sum(1 for c in self.idle_candidates(now) if c.status != "archived")
        for candidate in self.idle_candidates(now):
            if reapable(candidate, now=now, live_count=open_now, policy=policy) is not None:
                continue
            live = self._live.get(candidate.session_id)
            if live is None:
                continue
            async with live.lock:
                # Re-read inside the lock: this is the re-check the docstring promises.
                if live.state.running() is not None or self.watchers(candidate.session_id):
                    continue
                if live.state.session.status is SessionStatus.ARCHIVED:
                    continue
                if self._store.durable:
                    if live.state.session.requires_resume:
                        continue
                    if live.handle:
                        live.extra["agent_session_id"] = live.handle.session_id
                        await self._rt.close(live.handle)
                        live.handle = None
                    await self._tools.stop(candidate.session_id)
                    live.state.session = updated(live.state.session, requires_resume=True)
                    await self._emit(Event(candidate.session_id, "session.recovery_required",
                                           {"requiresResume": True}))
                else:
                    await self.archive(candidate.session_id)
            reaped.append(candidate.session_id)
            open_now -= 1
        return reaped

    def scope(self, session_id: str) -> Scope:
        s = self.get(session_id).state.session
        return Scope.for_session(s.id, s.folder, s.schema)

    def scope_description(self, session_id: str) -> dict:
        return describe(self.scope(session_id))

    async def create(
        self,
        user_id: str,
        folder: str,
        model: str,
        schema: str | None,
        title: str = "New session",
        user_token: str | None = None,
        write_mode: str = "fenced",
        principal: str = "",
    ) -> Session:
        resolved = await self._resolve(model, user_id, session_id="")
        sid = uuid4().hex[:16]
        session = Session(
            id=sid,
            user_id=user_id,
            folder=folder,
            schema=schema,
            model=resolved.id.value,
            title=title,
            created_at=time.time(),
            write_mode=write_mode,
        )
        live = Live(
            state=SessionState(session=session),
            workspace_folder=folder,
            last_seen=time.time(),
            resolved=resolved,
        )
        # The user's forwarded token: the agent and the tool server act as this user, not as the app.
        live.extra["user_token"] = user_token
        live.extra["principal"] = principal or user_id
        self._live[sid] = live
        try:
            await self._emit(session_created(sid, folder, resolved.id.value, schema))
        except BaseException:
            self._live.pop(sid, None)
            raise
        try:
            if self.work:
                settings = await self.work.prepare(sid)
                live.state.session = updated(live.state.session, mode=settings["mode"])
            if self.lazy_agents:
                live.state.session = live.state.session.transition(SessionStatus.READY)
                await self._emit(session_ready(sid, 0, "", "", {}))
            else:
                await self._provision(live)
        except Exception as exc:  # noqa: BLE001 - a failed provision is a visible state, not a crash
            await self._release(live)
            with contextlib.suppress(DomainError):
                live.state.session = live.state.session.transition(SessionStatus.FAILED)
            try:
                await self._emit(Event(sid, "session.degraded", {"detail": str(exc)[:400]}))
            except Exception:
                logging.getLogger("app.session").warning("Could not journal provisioning failure", exc_info=True)
            raise
        return live.state.session

    async def archive(self, session_id: str) -> None:
        live = self._live.get(session_id)
        if not live or live.state.session.status is SessionStatus.ARCHIVED:
            return
        if self.work:
            await self.work.expire(session_id)
        await self.cancel(session_id)
        if live.task and not live.task.done():
            with contextlib.suppress(asyncio.CancelledError):
                await live.task
        live.state.session = live.state.session.transition(SessionStatus.ARCHIVED)
        live.cancel = True  # a provision still in flight must not finish
        if live.handle:
            await self._rt.close(live.handle)
        await self._tools.stop(session_id)
        token_file = live.extra.get("token_file")
        if token_file:  # only ever our own mkdtemp folder; never derive a path from nothing
            shutil.rmtree(os.path.dirname(token_file), ignore_errors=True)
        secret_dir = live.extra.get("secret_dir")
        if secret_dir:  # the provider key files; same rule: only our own mkdtemp folder
            shutil.rmtree(secret_dir, ignore_errors=True)
        if self._blobs is not None and not self.work:
            await self._blobs.store.delete_session(session_id)
        await self._emit(Event(session_id, "session.archived", {}))
        if self.lazy_agents and not self.watchers(session_id):
            self._live.pop(session_id, None)

    async def record_document_saved(self, session_id: str, path: str, size: int, *, by: str) -> None:
        """Put a human write into the session's event stream (spec 003 WR-4).

        The transcript and the audit are one record: a save that happened in the editor has to be
        visible where a turn is visible, with who did it. The session must exist; a caller that
        already saved should not fail because recording did not — the route decides that.
        """
        self.get(session_id)  # KeyError if there is no such session
        await self._emit(document_saved(session_id, path, size, by=by))

    async def storage_report(self, sid):
        self.get(sid)
        journal = await self._store.storage(sid)
        ledgers = await self.work.store.storage(sid) if self.work else {}
        return {
            "sessionId": sid,
            "journal": journal,
            "ledgers": ledgers,
            "unit": "bytes",
            "measurement": "Serialized payload bytes, including ledger encryption envelopes; excludes indexes, database pages, blobs and native agent history.",
            "undoRetentionDays": 30,
        }

    async def purge_session(self, sid, *, erase_blobs=None):
        from ..domain.asset import WorkError
        from pathlib import Path

        live = self.get(sid)
        async with live.lock:
            if live.state.session.status is not SessionStatus.ARCHIVED:
                raise WorkError("Archive this session before deleting its history.")
            if self.watchers(sid):
                raise WorkError("Close this session's event streams before deleting history.")

            async def erase_local():
                if live.agent_cwd:
                    path = Path(live.agent_cwd)
                    if (
                        path.is_symlink()
                        or path.resolve().parent != Path("/tmp").resolve()
                        or not path.name.startswith(f"agent-{sid[:8]}-")
                    ):
                        raise WorkError("The native agent history path needs operator review before purge.")
                    if path.exists():
                        shutil.rmtree(path, ignore_errors=False)
                if erase_blobs:
                    await erase_blobs(sid)

            if self.work:
                await self.work.purge_session(self._store, sid, erase_local=erase_local)
            else:
                await erase_local()
                await self._store.purge_session(sid)
            self._live.pop(sid, None)
            self._hydrate_locks.pop(sid, None)

    async def _release(self, live: Live) -> None:
        """Give back a session's processes and private files. Best effort, and safe to call twice."""
        sid = live.state.session.id
        log = logging.getLogger("app.session")
        if live.handle:
            handle, live.handle = live.handle, None
            try:
                await self._rt.close(handle)
            except Exception:  # noqa: BLE001
                log.warning("could not close the agent of session %s", sid, exc_info=True)
        try:
            await self._tools.stop(sid)
        except Exception:  # noqa: BLE001
            log.warning("could not stop the tool server of session %s", sid, exc_info=True)
        for key in ("token_file", "secret_dir"):
            path = live.extra.pop(key, "")
            if path:
                shutil.rmtree(os.path.dirname(path) if key == "token_file" else path, ignore_errors=True)

    def projection_candidates(self) -> list:
        """The in-memory projections, with the fields the eviction policy needs.

        Separate from `idle_candidates` because the two ask different questions of different sets:
        the reaper considers *open* sessions and decides whether to stop their processes, while
        eviction considers *archived* ones and decides whether their projection may leave memory.
        """
        from ..domain.projection import Candidate as ProjectionCandidate
        return [
            ProjectionCandidate(
                session_id=sid,
                status=live.state.session.status.value,
                last_seen=live.last_seen or 0.0,
                watchers=self.watchers(sid),
                busy=live.state.running() is not None or (live.task is not None and not live.task.done()),
            )
            for sid, live in self._live.items()
        ]

    def evict_archived(self, now: float | None = None, *, grace_seconds: float | None = None) -> list[str]:
        """Drop archived projections from memory. The journal is untouched.

        Nothing used to remove an entry from `_live`, so a long-lived server grew by one conversation's
        worth of memory per conversation. This is the fix, and it is deliberately *not* a size cap: a
        cap would delete a projection a request is about to read and make behaviour depend on how many
        sessions happened to be open. `domain/projection.py` holds the rule; this only obeys it.

        Evicting is a cache miss, never data loss: `agent.session_snapshot` and `agent.session_event`
        stay, and `restore()` rebuilds the projection on the next boot.
        """
        from ..domain.projection import evictable
        now = now if now is not None else time.time()
        kwargs = {} if grace_seconds is None else {"grace_seconds": grace_seconds}
        gone: list[str] = []
        for sid in evictable(self.projection_candidates(), now=now, **kwargs):
            live = self._live.get(sid)
            if live is None:
                continue
            # A last look under the door: a stream could have connected since the snapshot.
            if self.watchers(sid) or (live.task is not None and not live.task.done()):
                continue
            self._live.pop(sid, None)
            gone.append(sid)
        return gone

    async def record_blob_attached(self, session_id: str, _name: str, payload: dict) -> None:
        """Put an attachment into the session's event stream.

        `blob.attached` was in the event vocabulary and emitted by nobody: `BlobService` takes an
        `emit` callback and `build()` constructed it without one, so an attachment left a row and a
        file and no record. A transcript could show a chip whose provenance the journal never had.

        A blob uploaded before its session exists lives under `pending:<user>` and has no session to
        record against — `get` raises `KeyError` and the caller logs it. Its event belongs to the turn
        that adopts it, which is where the chip appears.
        """
        self.get(session_id)          # KeyError when this blob has no session yet
        await self._emit(Event(session_id, "blob.attached", dict(payload)))

    async def record_sql_change(self, session_id: str, turn_id: str, draft_id: str,
                                version: int, run_id: str = "") -> None:
        await self._emit(Event(session_id, "sql.changed", {
            "draftId": draft_id, "version": version, "runId": run_id,
        }, turn_id=turn_id, actor="app"))

    def attach_sql(self, service, workspace: str) -> None:
        self._sql_service, self._sql_workspace = service, workspace

    async def _cancel_agent_sql(self, live: Live) -> None:
        service = getattr(self, "_sql_service", None)
        if service is None:
            return
        from ..domain.sqlquery import SqlActor

        try:
            path = live.extra.get("token_file")
            token = Path(path).read_text().strip() if path else None
        except OSError:
            token = None
        actor = SqlActor(self._sql_workspace, live.state.session.user_id, token)
        async def cancel_one(run_id):
            try:
                row = await service.observe(actor, run_id, cancel=True)
                await self.record_sql_change(live.state.session.id, "", row["sourceRef"], 0, run_id)
            except Exception as exc:
                # Cancellation intent is recorded before contacting the provider; status can reconcile it.
                logging.getLogger("app.sql").warning("agent SQL cancellation needs reconciliation: %s", type(exc).__name__)
        try:
            await asyncio.wait_for(asyncio.gather(*(cancel_one(r) for r in live.extra.get("sql_runs", set()))), 6)
        except TimeoutError:
            logging.getLogger("app.sql").warning("agent SQL cancellation is still pending")


    async def compact(self, session_id: str, *, budget: int = 0, summary: str = "") -> dict:
        """Summarise the middle of a conversation when it outgrows the window. `[R-11]`, `[F-10]`.

        The PLAN is pure (`domain/compaction.py`); this only records it. `session.compacted` was one of
        the 27 declared event types and emitted by nobody, so a long conversation had no way to shed
        history — and at the window boundary the provider truncated, after which the supervisor reported
        "requirements without verified evidence" for work that had been done.

        `budget` is the context window minus what the next turn needs. `0` means "the model's declared
        context", which is what a caller with no better number should pass.
        """
        live = self.get(session_id)
        turns = [compaction.Turn(t.id, t.index, (t.input_tokens or 0) + (t.output_tokens or 0))
                 for t in live.state.turns]
        window = budget or (live.resolved.context if live.resolved else 0)
        plan = compaction.plan(turns, budget=window)
        if plan is None:
            return {"changed": False, "reason": "nothing needs shedding"}
        await self._emit(session_compacted(session_id, plan.to_event(), summary=summary))
        # The record is the deliverable: the summary text itself is produced by the caller (a model call)
        # and stored as a projection field by the API that owns the transcript. Recording first means a
        # compaction is never silent, even if the summariser fails afterwards.
        live.extra["compacted"] = plan.to_event()
        return {"changed": True, **plan.to_event()}
