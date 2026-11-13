"""Python sessions: start one, send it cells, watch it, stop it. Owns the handles; knows no HTTP and no SDK.

A session is a serverless job that stays running (`domain/kernel_runtime.py`) and is driven through files
in a store (a Unity Catalog volume). This service is the app's half of that conversation:

  * a command is a numbered file; the answer is a numbered file; both survive a restart of either side;
  * "is it alive" is judged from counters the kernel writes, by THIS machine's clock, never by comparing
    two machines' clocks;
  * the app holds a lease on the session and renews it while a notebook is open. If the app is gone the
    lease runs out and the kernel ends itself, so nothing keeps billing for a tab nobody has open;
  * every command ends with a result. A session that dies mid-cell gives that cell a sentence saying so
    (and that the variables are gone), never a spinner that does not stop.

One session per user and notebook. A handle belongs to whoever started it: another user's handle is "not
found", so a guessed id reveals nothing. A cell that cannot be sent to a session at all (no volume, no
quota, switched off) raises `Unavailable` with the reason; the caller falls back to a one-shot run.
"""
from __future__ import annotations

import dataclasses
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from ..domain import kernel, kernel_runtime
from ..domain.cellrun import RunResult, RunState

#: How often the app renews its hold on a session. The kernel gives up after `lease_seconds` of silence,
#: so one missed renewal (or five) is harmless.
LEASE_RENEW_SECONDS = 30.0
#: How often the heartbeat file is read while waiting for something else (reading costs a request).
BEAT_READ_SECONDS = 3.0
#: How often the platform is asked whether the job is still running.
JOB_CHECK_SECONDS = 10.0
#: An ended session's files are kept this long so a slow poll still gets its answer.
KEEP_SECONDS = 600.0
#: After Stop, the job is cancelled if the kernel has not ended by itself in this long.
STOP_GRACE_SECONDS = 20.0

_JOB_ENDED = {"TERMINATED", "INTERNAL_ERROR", "SKIPPED"}


class Unavailable(Exception):
    """A session cannot be used right now. The message is for the person, in words they can act on."""


#: Turns `%run <ref>` written in the notebook at `key` into the command that carries its cells, or a refusal.
Expander = Callable[[str, str], Awaitable["kernel.Command | kernel.Refusal"]]


class Store(Protocol):
    async def put(self, path: str, doc: dict[str, Any]) -> None: ...
    async def get(self, path: str) -> dict[str, Any] | None: ...
    async def delete_tree(self, root: str) -> None: ...


class Runner(Protocol):
    async def submit(self, name: str, source: str, *, timeout_seconds: int | None = None) -> tuple[int, str]: ...
    async def info(self, run_id: int) -> Any: ...
    async def output(self, task_run_id: int | None) -> tuple[str | None, str]: ...
    async def cancel(self, run_id: int) -> None: ...
    async def discard(self, path: str) -> None: ...


@dataclass(frozen=True, slots=True)
class Policy:
    """What the app allows. Every number is a cost control or a safety margin."""

    volume: str = "/Volumes/workspace/agent_scratch/kernel_sessions"
    idle_seconds: float = kernel.DEFAULT_IDLE_SECONDS
    lease_seconds: float = kernel.DEFAULT_LEASE_SECONDS
    max_per_user: int = 2
    max_total: int = 3
    max_session_seconds: int = kernel.MAX_SESSION_SECONDS
    interrupt_grace: float = kernel.INTERRUPT_GRACE_SECONDS
    heartbeat_stale: float = kernel.HEARTBEAT_STALE_SECONDS
    start_timeout: float = kernel.START_TIMEOUT_SECONDS


@dataclass
class _Session:
    id: str
    owner: str
    key: str                      # the notebook it belongs to
    root: str
    run_id: int
    nb_path: str
    started: float
    state: str = "starting"       # starting | ready | stopping | ended
    seq: int = 0                  # the last command sent
    beat: int = -1
    beat_changed: float = 0.0
    beat_read: float = 0.0
    job_checked: float = 0.0
    lease_n: int = 0
    lease_sent: float = 0.0
    reason: str = ""              # why it ended, in words
    ended_at: float = 0.0
    stop_asked: float = 0.0
    cleaned: bool = False


@dataclass
class _Cmd:
    session: _Session
    owner: str
    seq: int
    command_id: str
    started: float
    interrupt_asked: float = 0.0
    done: RunResult | None = None
    stamped: bool = False


def _wall_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class KernelSessions:
    def __init__(self, runner: Runner, store: Store, policy: Policy | None = None, *,
                 clock=time.monotonic, wall=_wall_now) -> None:
        self._runner = runner
        self._store = store
        self.policy = policy or Policy()
        self._now = clock
        self._wall = wall
        self._sessions: dict[str, _Session] = {}
        self._by_key: dict[tuple[str, str], str] = {}
        self._cmds: dict[str, _Cmd] = {}
        self._lost: dict[tuple[str, str], str] = {}   # why the last session for a notebook ended

    # -- who has what -----------------------------------------------------------------------

    def _live(self, owner: str | None = None) -> list[_Session]:
        return [s for s in self._sessions.values() if s.state != "ended" and (owner is None or s.owner == owner)]

    def _current(self, owner: str, key: str) -> _Session | None:
        sid = self._by_key.get((owner, key))
        s = self._sessions.get(sid) if sid else None
        return s if s is not None and s.state in {"starting", "ready"} else None

    def _path(self, s: _Session, *parts: str) -> str:
        return "/".join((s.root, *parts))

    # -- starting ---------------------------------------------------------------------------

    async def _ensure(self, owner: str, key: str) -> tuple[_Session, str]:
        """The live session for this notebook, starting one if there is none. Also: why the previous one
        is gone, when this one replaces it ("" for a first session)."""
        await self._reap()
        s = self._current(owner, key)
        if s is not None:
            return s, ""
        replaced = self._lost.pop((owner, key), "")
        if len(self._live(owner)) >= self.policy.max_per_user:
            raise Unavailable(f"you already have {self.policy.max_per_user} Python sessions running. Stop one "
                              "from its notebook, or wait for an idle one to end.")
        if len(self._live()) >= self.policy.max_total:
            raise Unavailable("the app is already running as many Python sessions as it allows. Try again in a "
                              "few minutes, or run the cell as a one-shot run.")
        sid = secrets.token_urlsafe(9).replace("-", "a").replace("_", "b")
        root = f"{self.policy.volume.rstrip('/')}/{sid}"
        session = _Session(id=sid, owner=owner, key=key, root=root, run_id=0, nb_path="", started=self._now())
        # Writing the lease first proves the store is writable BEFORE compute is started and billed.
        try:
            await self._store.put(self._path(session, "ctl", "lease.json"), {"n": 0})
        except Exception as exc:  # noqa: BLE001 - any store failure means no session, and the reason is the point
            raise Unavailable(f"the session store could not be written ({_short(exc)}). The app's service "
                              f"principal needs read and write on {self.policy.volume}.") from exc
        session.lease_sent = self._now()
        source = kernel.kernel_notebook(root, sid, idle_seconds=self.policy.idle_seconds,
                                        lease_seconds=self.policy.lease_seconds)
        try:
            session.run_id, session.nb_path = await self._runner.submit(
                f"session_{sid}", source, timeout_seconds=self.policy.max_session_seconds)
        except Exception as exc:  # noqa: BLE001
            await self._cleanup(session)
            raise Unavailable(f"serverless compute could not be started for a session ({_short(exc)})") from exc
        self._sessions[sid] = session
        self._by_key[(owner, key)] = sid
        return session, replaced

    # -- running a cell ---------------------------------------------------------------------

    async def run(self, owner: str, key: str, language: str, source: str, *,
                  index: int | None = None, expand: Expander | None = None,
                  widgets: dict[str, str] | None = None) -> dict[str, Any]:
        """Send one cell. Returns a handle, or the cell's refusal.

        `%run` is expanded by the caller (`expand`), before any compute is used, because reading the other
        notebook needs the user's token and the service does not have it.
        """
        verdict = kernel.classify(language, source)
        if isinstance(verdict, kernel.Command) and verdict.kind == "run":
            verdict = await expand(key, verdict.source) if expand else kernel.Refusal(
                "%run is not available here")
        if isinstance(verdict, kernel.Refusal):
            return {"refused": RunResult(state=RunState.REFUSED, error=verdict.why).to_dict()}
        session, replaced = await self._ensure(owner, key)
        await self._renew(session)
        seq = session.seq + 1
        command_id = secrets.token_hex(6)
        try:
            await self._store.put(self._path(session, "cmd", kernel_runtime.seq_name(seq)),
                                  kernel.command_doc(seq, command_id, verdict, index=index, widgets=widgets))
        except Exception as exc:  # noqa: BLE001
            raise Unavailable(f"the cell could not be sent to the session ({_short(exc)})") from exc
        session.seq = seq
        token = secrets.token_urlsafe(12)
        self._cmds[token] = _Cmd(session=session, owner=owner, seq=seq, command_id=command_id, started=self._now())
        out: dict[str, Any] = {"handle": token, "session": self._describe(session)}
        if replaced:
            out["replaced"] = replaced
        return out

    def _own(self, owner: str, token: str) -> _Cmd:
        c = self._cmds.get(token)
        if c is None or c.owner != owner:
            raise LookupError("this run is no longer known to the app (it restarted, or the result expired); "
                              "run the cell again")
        return c

    async def poll(self, owner: str, token: str) -> dict[str, Any]:
        c = self._own(owner, token)
        s = c.session
        seconds = round(self._now() - c.started, 2)
        if c.done is None:
            await self._renew(s)
            progress = await self._read_out(s, c)
            if progress is not None and progress.final and progress.result is not None:
                c.done = progress.result
            else:
                await self._check_alive(s)
                if progress is not None and not progress.final:
                    self._saw_beat(s, progress.beat)
                if c.interrupt_asked and self._now() - c.interrupt_asked > self.policy.interrupt_grace \
                        and s.state != "ended":
                    await self._end(s, "the cell did not stop when asked, so the session was ended. "
                                       "Variables from earlier cells are gone.", cancel=True)
                if s.state == "ended":
                    # One last look: the result may have been written just before the end was noticed.
                    last = await self._read_out(s, c)
                    c.done = last.result if last and last.final and last.result else self._ended_result(c, seconds)
                else:
                    stage = ("starting serverless compute" if s.state == "starting"
                             else "running your cell" if progress is not None else "waiting for the session")
                    return {"state": "running", "seconds": seconds, "stage": stage,
                            "outputs": progress.outputs if progress is not None else [],
                            "session": self._describe(s)}
        if not c.stamped:
            c.done = dataclasses.replace(c.done, finished_at=self._wall(), ran_by=c.owner)
            c.stamped = True
        return {"state": "done", "seconds": seconds, "result": c.done.to_dict(), "session": self._describe(s)}

    async def _read_out(self, s: _Session, c: _Cmd):
        try:
            doc = await self._store.get(self._path(s, "out", kernel_runtime.seq_name(c.seq)))
        except Exception:  # noqa: BLE001 - a failed read is "not yet"; liveness decides whether that is fatal
            return None
        return kernel.read_out(doc, command_id=c.command_id) if doc is not None else None

    def _ended_result(self, c: _Cmd, seconds: float) -> RunResult:
        why = c.session.reason or "the session ended"
        return RunResult(state=RunState.FAILED, seconds=seconds, warehouse=kernel.WHERE,
                         error=f"{why[0].upper()}{why[1:]}. This cell did not finish, and variables from earlier "
                               "cells are gone: run them again.")

    # -- watching the session ---------------------------------------------------------------

    def _saw_beat(self, s: _Session, beat: int) -> None:
        if beat != s.beat:
            s.beat = beat
            s.beat_changed = self._now()
            if s.state == "starting":
                s.state = "ready"

    async def _check_alive(self, s: _Session) -> None:
        """Decide whether the session is alive, from the heartbeat counter and the platform's own word."""
        if s.state in {"ended"}:
            return
        now = self._now()
        if now - s.beat_read >= BEAT_READ_SECONDS:
            s.beat_read = now
            try:
                hb = await self._store.get(self._path(s, "hb.json"))
            except Exception:  # noqa: BLE001
                hb = None
            if isinstance(hb, dict) and hb.get("protocol") == kernel_runtime.PROTOCOL:
                if hb.get("state") == "ended":
                    why = kernel_runtime.ENDED.get(str(hb.get("reason")), "the session ended")
                    await self._end(s, why)
                    return
                if isinstance(hb.get("n"), int):
                    self._saw_beat(s, hb["n"])
        if s.state == "starting":
            if now - s.started > self.policy.start_timeout:
                await self._end(s, f"the session did not start in {int(self.policy.start_timeout // 60)} minutes",
                                cancel=True)
                return
        elif s.beat_changed and now - s.beat_changed > self.policy.heartbeat_stale:
            await self._end(s, "the session stopped responding", cancel=True)
            return
        if now - s.job_checked >= JOB_CHECK_SECONDS:
            s.job_checked = now
            try:
                info = await self._runner.info(s.run_id)
            except Exception:  # noqa: BLE001
                return
            if (info.life_cycle or "").upper() in _JOB_ENDED:
                detail = (info.message or "").strip()
                why = "the session's compute stopped" + (f": {detail[:300]}" if detail else "")
                await self._end(s, why)

    async def _end(self, s: _Session, why: str, *, cancel: bool = False) -> None:
        if s.state == "ended":
            return
        s.state, s.reason, s.ended_at = "ended", why, self._now()
        self._lost[(s.owner, s.key)] = why
        if cancel:
            try:
                await self._runner.cancel(s.run_id)
            except Exception:  # noqa: BLE001 - the lease ends it anyway
                pass
        try:
            await self._runner.discard(s.nb_path)
        except Exception:  # noqa: BLE001
            pass

    async def _renew(self, s: _Session) -> None:
        now = self._now()
        if s.state == "ended" or now - s.lease_sent < LEASE_RENEW_SECONDS:
            return
        s.lease_n += 1
        s.lease_sent = now
        try:
            await self._store.put(self._path(s, "ctl", "lease.json"), {"n": s.lease_n})
        except Exception:  # noqa: BLE001 - the next call tries again; the kernel tolerates misses
            pass

    async def _reap(self) -> None:
        """Housekeeping on each call: finish stopping, and delete the files of sessions long over."""
        now = self._now()
        for s in list(self._sessions.values()):
            if s.state == "stopping":
                if now - s.stop_asked > STOP_GRACE_SECONDS:
                    await self._end(s, s.reason or "the session was stopped", cancel=True)
                else:
                    await self._check_alive(s)
            elif s.state == "ended" and not s.cleaned and now - s.ended_at > KEEP_SECONDS:
                await self._cleanup(s)
        for token in [t for t, c in self._cmds.items()
                      if c.done is not None and c.session.cleaned]:
            del self._cmds[token]
        for sid in [i for i, s in self._sessions.items() if s.cleaned]:
            self._by_key = {k: v for k, v in self._by_key.items() if v != sid}
            del self._sessions[sid]

    async def _cleanup(self, s: _Session) -> None:
        s.cleaned = True
        try:
            await self._store.delete_tree(s.root)
        except Exception:  # noqa: BLE001 - leftover scratch files are not worth failing a request
            pass

    # -- the person's controls --------------------------------------------------------------

    def _describe(self, s: _Session | None) -> dict[str, Any]:
        if s is None:
            return {"state": "none"}
        busy = any(c.session is s and c.done is None for c in self._cmds.values())
        state = {"starting": "starting", "ready": "busy" if busy else "idle", "stopping": "stopping",
                 "ended": "ended"}[s.state]
        out: dict[str, Any] = {"state": state, "id": s.id, "idleSeconds": int(self.policy.idle_seconds)}
        if s.state == "ended":
            out["reason"] = s.reason
        return out

    async def status(self, owner: str, key: str) -> dict[str, Any]:
        """What the chip shows. Also the keepalive: asking keeps the session's lease fresh."""
        await self._reap()
        sid = self._by_key.get((owner, key))
        s = self._sessions.get(sid) if sid else None
        if s is None:
            lost = self._lost.get((owner, key))
            return {"state": "none", **({"reason": lost} if lost else {})}
        if s.state in {"starting", "ready"}:
            await self._renew(s)
        if s.state != "ended":
            await self._check_alive(s)
        return self._describe(s)

    async def interrupt(self, owner: str, token: str) -> dict[str, Any]:
        c = self._own(owner, token)
        if c.done is None and c.session.state != "ended":
            c.interrupt_asked = self._now()
            await self._store.put(self._path(c.session, "ctl", "interrupt"), {"seq": c.seq})
        return {"ok": True}

    async def stop(self, owner: str, key: str) -> dict[str, Any]:
        """End the session. The next cell starts a fresh one; this one finishes ending in the background."""
        sid = self._by_key.get((owner, key))
        s = self._sessions.get(sid) if sid else None
        if s is None or s.state in {"ended", "stopping"}:
            return self._describe(s)
        s.state, s.reason, s.stop_asked = "stopping", "the session was stopped", self._now()
        self._lost[(owner, key)] = s.reason
        try:
            await self._store.put(self._path(s, "ctl", "stop"), {})
        except Exception:  # noqa: BLE001 - cancelling the job is the other way
            await self._end(s, s.reason, cancel=True)
        return self._describe(s)


def _short(exc: Exception) -> str:
    return (str(exc) or type(exc).__name__)[:200]
