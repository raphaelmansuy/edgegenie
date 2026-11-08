/** On the DEPLOYED app: the user keeps scrolling and the caret stays while the real agent edits the notebook.
 *   DATABRICKS_TOKEN=... APP_URL=... node scripts/deployed-scroll-e2e.mjs */
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
const APP = process.env.APP_URL, TOKEN = process.env.DATABRICKS_TOKEN;
const PATH = process.env.NB ?? "/Users/raphael.mansuy@gmail.com/agent_scratch/tall_demo";
const out = process.env.OUT ?? "../../../specs/006-databricks/e2e/keyboard-scroll";
mkdirSync(out, { recursive: true });
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2, extraHTTPHeaders: { Authorization: `Bearer ${TOKEN}` } });
const p = await ctx.newPage();
const problems = [];
p.on("pageerror", (e) => problems.push(`pageerror: ${e}`));
let failed = 0;
const check = (n, ok, d = "") => { if (!ok) failed++; console.log(`  ${ok ? "PASS" : "FAIL"} ${n}${d ? " — " + d : ""}`); };
await p.goto(`${APP}/#/notebook${PATH}`, { waitUntil: "load" });
await p.locator(".cell-block").first().waitFor({ timeout: 60000 });
await p.waitForTimeout(2500);
const st = () => p.evaluate(() => {
  const c = document.querySelector(".cells"); const a = document.activeElement, cell = a?.closest(".cell-block");
  return { scroll: Math.round(c.scrollTop), max: c.scrollHeight - c.clientHeight, cells: document.querySelectorAll(".cell-block").length,
    cell: cell ? Number(cell.dataset.cell) : 0, inText: !!a?.closest?.(".cm-content"), doc: document.scrollingElement.scrollTop,
    chip: document.querySelector(".session-chip")?.textContent ?? "" };
});
const before = await st();
const stamp = new Date().toISOString().slice(11, 19);
const box = p.locator("textarea").last();
await box.fill(`Append a markdown cell at the very end titled 'Scroll test ${stamp}' with one sentence. Do not change anything else.`);
await box.press("Enter");
await p.waitForTimeout(2000);
// While the agent works, keep reading: wheel down, and up, continuously.
await p.mouse.move(600, 450);
let jumps = 0, moves = 0, lastMax = (await st()).max, last = (await st()).scroll, dir = 1, sawBanner = false, working = true;
for (let i = 0; i < 150 && working; i++) {
  await p.mouse.wheel(0, 90 * dir); await p.waitForTimeout(450);
  const s = await st();
  const delta = s.scroll - last;
  if (delta !== 0) moves++;
  // A jump is movement AGAINST the direction the user is wheeling, or a large leap beyond the wheel.
  // Content that shrank or grew under the reader moves scrollTop by itself (the browser clamps it):
  // only count a jump when the document's length did not change in the same tick.
  const stable = Math.abs(s.max - lastMax) < 50;
  if (stable && Math.sign(delta) === -dir && Math.abs(delta) > 4) jumps++;
  if (stable && Math.abs(delta) > 400) jumps++;
  last = s.scroll; lastMax = s.max;
  if (s.scroll >= s.max - 5) dir = -1;
  if (s.scroll <= 5) dir = 1;
  if (await p.locator(".agent-banner").count()) sawBanner = true;
  working = !(i > 6 && s.chip === "ready");
  if (i % 20 === 0) console.log("  tick", i, JSON.stringify(s));
}
for (let i = 0; i < 60 && (await st()).chip !== "ready"; i++) await p.waitForTimeout(3000);
await p.waitForTimeout(4000);
const after = await st();
await p.screenshot({ path: `${out}/deployed-while-agent-works.png` });
console.log({ before, after, moves, jumps });
check("the notebook scrolled throughout the agent's run", moves > 10, `moves=${moves}`);
check("no jumps against the user's wheel", jumps === 0, `jumps=${jumps}`);
check("the agent's cell arrived on screen", after.cells > before.cells, `${before.cells} -> ${after.cells}`);
check("the banner announced it", sawBanner || (await p.locator(".agent-banner").count()) > 0);
check("the app shell never scrolled", after.doc === 0);
await p.locator(".agent-banner button", { hasText: "Show" }).click().catch(() => {});
await p.waitForTimeout(1500);
const shown = await p.evaluate(() => { const c = document.querySelector(".cells"); const t = [...document.querySelectorAll(".cell-block.is-agent-changed")][0]; if (!t) return -1; const r = t.getBoundingClientRect(), cr = c.getBoundingClientRect(); return r.top >= cr.top - 2 && r.bottom <= cr.bottom + 2 ? 1 : 0; });
check("Show brings the changed cell into view", shown === 1, String(shown));
await p.screenshot({ path: `${out}/deployed-show.png` });
check("no page errors", problems.length === 0, problems.join(" | "));
await browser.close();
console.log(failed ? `${failed} failed` : "all passed");
