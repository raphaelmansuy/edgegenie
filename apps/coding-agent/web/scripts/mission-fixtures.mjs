/** Rare UI states as normalized journal events. Persistent native SSE; no EventSource monkey patch. */
import http from 'node:http';
import { once } from 'node:events';
import { fixture } from './ui-fixtures.mjs';
export async function missionFixture(context, { status = 'running', long = false, invalidProof = false, empty = false, incompletePlan = false } = {}) {
  const errors = [], mutations = [];
  await fixture(context, { unknown: errors, mutations, user: 'mission-fixture@example.test' });
  const id = 'mission-fixture';
  const title = long ? 'Validate the exceptionally_long_revenue_reconciliation_workflow_'.repeat(3) + '\nPreserve every original requirement, including unicode: 数据质量.' : 'Validate the revenue pipeline';
  const events = []; const add = (type, turnId, data = {}) => events.push({ seq: events.length + 1, sessionId: id, type, turnId, ...data });
  add('session.ready', null, { toolCount: 28, agent: 'Fixture', agentVersion: '1' });
  const old = { id: 'old', index: 1, prompt: 'Build the monthly revenue notebook', model: 'test/model-a', status: 'completed' };
  const current = { id: 'current', index: 2, prompt: title, model: 'test/model-b', status: status === 'archived' ? 'completed' : status };
  function recorded(t, broken = false) {
    add('turn.started', t.id, { text: t.prompt, model: t.model });
    add('plan.updated', t.id, { entries: [{ content: 'Inspect source and schema', status: 'completed' }, { content: long ? 'Reconcile ' + 'long_identifier_'.repeat(12) : 'Check the notebook results', status: incompletePlan ? 'unknown' : t.status === 'completed' ? 'completed' : 'in_progress' }, { content: 'Verify the requested outcome', status: t.status === 'completed' ? 'completed' : 'pending' }] });
    add('tool_call.started', t.id, { callId: `${t.id}-write`, name: 'dbx_write_notebook', args: JSON.stringify({ path: `/Shared/demo/${long ? 'very_long_'.repeat(10) : 'revenue_'}report` }) });
    add('tool_call.updated', t.id, { callId: `${t.id}-write`, status: 'completed', summary: 'Notebook saved with the requested cells.' });
    add('tool_call.started', t.id, { callId: `${t.id}-run`, name: 'dbx_run_notebook', args: '{"path":"/Shared/demo/revenue_report"}' });
    add('tool_call.updated', t.id, { callId: `${t.id}-run`, status: broken ? 'error' : 'completed', summary: broken ? 'PERMISSION_DENIED: USE SCHEMA required.' : 'SUCCESS, exit_value 24' });
    add('evidence.proposed', t.id, { rows: [{ requirement: 'Write the revenue notebook', toolCallId: `${t.id}-write`, tool: 'dbx_write_notebook', summary: 'Saved', verified: true }, { requirement: 'Verify the notebook runs successfully', toolCallId: invalidProof ? 'missing-call' : `${t.id}-run`, tool: 'dbx_run_notebook', summary: broken ? 'Permission denied' : 'Exit value 24', verified: true }] });
    if (t.status === 'completed') { add('message.delta', t.id, { text: '## Revenue notebook is ready\n\nCreated the notebook and checked its output. Review the source results below before using it.\n\n- Schema inspected\n- Notebook saved\n- Exit value: **24**' }); add('turn.completed', t.id, { seconds: 12.4 }); }
    else if (t.status === 'auditing') add('turn.auditing', t.id);
    else if (t.status !== 'running' && t.status !== 'queued') add(`turn.${t.status}`, t.id, { reason: 'The source schema is unavailable. Ask the owner for access before continuing.', missing: ['USE SCHEMA permission'] });
    else if (t.status === 'queued') add('turn.queued', t.id);
  }
  if (!empty) { recorded(old); recorded(current, status === 'blocked' || status === 'failed'); }
  const session = { id, title: 'Revenue workspace', folder: long ? '/Shared/' + 'long_folder_'.repeat(16) : '/Shared/demo', model: 'test/model-b', status: empty ? 'ready' : status === 'running' || status === 'auditing' ? 'streaming' : status === 'archived' ? 'archived' : 'ready',
    execution: { persistence: 'durable', state: status, queued: 0, pendingApprovals: 0, maxRunSeconds: 21600 }, turns: empty ? [] : [old, current] };
  if (status === 'archived') add('session.archived');
  const connections = new Set();
  const server = http.createServer((req, res) => {
    res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', 'Access-Control-Allow-Origin': '*' });
    res.write(events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join(''));
    const timer = setInterval(() => res.write(': keepalive\n\n'), 1000).unref();
    connections.add(res); req.on('close', () => { clearInterval(timer); connections.delete(res); });
  });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  await context.route((u) => u.pathname === '/api/workspace/object', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ path: new URL(route.request().url()).searchParams.get('path'), name: 'revenue_report', kind: 'notebook', language: 'PYTHON', version: 'fixture-v1', truncated: false, cells: [{ index: 0, kind: 'markdown', language: 'MARKDOWN', source: '# Revenue report', truncated: false }, { index: 1, kind: 'code', language: 'PYTHON', source: 'print(24)', truncated: false }], text: '' }) }));
  await context.route((u) => u.pathname === '/api/sessions' || u.pathname.startsWith(`/api/sessions/${id}`), async (route) => {
    const request = route.request(), path = new URL(request.url()).pathname;
    if (path.endsWith('/stream')) return route.continue({ url: `http://127.0.0.1:${server.address().port}/events` });
    if (request.method() !== 'GET') { mutations.push(`${request.method()} ${path}`); return route.fulfill({ status: 409, contentType: 'application/json', body: '{"detail":"Fixture mutation not allowed"}' }); }
    return route.fulfill({ contentType: 'application/json', body: JSON.stringify(path === '/api/sessions' ? { sessions: [session] } : session) });
  });
  return { id, title, errors, mutations, close: async () => { for (const connection of connections) connection.end(); await new Promise((r) => server.close(r)); } };
}
