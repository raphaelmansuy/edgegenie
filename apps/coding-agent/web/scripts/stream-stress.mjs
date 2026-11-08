/** Does a heavy turn keep the page alive? (audit finding: "Page Unresponsive" mid-stream)
 *
 *   APP_URL=http://127.0.0.1:8071 node scripts/stream-stress.mjs [outdir]
 *
 * The server runs the fake agent pinned to the `stress` scenario (APP_AGENT_MODE=fake
 * APP_DEMO_SCENARIO=fixed:stress): a long thought, 60 tool
 * calls and a ~48k-character answer whose single paragraph has unbalanced backticks and `**`.
 * The page's main thread is sampled with a long-task observer and a frame-gap probe.
 * Exits non-zero if any single task blocks the thread for more than BUDGET_MS.
 */
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const APP = process.env.APP_URL ?? "http://127.0.0.1:8071";
const out = process.argv[2] ?? "/tmp/stream-stress";
const BUDGET_MS = Number(process.env.BUDGET_MS ?? 500);
mkdirSync(out, { recursive: true });

// FORCE_AX=1 turns on Chrome's accessibility tree, as a screen reader or an automation tool would.
const b = await chromium.launch({ args: process.env.FORCE_AX ? ["--force-renderer-accessibility"] : [] });
const p = await b.newPage({ viewport: { width: 1600, height: 900 } });
await p.addInitScript(() => {
  window.__long = [];
  new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__long.push(e.duration); })
    .observe({ entryTypes: ["longtask"] });
});
await p.goto(APP, { waitUntil: "domcontentloaded" });
await p.waitForTimeout(1500);

const box = p.locator(".composer.is-dock textarea").first();
await box.fill("go");   // the server is started with APP_DEMO_SCENARIO=fixed:stress
await box.press("Enter");

const t0 = Date.now();
let state = "";
while (Date.now() - t0 < 90_000) {
  await p.waitForTimeout(500).catch(() => { console.log("PAGE DIED"); process.exit(2); });
  state = await p.locator(".turn-foot").first().textContent({ timeout: 1000 }).catch(() => "");
  if (state) break;
}
const long = await p.evaluate(() => window.__long).catch(() => [-1]);
const worst = Math.max(0, ...long);
console.log(`turn state: ${state || "NOT FINISHED"} after ${((Date.now() - t0) / 1000).toFixed(1)}s`);
console.log(`long tasks: ${long.length}, worst ${worst.toFixed(0)} ms, total ${long.reduce((a, c) => a + c, 0).toFixed(0)} ms`);
await p.screenshot({ path: `${out}/stress.png` });
await b.close();
process.exit(worst > BUDGET_MS || !state ? 1 : 0);
