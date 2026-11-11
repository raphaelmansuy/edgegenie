/** Local UI fixtures only; no connected workspace is accessed. */
export const paths = ['/Shared/demo/display_unity_catalog_tables', '/Repos/demo/databricks.yml', '/Repos/demo/package.json', '/Repos/demo/pyproject.toml', '/Repos/demo/app.yaml', '/Repos/demo/Makefile', '/Shared/analytics/revenue.py', '/Shared/experiments/revenue.py', '/Shared/demo/quarterly_revenue_forecast_with_a_very_long_name.sql', '/Shared/demo/报表.sql', '/Shared/demo/a.b', '/Shared/demo/a_b'];
export async function fixture(context, { mutations = [], unknown = [], user = "tab-review@example.test" } = {}) {
  const saved = new Map();
  await context.route((u) => u.pathname.startsWith('/api/'), async (route) => {
    const req = route.request(), u = new URL(req.url()), p = u.pathname;
    const reply = (data, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
    if (req.method() !== 'GET' && p !== '/api/workspace/fence') mutations.push(`${req.method()} ${p}`);
    if (p === '/api/me') return reply({ user, scratch: '/Shared/demo', demo: true, pythonRun: { enabled: false, reason: 'Local UI fixture; no compute is connected.' } });
    if (p === '/api/version') return reply({ version: '1.0.0', commit: '', docs: 'https://raphaelmansuy.github.io/opengenie/', agentMode: 'fixture' });
    if (p === '/api/sessions') return reply({ sessions: [] });
    if (p === '/api/models') return reply({ default: 'fixture', available: [{ id: 'fixture', name: 'UI test model', provider: 'test', providerName: 'Local fixture', wire: 'fixture', state: 'available', selectable: true, refusal: '', detail: '', capability: 'tools', group: 'Local fixture', credential: { kind: 'none', source: 'env', hint: 'Local fixture' }, limits: { context: 64000, output: 4000, evidence: 'documented', source: '', unverified: false } }], providers: [] });
    if (p === '/api/workspace/save') { const body = req.postDataJSON(); saved.set(body.path, body.text); return reply({ path: body.path, size: body.text.length, version: { token: 'fixture-v2' } }); }
    if (p === '/api/workspace/fence') return reply({ verdict: 'ask', reason: 'no session — local UI review', approval: null });
    if (p === '/api/workspace/object') {
      const path = u.searchParams.get('path');
      if (path === '/Shared/denied.sql') return reply({ detail: 'Permission denied by Unity Catalog' }, 403);
      const nb = path === paths[0], text = saved.get(path) ?? (path.endsWith('.json') ? '{ "name": "edgegenie", "private": true }\n' : '# Configuration for the working project\nworkspace: demo\n');
      return reply({ path, name: path.split('/').at(-1), kind: nb ? 'notebook' : 'file', language: nb ? 'PYTHON' : path.endsWith('.json') ? 'JSON' : 'YAML', version: saved.has(path) ? 'fixture-v2' : 'fixture-v1', size: text.length, truncated: false, text: nb ? '' : text, cells: nb ? [{ index: 0, kind: 'markdown', language: 'MARKDOWN', source: '# Explore your catalog\nKeep related documents within reach.', truncated: false }, { index: 1, kind: 'code', language: 'PYTHON', source: 'catalog = "main"\nprint(catalog)', truncated: false }] : [] });
    }
    if (p === '/api/workspace/version') return reply({ path: u.searchParams.get('path'), version: saved.has(u.searchParams.get('path')) ? 'fixture-v2' : 'fixture-v1', modifiedAt: 1 });
    if (p === '/api/workspace/list') return reply({ path: '/Shared/demo', nodes: [], items: [] });
    if (p === '/api/workspace/search') return reply({ root: '/Shared/demo', complete: true, results: [] });
    if (p === '/api/catalog') return reply({ items: [] });
    if (p === '/api/catalog/find') return reply({ results: [] });
    if (p === '/api/catalog/table') return reply({ fullName: 'main.demo.orders', tableType: 'MANAGED', owner: 'fixture', comment: 'Fixture table', format: 'DELTA', columns: [{ name: 'order_id', type: 'BIGINT', nullable: false, comment: '' }] });
    if (p === '/api/catalog/preview') return reply({ columns: ['order_id'], rows: [['1']], warehouse: 'Fixture only' });
    unknown.push(`${req.method()} ${p}`); return reply({ detail: `No fixture for ${p}` }, 404);
  });
}
