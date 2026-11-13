"""Eviction of archived projections, and the two things it must never do.

`Orchestrator._live` is the in-memory projection: one `Live` per conversation. Nothing removed an
entry, so a long-lived server grew by one conversation's worth of memory per conversation served. This
closes that, and the interesting part is not the eviction — it is the rule that must survive it:

  * **An archived projection may go. A live one may not.** Archiving is the user's delete; an open
    conversation that quietly left memory would answer "no such session" for a session the user can
    still see listed.
  * **The journal is untouched.** Eviction is a cache miss, not deletion. The snapshot and the events
    stay in the store, and a fresh `Orchestrator.restore()` rebuilds the projection.
  * **Nobody watching, nothing running.** An open stream is a human reading a transcript; a running
    task is a turn in flight. Both are reasons to keep the object.
"""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from api.config import Settings
from api.domain import projection
from api.main import build


# =============================================================== the rule, pure

def cand(status="archived", age=0.0, watchers=0, busy=False):
    return projection.Candidate(session_id="s", status=status, last_seen=1000.0 - age,
                                watchers=watchers, busy=busy)


NOW = 1000.0


def test_an_archived_unwatched_idle_projection_may_go():
    assert projection.disposition(cand(age=projection.GRACE_SECONDS + 1), now=NOW) \
        is projection.Disposition.EVICT


def test_a_freshly_archived_projection_is_kept_for_the_grace_period():
    assert projection.disposition(cand(age=0), now=NOW) is projection.Disposition.KEPT_RECENT


@pytest.mark.parametrize("status", ["ready", "streaming", "blocked", "provisioning", "failed"])
def test_an_unarchived_projection_is_never_evicted(status):
    """The dangerous direction: evicting a session the user can still see in their list."""
    d = projection.disposition(cand(status=status, age=1e9), now=NOW)
    assert d is projection.Disposition.KEPT_NOT_ARCHIVED


def test_a_busy_projection_is_never_evicted():
    assert projection.disposition(cand(age=1e9, busy=True), now=NOW) is projection.Disposition.KEPT_BUSY


def test_a_watched_projection_is_never_evicted():
    assert projection.disposition(cand(age=1e9, watchers=1), now=NOW) \
        is projection.Disposition.KEPT_WATCHED


def test_the_rule_is_total():
    for status in ("archived", "ready", "streaming", "", "nonsense"):
        for age in (-1, 0, 1e9):
            for watchers in (0, 3):
                for busy in (False, True):
                    projection.disposition(cand(status, age, watchers, busy), now=NOW)


def test_evictable_returns_only_what_may_go():
    rows = [
        projection.Candidate("keep_live", "ready", NOW - 1e6),
        projection.Candidate("keep_fresh", "archived", NOW - 5),
        projection.Candidate("keep_busy", "archived", NOW - 1e6, busy=True),
        projection.Candidate("keep_watched", "archived", NOW - 1e6, watchers=2),
        projection.Candidate("evict_me", "archived", NOW - projection.GRACE_SECONDS - 1),
    ]
    assert projection.evictable(rows, now=NOW) == ["evict_me"]


# =============================================================== through the orchestrator

def config(tmp_path, **kwargs):
    return Settings(agent_mode="fake", default_model="fake/model-a", allowed_models=["fake/model-a"],
                    session_db_path=str(tmp_path / "sessions.sqlite"), dev_user="alice", **kwargs)


@pytest.fixture()
def app_blobs(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_BLOB_DIR", str(tmp_path / "blobs"))


def test_archiving_then_evicting_releases_the_projection(tmp_path, app_blobs):
    with TestClient(build(config(tmp_path))) as c:
        orch = c.app.state.orchestrator
        sid = c.post("/api/sessions", json={"folder": "/Users/alice/agent_scratch"}).json()["id"]
        assert c.delete(f"/api/sessions/{sid}").status_code == 204
        assert sid in orch._live, "the projection should still be there right after an archive"

        gone = orch.evict_archived(now=time.time() + projection.GRACE_SECONDS + 1)
        assert sid in gone
        assert sid not in orch._live, "an archived, idle, unwatched projection was not evicted"


def test_an_open_session_is_never_evicted(tmp_path, app_blobs):
    """The blast-radius check: a session the user can still see must not vanish from memory."""
    with TestClient(build(config(tmp_path))) as c:
        orch = c.app.state.orchestrator
        sid = c.post("/api/sessions", json={"folder": "/Users/alice/agent_scratch"}).json()["id"]
        gone = orch.evict_archived(now=time.time() + projection.GRACE_SECONDS * 100)
        assert gone == []
        assert sid in orch._live
        assert c.get(f"/api/sessions/{sid}").status_code == 200


def test_eviction_leaves_the_journal_intact(tmp_path, app_blobs):
    """Eviction is a cache miss, not a delete. `restore()` must rebuild the projection."""
    with TestClient(build(config(tmp_path, demo_event_delay=0))) as c:
        orch = c.app.state.orchestrator
        sid = c.post("/api/sessions", json={"folder": "/Users/alice/agent_scratch"}).json()["id"]
        c.delete(f"/api/sessions/{sid}")

        snapshot_before = [row for row in c.portal.call(orch._store.snapshots)
                           if row and row["session"]["id"] == sid]
        assert snapshot_before, "the archive should have left a snapshot"

        assert sid in orch.evict_archived(now=time.time() + projection.GRACE_SECONDS + 1)

        # A fresh orchestrator over the same store must find the session again.
        rebuilt = type(orch)(orch._rt, orch._tools, orch._store, orch._models, demo=True)
        c.portal.call(rebuilt.restore)
        assert sid in rebuilt._live, "the journal did not rebuild an evicted projection"
        assert rebuilt._live[sid].state.session.status.value == "archived"
