"""The reaper's race: a turn that starts between the decision and the teardown.

`reap_idle` reads a list of candidates, decides, and *then* awaits. Between those points the server
keeps running: another coroutine can accept a message, and `submit` will happily start a turn on a
session the reaper has already decided to archive. The archive then cancels the turn it did not know
about, and the user sees a request they made vanish.

This is the same class of bug the reaper itself was built to fix — a decision made about a moving
object — so it is worth a test rather than a comment. The rule is: **reaping must re-check under the
session's own lock**, the same lock a turn is submitted under, so the decision and the teardown cannot
straddle a submission.

These tests drive the real `Orchestrator.reap_idle`, with the real fake agent, and no network.
"""
from __future__ import annotations

import asyncio
import contextlib
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.config import Settings
from api.domain import reaper
from api.domain.session import SessionStatus
from api.main import build

API = Path(__file__).resolve().parents[1] / "api"


# =============================================================== the policy: still pure

def cand(status="ready", last_seen=0.0, watchers=0, turns=1):
    return reaper.Candidate(session_id="s", status=status, last_seen=last_seen,
                            watchers=watchers, turns=turns)


POLICY = reaper.Policy(idle_seconds=100, empty_idle_seconds=10, keep_minimum=0)
#: What a test uses when it wants the real reaper to actually reap: no floor, a short idle window.
EAGER = reaper.Policy(idle_seconds=1, empty_idle_seconds=1, keep_minimum=0)


@pytest.mark.parametrize("status", ["provisioning", "streaming", "blocked", "auditing"])
def test_a_session_doing_anything_is_never_reaped(status):
    """The session statuses that mean "mid-flight". `blocked` is included on purpose: it is waiting
    for a human answer, and killing it discards the question the human is about to answer."""
    assert reaper.reapable(cand(status=status), now=10_000, live_count=99, policy=POLICY) is not None


@pytest.fixture()
def app_blobs(tmp_path, monkeypatch):
    """A blob root per test, for the same reason `test_blob_retention.py` needs one: `build()` defaults
    `APP_BLOB_DIR` to a shared path in the system temp directory, so two tests storing the same bytes
    under the same session collide on the content-addressed `put()`."""
    monkeypatch.setenv("APP_BLOB_DIR", str(tmp_path / "blobs"))


def test_a_ready_session_is_reapable_only_when_idle():
    """`ready` is the idle status, so it is the one whose *time* decides, not whose name does."""
    # 5 s idle against a 100 s window: too young.
    assert reaper.reapable(cand(status="ready", last_seen=9_995), now=10_000,
                           live_count=99, policy=POLICY) is reaper.Why.YOUNG
    # 9 000 s idle: past the window.
    assert reaper.reapable(cand(status="ready", last_seen=1_000), now=10_000,
                           live_count=99, policy=POLICY) is None


def test_a_watched_session_is_never_reaped():
    why = reaper.reapable(cand(watchers=1), now=10_000, live_count=99, policy=POLICY)
    assert why is reaper.Why.WATCHED


def test_an_archived_session_is_not_reaped_twice():
    assert reaper.reapable(cand(status="archived"), now=10_000, live_count=99,
                           policy=POLICY) is reaper.Why.ARCHIVED


def test_an_idle_session_above_the_floor_is_reaped():
    assert reaper.reapable(cand(last_seen=0), now=10_000, live_count=5, policy=POLICY) is None


def test_an_idle_session_below_the_floor_is_kept():
    policy = reaper.Policy(idle_seconds=100, empty_idle_seconds=10, keep_minimum=8)
    assert reaper.reapable(cand(last_seen=0), now=10_000, live_count=8,
                           policy=policy) is reaper.Why.UNDER_CAP


# =============================================================== the race, end to end

def config(tmp_path, **kwargs):
    return Settings(agent_mode="fake", default_model="fake/model-a", allowed_models=["fake/model-a"],
                    session_db_path=str(tmp_path / "sessions.sqlite"), dev_user="alice",
                    demo_event_delay=0, **kwargs)


def test_a_turn_that_started_during_a_reap_is_not_archived(tmp_path, app_blobs):
    """The race, forced without deadlocking.

    `reap_idle` decides from a snapshot, then takes the session's lock to tear down. The window this
    test occupies is between those two: `idle_candidates` is where the decision is made, so a
    submission is placed immediately after it returns and before the lock is acquired.

    The interception is the point. Awaited concurrently with `gather`, a submit and a reap have no
    forced order — asyncio usually runs one to completion first — so a gather-based version of this
    test passed against a reaper with no lock at all. A submit placed *inside* the lock deadlocks
    instead, which is a correct lock and a useless test.

    The rule under test: a session that accepted a turn during the pass is skipped, not archived.
    """
    with TestClient(build(config(tmp_path))) as c:
        orch = c.app.state.orchestrator
        sid = c.post("/api/sessions", json={"folder": "/Users/alice/agent_scratch"}).json()["id"]

        async def scenario():
            live = orch.get(sid)
            live.last_seen = time.time() - 10_000

            pending: list = []
            real_candidates = orch.idle_candidates
            fired = asyncio.Event()

            def candidates_then_submit(now=None):
                """Decide as usual, then slip a submission into the gap before the teardown."""
                rows = real_candidates(now)
                if not fired.is_set():
                    fired.set()
                    # Accepted here: after the decision, before the reaper takes `live.lock`.
                    pending.append(asyncio.ensure_future(
                        orch.submit(sid, "list the tables", "", None, None)))
                return rows

            orch.idle_candidates = candidates_then_submit
            try:
                reaped = await orch.reap_idle(now=time.time(), policy=EAGER)
            finally:
                orch.idle_candidates = real_candidates

            assert fired.is_set(), "the reaper never made a decision, so nothing was tested"
            assert pending, "the interposed submission did not happen"
            task = pending[0]
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task

            session = orch.get(sid).state.session
            if task.done() and not task.cancelled():
                exc = task.exception()
                if exc is None:
                    assert task.result().status.value != "cancelled", (
                        "a turn was accepted and then cancelled by the reaper: the user loses the request")
                    assert session.status.value != "archived", (
                        "a turn was accepted into a session the same reap archived")
                    assert sid not in reaped, (
                        "the reap archived a session that accepted a turn during the reap")

        c.portal.call(scenario)


def test_the_reap_re_checks_under_the_session_lock():
    """The structural form of the same guarantee, so it cannot be lost to a refactor.

    `reap_idle` must acquire the session's lock and re-read the live state inside it. Asserting the
    shape alone is weak, which is why the behavioural test above exists beside it — but the behaviour
    depends on a window that a refactor could close without changing any output on a quiet machine,
    so both are needed and both are here.
    """
    src = (API / "services" / "orchestrator.py").read_text(encoding="utf-8")
    start = src.index("async def reap_idle")
    rest = src[start:]
    end = rest.find("\n    def scope(")
    body = rest[: end if end > 0 else len(rest)]
    assert "async with live.lock" in body, (
        "reap_idle no longer takes the session lock, so a submission can start mid-teardown")
    assert "live.state.running()" in body, (
        "reap_idle no longer re-checks whether a turn is in flight under the lock")


def test_the_reaper_never_archives_a_session_with_a_running_turn(tmp_path, app_blobs):
    """The simpler invariant, asserted directly: a session whose turn is in flight is not a candidate."""
    with TestClient(build(config(tmp_path))) as c:
        orch = c.app.state.orchestrator
        sid = c.post("/api/sessions", json={"folder": "/Users/alice/agent_scratch"}).json()["id"]

        async def scenario():
            live = orch.get(sid)
            live.last_seen = time.time() - 10_000
            live.state.session = live.state.session.transition(SessionStatus.STREAMING)
            candidates = orch.idle_candidates(time.time())
            why = reaper.reapable(candidates[0], now=time.time(), live_count=99, policy=reaper.Policy())
            assert why is reaper.Why.BUSY
            assert await orch.reap_idle(now=time.time(), policy=EAGER) == []

        c.portal.call(scenario)


async def test_reaping_stops_the_process_and_keeps_the_journal(tmp_path):
    """What reaping is for: the subprocess goes, the record stays, and the session offers resume.

    `reap_idle` takes a `policy` argument so a test can exercise the cap without opening nine
    sessions. Without it the default `keep_minimum=8` meant a single-session test could never reap
    anything — which is how a test of "does reaping work" can pass while reaping nothing.
    """
    with TestClient(build(config(tmp_path))) as c:
        orch = c.app.state.orchestrator
        sid = c.post("/api/sessions", json={"folder": "/Users/alice/agent_scratch"}).json()["id"]

        async def scenario():
            live = orch.get(sid)
            # one turn, so it is "idle with history" rather than "never used"
            await orch.submit(sid, "hello", "", None, None)
            while live.state.running() is not None:
                await asyncio.sleep(0.02)
            live.last_seen = time.time() - 10_000

            reaped = await orch.reap_idle(now=time.time(), policy=EAGER)
            assert sid in reaped
            assert live.handle is None, "the agent process was not stopped"
            assert (live.state.session.requires_resume
                    or live.state.session.status.value == "archived")

        c.portal.call(scenario)
