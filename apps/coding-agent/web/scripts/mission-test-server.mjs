/** Disposable local ACP app. Clears credential-bearing deployment settings and never contacts a workspace. */
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { createWriteStream, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import net from 'node:net';
import { expect } from '@playwright/test';
export async function localApp(options = {}) {
  const web = resolve(dirname(fileURLToPath(import.meta.url)), '..');
  const app = resolve(web, '..');
  const scratch = mkdtempSync(resolve(tmpdir(), 'opengenie-mission-'));
  const probe = net.createServer(); probe.listen(0, '127.0.0.1'); await once(probe, 'listening');
  const port = probe.address().port; await new Promise((r) => probe.close(r));
  const url = `http://127.0.0.1:${port}`;
  const env = Object.fromEntries(Object.entries(process.env).filter(([key]) => !/^(APP_|DATABRICKS_|LLM_)/.test(key)));
  Object.assign(env, { APP_AGENT_MODE: 'fake', APP_DEFAULT_MODEL: 'fake/model-a', APP_ALLOWED_MODELS: '["fake/model-a"]',
    APP_TOOL_MODE: 'none', APP_DEMO_SCENARIO: 'longrun', APP_DEMO_EVENT_DELAY: process.env.MISSION_EVENT_DELAY ?? '.12', APP_SESSION_DB_PATH: resolve(scratch, 'journal.sqlite'),
    APP_BLOB_DIR: resolve(scratch, 'blobs'), APP_STREAM_HEARTBEAT_SECONDS: '1', APP_DEV_USER: 'mission@example.test', DATABRICKS_HOST: '', APP_DEV_TOKEN_AUTO: '0' });
  if (options.agentWork) Object.assign(env, { APP_CHANGES:'1', APP_OPERATIONS:'1', APP_ASSETS:'1', APP_EVIDENCE_V2:'1',
    APP_JOURNAL_V2:'1', APP_AGENT_WORKSPACE_DEMO:'1', APP_TOOL_MODE:'subprocess', APP_INTERNAL_URL:url, APP_AGENT_POLL_SECONDS:'.1' });
  if (options.pgDsn) Object.assign(env,{ APP_SESSION_DATABASE_URL:options.pgDsn, APP_AGENT_KEY:Buffer.from("t".repeat(32)).toString("base64") });
  if (options.asCode) env.APP_AGENT_ASCODE_DEMO="1";
  let processHandle;
  process.once('exit', () => { if (processHandle?.exitCode === null) processHandle.kill('SIGTERM'); });
  async function start() {
    processHandle = spawn(resolve(app, '.venv/bin/python'), ['-m', 'uvicorn', 'api.main:app', '--host', '127.0.0.1', '--port', String(port), '--timeout-graceful-shutdown', '1'], { cwd: app, env, stdio: ['ignore', 'pipe', 'pipe'] });
    const log = createWriteStream(resolve(scratch, `server-${Date.now()}.log`)); processHandle.stdout.pipe(log); processHandle.stderr.pipe(log);
    await expect.poll(async () => { try { return (await fetch(`${url}/api/ready`)).status; } catch { return 0; } }, { timeout: 20000 }).toBe(200);
  }
  async function stop() {
    if (!processHandle || processHandle.exitCode !== null || processHandle.signalCode !== null) return;
    const ended = once(processHandle, 'exit'); processHandle.kill('SIGTERM');
    await Promise.race([ended, new Promise((_, reject) => setTimeout(() => reject(new Error('Local app shutdown exceeded 12 seconds')), 12000).unref())]);
  }
  async function json(path, init) {
    const response = await fetch(`${url}${path}`, init);
    if (!response.ok) throw new Error(`${path}: ${response.status} ${await response.text()}`);
    return response.json();
  }
  await start(); return { url, start, stop, json, scratch };
}
