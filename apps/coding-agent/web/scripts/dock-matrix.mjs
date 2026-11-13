#!/usr/bin/env node
/** Spec 012 gate: every (width x rail x inspector x dock) cell, then the invariants below.
 *   npm run build && node scripts/dock-matrix.mjs        (WIDTHS=700,1000,... to narrow it; ~3 min for all)
 *  I1  a toggle that says "on" has a panel on screen, and vice versa
 *  I2  the centre of every visible panel hit-tests to that panel (nothing covers it)
 *  I3  a click on dead space inside a visible panel never changes which panels are visible
 *  I4  Escape pressed with focus inside a visible column-like panel never hides it */
import { chromium } from '@playwright/test';
import { localApp } from './mission-test-server.mjs';

const widths = (process.env.WIDTHS ?? '700,800,860,900,1000,1100,1150,1200,1300,1400,1480,1600,2000').split(',').map(Number);
const app = await localApp();
const browser = await chromium.launch();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const SEL = { rail: '.pane.rail', insp: '.pane.inspector', dock: '.pane.assistant' };

const snap = (p) => p.evaluate((SEL) => {
  const vis = (el) => { if (!el) return null; const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
    return r.width > 4 && r.height > 4 && cs.visibility !== 'hidden' && cs.display !== 'none' ? { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) } : null; };
  const out = {};
  for (const [k, s] of Object.entries(SEL)) {
    const el = document.querySelector(s);
    const r = vis(el);
    let hit = null;
    if (r) {
      const px = r.x + Math.min(r.w - 3, Math.max(3, r.w / 2)), py = r.y + r.h / 2;
      const top = document.elementFromPoint(px, py);
      hit = top && el.contains(top) ? 'self' : (top ? `${top.tagName.toLowerCase()}.${String(top.className).slice(0, 28)}` : 'none');
    }
    out[k] = { rect: r, hit, cls: el?.className.replace(/^pane\s+\w+\s*/, '') };
  }
  const pressed = (label) => document.querySelector(`.topbar [aria-label="${label}"]`)?.getAttribute('aria-pressed') ?? null;
  const btn = (re) => [...document.querySelectorAll('.topbar button[aria-pressed]')].find((b) => re.test(b.getAttribute('aria-label') || ''));
  out.toggles = { rail: btn(/navigator/i)?.getAttribute('aria-pressed'), dock: btn(/assistant/i)?.getAttribute('aria-pressed'), insp: btn(/inspector/i)?.getAttribute('aria-pressed') };
  out.main = vis(document.querySelector('main.pane.main'));
  return out;
}, SEL);
const shown = (s) => ['rail', 'insp', 'dock'].filter((k) => s[k].rect).join('+') || '-';

const problems = [];
const note = (w, combo, what) => { problems.push(`${w} ${combo}: ${what}`); };

for (const width of widths) {
  for (const rail of [true, false]) for (const insp of [true, false]) for (const dock of [true, false]) {
    const combo = `rail=${+rail} insp=${+insp} dock=${+dock}`;
    const ctx = await browser.newContext({ viewport: { width, height: 760 }, reducedMotion: 'reduce' });
    await ctx.addInitScript((l) => { localStorage.setItem('coding-agent:layout:v1', JSON.stringify({ version: 2, railWidth: 276, inspectorWidth: 340, assistantWidth: 380, railVisible: l.rail, inspectorVisible: l.insp, assistantVisible: l.dock, railTab: 'sessions' })); }, { rail, insp, dock });
    const p = await ctx.newPage(); p.setDefaultTimeout(5000);
    await p.goto(app.url); await p.waitForSelector('.topbar'); await sleep(250);
    const check = async (stage) => {
      const s = await snap(p);
      const tag = `[${stage}] shows ${shown(s)} toggles ${JSON.stringify(s.toggles)}`;
      for (const [k, t] of [['rail', 'rail'], ['dock', 'dock'], ['insp', 'insp']]) {
        const on = s.toggles[t] === 'true';
        if (on !== Boolean(s[k].rect)) note(width, combo, `${tag} I1 toggle ${k} says ${on} but panel ${s[k].rect ? 'visible' : 'absent'}`);
        if (s[k].rect && s[k].hit !== 'self') note(width, combo, `${tag} I2 ${k} centre is covered by ${s[k].hit}`);
      }
      if (s.main && s.main.w < 470) note(width, combo, `${tag} centre ${s.main.w}px < CENTRE_MIN`);
      return s;
    };
    let s = await check('initial');
    // Open the dock if it is not drawn, the way a user would.
    if (!s.dock.rect) { await p.keyboard.press('Meta+j'); await sleep(250); s = await check('after ⌘J'); }
    if (s.dock.rect) {
      const before = shown(s);
      const r = s.dock.rect;
      // Dead space: the gap in the header, right of the context chip.
      const head = await p.locator('.dock-head .dock-head-spacer').boundingBox();
      const pts = [[head.x + 1, head.y + head.height / 2], [r.x + r.w - 6, r.y + r.h - 70], [r.x + r.w / 2, r.y + r.h / 2]];
      for (const [x, y] of pts) {
        await p.mouse.click(x, y); await sleep(150);
        const a = await snap(p);
        if (shown(a) !== before) note(width, combo, `I3 click at (${Math.round(x)},${Math.round(y)}) in dock changed ${before} -> ${shown(a)}`);
        if (!a.dock.rect) break;
      }
      s = await snap(p);
      if (s.dock.rect) {
        const column = !/is-drawer/.test(s.dock.cls ?? '');
        await p.locator('.dock-body').click({ position: { x: 4, y: 4 } }).catch(() => {});
        await p.keyboard.press('Escape'); await sleep(200);
        const a = await snap(p);
        if (!a.dock.rect && column) note(width, combo, `I4 Escape hid a column dock (${s.dock.cls})`);
      }
    }
    await ctx.close();
  }
}
await browser.close(); await app.stop();
const uniq = [...new Set(problems)];
console.log(uniq.join('\n') || 'no violations');
console.log(`\n${uniq.length} violations`);
process.exit(uniq.length ? 1 : 0);
