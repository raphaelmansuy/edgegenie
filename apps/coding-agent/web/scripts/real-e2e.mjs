/** End-to-end against a running app with a REAL model and tools: asks a data question,
 *  waits for the turn to finish, and reports what actually happened. */
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
const url = process.env.APP_URL ?? "http://127.0.0.1:8050";
const out = process.argv[2] ?? "/tmp/real";
mkdirSync(out, { recursive: true });
const b = await chromium.launch({ executablePath: process.env.CHROME_PATH || undefined });
const p = await b.newPage({ viewport: { width: 1440, height: 940 }, deviceScaleFactor: 2 });
const problems = [];
p.on("pageerror", (e) => problems.push(String(e)));
p.on("console", (m) => { if (m.type() === "error") problems.push(m.text()); });
await p.goto(url, { waitUntil: "domcontentloaded" });
const card = p.getByRole("button", { name: new RegExp(process.env.CARD ?? "Investigate a number", "i") });
await card.waitFor({ state: "visible", timeout: 20000 });
await p.waitForTimeout(800);
await card.click();
await p.waitForSelector(".turn", { timeout: 30000 });
// Ask something the workspace can actually answer, through the tools.
const box = p.getByRole("textbox", { name: /Message the agent/i });
if (process.env.ASK) { await box.fill(process.env.ASK); await p.keyboard.press("Meta+Enter"); }
await p.screenshot({ path: `${out}/real-01-running.png` });
console.log("turn started; waiting for the model…");
await p.waitForFunction(() => !!document.querySelector(".evidence, .blocked"), { timeout: 300000 })
  .catch(() => console.log("no terminal state in 5 min"));
await p.screenshot({ path: `${out}/real-02-done.png` });
const t = async (s) => (await p.locator(s).first().innerText().catch(() => "(none)")).slice(0, 400);
console.log("strip   :", (await t(".strip")).replace(/\n/g, " "));
console.log("tools   :", await p.locator(".tool .name").allInnerTexts());
console.log("evidence:", await p.locator(".evidence-row").count());
console.log("answer  :", (await t(".answer")).replace(/\n/g, " ").slice(0, 300));
console.log("problems:", problems.length ? problems : "none");
await b.close();
