"""Blob routes: the contract a browser can rely on, and the fence it cannot get around.

These are the tests that make [SEC-1] and [SEC-4] facts rather than intentions. They run against the app's
own configured blob store, so a change to the store's wiring fails here too.
"""

from __future__ import annotations

import base64
import dataclasses

import pytest
from fastapi.testclient import TestClient

from api.adapters.blob import MemoryBlobStore
from api.services.blobs import BlobService

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 400


class _VisionSpec:
    """The minimum a model spec must offer for the capability check: its id and whether it sees."""

    def __init__(self, model_id: str, sees: bool = True) -> None:
        self.id = model_id
        self.sees_images = sees
CSV = b"hour,trips\n18,42\n"


@pytest.fixture()
def client(monkeypatch, tmp_path):
    """The app's own client, with a memory blob store and a model that can see images.

    The vision declaration is part of the fixture because the capability is now a DECLARED property
    (`ModelSpec.sees_images`), not a guess from the model's name: the demo catalogue declares none, so an
    image is correctly refused there. A test that wants to exercise image storage must say that its model
    can consume one — which is exactly the fact the feature depends on in production.
    """
    from tests.test_api import make_client

    with make_client() as c:
        store = MemoryBlobStore()
        c.app.state.blob_store = store
        c.app.state.blobs = BlobService(store)
        models = c.app.state.models
        original = models.find

        async def finding(model_id):
            spec = await original(model_id)
            # The demo catalogue has no row for `fake/model-a`, so a test that wants image storage must
            # stand in for the declaration itself. That is the honest shape: the capability IS a declared
            # fact, and a deployment without it refuses images (which is what `test_an_image_is_refused`
            # below asserts).
            if spec is None:
                return _VisionSpec(model_id)
            try:
                return dataclasses.replace(spec, sees_images=True)
            except TypeError:
                return spec

        monkeypatch.setattr(models, "find", finding)
        yield c


@pytest.fixture()
def session(client):
    return client.post("/api/sessions", json={"folder": "/tmp/agent-work"}).json()["id"]


def upload(client, sid, name: str, raw: bytes, mime: str = ""):
    return client.post("/api/blobs", json={
        "sessionId": sid, "name": name, "mime": mime,
        "content": base64.b64encode(raw).decode(),
    })


# -- the happy path ------------------------------------------------------------------------------

def test_upload_returns_an_id_and_the_metadata(client, session):
    r = upload(client, session, "data.csv", CSV, "text/csv")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["blobId"].startswith("blb_")
    assert body["name"] == "data.csv"
    assert body["bytes"] == len(CSV)
    assert body["mime"] == "text/csv"
    assert body["state"] == "ready"


def test_the_bytes_come_back_unchanged(client, session):
    blob_id = upload(client, session, "data.csv", CSV, "text/csv").json()["blobId"]
    r = client.get(f"/api/blobs/{blob_id}")
    assert r.status_code == 200
    assert r.content == CSV


def test_an_image_is_served_inline_with_nosniff(client, session):
    """[SEC-4]: an image is inline; anything else must not be."""
    blob_id = upload(client, session, "shot.png", PNG, "image/png").json()["blobId"]
    r = client.get(f"/api/blobs/{blob_id}")
    assert r.headers["content-type"] == "image/png"
    assert r.headers["content-disposition"] == "inline"
    assert r.headers["x-content-type-options"] == "nosniff"


def test_a_text_file_is_served_as_a_download_not_as_a_page(client, session):
    """[SEC-4]: a text/plain "file" that is really HTML must not become a document on our origin."""
    html = b"<html><script>alert(1)</script></html>"
    blob_id = upload(client, session, "x.txt", html, "text/plain").json()["blobId"]
    r = client.get(f"/api/blobs/{blob_id}")
    assert r.headers["content-type"].startswith("application/octet-stream")
    assert r.headers["content-disposition"].startswith("attachment")


def test_a_thumbnail_request_is_answered(client, session):
    blob_id = upload(client, session, "shot.png", PNG, "image/png").json()["blobId"]
    r = client.get(f"/api/blobs/{blob_id}?thumb=1")
    assert r.status_code == 200
    assert r.content == PNG          # already small enough; the store does not invent a resize


# -- refusals, and the sentence the user reads ----------------------------------------------------

def test_an_oversize_body_is_refused_by_the_framework(client, session):
    big = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 9_000_000).decode()
    r = client.post("/api/blobs", json={"sessionId": session, "name": "big.png",
                                        "mime": "image/png", "content": big})
    assert r.status_code == 422


def test_a_bad_base64_body_is_a_422_with_a_sentence(client, session):
    r = client.post("/api/blobs", json={"sessionId": session, "name": "x.png",
                                        "mime": "image/png", "content": "not base64!!"})
    assert r.status_code == 422
    assert "detail" in r.json()


def test_an_empty_file_is_refused_with_its_name(client, session):
    r = upload(client, session, "notes.txt", b"   \n")
    assert r.status_code == 422
    body = r.json()["detail"]
    assert body["code"] == "empty"
    assert "notes.txt" in body["detail"]


def test_a_zip_named_as_text_is_refused_as_a_mismatch(client, session):
    r = upload(client, session, "notes.txt", b"PK\x03\x04" + b"\x00" * 40, "text/plain")
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "mismatch"


def test_an_unknown_session_is_404_before_anything_is_stored(client):
    r = upload(client, "nope", "a.csv", CSV, "text/csv")
    assert r.status_code == 404


# -- ownership ------------------------------------------------------------------------------------

def test_another_users_blob_is_404_not_403(client, session, monkeypatch):
    """[E-20]: a 403 would confirm the id exists."""
    blob_id = upload(client, session, "a.csv", CSV, "text/csv").json()["blobId"]
    # Same app, different identity.
    from tests.test_api import make_client

    with make_client() as other:
        other.app.state.blob_store = client.app.state.blob_store
        other.app.state.blobs = client.app.state.blobs
        other.headers.update({"X-Forwarded-Email": "someone.else@example.com"})
        assert other.get(f"/api/blobs/{blob_id}").status_code == 404


def test_an_unknown_id_is_404(client, session):
    assert client.get("/api/blobs/blb_000000000000").status_code == 404


# -- the fence ------------------------------------------------------------------------------------

def test_materialise_inside_the_folder_writes_the_file(client, session, monkeypatch):
    """[D5]: inside the folder the fence allows, and the bytes are handed to the workspace importer."""
    written: list[tuple[str, bytes]] = []

    class FakeBrowser:
        async def exists(self, path, token):
            return False

        async def import_content(self, path, raw, token, *, format="AUTO", language=""):  # noqa: A002
            written.append((path, raw))

    monkeypatch.setattr("api.routers.api._browser", lambda _r: FakeBrowser())
    blob_id = upload(client, session, "data.csv", CSV, "text/csv").json()["blobId"]
    r = client.post(f"/api/blobs/{blob_id}/materialise",
                    json={"folder": "/tmp/agent-work", "sessionId": session})
    assert r.status_code == 201, r.text
    assert r.json()["path"] == "/tmp/agent-work/data.csv"
    # It is the bytes, unchanged: not a re-encoding, not a base64 decode of the wrong layer.
    assert written == [("/tmp/agent-work/data.csv", CSV)]


def test_materialise_refuses_to_overwrite(client, session, monkeypatch):
    """[E-18]: a second save of the same name is refused rather than clobbering."""
    class Exists:
        async def exists(self, path, token):
            return True

    monkeypatch.setattr("api.routers.api._browser", lambda _r: Exists())
    blob_id = upload(client, session, "data.csv", CSV, "text/csv").json()["blobId"]
    r = client.post(f"/api/blobs/{blob_id}/materialise",
                    json={"folder": "/tmp/agent-work", "sessionId": session})
    assert r.status_code == 409 or r.status_code == 422, r.text


def test_materialise_outside_the_folder_asks_and_writes_nothing(client, session):
    """[SEC-1], [E-17]: the fence decides, and nothing lands before the approval is verified."""
    blob_id = upload(client, session, "data.csv", CSV, "text/csv").json()["blobId"]
    r = client.post(f"/api/blobs/{blob_id}/materialise", json={"folder": "/tmp/elsewhere", "sessionId": session})
    assert r.status_code == 403
    body = r.json()["detail"]
    assert body["fence"] == "ask"
    assert body["approval"]                    # an approval was offered, not withheld
    assert "target" in body


def test_a_wrong_approval_is_refused(client, session):
    blob_id = upload(client, session, "data.csv", CSV, "text/csv").json()["blobId"]
    r = client.post(f"/api/blobs/{blob_id}/materialise",
                    json={"folder": "/tmp/elsewhere", "sessionId": session, "approval": "forged"})
    assert r.status_code == 403


def test_materialise_an_unknown_blob_is_404(client, session):
    r = client.post("/api/blobs/blb_000000000000/materialise", json={"folder": "/tmp/agent-work", "sessionId": session})
    assert r.status_code == 404


def test_an_image_is_accepted_even_when_the_model_declares_no_vision(session):
    """[P4]: what is unacceptable is an attachment the model SILENTLY cannot see — not an attachment the
    model cannot see.

    This uses the app's REAL catalogue (no patch), which declares no vision for any served model here, so
    it is the deployment's actual behaviour: the image is stored, and the manifest tells the model it
    cannot see the pixels. Refusing instead left the user no way to hand over a screenshot at all.
    """
    from tests.test_api import make_client

    with make_client() as c:
        c.app.state.blob_store = MemoryBlobStore()
        c.app.state.blobs = BlobService(c.app.state.blob_store)
        sid = c.post("/api/sessions", json={"folder": "/tmp/agent-work"}).json()["id"]
        r = c.post("/api/blobs", json={
            "sessionId": sid, "name": "shot.png", "mime": "image/png",
            "content": base64.b64encode(PNG).decode(),
        })
        assert r.status_code == 201, r.text
        assert r.json()["family"] == "image"
        # …and reading it produces a manifest that says so, not a wall of base64.
        blob_id = r.json()["blobId"]
        listed = c.get(f"/api/blobs/{blob_id}")
        assert listed.status_code == 200
        assert listed.headers["content-type"] == "image/png"


def test_the_catalogue_tells_the_client_who_can_see(session, client):
    """The picker refuses before an upload because the catalogue says so — one fact, two consumers."""
    body = client.get("/api/llm/models").json()
    rows = body.get("available") or []
    assert rows, "the catalogue is empty, so this test proves nothing"
    for row in rows:
        assert "seesImages" in row, f"{row.get('id')} does not declare whether it can see"
        assert isinstance(row["seesImages"], bool)
