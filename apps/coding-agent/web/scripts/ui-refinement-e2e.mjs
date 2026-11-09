#!/usr/bin/env node
/** Acceptance for the application UX refinement; every retained screen is inspected separately. */
import { chromium, webkit, expect } from '@playwright/test';
import { fixture, paths } from './ui-fixtures.mjs';
import { spawn } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const output = resolve(root, '../../../specs/010-tab-management/e2e');
const iteration = process.env.UI_ITERATION || 'iteration-01';
const shots = resolve(output, 'screenshots/ui-refinement', iteration);
mkdirSync(shots, { recursive: true });
const url = process.env.APP_URL || 'http://127.0.0.1:5190';
const results = [], screenshots = [], errors = [], unknown = [], mutations = [];
let server, browser, context, page;
const note = (name) => { results.push({ name, ok: true }); console.log(`PASS ${name}`); };
async function create(width = 1480, height = 960, theme = 'light', engine = chromium, extra = {}) {
  browser = await engine.launch();
  context = await browser.newContext({ viewport: { width, height }, colorScheme: theme, reducedMotion: 'reduce', hasTouch: width <= 820, ...extra });
  await fixture(context, { unknown, mutations });
  page = await context.newPage(); page.setDefaultTimeout(8000); page.on('pageerror', (e) => errors.push(e.message));
  await page.goto(url); await expect(page.getByRole('button', { name: 'Open a document', exact: false })).toBeVisible();
  await expect(page.locator('.topbar .model-trigger')).toHaveAttribute('aria-label', 'Model: UI test model');
}
async function open(path = paths[1]) {
  const kind = path === paths[0] ? 'notebook' : 'file';
  await page.evaluate((hash) => { location.hash = hash; }, `#/${kind}${path}`);
  await expect(page.locator('.editor-surface')).toBeVisible();
  await expect(page.locator('.editor-host[data-status=loading]')).toHaveCount(0);
}
async function capture(name) {
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  const geometry = await page.evaluate(() => {
    const pop = document.querySelector('.action-menu, .tab-popover'), r = pop?.getBoundingClientRect();
    return { overflow: document.documentElement.scrollWidth > innerWidth + 1,
      bodyScroll: document.scrollingElement.scrollTop,
      popupFits: !r || r.left >= 0 && r.right <= innerWidth + 1 && r.top >= 0 && r.bottom <= innerHeight + 1,
      popupUncovered: !r || !!document.elementFromPoint(r.right - 12, r.top + 12)?.closest('.action-menu, .tab-popover') };
  });
  if (!geometry.popupUncovered) console.log('Popup hit diagnostic', await page.evaluate(() => { const r=document.querySelector('.action-menu, .tab-popover').getBoundingClientRect(); const hit=document.elementFromPoint(r.right-12,r.top+12); return { rect:{x:r.x,y:r.y,width:r.width,height:r.height}, hit:hit?.outerHTML?.slice(0,500) }; }));
  await page.screenshot({ path: resolve(shots, `${name}.png`), fullPage: true });
  expect(geometry, name).toEqual({ overflow: false, bodyScroll: 0, popupFits: true, popupUncovered: true });
  await expect(page.locator('.editor-host[data-status=loading]')).toHaveCount(0);
  screenshots.push(`${name}.png`);
}
async function hitSave() {
  const save = page.locator('.doc-save'); await expect(save).toBeVisible();
  expect(await save.evaluate((el) => {
    const r = el.getBoundingClientRect(), bar = el.closest('.doc-bar').getBoundingClientRect();
    return r.left >= bar.left && r.right <= bar.right + 1 && el.contains(document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2));
  }), 'Save fits its toolbar and receives the pointer').toBe(true);
}
const order = () => page.locator('[data-tab-id]').evaluateAll((els) => els.map((e) => e.dataset.tabId));
try {
  if (!process.env.APP_URL) {
    server = spawn(process.execPath, ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', '5190', '--strictPort'], { cwd: root, stdio: 'ignore' });
    await expect.poll(async () => { try { return (await fetch(url)).ok; } catch { return false; } }, { timeout: 15000 }).toBe(true);
  }
  await create();
  await expect(page.locator('.home-start')).toHaveCount(3);
  await expect(page.locator('.pane.inspector')).toHaveCount(0);
  await capture('01-home-desktop');
  await page.getByText('More workflows and session settings', { exact: true }).click();
  await expect(page.getByRole('button', { name: /Debug a failing job/ })).toBeVisible();
  await capture('02-home-workflows');
  await page.getByText('More workflows and session settings', { exact: true }).click();
  await page.getByRole('button', { name: /Ask the assistant Explore/ }).click();
  await expect(page.getByRole('textbox', { name: 'Message the agent' })).toBeFocused();
  note('UX-07 Three real starting actions, preserved advanced workflows, and assistant focus');
  await open(paths[0]); await hitSave();
  expect(await page.locator('.pane.main').evaluate((el) => el.getBoundingClientRect().width)).toBeGreaterThan(800);
  await capture('03-desktop-editor');
  expect(await page.locator('.nb-bar-dot').evaluate((el) => getComputedStyle(el).backgroundColor)).toBe('rgba(0, 0, 0, 0)');
  await page.getByRole('button', { name: 'Show the inspector', exact: true }).click();
  await expect(page.locator('.pane.inspector')).toBeVisible();
  await expect(page.locator('.pane.rail')).toHaveCount(0);
  expect(await page.locator('.pane.main').evaluate((el) => el.getBoundingClientRect().width)).toBeGreaterThan(700);
  await capture('04-context-on-demand');
  await page.getByRole('button', { name: 'Show the navigator', exact: true }).click();
  await expect(page.locator('.pane.rail')).toBeVisible(); await expect(page.locator('.pane.inspector')).toHaveCount(0);
  note('UX-02 Default editor width and explicit panel choices preserve useful editing space');
  const ask = page.getByRole('button', { name: 'Ask the agent', exact: true });
  await ask.focus(); await page.keyboard.press('Enter');
  await expect(page.getByRole('menuitem', { name: 'Add to chat', exact: true })).toBeFocused();
  await page.keyboard.press('ArrowDown'); await expect(page.getByRole('menuitem', { name: 'Explain', exact: true })).toBeFocused();
  await capture('05-ask-keyboard');
  await page.keyboard.press('End'); await expect(page.getByRole('menuitem', { name: 'Optimize', exact: true })).toBeFocused();
  await page.keyboard.press('Escape'); await expect(ask).toBeFocused();
  await page.getByRole('button', { name: 'Document actions', exact: true }).click();
  await capture('06-document-actions'); await page.keyboard.press('Tab'); await expect(page.getByRole('menu')).toHaveCount(0);
  await page.getByRole('button', { name: 'Layout and panels', exact: true }).click(); await capture('07-layout-menu');
  await page.getByRole('menuitem', { name: 'Focus editor', exact: true }).click();
  await expect(page.locator('.pane.rail, .pane.assistant, .pane.inspector')).toHaveCount(0); await capture('08-focus-editor');
  await page.getByRole('button', { name: 'Layout and panels', exact: true }).click(); await page.getByRole('menuitem', { name: 'Reset layout', exact: true }).click();
  await page.getByRole('button', { name: /^Colour theme:/ }).click(); await capture('09-theme-menu');
  const editorNode = await page.locator('.cm-editor').elementHandle();
  const textBeforeTheme = await page.locator('.cm-content').allTextContents();
  await page.getByRole('menuitemcheckbox', { name: 'Dark', exact: true }).click();
  await expect.poll(() => page.evaluate(() => getComputedStyle(document.querySelector('.cm-editor')).backgroundColor === getComputedStyle(document.querySelector('.doc-bar')).backgroundColor)).toBe(true);
  expect(await editorNode.evaluate((el) => el === document.querySelector('.cm-editor'))).toBe(true);
  expect(await page.locator('.cm-content').allTextContents()).toEqual(textBeforeTheme);
  await capture('10-desktop-dark');
  note('UX-03 Shared menus support initial focus, arrows, Home/End, Escape, Tab, theme and layout actions');
  for (const path of paths.slice(1, 6)) await open(path);
  await page.locator('.doc-tab[aria-selected=true]').focus(); await page.keyboard.press('Alt+Shift+ArrowLeft');
  const before = await order(), selectedBefore = await page.locator('.doc-tab[aria-selected=true]').getAttribute('data-tab-id');
  await page.reload(); await expect(page.locator('.editor-surface')).toBeVisible();
  await expect.poll(order).toEqual(before); await expect(page.locator('.doc-tab[aria-selected=true]')).toHaveAttribute('data-tab-id', selectedBefore);
  await capture('11-working-set-restored');
  const mod = await page.evaluate(() => /mac/i.test(navigator.platform)) ? 'Meta' : 'Control';
  await page.keyboard.press(`${mod}+w`); await expect(page.locator('[data-tab-id]')).toHaveCount(5);
  await page.reload(); await expect(page.locator('[data-tab-id]')).toHaveCount(5);
  await page.keyboard.press(`${mod}+Shift+t`); await expect.poll(order).toEqual(before);
  await page.goto(`${url}/#/file${paths[7]}`);
  await expect(page.locator('.doc-tab[aria-selected=true]')).toHaveAttribute('data-tab-id', `file:${paths[7]}`);
  await expect(page.locator('[data-tab-id]')).toHaveCount(7);
  note('UX-04 Ordered working set, reopen history and active route survive reload; pasted URLs override saved selection');
  await browser.close();

  for (const [width, height, theme, label] of [[390,844,'light','12-mobile-390'],[375,844,'dark','13-mobile-375-dark'],[320,720,'light','14-mobile-320'],[760,540,'light','15-tablet-landscape']]) {
    await create(width, height, theme);
    await expect(page.getByRole('button', { name: /Ask the assistant Explore/ })).toBeInViewport({ ratio: 1 });
    await capture(`${label}-home`); await open(); await hitSave();
    const composerHeight = await page.locator('.composer').evaluate((el) => el.getBoundingClientRect().height);
    expect(composerHeight, 'compact composer height').toBeLessThan(125);
    await page.locator('.cm-content').last().click(); await page.keyboard.insertText('# ux-save-proof\n');
    await expect(page.locator('.doc-save')).toBeEnabled(); await hitSave(); await capture(`${label}-editor`);
    const receipt = page.waitForResponse((r) => new URL(r.url()).pathname === '/api/workspace/save');
    await page.locator('.doc-save').tap(); expect((await receipt).status()).toBe(200);
    await expect(page.locator('.doc-save')).toBeDisabled();
    await expect(page.locator('.cm-content')).toContainText('ux-save-proof');
    await page.getByRole('button', { name: 'Document actions', exact: true }).tap(); await capture(`${label}-actions`); await page.keyboard.press('Escape');
    if (width === 375) {
      await page.route('**/api/workspace/save', (route) => route.fulfill({ status: 422, contentType: 'application/json', body: JSON.stringify({ detail: 'The document could not be saved. Review the path and try again.' }) }));
      await page.locator('.cm-content').click(); await page.keyboard.insertText('# unsaved\n'); await page.locator('.doc-save').tap();
      await expect(page.getByRole('alert')).toContainText('could not be saved'); await capture('16-mobile-error-feedback');
    }
    await browser.close();
  }
  note('UX-01/05/06 Save receives taps at 320/375/390/760px; compact composition, visible errors and readable menus');
  await create(390, 844, 'dark', webkit); await open(); await hitSave();
  await page.getByRole('button', { name: 'Ask the agent', exact: true }).click(); await expect(page.getByRole('menuitem', { name: 'Add to chat', exact: true })).toBeFocused();
  await capture('17-webkit-mobile-menu'); await page.keyboard.press('Escape'); await browser.close();
  note('WebKit mobile toolbar hit testing, menu focus, dark theme and popup geometry');
  expect(errors).toEqual([]); expect(unknown).toEqual([]);
  expect(mutations.every((m) => m === 'POST /api/workspace/save')).toBe(true);
  note('No browser runtime errors or unexpected API calls; saves only hit local fixtures');
} catch (error) {
  results.push({ name: 'failure', ok: false, detail: error.stack || String(error) }); console.error(error); process.exitCode = 1;
} finally {
  await browser?.close();
  if (server && server.exitCode == null) { const ended = new Promise((r) => server.once('exit', r)); server.kill('SIGTERM'); await ended; }
  writeFileSync(resolve(output, `ui-refinement-${iteration}.json`), JSON.stringify({ iteration, results, screenshots, errors, unknown, mutations }, null, 2) + '\n');
}
