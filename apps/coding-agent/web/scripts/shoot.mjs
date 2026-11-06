/**
 * Capture every UI state end to end, starting its own server per scenario so each
 * screenshot is honest about which agent behaviour it shows.
 *
 *   node scripts/shoot.mjs <outdir>
 *
 * Scenarios come from api/adapters/fake/scenarios/*.json (notebook, blocked, injection, slow).
 */
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { spawn } from "node:child_process";
import { setTimeout as sleep } from "node:timers/promises";

const out = process.argv[2] ?? "shots";
mkdirSync(out, { recursive: true });
const web = new URL("..", import.meta.url).pathname;
const app = new URL("../../", import.meta.url).pathname;
const port = 8010;

const startServer = async (scenario) => {
  const proc = spawn(`${app}.venv/bin/python`, ["-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", String(port)], {
    cwd: app,
    env: { ...process.env, APP_AGENT_MODE: "fake", APP_DEMO_SCENARIO: scenario,
      APP_DEV_USER: "you@example.com", APP_DEFAULT_MODEL: "fake/model-a",
      APP_ALLOWED_MODELS: '["fake/model-a","fake/model-b"]' },
    stdio: "ignore",
  });
  for (let i = 0; i < 60; i++) {
    try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) return proc; } catch { /* not up yet */ }
    await sleep(200);
  }
  throw new Error(`server did not start for ${scenario}`);
};

const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || undefined });

const newPage = async () => {
  // A fresh page per scenario. (A fresh BrowserContext also works, but plain pages are lighter and
  // the cursor key already includes the session id, so there is nothing to leak between sessions.)
  const page = await browser.newPage({ viewport: { width: 1440, height: 940 }, deviceScaleFactor: 1.5 });
  page.problems = [];
  page.on("pageerror", (e) => page.problems.push(`pageerror: ${e}`));
  page.on("console", (m) => { if (m.type() === "error") page.problems.push(`console: ${m.text()}`); });
  return page;
};
const shot = async (page, name, wait = 400) => {
  await page.waitForTimeout(wait);
  await page.screenshot({ path: `${out}/${name}.png` });
  console.log("shot", name);
};
const open = async (page, cardName) => {
  await page.goto(`http://127.0.0.1:${port}/`, { waitUntil: "domcontentloaded" });
  const card = page.getByRole("button", { name: cardName });
  await card.waitFor({ state: "visible", timeout: 20000 });
  await page.waitForTimeout(600);          // let the models fetch land, or the click does nothing
  await card.click();
  await page.waitForFunction(
    () => document.querySelectorAll(".turn, .evidence, .blocked").length > 0 ||
          document.querySelectorAll(".card").length === 0,
    { timeout: 25000 },
  )
    .catch(() => { throw new Error(`click on ${cardName} did nothing`); });
};

/** Wait until the visible turn reached a terminal state (evidence or blocked panel present). */
const finished = async (page) => {
  await page.waitForFunction(
    () => document.querySelector(".evidence, .blocked") !== null ||
          !!document.querySelector(".turn .who time")?.textContent?.includes("done"),
    { timeout: 30000 },
  ).catch(() => {});
  await page.waitForTimeout(300);
};

const problems = [];
// One server, several sessions: the demo agent chooses its behaviour from the prompt, so every
// state can be captured without restarting anything (which is also how a real deployment works).
const server = await startServer("notebook");
try {
  const page = await newPage();

  await page.goto(`http://127.0.0.1:${port}/`, { waitUntil: "domcontentloaded" });
  await shot(page, "01-empty");

  await open(page, /Build a notebook/i);
  await page.waitForSelector(".turn", { timeout: 25000 });
  await shot(page, "02-streaming", 600);
  await finished(page);
  await shot(page, "03-completed");
  await page.locator(".tool-row").first().click();
  await shot(page, "04-tool-expanded");
  await page.locator(".thought-toggle").first().click();
  await shot(page, "05-thinking");

  await page.setViewportSize({ width: 900, height: 940 });
  await shot(page, "06-narrow");
  console.log("horizontal overflow at 900px:",
    await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 2));
  await page.setViewportSize({ width: 1440, height: 940 });

  problems.push(...page.problems);
  await page.close();

  const blocked = await newPage();
  await open(blocked, /Investigate a number/i);
  await blocked.waitForSelector(".blocked", { timeout: 30000 });
  await shot(blocked, "07-blocked");
  problems.push(...blocked.problems);
  await blocked.close();

  const inj = await newPage();
  await open(inj, /Document tables/i);
  await finished(inj);
  await shot(inj, "08-injection-report");
  problems.push(...inj.problems);
  await inj.close();

  const run = await newPage();
  await open(run, /Create a job/i);
  await run.waitForSelector(".turn", { timeout: 25000 });
  await shot(run, "09-running-stop-visible", 150);
  const stop = run.getByRole("button", { name: /Stop/i });
  if (await stop.count()) { await stop.click(); await run.waitForTimeout(900); }
  await shot(run, "10-cancelled");
  problems.push(...run.problems);
  await run.close();
} finally {
  server.kill();
}

console.log("problems:", problems.length ? problems : "none");
await browser.close();
