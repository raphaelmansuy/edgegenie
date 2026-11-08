/** Measure the shell: zones, scrollers, focus, keyboard reach. Prints a report; writes a JSON file.
 *   APP_URL=http://127.0.0.1:8062 node scripts/shell-audit.mjs */
import { chromium } from "playwright";
import { writeFileSync, mkdirSync } from "node:fs";
const APP = process.env.APP_URL ?? "http://127.0.0.1:8062";
const OUT = process.env.OUT ?? "../../../specs/007-ux-ui-improve/e2e";
mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const p = await ctx.newPage();
await p.goto(APP, { waitUntil: "load" });
await p.locator(".home").waitFor({ timeout: 40000 });
await p.waitForTimeout(2000);

const report = { zones: {}, tabbables: [], noFocusStyle: [], scrollers: [], nesting: 0, shortcuts: [] };

report.zones = await p.evaluate(() => {
  const grab = (sel) => {
    const el = document.querySelector(sel);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    return { w: Math.round(r.width), h: Math.round(r.height), x: Math.round(r.left), overflowY: cs.overflowY, scrollH: el.scrollHeight, clientH: el.clientHeight };
  };
  return {
    topbar: grab(".topbar"), rail: grab(".pane.rail"), centre: grab(".pane.main"),
    dock: grab(".pane.assistant"), inspector: grab(".pane.inspector"), tabs: grab(".doc-tabs"),
    home: grab(".home"), body: { scrollW: document.documentElement.scrollWidth, innerW: innerWidth, scrollH: document.documentElement.scrollHeight, innerH: innerHeight },
  };
});

// Every tabbable: does focusing it produce a visible change? (outline, box-shadow, background, border)
report.tabbables = await p.evaluate(() => [...document.querySelectorAll("a[href], button, input, select, textarea, [tabindex]")]
  .filter((e) => e.tabIndex >= 0 && !e.disabled && e.offsetParent !== null)
  .map((e) => `${e.tagName.toLowerCase()}.${(e.className || "").toString().split(" ")[0] || "-"}`));
report.noFocusStyle = await p.evaluate(() => {
  const out = [];
  const items = [...document.querySelectorAll("a[href], button, input, select, textarea, [tabindex]")]
    .filter((e) => e.tabIndex >= 0 && !e.disabled && e.offsetParent !== null);
  for (const el of items) {
    el.focus();
    const cs = getComputedStyle(el);
    const visible = cs.outlineStyle !== "none" && parseFloat(cs.outlineWidth) > 0;
    const ring = cs.boxShadow !== "none" && cs.boxShadow !== "";
    if (!visible && !ring) out.push(`${el.tagName.toLowerCase()}.${(el.className || "").toString().split(" ")[0] || "-"} "${(el.textContent || el.getAttribute("aria-label") || "").trim().slice(0, 34)}"`);
  }
  return out.slice(0, 40);
});

// Scroll areas and whether the wheel over one chains to an ancestor.
report.scrollers = await p.evaluate(() => [...document.querySelectorAll("body *")].filter((e) => {
  const cs = getComputedStyle(e);
  return /(auto|scroll)/.test(cs.overflowY) && e.scrollHeight > e.clientHeight + 4;
}).map((e) => ({
  sel: `${e.tagName.toLowerCase()}.${(e.className || "").toString().split(" ").slice(0, 2).join(".")}`,
  scrollH: e.scrollHeight, clientH: e.clientHeight, overscroll: getComputedStyle(e).overscrollBehaviorY,
})));
report.nesting = await p.evaluate(() => {
  const areas = [...document.querySelectorAll("body *")].filter((e) => /(auto|scroll)/.test(getComputedStyle(e).overflowY) && e.scrollHeight > e.clientHeight + 4);
  return areas.filter((a) => areas.some((b) => b !== a && b.contains(a))).length;
});

report.shortcuts = await p.evaluate(() => [...document.querySelectorAll(".keys-sheet")].length);
writeFileSync(`${OUT}/shell-audit.json`, JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 1).slice(0, 6000));
await browser.close();
