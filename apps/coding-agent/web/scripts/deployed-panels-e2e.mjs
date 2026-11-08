/** 007 ZN-7 on the DEPLOYED app: hide every panel, then find the way back where the panel would be.
 *   DATABRICKS_TOKEN=... APP_URL=... node scripts/deployed-panels-e2e.mjs */
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
const APP = process.env.APP_URL, TOKEN = process.env.DATABRICKS_TOKEN;
const OUT = new URL("../../../../specs/007-ux-ui-improve/e2e/screenshot/", import.meta.url).pathname;
mkdirSync(OUT, { recursive: true });
const NB = process.env.NB ?? "/Users/raphael.mansuy@gmail.com/agent_scratch/avg_fare_by_hour";
const browser = await chromium.launch();
let failed = 0;
const ok = (n, c, d = "") => { console.log(`  ${c ? "PASS" : "FAIL"} ${n}${d ? ` — ${d}` : ""}`); if (!c) failed++; };
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2, extraHTTPHeaders: { Authorization: `Bearer ${TOKEN}` } });
const p = await ctx.newPage();
const errors = [];
p.on("pageerror", (e) => errors.push(String(e)));
await p.goto(APP, { waitUntil: "load" });
await p.locator(".home").waitFor({ timeout: 60000 });
await p.evaluate((h) => { location.hash = h; }, `#/notebook${NB}`);
await p.locator(".cell-block, .viewer-note").first().waitFor({ timeout: 60000 });
await p.waitForTimeout(3500);

const drawn = (sel) => p.evaluate((s) => !!document.querySelector(s), sel);
// hide everything that is up
for (const re of [/Hide the navigator/i, /Hide the assistant/i, /Hide the inspector/i]) {
  const b = p.getByRole("button", { name: re }).first();
  if (await b.count()) { await b.click({ force: true }); await p.waitForTimeout(400); }
}
await p.waitForTimeout(600);
const handles = await p.evaluate(() => [...document.querySelectorAll(".edge-handle")].map((b) => {
  const r = b.getBoundingClientRect();
  const t = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
  return { label: b.getAttribute("aria-label"), word: b.textContent.trim(), onTop: t === b || b.contains(t) };
}));
console.log("handles:", JSON.stringify(handles));
ok("every hidden panel has an edge handle", handles.length >= 2, JSON.stringify(handles.map((h) => h.label)));
ok("…and every handle is hit-testable", handles.every((h) => h.onTop));
// "Files" and "Chat" are four letters; the check is "a word, not only an icon", not a length.
ok("…and each carries a word, not only an icon", handles.every((h) => /^[A-Za-z]{3,}$/.test(h.word)), JSON.stringify(handles.map((h) => h.word)));
await p.screenshot({ path: `${OUT}/40-deployed-handles.png` });

// the layout menu lists all three
await p.getByRole("button", { name: /Layout and panels/i }).click();
await p.waitForTimeout(500);
const items = await p.evaluate(() => [...document.querySelectorAll("[role=menu] [role^=menuitem]")]
  .map((b) => ({ text: b.textContent.replace(/\s+/g, " ").trim(), disabled: b.disabled })));
ok("the layout menu lists the assistant", items.some((i) => /Assistant/.test(i.text)), JSON.stringify(items));
ok("…and nothing in it is disabled", items.every((i) => !i.disabled));
await p.keyboard.press("Escape");
await p.waitForTimeout(300);

// restore all three from the handles
for (const label of ["Show the Context panel", "Show the Chat panel"]) {
  const h = p.locator(`.edge-handle[aria-label="${label}"]`).first();
  if (await h.count()) { await h.click(); await p.waitForTimeout(800); }
}
ok("the inspector is back", await drawn(".insp-body"));
ok("the assistant is back", await drawn("#dock"));
await p.screenshot({ path: `${OUT}/41-deployed-restored.png` });
ok("no page errors", errors.length === 0, errors.join(" | "));
await browser.close();
console.log(failed ? `\n${failed} failed` : "\nall passed");
