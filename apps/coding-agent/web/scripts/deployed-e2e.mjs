/**
 * End-to-end against the DEPLOYED app, as a signed-in user.
 *
 * The app sits behind Databricks SSO, so this script:
 *   1. opens the app in a real browser and waits for you to sign in (once per run),
 *   2. saves the session for the rest of the run,
 *   3. clicks a task card, waits for a terminal state, and screenshots it.
 *
 *   APP_URL=https://<app-url> node scripts/deployed-e2e.mjs <outdir>
 */
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const url = process.env.APP_URL;
if (!url) throw new Error("set APP_URL");
const out = process.argv[2] ?? "shots";
mkdirSync(out, { recursive: true });

const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH || undefined,
  headless: false,                 // SSO needs a visible window
});
const ctx = await browser.newContext({ viewport: { width: 1440, height: 940 } });
const page = await ctx.newPage();
const problems = [];
page.on("pageerror", (e) => problems.push(`pageerror: ${e}`));
page.on("console", (m) => { if (m.type() === "error") problems.push(`console: ${m.text()}`); });

console.log("opening", url, "- sign in if asked (120s)");
await page.goto(url, { waitUntil: "domcontentloaded" });
await page.waitForSelector(".card, .empty", { timeout: 120_000 });
console.log("signed in; the app rendered");
await page.screenshot({ path: `${out}/deployed-01-empty.png` });

const card = page.getByRole("button", { name: /Build a notebook/i });
await card.waitFor({ state: "visible", timeout: 30_000 });
await page.waitForTimeout(800);
await card.click();
await page.waitForFunction(() => document.querySelectorAll(".turn").length > 0, { timeout: 60_000 });
await page.screenshot({ path: `${out}/deployed-02-running.png` });
console.log("turn started");

// A turn may take minutes on a real model; wait for a terminal state.
await page.waitForFunction(() => !!document.querySelector(".evidence, .blocked"), { timeout: 420_000 })
  .catch(() => console.log("no terminal state within 7 min"));
await page.screenshot({ path: `${out}/deployed-03-terminal.png` });

const txt = async (sel) => (await page.locator(sel).first().innerText().catch(() => "(none)")).slice(0, 300);
console.log("strip   :", (await txt(".strip")).replace(/\n/g, " "));
console.log("evidence:", await page.locator(".evidence-row").count(), "rows");
console.log("blocked :", JSON.stringify(await txt(".blocked")));
console.log("tools   :", await page.locator(".tool .name").allInnerTexts());
console.log("problems:", problems.length ? problems : "none");
await browser.close();
