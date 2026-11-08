/** 007 on the DEPLOYED app: the same contract, a real token, a real agent.
 *   DATABRICKS_TOKEN=... APP_URL=... node scripts/deployed-shell-e2e.mjs */
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
const APP = process.env.APP_URL, TOKEN = process.env.DATABRICKS_TOKEN;
const OUT = new URL("../../../../specs/007-ux-ui-improve/e2e/screenshot/", import.meta.url).pathname;
mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch();
let failed = 0;
const ok = (n, c, d = "") => { console.log(`  ${c ? "PASS" : "FAIL"} ${n}${d ? ` — ${d}` : ""}`); if (!c) failed++; };
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2, extraHTTPHeaders: { Authorization: `Bearer ${TOKEN}` } });
const p = await ctx.newPage();
const errors = [];
p.on("pageerror", (e) => errors.push(String(e)));
const focus = () => p.evaluate(() => {
  const e = document.activeElement;
  return { tag: e?.tagName.toLowerCase(), cls: (e?.className || "").toString().split(" ")[0], id: e?.id || "", inMain: !!e?.closest?.("main") };
});
await p.goto(APP, { waitUntil: "load" });
await p.locator(".home").waitFor({ timeout: 60000 });
await p.waitForTimeout(2500);

console.log("\ndeployed: skip links and Tab budget");
await p.keyboard.press("Tab");
await p.waitForTimeout(400);
ok("the first Tab stop is a skip link", (await focus()).cls === "skip-link");
await p.screenshot({ path: `${OUT}/20-deployed-skip.png` });
await p.keyboard.press("Enter");
ok("Enter focuses the work region", (await focus()).id === "doc-panel", JSON.stringify(await focus()));

console.log("\ndeployed: dialogs return focus");
await p.evaluate(() => document.activeElement?.blur());
await p.getByRole("button", { name: /Search or run a command/i }).first().focus();
await p.keyboard.press("Meta+k");
await p.locator('[role="dialog"]').waitFor({ timeout: 8000 });
await p.keyboard.press("Escape");
await p.waitForTimeout(600);
ok("the palette returns focus to its opener", (await focus()).cls === "search-trigger", JSON.stringify(await focus()));
await p.screenshot({ path: `${OUT}/21-deployed-focus-return.png` });

console.log("\ndeployed: zones");
const z = await p.evaluate(() => {
  const w = (s) => { const e = document.querySelector(s); return e ? Math.round(e.getBoundingClientRect().width) : null; };
  return { rail: w(".pane.rail"), main: w(".pane.main"), dock: w(".pane.assistant"),
    page: document.documentElement.scrollWidth <= innerWidth, doc: document.scrollingElement.scrollTop };
});
ok("the centre has room", (z.main ?? 0) >= 480, JSON.stringify(z));
ok("no horizontal overflow", z.page);
ok("the page never scrolls", z.doc === 0);
await p.screenshot({ path: `${OUT}/22-deployed-zones.png` });
ok("no page errors", errors.length === 0, errors.join(" | "));
await browser.close();
console.log(failed ? `\n${failed} failed` : "\nall passed");
