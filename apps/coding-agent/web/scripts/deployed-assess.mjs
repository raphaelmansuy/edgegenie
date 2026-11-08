/** A real task on the DEPLOYED app, with a real model, watched the way a user would watch it.
 *
 *   DATABRICKS_TOKEN=... APP_URL=https://<app>.databricksapps.com node scripts/deployed-assess.mjs "<prompt>" [outdir]
 *
 * The bearer token stands in for the SSO session (the proxy accepts either), so this runs unattended.
 * It records what the user sees and what went wrong: console errors, failed requests, the transcript,
 * how long the first token took, and a screenshot at each stage.
 */
import { chromium } from "playwright";
import { mkdirSync, writeFileSync } from "node:fs";

const APP = process.env.APP_URL, TOKEN = process.env.DATABRICKS_TOKEN;
if (!APP || !TOKEN) throw new Error("set APP_URL and DATABRICKS_TOKEN");
const prompt = process.argv[2] ?? "Create a notebook that calculates pi with the Leibniz series, run it and show the result";
const out = process.argv[3] ?? "../../../specs/006-databricks/e2e/assess";
mkdirSync(out, { recursive: true });

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2,
  extraHTTPHeaders: { Authorization: `Bearer ${TOKEN}` } });
const p = await ctx.newPage();
const problems = [];
p.on("pageerror", (e) => problems.push(`pageerror: ${e}`));
p.on("console", (m) => { if (m.type() === "error") problems.push(`console: ${m.text().slice(0, 200)}`); });
p.on("response", (r) => { if (r.status() >= 400 && r.url().includes("/api/")) problems.push(`${r.status()} ${r.url().replace(APP, "")}`); });
const shot = async (n) => { await p.waitForTimeout(400); await p.screenshot({ path: `${out}/${n}.png` }); console.log("shot", n); };

await p.goto(APP, { waitUntil: "load" });
await p.waitForSelector(".topbar", { timeout: 60000 });
await shot("01-start");
const t0 = Date.now();
const box = p.getByRole("textbox").last();
await box.fill(prompt);
await box.press("Enter");
await p.waitForFunction(() => document.querySelectorAll(".turn").length > 0, null, { timeout: 45000 }).catch(async () => {
  await shot("02-no-turn"); console.log("NO TURN APPEARED\n" + problems.join("\n")); await browser.close(); process.exit(1);
});
let first = null;
const seen = new Set();
for (let i = 0; i < 100; i++) {                       // up to ~5 minutes
  await p.waitForTimeout(3000);
  const st = await p.evaluate(() => ({
    tools: [...document.querySelectorAll(".tool .name")].map((e) => e.textContent),
    answer: document.querySelector(".answer")?.textContent?.length ?? 0,
    running: Boolean(document.querySelector(".stop, [aria-label='Stop'], button.stop")),
    status: document.querySelector(".status, .pill")?.textContent ?? "",
    approvals: document.querySelectorAll(".approval, [role=dialog]").length,
  }));
  if (first === null && (st.tools.length || st.answer)) first = Date.now() - t0;
  const key = JSON.stringify([st.tools.length, st.answer > 0, st.approvals]);
  if (!seen.has(key)) { seen.add(key); await shot(`02-progress-${seen.size}`); }
  if (st.approvals) { console.log("approval asked"); }
  if (!st.running && i > 2 && (st.answer > 0 || st.tools.length > 0)) break;
}
console.log("first output after ms:", first, "total ms:", Date.now() - t0);
await shot("03-final");
const text = await p.evaluate(() => document.querySelector(".turn")?.parentElement?.innerText ?? document.body.innerText);
writeFileSync(`${out}/transcript.txt`, text);
console.log("--- transcript (first 3500 chars) ---\n" + text.slice(0, 3500));
console.log("--- problems ---\n" + (problems.join("\n") || "none"));
await browser.close();
