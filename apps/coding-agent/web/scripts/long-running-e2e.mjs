/** Spec 010. Real HTTP + ACP subprocess + persistent journal; no mocked browser responses.
 * Owns a disposable server and writes all screenshots under specs/010-long-running/e2e/screenshots.
 */
import { chromium, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { mkdirSync, mkdtempSync, writeFileSync, createWriteStream } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import net from 'node:net';

const web = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const app = resolve(web, '..');
const out = process.env.E2E_OUTPUT || resolve(web, '../../../specs/010-long-running/e2e');
const shots = resolve(out, 'screenshots');
mkdirSync(shots, { recursive: true });
const scratch = mkdtempSync(resolve(tmpdir(), 'opengenie-lr-e2e-'));
const probe = net.createServer();
probe.listen(0, '127.0.0.1'); await once(probe, 'listening');
const port = probe.address().port;
await new Promise((r) => probe.close(r));
const url = `http://127.0.0.1:${port}`;
let server;
let browser;
const results = [];
const screenshots = [];
const errors = [];
const note = (name, detail = '') => { results.push({ name, ok: true, detail }); console.log(`PASS ${name}`); };
const environment = Object.fromEntries(Object.entries(process.env).filter(([key]) =>
  !key.startsWith('APP_') && !key.startsWith('DATABRICKS_') && !key.startsWith('LLM_')));
Object.assign(environment, {
  APP_AGENT_MODE: 'fake', APP_DEFAULT_MODEL: 'fake/model-a', APP_ALLOWED_MODELS: '["fake/model-a"]',
  APP_TOOL_MODE: 'none', APP_DEMO_SCENARIO: 'longrun', APP_DEMO_EVENT_DELAY: '.22',
  APP_SESSION_DB_PATH: resolve(scratch, 'journal.sqlite'), APP_BLOB_DIR: resolve(scratch, 'blobs'),
  APP_STREAM_HEARTBEAT_SECONDS: '1', APP_DEV_USER: 'lifecycle@example.com', DATABRICKS_HOST: '',
  APP_DEV_TOKEN_AUTO: '0',
});
async function startServer() {
  server = spawn(resolve(app, '.venv/bin/python'), ['-m', 'uvicorn', 'api.main:app', '--host', '127.0.0.1', '--port', String(port), '--timeout-graceful-shutdown', '1'],
    { cwd: app, env: environment, stdio: ['ignore', 'pipe', 'pipe'] });
  const log = createWriteStream(resolve(scratch, `server-${Date.now()}.log`));
  server.stdout.pipe(log); server.stderr.pipe(log);
  await expect.poll(async () => {
    try { return (await fetch(`${url}/api/ready`)).status; } catch { return 0; }
  }, { timeout: 20000 }).toBe(200);
}
async function stopServer() {
  if (!server || server.exitCode !== null) return;
  const ended = once(server, 'exit'); server.kill('SIGTERM');
  await Promise.race([ended, new Promise((_, reject) => setTimeout(() => reject(new Error('server shutdown exceeded 12s')), 12000).unref())]);
}
async function json(path, init) {
  const r = await fetch(`${url}${path}`, init);
  if (!r.ok) throw new Error(`${path}: ${r.status} ${await r.text()}`);
  return r.json();
}
const detail = (id) => json(`/api/sessions/${id}`);
async function pageFor(id = '', width = 1440, theme = 'light') {
  const context = await browser.newContext({ viewport: { width, height: 960 }, colorScheme: theme,
    permissions: ['clipboard-read', 'clipboard-write'], reducedMotion: 'reduce' });
  const page = await context.newPage();
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto(`${url}/${id ? `#/session/${id}` : ''}`);
  if (id) await expect(page.locator('.mission-screen')).toBeVisible();
  return { page, context };
}
async function submit(page, text) {
  const receipt = page.waitForResponse((r) => r.request().method() === 'POST' && /\/messages$/.test(r.url()));
  const input = page.locator('.composer textarea:visible').first();
  await expect(input).toBeEnabled();
  await input.fill(text); await input.press('Enter');
  const r = await receipt;
  expect(r.status()).toBe(202);
  return /\/sessions\/([^/]+)\/messages/.exec(r.url())[1];
}
async function shot(page, name) {
  await page.screenshot({ path: resolve(shots, `${name}.png`), fullPage: false });
  screenshots.push(`${name}.png`);
  // Check every captured state for viewport overflow and clipped run controls.
  const layout = await page.evaluate(() => {
    const visible = [...document.querySelectorAll('.run-status button')].filter((e) => e.getBoundingClientRect().width);
    return { overflow: document.documentElement.scrollWidth > innerWidth + 1,
      clipped: visible.some((e) => { const r = e.getBoundingClientRect(); return r.x < 0 || r.right > innerWidth + 1 || r.bottom > innerHeight; }) };
  });
  expect(layout, `layout ${name}`).toEqual({ overflow: false, clipped: false });
}

try {
  await startServer(); browser = await chromium.launch();
  let { page, context } = await pageFor();
  const id = await submit(page, 'Explain how a server session survives disconnects. Do not use tools. [[scenario:longrun]]');
  await expect(page.getByText('Working on the server', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Copy return link' }).click();
  await expect(page.getByText(/Conversation link copied/)).toBeVisible();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain(`#/session/${id}`);
  await shot(page, '01-server-running-light'); note('Server-owned work and a usable return link');

  await context.setOffline(true);
  await expect(page.getByText('You’re offline', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Stop work', exact: true })).toBeDisabled();
  await expect(page.locator('.composer .btn.stop:visible')).toBeDisabled();
  await shot(page, '02-offline'); note('Offline is observation loss; mutation controls disabled');
  await context.setOffline(false);
  await expect(page.getByText('You’re offline', { exact: true })).toHaveCount(0);
  await shot(page, '03-reconnected'); note('Reconnect catches up without replacing the task');

  await context.close(); // every viewer is gone; Node HTTP polling is not an SSE subscriber
  await expect.poll(async () => (await detail(id)).turns.at(-1)?.status, { timeout: 30000 }).toBe('completed');
  ({ page, context } = await pageFor(id));
  await expect(page.getByText('Ready for your review', { exact: true })).toBeVisible();
  await expect(page.locator('.turn')).toHaveCount(1);
  await expect(page.locator('.answer').first()).toContainText('No Databricks operation was executed.');
  await shot(page, '04-return-after-page-close'); note('Work finishes after every browser closes; a fresh page restores the answer');
  await context.close();

  ({ page, context } = await pageFor());
  const queueId = await submit(page, 'Explain durable execution. Do not use tools. [[scenario:longrun]]');
  await submit(page, 'Then explain the return journey. Do not use tools.');
  await expect(page.locator('.run-queued')).toHaveText('1 queued');
  await shot(page, '05-queued-work');
  await page.getByRole('button', { name: 'Stop work', exact: true }).click();
  await expect.poll(async () => (await detail(queueId)).turns.every((t) => t.status === 'cancelled')).toBe(true);
  await expect(page.getByText('Work stopped', { exact: true })).toBeVisible();
  await shot(page, '06-stopped-queue'); note('Stop work cancels active and queued turns');
  await context.close();

  ({ page, context } = await pageFor());
  const permissionId = await submit(page, 'Explain a permission decision. Do not use tools. [[scenario:approval]]');
  await expect(page.getByText('Waiting for your decision', { exact: true })).toBeVisible();
  await shot(page, '07-waiting-for-approval');
  await context.close();
  expect((await detail(permissionId)).execution.pendingApprovals).toBe(1);
  ({ page, context } = await pageFor(permissionId));
  await expect(page.getByRole('button', { name: 'Allow this session', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Allow this session', exact: true }).click();
  await expect.poll(async () => (await detail(permissionId)).turns.at(-1)?.status, { timeout: 10000 }).toBe('completed');
  await expect(page.getByText('Ready for your review', { exact: true })).toBeVisible();
  await shot(page, '08-return-and-approve'); note('Permission survives viewer departure and the offered session option works');
  await context.close();

  ({ page, context } = await pageFor());
  const restartId = await submit(page, 'Explain restart recovery. Do not use tools. [[scenario:longrun]]');
  await expect(page.getByText('Working on the server', { exact: true })).toBeVisible();
  await stopServer(); await startServer();
  await page.reload();
  await expect(page.getByText('Your progress is saved', { exact: true })).toBeVisible();
  await expect(page.locator('.composer textarea:visible').first()).toBeDisabled();
  await shot(page, '09-server-restarted');
  await page.getByRole('button', { name: 'Restore agent', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Restore agent', exact: true })).toHaveCount(0);
  await expect(page.locator('.composer textarea:visible').first()).toBeEnabled();
  expect((await detail(restartId)).turns).toHaveLength(1);
  await shot(page, '10-agent-restored'); note('Server restart preserves progress; restore loads context without replaying the prompt');
  await context.close();

  await json(`/api/sessions/${id}/resume`, { method: 'POST' });
  for (const [width, theme, name] of [[1440, 'dark', '11-wide-dark'], [760, 'light', '12-narrow-light'], [390, 'dark', '13-mobile-dark']]) {
    ({ page, context } = await pageFor(id, width, theme));
    await expect(page.locator('.mission-state')).toHaveText('Ready for review');
    await expect(page.locator('.answer').first()).toContainText('No Databricks operation was executed.');
    await shot(page, name); await context.close();
  }
  note('Status and actions fit wide, tablet and mobile layouts in both themes');
  expect(errors, 'browser runtime errors').toEqual([]); note('No browser runtime errors');
} catch (e) {
  results.push({ name: 'E2E failure', ok: false, detail: e.stack || String(e) });
  console.error(e);
  process.exitCode = 1;
} finally {
  if (browser) await browser.close();
  await stopServer();
  writeFileSync(resolve(out, 'report.json'), JSON.stringify({ at: new Date().toISOString(), mode: 'local deterministic ACP subprocess + SQLite', results, screenshots, browserErrors: errors }, null, 2) + '\n');
}
