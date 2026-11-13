"""Index and lazy-process contracts use the complete HTTP app and durable restart path."""

from unittest.mock import AsyncMock
from fastapi.testclient import TestClient
from api.main import build
from api.config import Settings
from api.adapters.durable.sqlite import SqliteSessionStore


def config(tmp_path):
    return Settings(
        agent_mode="fake",
        default_model="fake/model-a",
        allowed_models=["fake/model-a"],
        dev_user="alice",
        session_db_path=str(tmp_path / "sessions.sqlite"),
        changes=True,
        journal_v2=True,
        agent_workspace_demo=True,
        tool_mode="none",
    )


def test_unused_sessions_spawn_nothing_and_restart_lists_without_hydrating(tmp_path, monkeypatch):
    cfg = config(tmp_path)
    with TestClient(build(cfg)) as client:
        runtime = client.app.state.orchestrator._rt
        runtime.start = AsyncMock(side_effect=AssertionError("An unused session must not start a process"))
        ids = [
            client.post("/api/sessions", json={"folder": "/Users/alice/agent_scratch"}).json()["id"]
            for _ in range(10)
        ]
        runtime.start.assert_not_called()

    async def no_full_scan(self):
        raise AssertionError("Boot and list must never scan every stored snapshot")

    monkeypatch.setattr(SqliteSessionStore, "snapshots", no_full_scan)
    with TestClient(build(cfg)) as client:
        orch = client.app.state.orchestrator
        assert len(orch._live) == 0
        page = client.get("/api/sessions?limit=3").json()
        assert len(page["sessions"]) == 3 and page["nextCursor"]
        next_page = client.get("/api/sessions?limit=3&cursor=" + page["nextCursor"]).json()
        assert not {s["id"] for s in page["sessions"]} & {s["id"] for s in next_page["sessions"]}
        assert len(orch._live) == 0
        assert client.get("/api/sessions", headers={"x-forwarded-user": "bob"}).json()["sessions"] == []
        assert client.get("/api/sessions/" + ids[0]).status_code == 200
        assert set(orch._live) == {ids[0]}
        assert client.delete("/api/sessions/" + ids[0]).status_code == 204
        assert not orch._live


async def test_proof_pending_and_expiry_include_rows_beyond_the_first_page():
    from api.adapters.durable.agent_ledgers import MemoryAgentLedgers
    from api.services.agent_work import AgentWork
    from types import SimpleNamespace
    store = MemoryAgentLedgers()
    async def expire(sid): pass
    service = AgentWork(None, None, SimpleNamespace(expire=expire), None, None, None, store, None, None)
    try:
        for kind, state in [('change', 'applied'), ('operation', 'succeeded'), ('approval', 'pending')]:
            await store.batch([(kind, {'id': f'{kind}_{i}', 'sessionId': 's', 'owner': 'u', 'turnId': 'old' if i == 0 else 'new', 'asset': {'kind': 'notebook', 'id': '/scratch/n'}, 'createdAt': i + 1, 'state': state, 'newRevision': 'r'}, None) for i in range(105)])
        missing = await service.observed('s', 'old')
        assert missing == ['Read back or run /scratch/n', 'Observe successful operation operation_0']
        pending = await service.pending('s', 'old')
        assert [r['id'] for r in pending['reviews']] == ['approval_0']
        await service.expire('s')
        assert not (await store.page('approval', session_id='s', states=('pending',)))['items']
    finally:
        await store.close()


def test_index_boot_and_listing_do_not_hydrate_ten_thousand_snapshots(tmp_path, monkeypatch):
    import json
    import time
    cfg = config(tmp_path)
    store = SqliteSessionStore(cfg.session_db_path)
    db = store._connection()
    rows = []
    timings = []
    async def no_snapshot(*args):
        raise AssertionError('Boot/list touched a stored transcript')
    monkeypatch.setattr(SqliteSessionStore, 'snapshots', no_snapshot)
    monkeypatch.setattr(SqliteSessionStore, 'snapshot', no_snapshot)
    for count in (10, 1000, 10000):
        first = len(rows)
        for i in range(first, count):
            h = {'id': f'scale{i:05}', 'user_id': 'alice', 'status': 'ready', 'folder': '/Users/alice/agent_scratch', 'schema': None, 'model': 'fake/model-a', 'title': f'Mission {i}', 'updatedAt': i}
            rows.append(h)
        with db:
            db.executemany('INSERT INTO session_snapshot VALUES (?, ?)', [(r['id'], json.dumps({'session': r, 'turns': [{'answer': 'historical transcript ' * 1000}]})) for r in rows[first:]])
            db.executemany('INSERT INTO session_index VALUES (?, ?, ?, ?, ?)', [(r['id'], 'alice', r['updatedAt'], 'ready', json.dumps(r)) for r in rows[first:]])
        store.close()
        started = time.perf_counter()
        with TestClient(build(cfg)) as client:
            page = client.get('/api/sessions?limit=20').json()
            assert len(page['sessions']) == min(20, count)
            assert page['sessions'][0]['id'] == f'scale{count-1:05}'
            assert not client.app.state.orchestrator._live
        timings.append(time.perf_counter() - started)
        db = store._connection()
    store.close()
    # Broad wall-clock guard complements the strict no-hydration assertion and avoids CI jitter.
    assert timings[-1] < timings[0] * 5 + 1, timings
    print('indexed boot/list seconds (10, 1000, 10000):', timings)


async def test_unknown_change_is_never_mistaken_for_no_effect_to_verify():
    from api.adapters.durable.agent_ledgers import MemoryAgentLedgers
    from api.services.agent_work import AgentWork
    store=MemoryAgentLedgers()
    try:
        await store.put('change',{'id':'uncertain','sessionId':'s','owner':'u','turnId':'t','state':'unknown','asset':{'kind':'notebook','id':'/scratch/n'}})
        work=AgentWork(None,None,None,None,None,None,store,None,None)
        proof=await work.observation_proof('s','t')
        assert proof == {'effects':1,'missing':['Reconcile uncertain change uncertain']}
    finally:
        await store.close()
