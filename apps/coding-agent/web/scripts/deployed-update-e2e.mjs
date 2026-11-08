/** "Update this notebook" on the DEPLOYED app: open it by link, ask from the notebook's own
 *  composer, and check what the user sees: the conversation, the progress, and the edit landing in
 *  the open notebook.
 *
 *   DATABRICKS_TOKEN=... APP_URL=... W=1100 node scripts/deployed-update-e2e.mjs
 * Screenshots: specs/006-databricks/e2e/update-open-notebook.
 */
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
const APP = process.env.APP_URL, TOKEN = process.env.DATABRICKS_TOKEN, W = Number(process.env.W ?? 1100);
const PATH = process.env.NB ?? "/Users/raphael.mansuy@gmail.com/agent_scratch/leibniz_pi";
const out = `../../../specs/006-databricks/e2e/update-open-notebook`;
mkdirSync(out, { recursive: true });
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: W, height: 760 }, deviceScaleFactor: 2,
  extraHTTPHeaders: { Authorization: `Bearer ${TOKEN}` } });
const p = await ctx.newPage();
const problems = [];
p.on("pageerror", (e) => problems.push(`pageerror: ${e}`));
p.on("response", (r) => { if (r.status() >= 400 && r.url().includes("/api/")) problems.push(`${r.status()} ${r.url().replace(APP, "")}`); });
const shot = async (n) => { await p.waitForTimeout(500); await p.screenshot({ path: `${out}/${W}-${n}.png` }); console.log("shot", n); };
await p.goto(`${APP}/#/notebook${PATH}`, { waitUntil: "load" });
await p.locator(".cell-block").first().waitFor({ timeout: 60000 });
const before = await p.locator(".cell-block").count();
await shot("1-open");
const box = p.locator("textarea").last();
const stamp = new Date().toISOString().slice(11, 19);
await box.fill(`Add a markdown cell at the end titled 'Note ${stamp}' with one sentence about the accuracy of the result.`);
await box.press("Enter");
await p.waitForTimeout(2500);
await shot("2-sent");
let last = "";
for (let i = 0; i < 60; i++) {
  await p.waitForTimeout(3000);
  const st = await p.evaluate(() => ({
    chip: document.querySelector(".session-chip")?.textContent ?? "",
    peek: document.querySelector(".session-peek")?.textContent ?? "",
    cells: document.querySelectorAll(".cell-block").length,
  }));
  const key = JSON.stringify([st.chip, st.peek, st.cells]);
  if (key !== last) { last = key; console.log(key); await shot(`3-progress-${i}`); }
  if (st.chip === "ready" && i > 3) break;
}
await p.waitForTimeout(2500);
const after = await p.locator(".cell-block").count();
console.log("agent-updated banner:", await p.locator(".agent-banner").count());
console.log("new note on screen:", (await p.getByText(`Note ${stamp}`).count()) > 0);
console.log("cells before/after:", before, after);
await shot("4-final");
console.log(problems.join("\n") || "no problems");
await browser.close();
