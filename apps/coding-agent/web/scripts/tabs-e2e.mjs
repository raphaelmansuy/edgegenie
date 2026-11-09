#!/usr/bin/env node
/** TM-01..10 through real App/CodeMirror/DOM with deterministic HTTP-boundary fixtures. */
import { fixture as installFixture, paths } from './ui-fixtures.mjs';
import { chromium, firefox, webkit, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const out = resolve(root, '../../../specs/010-tab-management/e2e'), shots = resolve(out, 'screenshots');
mkdirSync(shots, { recursive: true });
const url = process.env.APP_URL || 'http://127.0.0.1:5187';
let server, browser, page;
const results = [], screenshots = [], errors = [], mutations = [], unknown = [], unavailable = [];

const idFor = (path) => `${path === paths[0] ? 'notebook' : 'file'}:${path}`;
const item = (path) => page.locator(`[data-tab-id=${JSON.stringify(idFor(path))}]`);
const order = () => page.locator('[data-tab-id]').evaluateAll((els) => els.map((el) => el.dataset.tabId));
const selected = () => page.locator('.doc-tab[aria-selected=true]').getAttribute('data-tab-id');
const note = (name) => { results.push({ name, ok: true }); console.log(`PASS ${name}`); };
async function shot(name) {
  const activeId = await page.locator('.doc-tab[aria-selected=true]').getAttribute('data-tab-id');
  if (activeId && !activeId.startsWith('table:')) await expect(page.locator('.editor-surface')).toBeVisible();
  await expect(page.locator('.editor-host[data-status=loading]')).toHaveCount(0);
  const popupClear = await page.evaluate(() => { const r = document.querySelector('.tab-popover')?.getBoundingClientRect(); return !r || !!document.elementFromPoint(r.right - 12, r.top + 16)?.closest('.tab-popover'); });
  expect(popupClear, `${name}: popup covered by shell controls`).toBe(true);
  expect(await page.evaluate(() => {
    const r = document.querySelector('.doc-tabs-controls')?.getBoundingClientRect();
    return { overflow: document.documentElement.scrollWidth > innerWidth + 1, bodyScroll: document.scrollingElement.scrollTop, controlsFit: !r || (r.left >= 0 && r.right <= innerWidth + 1 && r.bottom <= innerHeight) };
  }), name).toEqual({ overflow: false, bodyScroll: 0, controlsFit: true });
  await page.screenshot({ path: resolve(shots, `${name}.png`), fullPage: true }); screenshots.push(`${name}.png`);
}
async function open(path, kind = path === paths[0] ? 'notebook' : 'file') {
  await page.evaluate((hash) => { location.hash = hash; }, `#/${kind}/${path.replace(/^\//, "")}`);
  const loc = page.locator(`[data-tab-id=${JSON.stringify(`${kind}:${path}`)}]`);
  await expect(loc).toHaveAttribute('aria-selected', 'true');
  if (kind !== 'table' && !path.includes('denied')) await expect(page.locator('.editor-surface')).toBeVisible();
  await expect(page.locator('#doc-panel')).toHaveAttribute('aria-labelledby', await loc.getAttribute('id'));
}
async function reveal(path) { await item(path).focus(); await item(path).press('Enter'); await expect(item(path)).toHaveAttribute('aria-selected', 'true'); }
async function fullyVisible() {
  await expect.poll(() => page.evaluate(() => {
    const s = document.querySelector('.doc-tabs').getBoundingClientRect(), t = document.querySelector('.doc-tab[aria-selected=true]').getBoundingClientRect();
    return t.left >= s.left - 1 && t.right <= s.right + 1;
  })).toBe(true);
}
async function startPage(engine = chromium, options = {}) {
  browser = await engine.launch();
  const context = await browser.newContext({ viewport: { width: 1480, height: 960 }, reducedMotion: 'reduce', ...options });
  await installFixture(context, { mutations, unknown }); page = await context.newPage(); page.setDefaultTimeout(8000); page.on('pageerror', (e) => errors.push(e.message));
  await page.goto(url); await expect(page.locator('.topbar')).toBeVisible();
  const inspector = page.getByRole('button', { name: 'Hide the inspector', exact: true });
  if (await inspector.count()) await inspector.click();
  return context;
}
async function drag(from, x, y) {
  const r = await item(from).boundingBox();
  await page.mouse.move(r.x + 30, r.y + r.height / 2); await page.mouse.down(); await page.mouse.move(x, y, { steps: 12 });
  await expect(page.locator('.is-dragging')).toBeVisible();
}
try {
  if (!process.env.APP_URL) {
    server = spawn(process.execPath, ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', '5187', '--strictPort'], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
    let log = ''; server.stdout.on('data', (d) => { log += d; }); server.stderr.on('data', (d) => { log += d; });
    await expect.poll(async () => { try { return (await fetch(url)).ok; } catch { if (server.exitCode != null) throw new Error(log); return false; } }, { timeout: 15000 }).toBe(true);
  }
  await startPage(); await expect(page.locator('.doc-tabs')).toHaveCount(0); note('Empty workspace has no dead tab strip');
  for (const path of paths.slice(0, 3)) await open(path);
  await open(paths[0]); await shot('01-readable-tabs-light');
  const editor = page.locator('.cm-content').last(); await editor.click(); await page.keyboard.press('End'); await page.keyboard.insertText(' # tab-draft');
  await expect(item(paths[0]).locator('.doc-tab-dirty')).toBeVisible();
  const handle = await page.locator('.editor-surface').elementHandle(), textBefore = await page.locator('.cm-content').allTextContents(), before = await order();
  const dest = await item(paths[2]).boundingBox();
  await drag(paths[0], dest.x + dest.width - 6, dest.y + dest.height / 2); await shot('02-drag-insertion'); await page.mouse.up();
  await expect.poll(order).toEqual([before[1], before[2], before[0]]); expect(await selected()).toBe(idFor(paths[0]));
  expect(await handle.evaluate((el) => el === document.querySelector('.editor-surface'))).toBe(true);
  expect(await page.locator('.cm-content').allTextContents()).toEqual(textBefore);
  await shot('03-reordered-dirty-editor'); note('Drag retains active identity, mounted editor and unsaved notebook text');
  const stable = await order(); let r = await item(paths[0]).boundingBox();
  await page.mouse.move(r.x + 20, r.y + 15); await page.mouse.down(); await page.mouse.move(r.x + 22, r.y + 15); await page.mouse.up(); expect(await order()).toEqual(stable);
  r = await item(paths[1]).boundingBox();
  await drag(paths[0], r.x + 10, r.y + 15); await page.keyboard.press('Escape'); await page.mouse.up(); expect(await order()).toEqual(stable);
  await drag(paths[0], r.x + 10, r.y + 15); await page.mouse.move(r.x + 10, r.y + 160); await page.mouse.up(); expect(await order()).toEqual(stable);
  await drag(paths[0], r.x + 10, r.y + 15); await item(paths[0]).dispatchEvent('pointercancel', { pointerId: 1 }); await page.mouse.up();
  expect(await order()).toEqual(stable); await expect(page.locator('.is-dragging')).toHaveCount(0);
  note('Threshold, Escape, outside release and pointer cancellation preserve order');
  await item(paths[0]).focus(); await page.keyboard.press('Alt+Shift+ArrowLeft');
  await expect.poll(order).toEqual([stable[0], stable[2], stable[1]]); await expect(item(paths[0])).toBeFocused();
  await page.keyboard.press('Shift+F10'); await expect(page.getByRole('menu', { name: /Tab actions/ })).toBeVisible(); await shot('04-accessible-tab-actions');
  await page.getByRole('menuitem', { name: /Move right/ }).click(); await expect.poll(order).toEqual(stable); await expect(item(paths[0])).toBeFocused();
  note('Keyboard and menu reorder retain focus');
  await item(paths[0]).press('Home');
  await expect(item(paths[1])).toHaveAttribute('aria-selected', 'true');
  await expect(page.locator('.editor-host[data-status=loading]')).toHaveCount(0);
  await expect(item(paths[1])).toBeFocused();
  await page.keyboard.press('ArrowLeft'); await expect(item(paths[0])).toHaveAttribute('aria-selected', 'true');
  await page.keyboard.press('ArrowRight'); await expect(item(paths[1])).toHaveAttribute('aria-selected', 'true');
  await page.keyboard.press('Control+Shift+Tab'); await expect(page.getByRole('region', { name: 'Home', exact: true })).toBeVisible();
  await page.keyboard.press('Control+Tab'); await expect(item(paths[1])).toHaveAttribute('aria-selected', 'true');
  await item(paths[1]).press('Shift+F10'); await expect(page.getByRole('menuitem', { name: /Move left/ })).toBeDisabled();
  await page.keyboard.press('Escape'); await expect(item(paths[1])).toBeFocused();
  note('Home/End/wrapping arrows, portable Control+Tab, disabled edge move and asynchronous editor focus');
  const target = await item(paths[2]).boundingBox();
  await drag(paths[1], target.x + target.width - 4, target.y + 16);
  await page.evaluate((id) => document.querySelector(`[data-tab-id=${JSON.stringify(id)}] .doc-close`).click(), idFor(paths[1]));
  await page.mouse.up(); await expect(page.locator('.is-dragging')).toHaveCount(0); await expect(item(paths[1])).toHaveCount(0);
  const primary = await page.evaluate(() => /mac/i.test(navigator.platform)) ? 'Meta' : 'Control';
  await page.keyboard.press(`${primary}+Shift+t`); await expect(item(paths[1])).toHaveAttribute('aria-selected', 'true');
  await expect.poll(order).toEqual(stable);
  const pen = await page.context().newCDPSession(page), a = await item(paths[1]).boundingBox(), b = await item(paths[2]).boundingBox();
  await pen.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: a.x + 30, y: a.y + 16, pointerType: 'pen' });
  await pen.send('Input.dispatchMouseEvent', { type: 'mousePressed', x: a.x + 30, y: a.y + 16, button: 'left', buttons: 1, clickCount: 1, pointerType: 'pen' });
  await pen.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: b.x + b.width - 4, y: b.y + 16, buttons: 1, pointerType: 'pen' });
  await expect(page.locator('.is-dragging')).toBeVisible(); await page.keyboard.press('Escape');
  await pen.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: b.x + b.width - 4, y: b.y + 16, button: 'left', buttons: 0, clickCount: 1, pointerType: 'pen' });
  expect(await order()).toEqual(stable); note('Removed drag source cleans up; pen threshold and cancellation use the same lifecycle');
  for (const path of paths.slice(3)) await open(path);
  await fullyVisible(); await expect(page.getByRole('button', { name: 'Scroll tabs right', exact: true })).toBeDisabled(); await shot('05-overflow-last-tab');
  const s = page.locator('.doc-tabs'); await s.hover(); const scrollStart = await s.evaluate((el) => el.scrollLeft); await page.mouse.wheel(0, -900);
  await expect.poll(() => s.evaluate((el) => el.scrollLeft)).toBeLessThan(scrollStart);
  expect(await selected()).toBe(idFor(paths.at(-1)));
  const manual = await s.evaluate((el) => el.scrollLeft); await page.waitForTimeout(200); expect(await s.evaluate((el) => el.scrollLeft)).toBe(manual);
  await page.mouse.wheel(300, 0); await expect.poll(() => s.evaluate((el) => el.scrollLeft)).toBeGreaterThan(manual);
  const zoom = await s.evaluate((el) => el.scrollLeft); await s.dispatchEvent('wheel', { deltaY: 200, ctrlKey: true }); expect(await s.evaluate((el) => el.scrollLeft)).toBe(zoom);
  await page.getByRole('button', { name: 'Scroll tabs left', exact: true }).click();
  await page.getByRole('button', { name: /^Open documents \(/ }).click(); await expect(page.getByRole('textbox', { name: 'Search open documents' })).toBeFocused(); await shot('06-open-document-picker');
  await page.getByRole('textbox', { name: 'Search open documents' }).fill('/Shared/experiments'); await expect(page.locator('.tab-picker-row')).toHaveCount(1); await shot('07-picker-filtered-path');
  await page.keyboard.press('ArrowDown'); await page.keyboard.press('Enter'); expect(await selected()).toBe(idFor(paths[7])); await fullyVisible();
  await s.hover(); await page.mouse.wheel(0, -1500);
  await page.getByRole('button', { name: /^Open documents \(/ }).click();
  await page.getByRole('textbox', { name: 'Search open documents' }).fill('/Shared/experiments'); await page.keyboard.press('Enter'); await fullyVisible();
  await page.getByRole('button', { name: /^Open documents \(/ }).click(); await page.getByRole('textbox', { name: 'Search open documents' }).fill('no-such-document');
  await expect(page.getByText(/No open documents match/)).toBeVisible(); await shot('08-picker-no-results'); await page.keyboard.press('Escape');
  await expect(page.getByRole('button', { name: /^Open documents \(/ })).toBeFocused();
  await page.setViewportSize({ width: 1050, height: 800 }); await fullyVisible(); await page.setViewportSize({ width: 1480, height: 960 }); await fullyVisible();
  note('Overflow wheel/trackpad/zoom/buttons, picker path search, empty results and resize');
  await reveal(paths[1]); await fullyVisible(); const box = await s.boundingBox();
  await drag(paths[1], box.x + box.width - 5, box.y + 18); const edgeStart = await s.evaluate((el) => el.scrollLeft);
  await expect.poll(() => s.evaluate((el) => el.scrollLeft)).toBeGreaterThan(edgeStart + 200);
  await expect(page.locator('.tab-drop-marker')).toBeVisible();
  expect(await page.locator('.tab-drop-marker').evaluate((el) => { const r = el.getBoundingClientRect(), s = document.querySelector('.doc-tabs').getBoundingClientRect(); return r.left >= s.left && r.right <= s.right + 1; })).toBe(true);
  await shot('09-edge-autoscroll'); await page.mouse.up();
  note('Stationary edge drag keeps scrolling');
  await reveal(paths[0]); await item(paths[0]).click({ button: 'right' }); await page.getByRole('menuitem', { name: 'Close others', exact: true }).click();
  await expect(page.locator('[data-tab-id]')).toHaveCount(1); for (const path of paths.slice(1, 3)) await open(path);
  await reveal(paths[1]); await item(paths[2]).locator('.doc-close').click(); expect(await selected()).toBe(idFor(paths[1]));
  const mod = await page.evaluate(() => /mac/i.test(navigator.platform)) ? 'Meta' : 'Control';
  await page.keyboard.press(`${mod}+Shift+t`); await expect(item(paths[2])).toHaveAttribute('aria-selected', 'true');
  await reveal(paths[1]); await item(paths[1]).locator('.doc-close').click(); await expect(item(paths[2])).toHaveAttribute('aria-selected', 'true');
  await item(paths[2]).click({ button: 'middle' }); await expect(item(paths[0])).toHaveAttribute('aria-selected', 'true'); await shot('10-adjacent-close-and-recovery');
  note('Active/inactive/middle close and reopen at prior position');
  await open(paths[1]); const content = page.locator('.cm-content').last(); await content.click(); await page.keyboard.press('End'); await page.keyboard.insertText(' # immediate-draft');
  await page.evaluate(() => document.querySelector('.doc-tab[aria-selected=true] .doc-close').click());
  const saved = await page.evaluate((path) => JSON.parse(localStorage.getItem(`coding-agent:draft:v1:${path}`) || 'null'), paths[1]); expect(saved.text).toContain('immediate-draft');
  await page.keyboard.press(`${mod}+Shift+t`); await expect(page.getByText('You have unsaved changes from earlier.')).toBeVisible();
  await page.getByRole('button', { name: 'Restore', exact: true }).click(); await expect(page.locator('.cm-content')).toContainText('immediate-draft'); await shot('11-restored-plain-file-draft');
  await open(paths[2]); await reveal(paths[1]);
  await page.getByRole('button', { name: 'Tab actions', exact: true }).click();
  await page.keyboard.press('Escape'); await expect(page.getByRole('button', { name: 'Tab actions', exact: true })).toBeFocused();
  await page.getByRole('button', { name: 'Tab actions', exact: true }).click();
  await page.getByRole('menuitem', { name: 'Close to the right', exact: true }).click();
  await expect(page.locator('[data-tab-id]')).toHaveCount(2); expect(await selected()).toBe(idFor(paths[1]));
  await page.keyboard.press(`${mod}+w`); await expect(item(paths[0])).toHaveAttribute('aria-selected', 'true');
  await page.keyboard.press(`${mod}+Shift+t`); await expect(item(paths[1])).toHaveAttribute('aria-selected', 'true');
  await page.evaluate(() => { location.hash = '#/file/Workspace/Repos/demo/databricks.yml'; });
  await expect(page.locator('[data-tab-id]')).toHaveCount(2);
  note('Tap/click actions, invoking-control focus return, close-to-right, close shortcut and canonical deduplication');
  note('Immediate file close flushes draft; explicit recovery restores latest text');
  await item(paths[1]).click({ button: 'right' }); await page.getByRole('menuitem', { name: 'Close all', exact: true }).click();
  await expect(page.locator('.doc-tabs')).toHaveCount(0); await expect(page.getByRole('region', { name: 'Home', exact: true })).toBeFocused();
  await page.keyboard.press(`${mod}+Shift+t`); await expect(page.locator('[data-tab-id]')).toHaveCount(1); note('Bulk/last close focus and reopen after strip unmount');
  await open('/Shared/denied.sql'); await expect(page.getByRole('alert')).toContainText('Permission denied'); await item('/Shared/denied.sql').press('Alt+Shift+ArrowLeft'); await item('/Shared/denied.sql').press('Delete');
  await open('main.demo.orders', 'table'); await expect(page.locator('.viewer')).toBeVisible(); note('Denied read stays movable/closable; table shares navigation'); await browser.close();
  for (const [width,height,colorScheme,name] of [[1480,960,'dark','12-wide-dark'],[760,540,'light','13-tablet-landscape'],[390,844,'light','14-mobile-light'],[390,844,'dark','15-mobile-dark']]) {
    await startPage(chromium, { viewport: { width, height }, colorScheme }); for (const path of paths.slice(0, 6)) await open(path); await fullyVisible(); await shot(name);
    await page.getByRole('button', { name: /^Open documents \(/ }).click(); await shot(`${name}-picker`); await page.keyboard.press('Escape'); await browser.close();
  }
  note('Light/dark wide/tablet/mobile layouts and pickers under reduced motion');
  await startPage(chromium, { viewport: { width: 760, height: 700 }, hasTouch: true }); for (const path of paths.slice(0, 6)) await open(path);
  await reveal(paths[1]); let rect = await item(paths[1]).boundingBox(); const cdp = await page.context().newCDPSession(page);
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: rect.x + 40, y: rect.y + 18 }] }); await page.waitForTimeout(300);
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: rect.x + 190, y: rect.y + 18 }] }); await expect(page.locator('.is-dragging')).toBeVisible(); await shot('16-touch-reorder');
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] }); await expect(page.locator('.is-dragging')).toHaveCount(0);
  const touchOrder = await order(); await reveal(paths[2]); rect = await item(paths[2]).boundingBox(); const sx = Math.min(rect.x + 50, 450), sy = rect.y + 18;
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: sx, y: sy }] }); await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: sx - 60, y: sy }] }); await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  expect(await order()).toEqual(touchOrder); await expect(page.locator('.is-dragging')).toHaveCount(0); note('Emulated native touch hold reorders; swipe preserves order');
  await reveal(paths[2]); await page.getByRole('button', { name: 'Tab actions', exact: true }).tap();
  await shot('16-touch-actions');
  const tapOrder = await order(); const left = page.getByRole('menuitem', { name: /Move left/ });
  await (await left.isEnabled() ? left : page.getByRole('menuitem', { name: /Move right/ })).tap();
  expect(await order()).not.toEqual(tapOrder); note('Touch users can reorder with taps alone through visible tab actions');
  await browser.close();
  for (const [engine,name] of [[firefox,'17-firefox'],[webkit,'18-webkit']]) {
    if (engine === firefox && process.env.TAB_E2E_SKIP_FIREFOX === '1') { unavailable.push({ engine: 'firefox', reason: 'Installed matching Firefox 159 cannot launch: Could not find profile folder. Two launch attempts ended; no further workaround attempted.' }); continue; }
    await startPage(engine); for (const path of paths.slice(0, 6)) await open(path); await reveal(paths[1]); const r = await item(paths[2]).boundingBox();
    await drag(paths[1], r.x + r.width - 4, r.y + 16); await page.mouse.up(); await item(paths[1]).focus(); await page.keyboard.press('Home'); await fullyVisible();
    await page.getByRole('button', { name: /^Open documents \(/ }).click(); await page.getByRole('textbox', { name: 'Search open documents' }).fill('package'); await page.keyboard.press('Enter'); await fullyVisible(); await shot(name); await browser.close(); note(`${name}: drag, keyboard reveal and picker selection`);
  }
  expect(errors, 'browser runtime errors').toEqual([]); expect(mutations, 'workspace mutation requests').toEqual([]); expect(unknown, 'unhandled fixtures').toEqual([]); note('No runtime errors, unhandled fixtures or workspace mutations');
} catch (e) { results.push({ name: 'E2E failure', ok: false, detail: e.stack || String(e) }); console.error(e); process.exitCode = 1; }
finally {
  await browser?.close();
  if (server && server.exitCode == null) { server.kill('SIGTERM'); await new Promise((r) => server.once('exit', r)); }
  writeFileSync(resolve(out, 'report.json'), JSON.stringify({ suite: 'tab-management', mode: 'real App + mocked HTTP boundary', results, screenshots, browserErrors: errors, workspaceMutations: mutations, unhandledFixtures: unknown, unavailable }, null, 2) + '\n');
}
