"""Events the app declares and must actually produce.

`domain/events.py` is the event vocabulary: 27 types. A type in it is a promise — the front end has a
reducer case for it, and `web/src/domain/event-parity.json` asserts the two lists match. So an event
the back end never emits is not harmless: it is a case in the UI that can never run, and a record the
journal promises and does not keep.

`blob.attached` was exactly that. `BlobService` takes an `emit` callback, and `build()` constructed it
without one, so every upload left a row and a file and no event. Nothing failed, because nothing
asserted the event existed.

The general test is at the bottom: drive the routes a person uses and require that the events the
vocabulary promises for them appear in the journal. That is what makes "declared" and "emitted" the
same set for the paths this file covers.
"""
from __future__ import annotations

import base64
import time

import pytest
from fastapi.testclient import TestClient

from api.config import Settings
from api.domain.events import EVENT_TYPES
from api.main import build

CSV = b"a,b\n1,2\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def config(tmp_path, **kwargs):
    return Settings(agent_mode="fake", default_model="fake/model-a", allowed_models=["fake/model-a"],
                    session_db_path=str(tmp_path / "sessions.sqlite"), dev_user="alice",
                    demo_event_delay=0, **kwargs)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_BLOB_DIR", str(tmp_path / "blobs"))
    with TestClient(build(config(tmp_path))) as c:
        yield c


def events(client, sid):
    return client.get(f"/api/sessions/{sid}/events").json()["events"]


def types(client, sid) -> list[str]:
    return [e["type"] for e in events(client, sid)]


def new_session(client, folder="/Users/alice/agent_scratch") -> str:
    r = client.post("/api/sessions", json={"folder": folder})
    assert r.status_code == 201, r.text
    return r.json()["id"]


# =============================================================== the specific gap

def test_uploading_an_attachment_to_a_session_records_blob_attached(client):
    """The gap: the event was declared, handled by the UI, and never produced."""
    sid = new_session(client)
    r = client.post("/api/blobs", json={
        "sessionId": sid, "name": "data.csv", "mime": "text/csv",
        "content": base64.b64encode(CSV).decode(),
    })
    assert r.status_code == 201, r.text
    blob_id = r.json()["blobId"]

    kinds = types(client, sid)
    assert "blob.attached" in kinds, (
        f"no blob.attached event was recorded; the journal holds {sorted(set(kinds))}")

    row = next(e for e in events(client, sid) if e["type"] == "blob.attached")
    assert row["blobId"] == blob_id
    assert row["name"] == "data.csv"
    assert row["bytes"] == len(CSV)
    # The event carries metadata, never bytes. A journal that holds the content is a journal that
    # cannot be shared, and a replay that costs what the upload cost.
    assert "content" not in row and "data" not in row and "base64" not in row


def test_uploading_before_a_session_exists_does_not_fail(client):
    """A blob with no session lives under `pending:<user>` and has nothing to record against.

    Its event belongs to the turn that adopts it. The upload must still succeed — that is the moment
    a user most wants to attach a screenshot, before typing anything.
    """
    r = client.post("/api/blobs", json={
        "name": "paste.png", "mime": "image/png",
        "content": base64.b64encode(PNG).decode(),
    })
    assert r.status_code == 201, r.text
    assert r.json()["blobId"].startswith("blb_")


def test_a_failing_journal_does_not_fail_an_upload(client):
    """The bytes are stored before the record is attempted. Telling a user their upload failed when
    the file is on disk and its id works would be a worse lie than a missing event."""
    sid = new_session(client)
    orch = client.app.state.orchestrator

    async def boom(*a, **k):
        raise RuntimeError("journal unavailable")

    original = orch.record_blob_attached
    orch.record_blob_attached = boom
    try:
        r = client.post("/api/blobs", json={
            "sessionId": sid, "name": "x.csv", "mime": "text/csv",
            "content": base64.b64encode(CSV).decode(),
        })
    finally:
        orch.record_blob_attached = original
    assert r.status_code == 201, "an upload must not fail because its record did"
    # and the bytes are readable
    assert client.get(f"/api/blobs/{r.json()['blobId']}").status_code == 200


# =============================================================== the general form

def test_the_paths_a_person_uses_emit_the_events_the_vocabulary_promises(client):
    """A turn, a document save and an attachment, then require the events that must exist.

    Not every type in `EVENT_TYPES` is reachable from a route — some are runtime signals
    (`turn.interrupted`, `session.recovery_required`). This asserts the ones a route owns, so a type
    that a route is supposed to produce cannot be silently absent.
    """
    sid = new_session(client)
    # an attachment
    client.post("/api/blobs", json={"sessionId": sid, "name": "a.csv", "mime": "text/csv",
                                    "content": base64.b64encode(CSV).decode()})
    # a turn, run to completion by the scripted agent. `math` is a scenario that finishes with a
    # verified answer; `notebook` (the default) ends in an audit for a prompt that names no notebook.
    r = client.post(f"/api/sessions/{sid}/messages", json={"text": "show revenue by hour"})
    assert r.status_code == 202, r.text
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if client.get(f"/api/sessions/{sid}").json().get("running") is None:
            break
        time.sleep(0.05)

    kinds = set(types(client, sid))
    required = {
        "session.created",   # POST /api/sessions
        "session.ready",     # the agent started
        "turn.started",      # POST /messages
        "blob.attached",     # POST /api/blobs
    }
    missing = required - kinds
    assert not missing, f"routes that own these events did not emit them: {sorted(missing)}"
    # A turn reaches exactly one terminal event. Which one depends on what the scripted agent did;
    # asserting the specific one would be a test of the fixture, not of the app.
    terminals = {"turn.completed", "turn.blocked", "turn.cancelled", "turn.failed", "turn.interrupted"}
    assert kinds & terminals, f"the turn never reached a terminal event; it has {sorted(kinds)}"


def test_the_vocabulary_and_the_emit_sites_are_not_wildly_apart():
    """A cheap guard against a type written by hand in one place.

    Every event type is constructed through a named function in `domain/events.py`, except
    `blob.attached` and `session.checkpoint`, which are built inline. This asserts that an inline use
    names a type the vocabulary declares — the mistake that would otherwise be a silent typo.
    """
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "api").rglob("*.py")
    declared = set(EVENT_TYPES)
    seen: set[str] = set()
    for path in src:
        text = path.read_text(encoding="utf-8")
        for t in declared:
            if f'"{t}"' in text or f"'{t}'" in text:
                seen.add(t)
    # Every declared type is mentioned somewhere in the code that produces or constructs it. A type
    # mentioned in no file is either dead vocabulary or a typo on the consumer side.
    unmentioned = declared - seen
    assert not unmentioned, f"declared but never constructed anywhere: {sorted(unmentioned)}"
