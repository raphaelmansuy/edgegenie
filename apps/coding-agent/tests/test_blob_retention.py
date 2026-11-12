"""The attachment sweeper: the rule, the wiring, and the two ways it could destroy work.

`BlobStore.sweep()` was implemented, contract-tested on two stores, and called by nothing. This file
exists so the opposite cannot silently become true again: it asserts the rule, it asserts that a
running application actually calls it, and it asserts the two properties whose failure would be worse
than the leak —

  1. a blob a turn references is NEVER deleted, at any age;
  2. archiving a session deletes its bytes, because archiving is the user's "delete".

The first is the feature's whole safety argument. The second is the other half of the leak: a sweeper
only sees unreferenced rows, so a referenced blob of an archived conversation would otherwise live
forever with nothing pointing at it.
"""
from __future__ import annotations

import asyncio
import contextlib
import time

import pytest
from fastapi.testclient import TestClient

from api.adapters.blob.files import FileBlobStore
from api.adapters.blob.memory import MemoryBlobStore
from api.config import Settings
from api.domain import retention
from api.domain.blob import validate
from api.main import _blob_sweep_loop, build

CSV = b"a,b\n1,2\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def spec_for(name: str, raw: bytes):
    return validate(name, raw, "", model_sees_images=True)


class Clock:
    def __init__(self, now: float = 1_000_000.0) -> None:
        self.now = now


# =============================================================== the rule, without a store

def cand(state: str, age: float, refcount: int = 0) -> retention.Candidate:
    return retention.Candidate(blob_id="blb_x", state=state, created_at=1000.0 - age,
                               refcount=refcount)


@pytest.mark.parametrize("age", [0, 59 * 60, retention.PENDING_TTL - 1])
def test_a_fresh_pending_blob_is_kept(age):
    assert retention.retention(cand("pending", age), now=1000.0) is retention.Disposition.KEPT_FRESH


def test_a_pending_blob_past_its_limit_is_swept():
    assert retention.retention(
        cand("pending", retention.PENDING_TTL + 1), now=1000.0
    ) is retention.Disposition.SWEEP_PENDING


def test_a_ready_blob_past_its_limit_is_swept():
    assert retention.retention(
        cand("ready", retention.READY_TTL + 1), now=1000.0
    ) is retention.Disposition.SWEEP_READY


@pytest.mark.parametrize("age", [0, 3600, retention.READY_TTL - 1, retention.READY_TTL * 365])
def test_a_REFERENCED_blob_is_never_swept_at_any_age(age):
    """The safety property. A transcript chip points at these bytes; deleting them is the bug."""
    assert retention.retention(
        cand("ready", age, refcount=1), now=1000.0
    ) is retention.Disposition.KEPT_REFERENCED


def test_an_attached_blob_with_no_reference_is_kept():
    """`attached` with refcount 0 is a transcript being replayed or a store that lost its index.
    Not grounds to delete: the event log still names the id."""
    assert retention.retention(
        cand("attached", retention.READY_TTL * 10), now=1000.0
    ) is retention.Disposition.KEPT_FRESH


def test_an_unknown_state_is_kept_not_swept():
    """A state a newer version wrote must not be read as 'expired'. Guessing here destroys a file."""
    for state in ("swept", "quarantined", "", "ATTACHED"):
        assert retention.retention(
            cand(state, retention.READY_TTL * 10), now=1000.0
        ) is retention.Disposition.KEPT_UNKNOWN_STATE, state


def test_the_ttls_are_the_documented_numbers():
    """A TTL that silently becomes 0 deletes everything on the first pass."""
    assert retention.PENDING_TTL == 60 * 60
    assert retention.READY_TTL == 24 * 60 * 60
    assert retention.PENDING_TTL < retention.READY_TTL


def test_sweepable_returns_only_the_expired_ids():
    now = 10_000.0
    rows = [
        retention.Candidate("blb_keep_ref", "ready", now - 1e6, refcount=2),
        retention.Candidate("blb_fresh", "ready", now - 10),
        retention.Candidate("blb_old_ready", "ready", now - retention.READY_TTL - 1),
        retention.Candidate("blb_old_pending", "pending", now - retention.PENDING_TTL - 1),
    ]
    assert retention.sweepable(rows, now=now) == ["blb_old_ready", "blb_old_pending"]


def test_the_policy_is_total_over_states():
    """Every state gets an answer and none raises — the property a timer depends on."""
    for state in ("pending", "ready", "attached", "swept", "nonsense", ""):
        for age in (-1, 0, 1e9):
            for n in (0, 1, 5):
                retention.retention(cand(state, age, n), now=1000.0)


# =============================================================== both stores obey the rule

@pytest.fixture(params=["memory", "files"])
def store(request, tmp_path):
    """The same contract, run against both implementations — which is what "interchangeable" means."""
    clock = Clock()
    s = (MemoryBlobStore(clock=lambda: clock.now) if request.param == "memory"
         else FileBlobStore(tmp_path / "blobs", clock=lambda: clock.now))
    return s, clock


async def test_a_referenced_blob_survives_a_sweep(store):
    s, clock = store
    row = await s.put("ses_1", "user_a", spec_for("a.csv", CSV), CSV)
    await s.mark_attached(row.id, "turn_1", "a.csv")
    clock.now += retention.READY_TTL * 30
    assert (await s.sweep(clock.now))["ready"] == 0
    assert await s.bytes_for(row.id, "user_a") == CSV


async def test_an_unreferenced_blob_expires(store):
    s, clock = store
    row = await s.put("ses_1", "user_a", spec_for("a.csv", CSV), CSV)
    clock.now += retention.READY_TTL + 1
    assert (await s.sweep(clock.now))["ready"] == 1
    with pytest.raises(LookupError):
        await s.meta(row.id, "user_a")


async def test_a_pending_blob_expires_sooner_than_a_ready_one(store):
    """The two TTLs must actually differ in the store, not only in the policy module."""
    s, clock = store
    await s.put("pending:user_a", "user_a", spec_for("p.csv", CSV), CSV)
    clock.now += retention.PENDING_TTL + 1
    report = await s.sweep(clock.now)
    assert report["pending"] == 1 and report["ready"] == 0


# =============================================================== the wiring: it is actually called

def config(tmp_path, **kwargs):
    base = dict(agent_mode="fake", default_model="fake/model-a", allowed_models=["fake/model-a"],
                session_db_path=str(tmp_path / "sessions.sqlite"), dev_user="alice")
    base.update(kwargs)
    return Settings(**base)


@pytest.fixture()
def app_blobs(tmp_path, monkeypatch):
    """A blob root per test.

    `build()` defaults `APP_BLOB_DIR` to a path in the system temp directory, which every test in
    every worker shares. Two tests that store the same bytes under the same session id then collide:
    `put()` deduplicates on (session, sha256) and returns the first row, whose bytes an earlier test
    may already have swept. That collision is a property of the test harness, not of the store — but
    it is exactly the shape a shared root would produce in production, so isolating it is the honest
    fix rather than reusing content.
    """
    root = tmp_path / "blobs"
    monkeypatch.setenv("APP_BLOB_DIR", str(root))
    return root


def test_the_app_has_a_blob_store_the_loop_can_use(tmp_path, app_blobs):
    """The gap was that nothing called `sweep`. The first half of the fix is that the store is on the
    app and has the method the loop uses."""
    with TestClient(build(config(tmp_path))) as c:
        store = c.app.state.blob_store
        assert callable(getattr(store, "sweep", None)), "the app's blob store has no sweep method"
        assert callable(getattr(store, "delete_session", None))


def test_the_sweeper_loop_deletes_what_the_rule_says(tmp_path, app_blobs):
    """The real `_blob_sweep_loop`, one pass, deleting a blob the rule calls expired.

    `APP_BLOB_SWEEP_SECONDS=1` means the loop sleeps one second and then sweeps. The store's clock is
    moved forward, so the row is expired by the rule; nothing calls `store.sweep` directly here.

    Everything runs on the app's own event loop (`c.portal.call`). A TestClient owns a loop of its
    own; a bare `asyncio.run` beside it is a second loop, and a subprocess or a task from the first
    cannot be awaited on the second.
    """
    with TestClient(build(config(tmp_path, blob_sweep_seconds=1))) as c:
        store = c.app.state.blob_store
        clock = Clock()
        store._clock = lambda: clock.now

        async def scenario():
            row = await store.put("ses_loop", "alice", spec_for("x.csv", CSV), CSV)
            clock.now += retention.READY_TTL + 1
            task = asyncio.create_task(_blob_sweep_loop(c.app))
            try:
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline:
                    try:
                        await store.meta(row.id, "alice")
                    except LookupError:
                        return                  # the sweeper reached it
                    await asyncio.sleep(0.05)
                raise AssertionError("the sweeper loop never deleted an expired blob")
            finally:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

        c.portal.call(scenario)


def test_the_sweeper_loop_never_deletes_a_referenced_blob(tmp_path, app_blobs):
    with TestClient(build(config(tmp_path, blob_sweep_seconds=1))) as c:
        store = c.app.state.blob_store
        clock = Clock()
        store._clock = lambda: clock.now

        async def scenario():
            row = await store.put("ses_loop", "alice", spec_for("y.csv", CSV), CSV)
            await store.mark_attached(row.id, "turn_1", "y.csv")
            clock.now += retention.READY_TTL * 5
            task = asyncio.create_task(_blob_sweep_loop(c.app))
            try:
                await asyncio.sleep(1.5)        # at least one pass
                assert await store.bytes_for(row.id, "alice") == CSV
            finally:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

        c.portal.call(scenario)


def test_switching_the_sweeper_off_is_the_documented_zero(tmp_path, app_blobs):
    """0 is the off switch, and off must not mean 'sweep everything now'."""
    with TestClient(build(config(tmp_path, blob_sweep_seconds=0))) as c:
        store = c.app.state.blob_store
        clock = Clock()
        store._clock = lambda: clock.now

        async def scenario():
            row = await store.put("ses_off", "alice", spec_for("z.csv", CSV), CSV)
            clock.now += retention.READY_TTL * 5
            await _blob_sweep_loop(c.app)       # returns at once, by design
            assert await store.bytes_for(row.id, "alice") == CSV

        c.portal.call(scenario)


def test_archiving_a_session_deletes_its_attachments(tmp_path, app_blobs):
    """The other half of the leak: archiving is the user's delete, so its bytes go too."""
    with TestClient(build(config(tmp_path))) as c:
        store = c.app.state.blob_store
        sid = c.post("/api/sessions", json={"folder": "/Users/alice/agent_scratch"}).json()["id"]
        row = asyncio.run(store.put(sid, "alice", spec_for("shot.png", PNG), PNG))
        assert asyncio.run(store.bytes_for(row.id, "alice")) == PNG
        assert c.delete(f"/api/sessions/{sid}").status_code == 204
        with pytest.raises(LookupError):
            asyncio.run(store.meta(row.id, "alice"))


def test_another_sessions_attachments_survive_an_archive(tmp_path, app_blobs):
    """The blast-radius check: one archive must not delete a neighbour's bytes."""
    with TestClient(build(config(tmp_path))) as c:
        store = c.app.state.blob_store
        keep = c.post("/api/sessions", json={"folder": "/Users/alice/a"}).json()["id"]
        gone = c.post("/api/sessions", json={"folder": "/Users/alice/b"}).json()["id"]
        kept = asyncio.run(store.put(keep, "alice", spec_for("k.csv", CSV), CSV))
        asyncio.run(store.put(gone, "alice", spec_for("g.csv", CSV), CSV))
        c.delete(f"/api/sessions/{gone}")
        assert asyncio.run(store.bytes_for(kept.id, "alice")) == CSV
