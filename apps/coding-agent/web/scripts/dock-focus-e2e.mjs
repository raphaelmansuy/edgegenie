#!/usr/bin/env node
/** Spec 012 — the assistant panel must take the pointer and the keyboard, working or not.
 *
 *   npm run build && node scripts/dock-focus-e2e.mjs
 *
 * Runs the real app against the disposable fake-agent server (mission-test-server.mjs) and asserts the
 * contracts of specs/012-panel-interaction/README.md §invariants: no layer over a panel that has a
 * column, a wheel that is never fought, a click on dead space that gives the panel focus, Escape that
 * only dismisses an overlay. Each block names the report it answers.
 */
import { chromium } from '@playwright/test';
import { localApp } from './mission-test-server.mjs';

process.env.MISSION_EVENT_DELAY ??= '0.25';              // a turn lasts ~4.5 s: long enough to act while it works
const app = await localApp();
const browser = await chromium.launch();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let failed = 0;
const check = (name, ok, detail = '') => { if (!ok) failed += 1; console.log(`  ${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ` — ${detail}` : ''}`); };

/** A page at `width`, with the layout the user left behind (dock visible or not). */
async function open(width, { dock = true, hash = '', height = 700 } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height }, reducedMotion: 'reduce' });
  await ctx.addInitScript((d) => localStorage.setItem('coding-agent:layout:v1', JSON.stringify({
    version: 2, railWidth: 276, inspectorWidth: 340, assistantWidth: 380, railVisible: true, inspectorVisible: false, assistantVisible: d, railTab: 'sessions' })), dock);
  const page = await ctx.newPage(); page.setDefaultTimeout(8000);
  const errors = []; page.on('pageerror', (e) => errors.push(e.message));
  await page.goto(`${app.url}/${hash}`); await page.waitForSelector('.topbar'); await sleep(200);
  return { ctx, page, errors };
}
const st = (p) => p.evaluate(() => {
  const d = document.querySelector('.pane.assistant'), b = document.querySelector('.dock-body');
  const a = document.activeElement;
  return {
    dock: Boolean(d && d.getBoundingClientRect().width > 4), cls: d?.className ?? '', state: d?.dataset.state,
    top: b ? Math.round(b.scrollTop) : -1, max: b ? Math.round(b.scrollHeight - b.clientHeight) : -1,
    scrims: document.querySelectorAll('.drawer-scrim').length,
    active: a ? (a.classList.contains('dock-body') ? 'log' : a.id === 'dock' ? 'aside' : a.tagName.toLowerCase()) : 'none',
  };
});
const settled = (p) => p.waitForFunction(() => document.querySelector('.pane.assistant')?.dataset.state === 'empty', null, { timeout: 40000 });
const streaming = (p) => p.waitForFunction(() => document.querySelector('.pane.assistant')?.dataset.state === 'streaming', null, { timeout: 15000 });
const say = async (p, text) => { const ta = p.locator('.composer textarea:visible').first(); await ta.fill(`${text} [[scenario:longrun]]`); await ta.press('Enter'); };

// A conversation with enough history to scroll: three finished turns, shared by every scene.
console.log('\n0. setup: a conversation with history');
const seed = await open(1500);
await say(seed.page, 'first');
const sid = await seed.page.waitForFunction(() => /session\/([^/?]+)/.exec(location.hash)?.[1], null, { timeout: 15000 }).then((h) => h.jsonValue());
for (let i = 0; i < 3; i++) { await streaming(seed.page); await settled(seed.page); if (i < 2) await say(seed.page, `again ${i}`); }
await seed.ctx.close();
console.log(`  session ${sid}`);
const HASH = `#/session/${sid}`;

// ---- 1. the report: open the dock with ⌘J at a width where it takes a column ----------------------
for (const width of [1500, 1200, 1150]) {
  console.log(`\n1. ${width}px: the dock was hidden, ⌘J opens it — nothing may cover it`);
  const { ctx, page: p, errors } = await open(width, { dock: false, hash: HASH });
  check('starts without the dock', !(await st(p)).dock);
  await p.keyboard.press('Meta+j'); await sleep(300);
  let s = await st(p);
  check('the dock is open as a column', s.dock && /dock-column/.test(s.cls), s.cls);
  check('no click-away layer exists over the window', s.scrims === 0, `scrims=${s.scrims}`);
  const hit = await p.evaluate(() => { const r = document.querySelector('.pane.assistant').getBoundingClientRect(); return !!document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2)?.closest('.pane.assistant'); });
  check('the panel itself is under the pointer', hit);
  const box = await p.locator('.dock-body').boundingBox();
  await p.mouse.click(box.x + box.width - 6, box.y + box.height - 6); await sleep(250);
  s = await st(p);
  check('a click inside the panel does not close it', s.dock, JSON.stringify(s));
  await p.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  const before = s.top; await p.mouse.wheel(0, -300); await sleep(250);
  check('the wheel scrolls the conversation', (await st(p)).top < before, `${before} -> ${(await st(p)).top}`);
  const edge = p.getByRole('button', { name: /Show the Chat panel/ });
  await p.keyboard.press('Meta+j'); await sleep(250);
  check('⌘J hides it again', !(await st(p)).dock);
  check('and the Chat edge handle brings it back', await edge.count() === 1 && (await edge.click(), await sleep(300), (await st(p)).dock && (await st(p)).scrims === 0));
  check('no page errors', errors.length === 0, errors.join('|'));
  await ctx.close();
}

// ---- 2. working: the reader's scroll position is theirs --------------------------------------------
for (const width of [1500, 1000, 760]) {
  console.log(`\n2. ${width}px: while the agent works, scrolling up must stick`);
  const { ctx, page: p } = await open(width, { hash: HASH });
  if (!(await st(p)).dock) { await p.keyboard.press('Meta+j'); await sleep(300); }
  await say(p, 'now'); await streaming(p);
  const box = await p.locator('.dock-body').boundingBox();
  await p.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await sleep(300);
  const tail = await st(p);
  await p.mouse.wheel(0, -60);                         // less than the old 80 px dead zone
  const samples = [];
  for (let i = 0; i < 6; i++) { await sleep(120); samples.push((await st(p)).top); }
  const held = samples.every((t) => t <= tail.top - 40);
  check('a 60 px scroll up is not pulled back by the stream', held, `${tail.top} -> ${samples.join(',')}`);
  check('the panel says how to resume', await p.locator('.dock-jump').isVisible(), '');
  check('the run is still going (this was measured while it worked)', (await st(p)).state === 'streaming');
  await p.mouse.wheel(0, -400); await sleep(200);
  const up = (await st(p)).top;
  await sleep(500);
  check('a bigger scroll up stays where it is', Math.abs((await st(p)).top - up) <= 2, `${up} -> ${(await st(p)).top}`);
  await p.locator('.dock-jump').click(); await sleep(300);
  const back = await st(p);
  check('"Follow the work" returns to the tail', back.max - back.top <= 24, JSON.stringify(back));
  check('and focus moves to the log instead of falling to the page', back.active === 'log', back.active);
  await settled(p);
  await ctx.close();
}

// ---- 3. the whole panel scrolls, and a click gives it the keyboard --------------------------------
for (const width of [1500, 1000]) {
  console.log(`\n3. ${width}px: the pointer anywhere on the panel scrolls it; a click focuses it`);
  const { ctx, page: p } = await open(width, { hash: HASH });
  if (!(await st(p)).dock) { await p.keyboard.press('Meta+j'); await sleep(300); }
  await sleep(300);
  const top0 = (await st(p)).top;
  const head = await p.locator('.dock-head').boundingBox();
  await p.mouse.move(head.x + head.width / 2, head.y + head.height / 2); await p.mouse.wheel(0, -250); await sleep(250);
  const top1 = (await st(p)).top;
  check('the wheel over the HEADER scrolls the conversation', top1 < top0, `${top0} -> ${top1}`);
  const rs = p.locator('.pane.assistant .run-status');
  if (await rs.count()) {
    const rb = await rs.boundingBox(); await p.mouse.move(rb.x + 30, rb.y + 10); await p.mouse.wheel(0, -250); await sleep(250);
    check('the wheel over the STATUS CARD scrolls the conversation', (await st(p)).top < top1, `${top1} -> ${(await st(p)).top}`);
  }
  await p.locator('.composer textarea:visible').first().focus();
  await p.mouse.click(head.x + head.width / 2, head.y + 12); await sleep(150);   // dead space in the header
  let s = await st(p);
  check('a click on the header focuses the conversation log', s.active === 'log', s.active);
  const t = s.top;
  await p.keyboard.press('PageUp'); await sleep(250);
  check('PageUp then scrolls it', (await st(p)).top < t, `${t} -> ${(await st(p)).top}`);
  await p.keyboard.press('Escape'); await sleep(200);
  check('Escape with the log focused does not hide a docked panel', (await st(p)).dock);
  await ctx.close();
}

// ---- 4. Escape dismisses an overlay, never a column ------------------------------------------------
console.log('\n4. Escape');
{
  const { ctx, page: p } = await open(1000, { dock: false, hash: HASH });
  await p.keyboard.press('Meta+j'); await sleep(300);
  let s = await st(p);
  check('900–1135 px: the dock opens as the focus column', s.dock && /dock-column/.test(s.cls) && s.scrims === 0, s.cls);
  await p.locator('.dock-body').click({ position: { x: 24, y: 6 } }); await p.keyboard.press('Escape'); await sleep(250);
  check('Escape does not hide the focus column', (await st(p)).dock);
  await ctx.close();
}
{
  const { ctx, page: p } = await open(700, { dock: false, hash: HASH });
  await p.keyboard.press('Meta+j'); await sleep(300);
  let s = await st(p);
  check('700 px: the dock opens as an overlay with a transparent click-away layer', s.dock && /is-drawer/.test(s.cls) && s.scrims === 1, `${s.cls} scrims=${s.scrims}`);
  const box = await p.locator('.dock-body').boundingBox();
  await p.mouse.click(box.x + box.width / 2, box.y + 8); await sleep(250);
  check('a click inside the overlay keeps it open', (await st(p)).dock);
  await p.mouse.move(box.x + box.width / 2, box.y + 40); await p.mouse.wheel(0, -200); await sleep(250);
  check('the wheel scrolls the overlay', (await st(p)).top < s.top, `${s.top} -> ${(await st(p)).top}`);
  await p.mouse.click(20, 400); await sleep(250);
  check('a click outside the overlay dismisses it, and the layer goes with it', !(await st(p)).dock && (await st(p)).scrims === 0, JSON.stringify(await st(p)));
  await p.keyboard.press('Meta+j'); await sleep(300);
  await p.locator('.dock-body').click({ position: { x: 24, y: 6 } }); await p.keyboard.press('Escape'); await sleep(250);
  check('Escape dismisses the overlay', !(await st(p)).dock && (await st(p)).scrims === 0);
  await ctx.close();
}

// ---- 5. a navigator drawer that outlives its reason must not dim a column ---------------------------
console.log('\n5. the navigator drawer left open when the dock closes');
{
  const { ctx, page: p } = await open(1000, { dock: false, hash: HASH });
  await p.keyboard.press('Meta+j'); await sleep(300);                      // focus dock: the navigator yields
  await p.getByRole('button', { name: 'Show the navigator' }).click(); await sleep(300);
  check('the navigator comes back as a dimming drawer', await p.locator('nav.rail.is-drawer').count() === 1 && (await st(p)).scrims === 1);
  await p.keyboard.press('Meta+j'); await sleep(300);                      // hide the assistant
  const s = await p.evaluate(() => ({ column: !!document.querySelector('nav.rail:not(.is-drawer)'), scrims: document.querySelectorAll('.drawer-scrim').length }));
  check('the navigator is a column again and nothing dims the window', s.column && s.scrims === 0, JSON.stringify(s));
  await ctx.close();
}

await browser.close(); await app.stop();
console.log(failed ? `\n${failed} failed` : '\nall passed');
process.exit(failed ? 1 : 0);
