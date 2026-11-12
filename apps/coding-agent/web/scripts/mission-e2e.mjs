#!/usr/bin/env node
/** Spec 011 acceptance: real local HTTP/SSE/ACP plus labelled presentation fixtures. */
import { chromium, webkit, expect } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { localApp } from './mission-test-server.mjs';
import { missionFixture } from './mission-fixtures.mjs';
const web = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const out = resolve(web, '../../../specs/011-ux-coding-mission/e2e');
const iteration = process.env.MISSION_ITERATION || 'iteration-03';
const shots = resolve(out, iteration); mkdirSync(shots, { recursive: true });
const smoke = process.env.MISSION_SMOKE === '1';
const results = [], screenshots = [], errors = [], audits = [];
let app, browser, context, page, fixtureHandle;
const note = (name) => { results.push({ name, ok: true }); console.log(`PASS ${name}`); };
async function create(id = '', width = 1440, theme = 'light', fixtureOptions, engine = chromium, height = 960) {
  browser = await engine.launch();
  context = await browser.newContext({ viewport: { width, height }, colorScheme: theme, reducedMotion: 'reduce', permissions: engine === chromium ? ['clipboard-read', 'clipboard-write'] : [] });
  if (fixtureOptions) { fixtureHandle = await missionFixture(context, fixtureOptions); id = fixtureHandle.id; }
  page = await context.newPage(); page.setDefaultTimeout(10000); page.on('pageerror', (e) => errors.push(e.message));
  await page.goto(`${app.url}/${id ? `#/session/${id}` : ''}`);
  if (id) await expect(page.locator('.mission-title')).toBeVisible();
}
async function close() {
  await browser?.close(); browser = undefined;
  if (fixtureHandle) { expect(fixtureHandle.errors, 'Unexpected fixture API requests').toEqual([]); expect(fixtureHandle.mutations, 'Mission view must not mutate fixture state').toEqual([]); await fixtureHandle.close(); fixtureHandle = undefined; }
}
async function submit(text) {
  const receipt = page.waitForResponse((r) => r.request().method() === 'POST' && /\/messages$/.test(r.url()));
  const input = page.locator('.composer textarea:visible').first(); await expect(input).toBeEnabled();
  await input.fill(text); await input.press('Enter'); const response = await receipt; expect(response.status()).toBe(202);
  await expect(page.locator('.mission-title')).toBeVisible();
  return /\/sessions\/([^/]+)\/messages/.exec(response.url())[1];
}
async function capture(name, { scrollTop = true } = {}) {
  if (scrollTop) await page.locator('.mission-scroll').evaluate((el) => { el.scrollTop = 0; });
  await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
  const audit = await page.evaluate(() => {
    const mission = document.querySelector('.mission-screen');
    const rect = mission.getBoundingClientRect();
    const clipped = [...mission.querySelectorAll('button, select, summary')].filter((el) => el.getClientRects().length).filter((el) => {
      const r = el.getBoundingClientRect(); return r.width && (r.left < rect.left - 1 || r.right > rect.right + 1);
    }).map((el) => el.textContent.slice(0, 60));
    const parse = (c) => (c.match(/[\d.]+/g) || []).map(Number);
    const lum = (c) => { const [r,g,b] = c.slice(0,3).map((v) => { v/=255; return v<=.04045 ? v/12.92 : ((v+.055)/1.055)**2.4; }); return .2126*r+.7152*g+.0722*b; };
    const contrast = [];
    for (const el of mission.querySelectorAll('*')) {
      if (!el.getClientRects().length || ![...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim()) || el.closest('.sr-only, [aria-hidden=true]')) continue;
      const s = getComputedStyle(el); let parent = el, bg;
      while (parent) { const c = parse(getComputedStyle(parent).backgroundColor); if (c.length && (c.length < 4 || c[3] > .99)) { bg = c; break; } parent = parent.parentElement; }
      if (!bg) continue;
      const fg = parse(s.color); if (fg.length < 3) continue;
      const a = lum(bg), b = lum(fg), ratio = (Math.max(a,b)+.05)/(Math.min(a,b)+.05);
      const required = parseFloat(s.fontSize) >= 24 ? 3 : 4.5;
      if (ratio < required) contrast.push({ text: el.textContent.slice(0,35), ratio: +ratio.toFixed(2), required });
    }
    return { overflow: document.documentElement.scrollWidth > innerWidth + 1, bodyScroll: document.scrollingElement.scrollTop,
      missionOverflow: mission.scrollWidth > mission.clientWidth + 1, clipped, contrast };
  });
  await page.screenshot({ path: resolve(shots, `${name}.png`), fullPage: false });
  screenshots.push(`${iteration}/${name}.png`); audits.push({ name, ...audit });
  expect(audit, name).toEqual({ overflow: false, bodyScroll: 0, missionOverflow: false, clipped: [], contrast: [] });
}
async function state(label) { await expect(page.locator('.mission-state')).toHaveText(label); }
try {
  app = await localApp();
  if (smoke) {
    for (const [width, theme, opts, name] of [[1440,'light',{},'01-running-desktop'],[1440,'dark',{status:'completed'},'02-achieved-dark'],[390,'light',{status:'completed'},'03-mobile-light'],[320,'dark',{long:true, invalidProof:true, status:'completed'},'04-long-mobile-dark']]) {
      await create('',width,theme,opts); await expect(page.locator('.mission-steps li')).toHaveCount(3); await capture(name); await close();
    }
    note('First visual iteration: desktop, achieved, mobile and long-content states');
  } else {
    await create();
    const id = await submit('Explain how a server session survives disconnects. Do not use tools. [[scenario:longrun]]');
    await state('In progress'); await expect(page.locator('.mission-steps li')).toHaveCount(3);
    await capture('01-running-desktop');
    await page.getByRole('button', { name: 'Copy mission link' }).click();
    expect(await page.evaluate(() => navigator.clipboard.readText())).toContain(`#/session/${id}`);
    note('M-01/07/11 real accepted instruction, streamed plan and copyable return link');
    await context.setOffline(true); await expect(page.locator('.mission-description')).toContainText('Updates paused');
    // Stop stays ENABLED offline (specs/012 [F3]): it is a POST, it does not travel over the event stream.
    await expect(page.getByRole('button', { name: 'Stop work', exact: true })).toBeEnabled(); await capture('02-offline');
    await context.setOffline(false); await expect(page.locator('.mission-description')).not.toContainText('Updates paused');
    await close();
    await expect.poll(async () => (await app.json(`/api/sessions/${id}`)).turns.at(-1)?.status, { timeout: 30000 }).toBe('completed');
    await create(id); await state('Ready for review'); await expect(page.locator('.mission-outcome')).toContainText('No Databricks operation was executed.');
    await capture('03-return-completed'); await close();
    note('M-04/08 viewer close, offline/reconnect and honest completed-without-proof state');

    await create();
    const queueId = await submit('Explain execution. Do not use tools. [[scenario:longrun]]');
    await submit('Explain the return journey. Do not use tools.');
    await expect(page.locator('.mission-title')).toHaveText('Explain execution. Do not use tools.');
    await expect(page.locator('.mission-queue')).toHaveText('1 queued');
    await page.getByRole('button', { name: 'Stop work', exact: true }).click();
    await expect.poll(async () => (await app.json(`/api/sessions/${queueId}`)).turns.every((t) => t.status === 'cancelled')).toBe(true);
    await state('Stopped'); await capture('04-stopped-queue'); await close(); note('M-02/08 queued follow-up never displaces foreground; stop cancels accepted queue');

    await create();
    const notebookId = await submit('Create the notebook taxi_hours. Run it and report the exit value. [[scenario:notebook]]');
    await expect(page.locator('.mission-state')).toHaveText('Achieved', { timeout: 30000 });
    await expect(page.locator('.mission-output')).toHaveCount(1); await capture('05-achieved-desktop');
    const proof = page.locator('.mission-proof').first(); await proof.locator('summary').click();
    await proof.locator('.tool-row').click(); await expect(proof.locator('.tool-body')).toContainText('input:');
    await proof.locator('.tool-body').scrollIntoViewIfNeeded();
    await capture('06-evidence-source', { scrollTop: false });
    await page.locator('.mission-output').click(); await expect(page.getByRole('region', { name: 'taxi_hours viewer', exact: true })).toBeVisible();
    await expect(page.locator('.viewer-error')).toContainText('DATABRICKS_HOST is not set');
    await page.getByRole('button', { name: /^Mission overview/ }).click(); await state('Achieved');
    await expect(page.locator('.mission-output')).toHaveCount(1); await close();
    note('M-04/06/09 actual local tool evidence, exact source inspection, output navigation, workspace-unavailable boundary and return');

    await create();
    const approvalId = await submit('Explain permission. Do not use tools. [[scenario:approval]]');
    await state('Needs approval'); await capture('07-approval'); await close();
    expect((await app.json(`/api/sessions/${approvalId}`)).execution.pendingApprovals).toBe(1);
    await create(approvalId); await state('Needs approval');
    await page.getByRole('button', { name: 'Allow once', exact: true }).click();
    await state('Ready for review'); await close(); note('M-08 approval survives return and requires an explicit working decision');

    await create();
    const restartId = await submit('Explain recovery. Do not use tools. [[scenario:longrun]]');
    await state('In progress'); await app.stop(); await app.start(); await page.reload();
    await state('Restore needed'); await capture('08-recovery');
    await page.getByRole('button', { name: 'Restore agent', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Restore agent', exact: true })).toHaveCount(0);
    expect((await app.json(`/api/sessions/${restartId}`)).turns).toHaveLength(1);
    await close(); note('M-08 restart/reload shows saved progress; explicit restore does not resubmit work');

    // Restore completed session after the server restart to enable normal composition.
    await app.json(`/api/sessions/${notebookId}/resume`, { method: 'POST' });
    for (const [width, theme, name] of [[1920,'dark','09-wide-dark'],[1024,'light','10-tablet-light'],[390,'light','11-mobile-light'],[375,'dark','12-mobile-dark'],[320,'light','13-mobile-320']]) {
      await create(notebookId, width, theme); await state('Achieved');
      await capture(name);
      const overview = page.getByRole('tab', { name: 'Overview', exact: true }); await overview.focus(); await overview.press('ArrowRight');
      await expect(page.getByRole('tab', { name: /^Activity/ })).toBeFocused();
      await expect(page.locator('.mission-panel .turn')).toHaveCount(1);
      await page.getByRole('tab', { name: /^Activity/ }).press('Home'); await expect(overview).toBeFocused();
      if (width === 390) {
        await page.getByRole('button', { name: 'Open conversation', exact: true }).click();
        await expect(page.locator('.pane.assistant')).toBeVisible();
        await page.locator('.pane.assistant .dock-close').click(); await state('Achieved');
      }
      await close();
    }
    note('M-07/10 keyboard tabs, 320/375/390/1024/1920 layouts, light/dark contrast and reduced motion');

    await create('',1440,'light',{}); await state('In progress');
    await page.getByRole('button', { name: 'Last achieved', exact: true }).click(); await state('Achieved');
    await capture('14-last-achieved');
    await page.getByRole('button', { name: 'Return to current mission', exact: true }).click(); await state('In progress');
    await page.getByRole('combobox', { name: 'Choose mission' }).selectOption('old'); await state('Achieved');
    await page.getByRole('tab', { name: /^Activity/ }).click(); await capture('15-history-activity');
    await page.getByRole('tab', { name: 'Overview', exact: true }).click();
    await page.locator('.mission-output').click(); await expect(page.locator('.editor-surface')).toBeVisible();
    await page.getByRole('button', { name: /^Mission overview/ }).click(); await state('In progress');
    await close();
    note('M-03 last achieved, current return, native mission picker and selected activity');

    for (const [opts, label, name] of [[{status:'blocked'},'Blocked','16-blocked'],[{status:'failed'},'Failed','17-failed'],[{status:'archived'},'Archived','18-archived'],[{empty:true},'Ready','19-empty'],[{status:'auditing'},'Checking work','20-checking']]) {
      await create('',1440,'light',opts); await state(label); if (opts.status === 'archived') {
        await expect(page.locator('.composer textarea:visible').first()).toBeDisabled();
        await expect(page.getByRole('button', { name: 'Retry', exact: true })).toHaveCount(0);
        await expect(page.getByRole('group', { name: 'Suggested next steps', exact: true })).toHaveCount(0);
      }
      await capture(name); await close();
    }
    await create('',375,'dark',{status:'completed', long:true, invalidProof:true, incompletePlan:true});
    await state('Ready for review'); await expect(page.locator('.mission-proof').last()).not.toHaveClass(/is-verified/);
    await page.getByText('Full request', { exact: true }).click(); await expect(page.locator('.mission-request p')).toContainText('数据质量');
    await capture('21-long-request-dark');
    await page.locator('.mission-proof').last().locator('summary').click(); await page.locator('.mission-proof').last().scrollIntoViewIfNeeded();
    await expect(page.getByText('No source tool call was found in this mission.')).toBeVisible();
    await capture('22-invalid-source-dark', { scrollTop: false }); await close();
    note('M-04/05/08/10 failure, archive, starting, audit, unknown plan, long unicode/path and missing-source states');

    await create('',390,'dark',{status:'completed'},webkit,844); await state('Achieved');
    expect(await page.getByRole('combobox', { name: 'Choose mission' }).evaluate((el) => el.getBoundingClientRect().height)).toBeGreaterThanOrEqual(44);
    await capture('23-webkit-mobile');
    await page.getByRole('tab', { name: 'Overview', exact: true }).focus(); await page.keyboard.press('End');
    await expect(page.getByRole('tab', { name: /^Activity/ })).toBeFocused(); await close();
    note('M-10 WebKit mobile layout, dark theme, live SSE and keyboard tab behavior');
  }
  expect(errors).toEqual([]); note('M-12 no browser runtime errors; every retained screenshot passes geometry/contrast checks');
} catch (e) {
  results.push({ name: 'failure', ok: false, detail: e.stack || String(e) }); console.error(e); process.exitCode = 1;
} finally {
  await close().catch((e) => { console.error(e); process.exitCode = 1; }); await app?.stop();
  writeFileSync(resolve(out, `${iteration}.json`), JSON.stringify({ iteration, mode: smoke ? 'Local presentation fixtures, persistent native SSE' : 'Real local HTTP + SSE + ACP subprocess + SQLite, plus labelled presentation fixtures', results, screenshots, errors, audits }, null, 2) + '\n');
}
