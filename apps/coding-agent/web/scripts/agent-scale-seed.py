"""Populate only a stopped, disposable local E2E journal with 200 historical turns."""
import asyncio
import dataclasses
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from api.adapters.durable.sqlite import SqliteSessionStore
from api.domain.events import Event
from api.domain.session import Turn, TurnStatus

async def main():
    journal = Path(sys.argv[1]).resolve()
    if not journal.parent.name.startswith('opengenie-mission-') or journal.name != 'journal.sqlite':
        raise RuntimeError('Only the disposable browser fixture journal may be seeded')
    sid = sys.argv[2]
    store = SqliteSessionStore(str(journal))
    snapshot = await store.snapshot(sid)
    snapshot['session'].update(title='200-turn recovery and wide results', status='ready')
    snapshot['turns'] = []
    rows = [[str(i), *[f'value-{i}-{j}' for j in range(1, 12)]] for i in range(100)]
    for index in range(1, 201):
        tid = f'history{index}'
        snapshot['turns'].append(dataclasses.asdict(Turn(tid, sid, index, f'Historical mission {index}', 'fake/model-a', status=TurnStatus.COMPLETED)))
        events = [
            ('turn.started', {'text': f'Historical mission {index}', 'model': 'fake/model-a'}),
            ('message.delta', {'text': f'Recovered mission {index}. ' + ('Saved native results remain available. ' * 20)}),
            ('tool_call.started', {'callId': tid, 'name': 'dbx_read', 'args': json.dumps({'id': '/fixture/results'})}),
            ('tool_call.updated', {'callId': tid, 'status': 'completed', 'table': {'columns': [f'column_{j}' for j in range(12)], 'rows': rows, 'truncated': True}}),
            ('turn.completed', {'seconds': 1}),
        ]
        for kind, payload in events:
            await store.commit(Event(sid, kind, payload, turn_id=tid), None)
    await store.commit(Event(sid, 'session.checkpoint', {}), snapshot)
    store.close()

asyncio.run(main())
