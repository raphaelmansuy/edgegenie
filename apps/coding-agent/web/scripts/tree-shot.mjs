/** Screenshot the workspace tree: roots, expanded home, and a nested folder. */
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
const url = process.env.APP_URL ?? "http://127.0.0.1:8040";
const out = process.argv[2] ?? "/tmp/tree";
mkdirSync(out, { recursive: true });
const b = await chromium.launch({ executablePath: process.env.CHROME_PATH || undefined });
const p = await b.newPage({ viewport: { width: 1440, height: 940 }, deviceScaleFactor: 2 });
const problems = [];
p.on("pageerror", (e) => problems.push(String(e)));
p.on("console", (m) => { if (m.type() === "error") problems.push(m.text()); });
await p.goto(url, { waitUntil: "domcontentloaded" });
const card = p.getByRole("button", { name: /Build a notebook/i });
await card.waitFor({ state: "visible", timeout: 20000 });
await p.waitForTimeout(700);
await card.click();
await p.waitForSelector(".turn, .strip", { timeout: 30000 });
await p.getByRole("tab", { name: "Files" }).click();
await p.waitForTimeout(1200);
await p.screenshot({ path: `${out}/tree-01-roots.png` });
await p.locator(".tree-row").first().click();            // My home
await p.waitForTimeout(1200);
await p.screenshot({ path: `${out}/tree-02-home.png` });
const coding = p.locator(".tree-row", { hasText: "coding-agent" }).first();
if (await coding.count()) {
  await coding.click();
  await p.waitForTimeout(1500);
  await p.screenshot({ path: `${out}/tree-03-nested.png` });
}
console.log("rows:", await p.locator(".tree-row").count());
console.log("names:", (await p.locator(".tree-name").allInnerTexts()).slice(0, 10));
console.log("errors in tree:", await p.locator(".tree-error").allInnerTexts());
console.log("problems:", problems.length ? problems : "none");
await b.close();
