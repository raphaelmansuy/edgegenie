/** Check a RUNNING app (local or deployed) in a browser: start a turn, wait for a terminal state,
 *  screenshot it, and report what the user sees. Usage: APP_URL=... node scripts/deployed-check.mjs <outdir> */
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { setTimeout as sleep } from "node:timers/promises";

const url = process.env.APP_URL ?? "http://127.0.0.1:8020";
const out = process.argv[2] ?? "shots";
mkdirSync(out, { recursive: true });
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || undefined });
const page = await browser.newPage({ viewport: { width: 1440, height: 940 }, deviceScaleFactor: 1.5 });
const problems = [];
page.on("pageerror", (e) => problems.push(`pageerror: ${e}`));
page.on("console", (m) => { if (m.type() === "error") problems.push(`console: ${m.text()}`); });

await page.goto(url, { waitUntil: "domcontentloaded" });
const card = page.getByRole("button", { name: /Build a notebook/i });
await card.waitFor({ state: "visible", timeout: 30000 });
await page.waitForTimeout(800);
await card.click();
await page.waitForFunction(() => document.querySelectorAll(".turn").length > 0, { timeout: 30000 });
await page.screenshot({ path: `${out}/deployed-01-running.png` });
console.log("shot deployed-01-running");

// terminal state: evidence, blocked, or a failed turn with a reason
await page.waitForFunction(
  () => !!document.querySelector(".evidence, .blocked"),
  { timeout: 300000 },
).catch(() => console.log("no terminal panel within 5 min"));
await page.screenshot({ path: `${out}/deployed-02-terminal.png` });
console.log("shot deployed-02-terminal");

const txt = async (sel) => (await page.locator(sel).first().innerText().catch(() => "(none)")).slice(0, 260);
console.log("strip  :", await txt(".strip"));
console.log("blocked:", JSON.stringify(await txt(".blocked")));
console.log("evidence rows:", await page.locator(".evidence-row").count());
console.log("problems:", problems.length ? problems : "none");
await browser.close();
