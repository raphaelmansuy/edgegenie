/** Notebook document scenes. Asserts, then photographs.
 *
 *   node scripts/notebook-e2e.mjs
 *
 * Starts the app itself (fake agent) and mocks the workspace, so the pictures do not need a warehouse.
 * Screenshots: specs/010-notebook/e2e/screenshots/
 */
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { spawn } from "node:child_process";
import { setTimeout as sleep } from "node:timers/promises";

const out = new URL("../../../../specs/010-notebook/e2e/screenshots/", import.meta.url).pathname;
mkdirSync(out, { recursive: true });
const app = new URL("../../", import.meta.url).pathname;
const port = Number(process.env.PORT || 8094);
const base = `http://127.0.0.1:${port}`;

const NOTEBOOK = {
  objectId: "1", path: "/Users/you/map_demo", name: "map_demo", kind: "notebook",
  language: "SQL", size: 400, truncated: false, modifiedAt: 1, version: "v1", text: "",
  cells: [
    { index: 1, kind: "markdown", language: "markdown", source: "# Revenue by hour", truncated: false },
    { index: 2, kind: "code", language: "sql", source: "-- trips by hour\nselect period, trips, fare from demo", truncated: false },
    { index: 3, kind: "code", language: "sql", source: "%skip\nselect 1 as left_out", truncated: false },
    { index: 4, kind: "code", language: "sql", source: "select * from missing_table", truncated: false },
  ],
};

const TABLE = {
  state: "succeeded", seconds: 0.31, warehouse: "Serverless Starter", totalRows: 3,
  columns: ["period", "trips", "fare"],
  rows: [["morning", "40", "80.00"], ["evening", "10", "12.50"], ["night", "5", "9.00"]],
};

const start = spawn(process.env.PYTHON || `${app}.venv/bin/python`, ["-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", String(port)], {
  cwd: app,
  env: {
    ...process.env, APP_AGENT_MODE: "fake", APP_DEMO_SCENARIO: "notebook",
    APP_DEV_USER: "you@example.com", APP_DEFAULT_MODEL: "fake/model-a",
    APP_ALLOWED_MODELS: '["fake/model-a","fake/model-b"]',
  },
  stdio: "ignore",
});
for (let i = 0; i < 80; i++) {
  try { if ((await fetch(`${base}/api/health`)).ok) break; } catch { /* not up */ }
  if (i === 79) throw new Error("server did not start");
  await sleep(200);
}

const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || undefined });
const failures = [];
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "ok" : "FAIL"}  ${name}${detail ? ` — ${detail}` : ""}`);
  if (!ok) failures.push(name);
};

async function install(page) {
  await page.route("**/api/workspace**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const json = (body) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    if (path.endsWith("/roots")) {
      return json({ roots: [{ path: "/Users/you", name: "My home", kind: "directory" }] });
    }
    if (path.endsWith("/search")) {
      return json({ root: "/Users/you", complete: true, results: [
        { path: NOTEBOOK.path, name: "map_demo", kind: "notebook", language: "SQL" },
      ] });
    }
    if (path.endsWith("/object")) return json(NOTEBOOK);
    if (path.endsWith("/version")) return json({ path: url.searchParams.get("path"), version: "v1", modifiedAt: 1 });
    if (path.endsWith("/fence")) return json({ verdict: "allow", reason: "inside the working folder", approval: null });
    if (route.request().method() === "GET") {
      return json({ root: "/Users/you", node: {
        path: "/Users/you", name: "you", kind: "directory", hasChildren: true,
        children: [{ path: NOTEBOOK.path, name: "map_demo", kind: "notebook", language: "SQL", hasChildren: false }],
      } });
    }
    return route.continue();
  });
  await page.route("**/api/notebook/run-cell", async (route) => {
    const body = JSON.parse(route.request().postData() || "{}");
    const src = String(body.source || "");
    const result = src.includes("missing")
      ? { state: "failed", seconds: 0.18, error: "[TABLE_OR_VIEW_NOT_FOUND] missing_table" }
      : TABLE;
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(result) });
  });
}

async function openNotebook(page) {
  await page.goto(base, { waitUntil: "domcontentloaded" });
  const box = page.getByRole("textbox", { name: "Message the agent" });
  await box.waitFor({ timeout: 20000 });
  await box.fill("Show revenue by hour");
  await page.keyboard.press("Meta+Enter");
  await page.locator(".turn-foot").first().waitFor({ timeout: 30000 });
  await page.getByRole("tab", { name: /Files/i }).click();
  const search = page.getByPlaceholder("Search notebooks and files");
  await search.fill("map");
  const hit = page.locator(".result").first();
  await hit.waitFor({ timeout: 15000 });
  await hit.click();
  await page.locator(".nb-bar").waitFor({ timeout: 15000 });
  await page.locator(".cell-block").first().waitFor({ timeout: 15000 });
  const dismiss = page.getByRole("button", { name: "Dismiss" });
  if (await dismiss.count()) await dismiss.first().click();
  // The notebook is what we are proving. The inspector is a third column that turns every SQL line
  // into an ellipsis; hide it so the pictures show the cells themselves.
  const hideInspector = page.locator(".shell-toggle[aria-label='Hide the inspector']");
  if (await hideInspector.count()) await hideInspector.click();
  await page.waitForTimeout(200);
}

const overflow = (page) => page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 2);

const shot = async (page, name) => {
  await page.waitForTimeout(250);
  await page.screenshot({ path: `${out}${name}` });
  console.log("shot", name);
};

const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2, colorScheme: "light" });
const page = await context.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
await install(page);

try {
  await openNotebook(page);

  console.log("\n== S1 idle");
  const bars = await page.locator(".nb-map-bar").count();
  check("S1 map has one bar per code cell", bars === 3, String(bars));
  check("S1 Run all is visible", await page.getByRole("button", { name: "Run all" }).isVisible());
  check("S1 the bar says what it will skip", /skipped/.test(await page.locator(".nb-bar-status").innerText()), await page.locator(".nb-bar-status").innerText());
  await shot(page, "01-idle-1440.png");

  console.log("\n== S2 run all");
  await page.getByRole("button", { name: "Run all" }).click();
  await page.locator(".cell-output[data-state='failed']").waitFor({ timeout: 15000 });
  const states = await page.locator(".cell-output").evaluateAll((els) => els.map((e) => e.getAttribute("data-state")));
  check("S2 succeeded then failed", JSON.stringify(states) === JSON.stringify(["succeeded", "failed"]), states.join(","));
  const status = await page.locator(".nb-bar-status").innerText();
  check("S2 the bar counts the failure and the skip", /1 ran/.test(status) && /1 failed/.test(status) && /skipped/.test(status), status);
  check("S2 Fix with agent is on the failure", await page.getByRole("button", { name: /Fix with agent/ }).isVisible());
  const tones = await page.locator(".nb-map-bar").evaluateAll((els) => els.map((e) => e.getAttribute("data-tone")));
  check("S2 map tones are ok, skip, failed", JSON.stringify(tones) === JSON.stringify(["ok", "skip", "failed"]), tones.join(","));
  await page.locator(".cell-block").nth(3).evaluate((el) => el.scrollIntoView({ block: "nearest" }));
  await shot(page, "02-run-failed-1440.png");

  console.log("\n== S3 map list");
  await page.locator(".nb-map-pin").click();
  await page.locator(".nb-map-pop").waitFor({ timeout: 3000 });
  check("S3 the list names the failed cell", /missing_table/.test(await page.locator(".nb-map-pop").innerText()));
  check("S3 First failed is a button", await page.getByRole("button", { name: "First failed" }).isVisible());
  await shot(page, "03-map-open-1440.png");
  await page.getByRole("button", { name: "First failed" }).click();
  await page.getByRole("button", { name: "Hide the execution list" }).click();
  await page.locator(".nb-bar").hover();
  await page.waitForTimeout(200);

  console.log("\n== S4 filter");
  const filter = page.getByRole("textbox", { name: "Filter rows" });
  await filter.fill("night");
  check("S4 one row matches", /1 of 3/.test(await page.locator(".cell-filter-n").innerText()), await page.locator(".cell-filter-n").innerText());
  await page.locator(".cell-output").first().scrollIntoViewIfNeeded();
  await shot(page, "04-filter-1440.png");
  await filter.fill("");

  console.log("\n== S5 run menu");
  const cell = page.locator(".cell-block").nth(1);
  await cell.hover();
  await cell.getByRole("button", { name: /More ways to run cell/ }).click();
  const menu = page.locator(".cell-run-menu");
  await menu.waitFor({ timeout: 3000 });
  check("S5 above and below are both offered", /Run all above/.test(await menu.innerText()) && /Run all below/.test(await menu.innerText()));
  await page.locator(".cell-block").nth(1).scrollIntoViewIfNeeded();
  await shot(page, "05-run-menu-1440.png");
  await page.keyboard.press("Escape");

  console.log("\n== S6 command mode");
  await page.locator(".cell-block").nth(1).locator(".cell-gutter").click();
  await page.keyboard.press("h");
  await page.locator(".keys-sheet").waitFor({ timeout: 5000 });
  check("S6 the sheet lists command mode", /Merge with the cell below/.test(await page.locator(".keys-sheet").innerText()));
  await page.locator(".keys-sheet section[aria-label='Command mode']").evaluate((el) => {
    el.scrollIntoView({ block: "start" });
  });
  await shot(page, "06-shortcuts-1440.png");
  await page.keyboard.press("Escape");

  console.log("\n== S8 narrow");
  if (await page.locator(".cell-run-menu").count()) await page.keyboard.press("Escape");
  await page.setViewportSize({ width: 860, height: 900 });
  await page.waitForTimeout(300);
  check("S8 no horizontal overflow", !(await overflow(page)));
  await page.locator(".cell-output[data-state='failed']").evaluate((el) => el.scrollIntoView({ block: "start" }));
  const runBox = await page.getByRole("button", { name: "Run all" }).boundingBox();
  check("S8 Run all stays in view", Boolean(runBox && runBox.y >= 0 && runBox.y < 220), JSON.stringify(runBox));
  await shot(page, "08-narrow-860.png");
} finally {
  await context.close();
}

const dark = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2, colorScheme: "dark" });
await dark.addInitScript(() => localStorage.setItem("coding-agent:theme:v1", "dark"));
const dpage = await dark.newPage();
dpage.on("pageerror", (e) => errors.push(String(e)));
await install(dpage);
try {
  console.log("\n== S7 dark");
  await openNotebook(dpage);
  await dpage.getByRole("button", { name: "Run all" }).click();
  await dpage.locator(".cell-output[data-state='failed']").waitFor({ timeout: 15000 });
  await dpage.locator(".nb-map-pin").click();
  check("S7 dark has no horizontal overflow", !(await overflow(dpage)));
  const theme = await dpage.evaluate(() => document.documentElement.getAttribute("data-theme"));
  check("S7 the document is dark", theme === "dark", theme || "(none)");
  await shot(dpage, "07-dark-1440.png");
} finally {
  await dark.close();
}

await browser.close();
start.kill("SIGTERM");

if (errors.length) {
  console.log("\npage errors:");
  errors.slice(0, 8).forEach((e) => console.log(" ", e.split("\n")[0]));
  failures.push("pageerror");
}
console.log(failures.length ? `\n${failures.length} failed` : "\nall scenes passed");
process.exit(failures.length ? 1 : 0);
