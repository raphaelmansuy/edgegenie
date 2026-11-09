"""Spec 010: real subprocess, HTTP ownership, durable recovery, receipts, and lossless replay."""
import asyncio
import json
import os
import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.adapters.durable.sqlite import SqliteSessionStore
from api.adapters.memory.store import MemoryEventStore
from api.config import Settings
from api.domain.events import Event
from api.main import build


def config(tmp_path, **kwargs):
    return Settings(agent_mode="fake", default_model="fake/model-a", allowed_models=["fake/model-a"],
                    session_db_path=str(tmp_path / "sessions.sqlite"), dev_user="alice", **kwargs)


def create(client):
    r = client.post("/api/sessions", json={"folder": "/Users/alice/agent_scratch"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def wait_until(client, sid, predicate, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        d = client.get(f"/api/sessions/{sid}").json()
        if predicate(d):
            return d
        time.sleep(.025)
    raise AssertionError(f"session did not reach expected state: {d}")


def test_work_finishes_without_any_browser_subscribers(tmp_path):
    with TestClient(build(config(tmp_path, demo_event_delay=.02))) as c:
        sid = create(c)
        assert c.post(f"/api/sessions/{sid}/messages", json={"text": "Hello, no tools needed."}).status_code == 202
        assert c.app.state.store.subscriber_count(sid) == 0
        d = wait_until(c, sid, lambda d: d["turns"][0]["status"] in ("completed", "blocked"))
        assert d["execution"]["persistence"] == "durable"
        events = c.get(f"/api/sessions/{sid}/events").json()["events"]
        assert any(e["type"] == "message.delta" for e in events)


def test_restart_preserves_history_and_receipt_without_repeating_work(tmp_path):
    cfg = config(tmp_path, demo_event_delay=.1)
    payload = {"text": "Create a job. [[scenario:slow]]"}
    with TestClient(build(cfg)) as c:
        sid = create(c)
        receipt = c.post(f"/api/sessions/{sid}/messages", json=payload, headers={"Idempotency-Key": "retry-1"}).json()
        wait_until(c, sid, lambda d: d["status"] == "streaming")
        original_agent_id = c.app.state.orchestrator.get(sid).handle.session_id
    with TestClient(build(cfg)) as c:
        d = c.get(f"/api/sessions/{sid}").json()
        assert d["requiresResume"] is True
        assert d["turns"][0]["status"] == "interrupted"
        assert c.app.state.orchestrator.get(sid).handle is None
        again = c.post(f"/api/sessions/{sid}/messages", json=payload, headers={"Idempotency-Key": "retry-1"})
        assert again.json()["turnId"] == receipt["turnId"]
        assert len(c.get(f"/api/sessions/{sid}").json()["turns"]) == 1
        assert c.post(f"/api/sessions/{sid}/messages", json={"text": "new"}).status_code == 409
        r = c.post(f"/api/sessions/{sid}/resume")
        assert r.status_code == 200, r.text
        assert r.json()["requiresResume"] is False
        assert c.app.state.orchestrator.get(sid).handle.session_id == original_agent_id
        assert len(c.get(f"/api/sessions/{sid}").json()["turns"]) == 1


def test_foreign_user_cannot_read_mutate_stream_restore_or_approve(tmp_path):
    with TestClient(build(config(tmp_path))) as c:
        sid = create(c)
        headers = {"x-forwarded-user": "bob"}
        requests = [
            ("GET", f"/api/sessions/{sid}", None),
            ("GET", f"/api/sessions/{sid}/events", None),
            ("GET", f"/api/sessions/{sid}/stream", None),
            ("GET", f"/api/sessions/{sid}/model-facts", None),
            ("GET", f"/api/sessions/{sid}/models", None),
            ("POST", f"/api/sessions/{sid}/model", {"model": "fake/model-a"}),
            ("POST", f"/api/sessions/{sid}/messages", {"text": "steal"}),
            ("POST", f"/api/sessions/{sid}/cancel", None),
            ("POST", f"/api/sessions/{sid}/resume", None),
            ("POST", f"/api/approvals/{sid}/ap_1", {"outcome": "allow_once"}),
            ("DELETE", f"/api/sessions/{sid}", None),
        ]
        for method, path, body in requests:
            assert c.request(method, path, json=body, headers=headers).status_code == 404, path
        assert c.get("/api/sessions", headers=headers).json()["sessions"] == []


def test_reused_key_with_different_body_is_a_conflict(tmp_path):
    with TestClient(build(config(tmp_path))) as c:
        sid = create(c)
        for text, status in [("hello", 202), ("something else", 409)]:
            assert c.post(f"/api/sessions/{sid}/messages", json={"text": text},
                          headers={"Idempotency-Key": "same"}).status_code == status


async def test_concurrent_retry_accepts_exactly_one_turn(tmp_path):
    app = build(config(tmp_path))
    orch = app.state.orchestrator
    try:
        s = await orch.create("alice", "/Users/alice/agent_scratch", "fake/model-a", None)
        turns = await asyncio.gather(*(orch.submit(s.id, "hello", request_key="one", request_hash="h") for _ in range(8)))
        assert len({t.id for t in turns}) == 1
        assert len(orch.get(s.id).state.turns) == 1
    finally:
        await orch.shutdown()
        app.state.store.close()


def test_stop_cancels_the_accepted_queue_and_does_not_launch_the_next_turn(tmp_path):
    with TestClient(build(config(tmp_path, demo_event_delay=.1))) as c:
        sid = create(c)
        c.post(f"/api/sessions/{sid}/messages", json={"text": "Create a job [[scenario:slow]]"})
        c.post(f"/api/sessions/{sid}/messages", json={"text": "Create another job"})
        c.post(f"/api/sessions/{sid}/cancel")
        wait_until(c, sid, lambda d: all(t["status"] == "cancelled" for t in d["turns"]))
        time.sleep(.15)
        assert all(t["status"] == "cancelled" for t in c.get(f"/api/sessions/{sid}").json()["turns"])


def test_permission_waits_without_viewer_and_rejects_invalid_or_stale_options(tmp_path):
    with TestClient(build(config(tmp_path, demo_event_delay=.01))) as c:
        sid = create(c)
        c.post(f"/api/sessions/{sid}/messages", json={"text": "Say hello, no tools [[scenario:approval]]"})
        wait_until(c, sid, lambda d: d["execution"]["pendingApprovals"] == 1)
        request = next(e for e in c.get(f"/api/sessions/{sid}/events").json()["events"] if e["type"] == "approval.requested")
        url = f"/api/approvals/{sid}/{request['approvalId']}"
        assert c.post(url, json={"outcome": "allow_once", "optionId": "invented"}).status_code == 409
        assert c.post(url, json={"outcome": "allow_session", "optionId": "once"}).status_code == 409
        assert c.post(url, json={"outcome": "allow_session", "optionId": "session"}).status_code == 200
        assert c.post(url, json={"outcome": "allow_once", "optionId": "once"}).status_code == 409
        wait_until(c, sid, lambda d: d["turns"][0]["status"] == "completed")


def test_restart_expires_permission_and_cancel_unblocks_pending_permission(tmp_path):
    cfg = config(tmp_path)
    with TestClient(build(cfg)) as c:
        sid = create(c)
        c.post(f"/api/sessions/{sid}/messages", json={"text": "Hello [[scenario:approval]]"})
        wait_until(c, sid, lambda d: d["execution"]["pendingApprovals"] == 1)
    with TestClient(build(cfg)) as c:
        events = c.get(f"/api/sessions/{sid}/events").json()["events"]
        assert any(e["type"] == "approval.decided" and e["outcome"] == "expired" for e in events)
        assert c.post(f"/api/sessions/{sid}/resume").status_code == 200
        c.post(f"/api/sessions/{sid}/messages", json={"text": "Hello [[scenario:approval]]"})
        wait_until(c, sid, lambda d: d["execution"]["pendingApprovals"] == 1)
        c.post(f"/api/sessions/{sid}/cancel")
        wait_until(c, sid, lambda d: d["turns"][-1]["status"] == "cancelled")


def test_runtime_limit_saves_partial_output_and_requires_restore(tmp_path):
    with TestClient(build(config(tmp_path, demo_event_delay=.2, session_max_run_seconds=1))) as c:
        sid = create(c)
        c.post(f"/api/sessions/{sid}/messages", json={"text": "Create a job [[scenario:slow]]"})
        d = wait_until(c, sid, lambda d: d["requiresResume"])
        assert d["turns"][0]["status"] == "interrupted"
        assert c.app.state.orchestrator.get(sid).handle is None


def test_known_expired_delegation_does_not_run_the_prompt(tmp_path):
    import base64
    token = "header." + base64.urlsafe_b64encode(json.dumps({"exp": time.time() - 1}).encode()).decode().rstrip("=") + ".signature"
    with TestClient(build(config(tmp_path))) as c:
        sid = create(c)
        c.post(f"/api/sessions/{sid}/messages", json={"text": "hello"}, headers={"x-forwarded-access-token": token})
        d = wait_until(c, sid, lambda d: d["requiresResume"])
        assert d["turns"][0]["status"] == "interrupted"
        assert not any(e["type"] == "tool_call.started" for e in c.get(f"/api/sessions/{sid}/events").json()["events"])


@pytest.mark.parametrize("factory", [lambda p: SqliteSessionStore(str(p / "journal.sqlite")), lambda p: MemoryEventStore()])
async def test_journal_order_pagination_and_overflow_replay(factory, tmp_path):
    store = factory(tmp_path)
    q = store.subscribe("s")
    try:
        for i in range(2010):
            await store.commit(Event("s", "message.delta", {"text": str(i)}), {"counter": i})
        assert q.qsize() <= 2000
        assert any(item is None for item in list(q._queue)), "overflow must force journal catch-up"
        first = await store.since("s", 0, 1000)
        second = await store.since("s", first[-1]["seq"], 2000)
        assert [r["seq"] for r in first + second] == list(range(1, 2011))
        assert (await store.snapshots())[0]["counter"] == 2009
    finally:
        if hasattr(store, "close"):
            store.close()


def test_finite_replay_validates_bounds_and_exposes_next_page(tmp_path):
    with TestClient(build(config(tmp_path))) as c:
        sid = create(c)
        page = c.get(f"/api/sessions/{sid}/events?limit=1").json()
        assert page["hasMore"] and page["nextAfter"] == 1
        assert c.get(f"/api/sessions/{sid}/events?limit=0").status_code == 422
        assert c.get(f"/api/sessions/{sid}/events?after=-1").status_code == 422
        assert c.get(f"/api/sessions/{sid}/stream?after=9999").status_code == 409


async def test_a_second_server_owner_is_refused(tmp_path):
    a, b = SqliteSessionStore(str(tmp_path / "j.sqlite")), SqliteSessionStore(str(tmp_path / "j.sqlite"))
    try:
        await a.snapshots()
        with pytest.raises(RuntimeError, match="server owner"):
            await b.snapshots()
    finally:
        a.close()
        b.close()


def test_tokens_are_excluded_from_checkpoint_and_journal_files(tmp_path):
    # Construct the synthetic token so push-protection scanners do not mistake a fixture for a key.
    secret = "".join(("da", "pi", "0123456789abcdef" * 2))
    with TestClient(build(config(tmp_path))) as c:
        c.post("/api/sessions", json={"folder": "/Users/alice/agent_scratch"},
               headers={"x-forwarded-access-token": secret})
        for path in tmp_path.glob("sessions.sqlite*"):
            assert secret.encode() not in path.read_bytes()
        assert os.stat(tmp_path / "sessions.sqlite").st_mode & 0o777 == 0o600


def test_production_refuses_volatile_sessions():
    with pytest.raises(RuntimeError, match="durable session journal"):
        with TestClient(build(Settings(app_env="production", agent_mode="fake"))):
            pass


async def test_failed_acceptance_commit_never_schedules_a_prompt(tmp_path, monkeypatch):
    app = build(config(tmp_path))
    orch = app.state.orchestrator
    try:
        s = await orch.create("alice", "/Users/alice/agent_scratch", "fake/model-a", None)
        async def fail(*args):
            raise OSError("disk full")
        monkeypatch.setattr(app.state.store, "commit", fail)
        with pytest.raises(OSError, match="disk full"):
            await orch.submit(s.id, "write something")
        assert orch.get(s.id).state.turns == []
        assert orch.get(s.id).task is None
    finally:
        await orch.shutdown()
        app.state.store.close()


async def test_postgres_owner_and_transaction_contract():
    from api.adapters.durable.postgres import PostgresSessionStore
    dsn = os.environ.get("TEST_SESSION_PG_DSN")
    if not dsn:
        pytest.skip("set TEST_SESSION_PG_DSN to an isolated Postgres database")
    cfg = Settings(session_database_url=dsn)
    store, other = PostgresSessionStore(cfg), PostgresSessionStore(cfg)
    sid = uuid4().hex
    try:
        await store.open()
        with pytest.raises(RuntimeError, match="server owner"):
            await other.open()
        await store.commit(Event(sid, "session.created"), {"test": sid})
        await store.commit(Event(sid, "message.delta", {"text": "hello"}), {"test": sid})
        assert [e["seq"] for e in await store.since(sid, 0)] == [1, 2]
        await store.close()
        await other.open()
        assert await other.latest_seq(sid) == 2
        assert any(s.get("test") == sid for s in await other.snapshots())
    finally:
        await store.close()
        await other.close()


async def test_idle_reaper_preserves_durable_conversation(tmp_path, monkeypatch):
    # Enough open sessions for the existing policy's floor, with one idle empty conversation.
    app = build(config(tmp_path))
    orch = app.state.orchestrator
    try:
        s = await orch.create("alice", "/Users/alice/agent_scratch", "fake/model-a", None)
        live = orch.get(s.id)
        live.last_seen = 1
        await orch.reap_idle(now=time.time() + 3600)
        assert live.handle is None
        assert live.state.session.requires_resume
        assert orch.sessions_for("alice")[0].id == s.id
        assert (await app.state.store.snapshots())[0]["session"]["status"] != "archived"
    finally:
        await orch.shutdown()
        app.state.store.close()


@pytest.mark.parametrize("capability", [False, True])
async def test_native_restore_capability_and_large_history_are_handled(tmp_path, capability):
    import sys
    from api.adapters.acp.runtime import AcpAgentRuntime
    from api.ports import AgentCrashed, SessionSpec
    agent = tmp_path / "restore_agent.py"
    # > queue capacity catches deadlocks that a short history cannot reveal.
    agent.write_text('''import json,sys
for line in sys.stdin:
    m=json.loads(line)
    method=m['method']
    if method=='initialize':
        result={'protocolVersion':1,'agentCapabilities':{'loadSession':CAPABILITY}}
    elif method=='session/load':
        for i in range(10005):
            print(json.dumps({'jsonrpc':'2.0','method':'session/update','params':{'sessionId':'saved','update':{'sessionUpdate':'agent_message_chunk','content':{'type':'text','text':'old'}}}}),flush=True)
        result={}
    elif method=='session/prompt':
        print(json.dumps({'jsonrpc':'2.0','method':'session/update','params':{'sessionId':'saved','update':{'sessionUpdate':'agent_message_chunk','content':{'type':'text','text':'fresh'}}}}),flush=True)
        result={'stopReason':'end_turn'}
    else:
        result={}
    if 'id' in m:
        print(json.dumps({'jsonrpc':'2.0','id':m['id'],'result':result}),flush=True)
'''.replace('CAPABILITY', repr(capability)))
    rt = AcpAgentRuntime(f"{sys.executable} {agent}")
    spec = SessionSpec("ours", str(tmp_path), "fake/model-a", "", agent_session_id="saved")
    if not capability:
        with pytest.raises(AgentCrashed, match="loadSession"):
            await rt.start(spec)
        assert not rt._procs
        return
    h = await asyncio.wait_for(rt.start(spec), 8)
    try:
        assert h.session_id == "saved"
        rt.set_turn("ours", "new")
        await rt.prompt_in_background(h, "continue")
        text = []
        async for item in rt.events(h):
            if isinstance(item, tuple):
                break
            if item.type == "message.delta":
                text.append(item.payload["text"])
        assert text == ["fresh"], "native load replay must not duplicate the application journal"
    finally:
        await rt.close(h)


async def test_agent_output_and_tool_payloads_are_redacted_before_journaling(tmp_path):
    app = build(config(tmp_path))
    orch = app.state.orchestrator
    secret = "sk-" + "x" * 32
    try:
        s = await orch.create("alice", "/Users/alice/agent_scratch", "fake/model-a", None)
        await orch._emit(Event(s.id, "message.delta", {"text": secret, "nested": {"value": secret}}))
        assert secret not in json.dumps(await app.state.store.since(s.id, 0))
    finally:
        await orch.shutdown()
        app.state.store.close()
