"""Cross-user reads must be refused, in every router that names a session.

The identity middleware guards `/api/sessions/**` and `/api/approvals/**`. That covers replay,
approvals and mutations. It does **not** cover a route that carries a session id in a path under a
different prefix, and `/api/llm/sessions/{sid}/turns` is exactly that: it returns which model each
turn used, for any session id the caller can name.

That is not a credential leak, but it is a cross-user disclosure: a session id plus the model
provenance of somebody else's conversation. The fix is to read the owner the same way everything
else does. These tests hold the boundary from both sides, so a future route cannot reopen it.

`docs/09-security.md` §3.1 states the rule; this file is the proof.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.config import Settings
from api.main import build


def config(tmp_path, **kwargs):
    return Settings(agent_mode="fake", default_model="fake/model-a", allowed_models=["fake/model-a"],
                    session_db_path=str(tmp_path / "sessions.sqlite"), dev_user="alice", **kwargs)


def as_user(client: TestClient, user: str, path: str) -> "object":
    """A request carrying a forwarded identity, as the Databricks proxy would supply it."""
    return client.get(path, headers={"x-forwarded-user": user, "x-forwarded-email": f"{user}@example.com"})


def make_session(client: TestClient, user: str) -> str:
    r = client.post("/api/sessions", json={"folder": f"/Users/{user}/agent_scratch"},
                    headers={"x-forwarded-user": user, "x-forwarded-email": f"{user}@example.com"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture()
def two_users(tmp_path):
    with TestClient(build(config(tmp_path))) as c:
        alice = make_session(c, "alice")
        bob = make_session(c, "bob")
        yield c, alice, bob


def test_the_owner_can_read_their_own_turn_provenance(two_users):
    c, alice, _bob = two_users
    r = as_user(c, "alice", f"/api/llm/sessions/{alice}/turns")
    assert r.status_code == 200, r.text
    assert r.json()["session"] == alice


def test_another_user_cannot_read_a_sessions_turn_provenance(two_users):
    """The leak: bob names alice's session and learns which model answered each of her turns."""
    c, alice, _bob = two_users
    r = as_user(c, "bob", f"/api/llm/sessions/{alice}/turns")
    assert r.status_code == 404, (
        "a session that is not yours must answer 404 (not 403, which confirms the id exists), "
        f"got {r.status_code}: {r.text}")


def test_the_session_routes_still_guard_themselves(two_users):
    """The control: the middleware's own boundary, so a fix above cannot be a regression here."""
    c, alice, _bob = two_users
    for path in (f"/api/sessions/{alice}", f"/api/sessions/{alice}/events"):
        r = as_user(c, "bob", path)
        assert r.status_code == 404, f"{path} answered {r.status_code} for a non-owner"


def test_cors_is_same_origin_by_default(tmp_path):
    """A wildcard was here from the first prototype, when Vite talked to the API on another port.

    On an app authenticated by the Databricks proxy it is wider than it needs to be: the built front
    end is served by the same process, so a browser on the app's own URL needs no grant at all. A
    cross-origin header on a default deployment would be a finding, so the default must be no grant.
    """
    with TestClient(build(config(tmp_path))) as c:
        r = c.get("/api/health", headers={"Origin": "https://evil.example"})
        assert r.status_code == 200
        assert "access-control-allow-origin" not in {k.lower() for k in r.headers}, (
            "a default deployment must not answer a cross-origin request")


def test_cors_can_be_named_for_a_dev_server(tmp_path):
    """The other half: a separate dev origin is a configuration, not a wildcard."""
    with TestClient(build(config(tmp_path, cors_origins="http://localhost:5173"))) as c:
        r = c.get("/api/health", headers={"Origin": "http://localhost:5173"})
        assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
