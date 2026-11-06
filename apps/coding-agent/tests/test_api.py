"""HTTP contract tests: statuses, idempotency, SSE replay, and the failure paths users will hit."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.config import Settings
from api.main import build

ROOT = Path(__file__).resolve().parents[1]


def make_client(scenario: str = "notebook", delay: float = 0.0) -> TestClient:
    cfg = Settings(
        agent_mode="fake",
        demo_scenario=scenario,
        agent_command=f"{sys.executable} -m api.adapters.fake.agent {scenario} {delay}",
        allowed_models=["fake/model-a", "fake/model-b"],
        default_model="fake/model-a",
        dev_user="tester@example.com",
    )
    app = build(cfg)
    app.state.orchestrator._rt._extra_env = {"PYTHONPATH": str(ROOT)}  # noqa: SLF001
    return TestClient(app)


@pytest.fixture
def client():
    with make_client() as c:
        yield c


def test_health_and_ready(client):
    assert client.get("/api/health").json() == {"ok": True}
    assert client.get("/api/ready").json()["agentMode"] == "fake"


def test_models_are_listed(client):
    body = client.get("/api/models").json()
    assert body["default"] == "fake/model-a"
    assert {m["id"] for m in body["available"]} == {"fake/model-a", "fake/model-b"}


def test_create_session_and_read_it_back(client):
    r = client.post("/api/sessions", json={"folder": "/tmp/agent-work", "schema": "workspace.scratch"})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    detail = client.get(f"/api/sessions/{sid}").json()
    assert detail["status"] == "ready"
    assert detail["scope"]["folder"].endswith("/tmp/agent-work/")
    assert detail["scope"]["schema"] == "workspace.scratch"


def test_unknown_session_is_404(client):
    assert client.get("/api/sessions/nope").status_code == 404
    assert client.post("/api/sessions/nope/messages", json={"text": "hi"}).status_code == 404


def test_a_disallowed_model_is_422(client):
    r = client.post("/api/sessions", json={"folder": "/tmp/x", "model": "openai/gpt-5"})
    assert r.status_code == 422


def test_sending_a_message_returns_202_with_a_turn(client):
    sid = client.post("/api/sessions", json={"folder": "/tmp/agent-work"}).json()["id"]
    r = client.post(
        f"/api/sessions/{sid}/messages",
        json={"text": "Build the notebook."},
        headers={"Idempotency-Key": "k1"},
    )
    assert r.status_code == 202 and r.json()["turnId"]
    again = client.post(
        f"/api/sessions/{sid}/messages",
        json={"text": "Build the notebook."},
        headers={"Idempotency-Key": "k1"},
    )
    assert again.json()["turnId"] == r.json()["turnId"], "a repeated key must not start a second turn"


def test_the_demo_marker_never_reaches_the_transcript(client):
    """The marker tells the reference agent which behaviour to play; it is not the user's words."""
    sid = client.post("/api/sessions", json={"folder": "/tmp/agent-work"}).json()["id"]
    client.post(f"/api/sessions/{sid}/messages", json={"text": "Build a notebook. [[scenario:notebook]]"})
    turns = client.get(f"/api/sessions/{sid}").json()["turns"]
    assert turns and "scenario:" not in turns[0]["prompt"]


def test_a_workspace_folder_is_not_used_as_the_process_cwd(client):
    """Regression: the session folder was passed as the agent's cwd, so a workspace path like
    /Users/me/x made session creation fail with Permission denied."""
    r = client.post("/api/sessions", json={"folder": "/Users/nobody@example.com/agent_scratch",
                                          "schema": "workspace.agent_scratch"})
    assert r.status_code == 201, r.text
    live = client.app.state.orchestrator.get(r.json()["id"])
    assert live.agent_cwd and not live.agent_cwd.startswith("/Users/"), live.agent_cwd
    assert live.workspace_folder == "/Users/nobody@example.com/agent_scratch"


def test_the_users_forwarded_token_reaches_the_agent_not_the_app(client):
    """A deployed app has no DATABRICKS_TOKEN of its own: the agent must run as the signed-in user."""
    r = client.post("/api/sessions", json={"folder": "/tmp/agent-work"},
                    headers={"x-forwarded-access-token": "dapi-user-token-value"})
    assert r.status_code == 201, r.text
    live = client.app.state.orchestrator.get(r.json()["id"])
    assert live.extra["user_token"] == "dapi-user-token-value"


def test_empty_message_is_rejected(client):
    sid = client.post("/api/sessions", json={"folder": "/tmp/agent-work"}).json()["id"]
    assert client.post(f"/api/sessions/{sid}/messages", json={"text": ""}).status_code == 422


async def _collect(app, sid: str, want: int = 3) -> list[dict]:
    """Read the SSE stream directly (TestClient buffers a never-ending stream)."""
    store = app.state.store
    queue = store.subscribe(sid)
    out = []
    try:
        while len(out) < want:
            ev = await asyncio.wait_for(queue.get(), 5)
            out.append(ev)
    finally:
        store.unsubscribe(sid, queue)
    return out


async def test_stream_replays_from_a_cursor_and_delivers_live_events():
    app = build(
        Settings(
            agent_mode="fake",
            agent_command=f"{sys.executable} -m api.adapters.fake.agent notebook",
            allowed_models=["fake/model-a"],
            default_model="fake/model-a",
        )
    )
    app.state.orchestrator._rt._extra_env = {"PYTHONPATH": str(ROOT)}  # noqa: SLF001
    orch = app.state.orchestrator
    s = await orch.create("tester@example.com", "/tmp/agent-work", "fake/model-a", None)
    await orch.submit(s.id, "Build a notebook with trips by hour, run it, and exit with the hour count.")
    for _ in range(100):
        if orch.get(s.id).task and orch.get(s.id).task.done():
            break
        await asyncio.sleep(0.05)
    rows = await app.state.store.since(s.id, 0)
    types = [r["type"] for r in rows]
    assert types[0] == "session.created"
    assert "turn.completed" in types or "turn.blocked" in types
    # a cursor replay must skip what the client already has
    tail = await app.state.store.since(s.id, len(rows) - 1)
    assert tail[-1]["seq"] == len(rows)


def test_scope_endpoint_reports_the_fence(client, tmp_path):
    folder = str(tmp_path / "agent_scratch")
    sid = client.post("/api/sessions", json={"folder": folder, "schema": "workspace.agent_scratch"}).json()[
        "id"
    ]
    scope = client.get(f"/api/sessions/{sid}").json()["scope"]
    assert scope["jobPrefix"].startswith("agent_")
    assert scope["appPrefix"].startswith("agent-")


def test_model_switch_endpoint(client):
    sid = client.post("/api/sessions", json={"folder": "/tmp/agent-work"}).json()["id"]
    r = client.post(f"/api/sessions/{sid}/model", json={"model": "fake/model-b"})
    assert r.status_code == 200 and r.json()["current"] == "fake/model-b"
    bad = client.post(f"/api/sessions/{sid}/model", json={"model": "nope/nope"})
    assert bad.status_code == 422


def test_cancel_is_idempotent(client):
    sid = client.post("/api/sessions", json={"folder": "/tmp/agent-work"}).json()["id"]
    assert client.post(f"/api/sessions/{sid}/cancel").status_code == 202
    assert client.post(f"/api/sessions/{sid}/cancel").status_code == 202


def test_archive_then_writes_are_refused(client):
    sid = client.post("/api/sessions", json={"folder": "/tmp/agent-work"}).json()["id"]
    assert client.delete(f"/api/sessions/{sid}").status_code == 204
    r = client.post(f"/api/sessions/{sid}/messages", json={"text": "more"})
    assert r.status_code == 409


def test_forwarded_user_header_wins_over_the_dev_user():
    app = build(
        Settings(
            agent_mode="fake",
            require_forwarded_user=True,
            agent_command=f"{sys.executable} -m api.adapters.fake.agent notebook",
        )
    )
    app.state.orchestrator._rt._extra_env = {"PYTHONPATH": str(ROOT)}  # noqa: SLF001
    with TestClient(app) as c:
        assert c.get("/api/sessions").status_code == 401, "no identity must fail closed"
        r = c.get("/api/sessions", headers={"x-forwarded-user": "alice@example.com"})
        assert r.status_code == 200


def test_no_token_is_ever_returned_to_the_browser(client):
    sid = client.post(
        "/api/sessions",
        json={"folder": "/tmp/agent-work"},
        headers={"x-forwarded-access-token": "dapi1234567890abcdef"},
    ).json()["id"]
    for path in (f"/api/sessions/{sid}", f"/api/sessions/{sid}/models", "/api/models"):
        assert "dapi" not in client.get(path).text
