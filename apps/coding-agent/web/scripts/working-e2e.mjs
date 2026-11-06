/** Capture the app doing real work: describe → write → run, then the report. */
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
const url = process.env.APP_URL ?? "http://127.0.0.1:8050";
const out = process.argv[2] ?? "/tmp/working";
mkdirSync(out, { recursive: true });
const b = await chromium.launch({ executablePath: process.env.CHROME_PATH || undefined });
const p = await b.newPage({ viewport: { width: 1440, height: 940 }, deviceScaleFactor: 2 });
const problems = [];
p.on("pageerror", (e) => problems.push(String(e)));
p.on("console", (m) => { if (m.type() === "error") problems.push(m.text()); });
await p.goto(url, { waitUntil: "domcontentloaded" });
await p.waitForSelector(".card", { timeout: 20000 });
await p.waitForTimeout(700);
// Start a session from the empty state, then ask the question that works.
await p.locator(".card").first().click();
await p.waitForSelector(".turn", { timeout: 30000 });
const box = p.getByRole("textbox", { name: /Message the agent/i });
await box.fill("Using the dbx tools, how many rows are in samples.nyctaxi.trips? Show the SQL you ran.");
await p.keyboard.press("Meta+Enter");
console.log("asked; waiting for the report…");
await p.waitForFunction(() => !!document.querySelector(".evidence"), { timeout: 300000 })
  .catch(() => console.log("no evidence panel in 5 min"));
await p.waitForTimeout(800);
await p.screenshot({ path: `${out}/working-01-answer.png` });
// the evidence + tool trace
await p.locator(".tool-row").first().click().catch(() => {});
await p.waitForTimeout(400);
await p.screenshot({ path: `${out}/working-02-evidence.png` });
const t = async (s) => (await p.locator(s).first().innerText().catch(() => "(none)")).slice(0, 600);
console.log("tools   :", await p.locator(".tool .name").allInnerTexts());
console.log("evidence:", await p.locator(".evidence-row").count());
console.log("answer  :", (await t(".answer")).replace(/\n/g, " ").slice(0, 280));
console.log("problems:", problems.length ? problems : "none");
await b.close();
