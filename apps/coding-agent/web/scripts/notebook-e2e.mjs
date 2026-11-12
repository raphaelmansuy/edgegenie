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
import { deflateSync } from "node:zlib";

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

const PY_NOTEBOOK = {
  objectId: "2", path: "/Users/you/py_demo", name: "py_demo", kind: "notebook",
  language: "PYTHON", size: 600, truncated: false, modifiedAt: 1, version: "v1", text: "",
  cells: [
    { index: 1, kind: "markdown", language: "markdown", source: "# Trips, in Python", truncated: false },
    { index: 2, kind: "code", language: "python", source: "print('loading')\ndisplay(df)\ndisplayHTML('<h3>done</h3>')\nplt.plot(x)", truncated: false },
    { index: 3, kind: "code", language: "sql", source: "create table scratch (id int)", truncated: false },
    { index: 4, kind: "code", language: "sql", source: "select 1 as a;\nselect * from missing_table;\nselect 3 as c", truncated: false },
  ],
};
const NOTEBOOKS = { [NOTEBOOK.path]: NOTEBOOK, [PY_NOTEBOOK.path]: PY_NOTEBOOK };

/** A small PNG, so the plot has something to show. Built here, with no image library. */
function png(width, height) {
  const crc = (buf) => {
    let c, crcv = 0xffffffff;
    for (const b of buf) { c = (crcv ^ b) & 0xff; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; crcv = (crcv >>> 8) ^ c; }
    return (crcv ^ 0xffffffff) >>> 0;
  };
  const chunk = (type, data) => {
    const len = Buffer.alloc(4); len.writeUInt32BE(data.length);
    const body = Buffer.concat([Buffer.from(type), data]);
    const sum = Buffer.alloc(4); sum.writeUInt32BE(crc(body));
    return Buffer.concat([len, body, sum]);
  };
  const head = Buffer.alloc(13);
  head.writeUInt32BE(width, 0); head.writeUInt32BE(height, 4); head[8] = 8; head[9] = 2;
  const raw = Buffer.alloc((width * 3 + 1) * height);
  for (let y = 0; y < height; y++) {
    const row = y * (width * 3 + 1);
    for (let x = 0; x < width; x++) {
      const dy = Math.round(height * (0.5 - 0.4 * Math.sin((x / width) * 6.28)));
      const on = Math.abs(y - dy) < 2;
      raw[row + 1 + x * 3] = on ? 31 : 255; raw[row + 2 + x * 3] = on ? 119 : 255; raw[row + 3 + x * 3] = on ? 180 : 255;
    }
  }
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk("IHDR", head), chunk("IDAT", deflateSync(raw)), chunk("IEND", Buffer.alloc(0))]).toString("base64");
}

const NOW = "2026-11-12T09:30:00Z";
/** What the mocked Python session does next. The scenes set these between steps. */
const kernel = { state: "none", unavailable: null, replaced: null, result: null, runs: 0, lastBody: null };
const PY_OUTPUTS = {
  state: "succeeded", seconds: 4.2, warehouse: "Serverless · as the app", finishedAt: NOW, ranBy: "you@example.com",
  outputs: [
    { type: "text", stream: "stdout", text: "loading\n" },
    { type: "table", columns: ["period", "trips", "fare", "note"], types: ["string", "int", "decimal", "string"],
      rows: [["morning", "40", "80.00", null], ["evening", "10", "12.50", "slow"], ["night", "5", "9.00", null]] },
    { type: "html", html: "<div style='font-family:sans-serif;padding:8px'><h3 style='margin:0;color:#0b6'>done</h3><p>drawn by displayHTML</p></div>" },
    { type: "image", png: png(320, 120) },
    { type: "text", stream: "stderr", text: "UserWarning: something to know\n" },
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
      const q = (url.searchParams.get("q") || "").toLowerCase();
      const all = [
        { path: NOTEBOOK.path, name: "map_demo", kind: "notebook", language: "SQL" },
        { path: PY_NOTEBOOK.path, name: "py_demo", kind: "notebook", language: "PYTHON" },
      ];
      return json({ root: "/Users/you", complete: true, results: all.filter((r) => r.name.includes(q)) });
    }
    if (path.endsWith("/object")) return json(NOTEBOOKS[url.searchParams.get("path")] ?? NOTEBOOK);
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
  await page.route("**/api/notebook/sql-runs", async (route) => {
    const body = JSON.parse(route.request().postData() || "{}");
    const src = String(body.source || "");
    const result = src.includes("select 1 as a")
      ? { state: "failed", seconds: 0.4, warehouse: "Serverless Starter", finishedAt: NOW, ranBy: "you@example.com",
          error: "statement 2 of 3: [TABLE_OR_VIEW_NOT_FOUND] The table or view `missing_table` cannot be found.",
          statement: "select * from missing_table" }
      : src.includes("create table")
      ? { state: "succeeded", seconds: 0.2, warehouse: "Serverless Starter", finishedAt: NOW, ranBy: "you@example.com", output: "OK" }
      : src.includes("missing")
      ? { state: "failed", seconds: 0.18, error: "[TABLE_OR_VIEW_NOT_FOUND] missing_table" }
      : TABLE;
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ result }) });
  });
  // The dev user is not an administrator; Python cells run as the app, so the policy is what allows them.
  await page.route("**/api/me", async (route) => {
    const res = await route.fetch();
    const body = await res.json();
    body.pythonRun = { enabled: true, session: true, reason: "Runs on serverless compute as the app, not as you." };
    await route.fulfill({ response: res, json: body });
  });
  // The Python session. `kernel` is what the scenes change between steps: whether a session can start, and
  // whether the one a cell lands in is a replacement for one that ended.
  await page.route("**/api/notebook/kernels**", async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const json = (body) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    const info = (state) => ({ state, id: "s1", idleSeconds: 1200 });
    if (url.pathname.endsWith("/kernels/run")) {
      if (kernel.unavailable) return json({ unavailable: kernel.unavailable });
      kernel.state = "starting";
      kernel.runs += 1;
      kernel.lastBody = req.postDataJSON();
      const replaced = kernel.replaced; kernel.replaced = null;
      return json({ handle: "k1", session: info("starting"), ...(replaced ? { replaced } : {}) });
    }
    if (url.pathname.includes("/kernels/runs/")) {
      kernel.state = "idle";
      return json({ state: "done", seconds: 1.2, result: kernel.result ?? PY_OUTPUTS, session: info("idle") });
    }
    if (req.method() === "DELETE") { kernel.state = "none"; return json({ state: "none" }); }
    return json({ state: kernel.state });
  });
  await page.route("**/api/notebook/python-runs**", async (route) => {
    const req = route.request();
    const json = (body) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    if (req.method() === "POST") {
      const body = JSON.parse(req.postData() || "{}");
      return json({ handle: "h1", show: body.show });
    }
    // The wrapper keys results by the cell's position, as the real service does.
    return json({ state: "done", seconds: 4.2, results: { "1": PY_OUTPUTS } });
  });
}

async function openNotebook(page, term = "map") {
  await page.goto(base, { waitUntil: "domcontentloaded" });
  const box = page.getByRole("textbox", { name: "Message the agent" });
  await box.waitFor({ timeout: 20000 });
  await box.fill("Show revenue by hour");
  await page.keyboard.press("Meta+Enter");
  await page.locator(".turn-foot").first().waitFor({ timeout: 30000 });
  await page.getByRole("tab", { name: /Files/i }).click();
  const search = page.getByPlaceholder("Search notebooks and files");
  await search.fill(term);
  const hit = page.locator(".result").first();
  await hit.waitFor({ timeout: 15000 });
  await hit.click();
  await page.locator(".nb-bar").waitFor({ timeout: 15000 });
  await page.locator(".cell-block").first().waitFor({ timeout: 15000 });
  const dismiss = page.getByRole("button", { name: "Dismiss" });
  // The banner's close button sits under the Context edge handle at this width: click it by script.
  if (await dismiss.count()) await dismiss.first().evaluate((el) => el.click());
  // The notebook is what we are proving. The inspector is a third column that turns every SQL line
  // into an ellipsis; hide it so the pictures show the cells themselves.
  const hideInspector = page.locator(".shell-toggle[aria-label='Hide the inspector']");
  if (await hideInspector.count()) await hideInspector.click();
  await page.waitForTimeout(200);
}


/** Open another notebook from the Files tab, in the app that is already running. */
async function openFromFiles(page, term) {
  await page.getByRole("tab", { name: /Files/i }).click();
  const search = page.getByPlaceholder("Search notebooks and files");
  await search.fill(term);
  // The list still shows the last search until the new one answers: wait for the right row.
  const hit = page.locator(".result", { hasText: term }).first();
  await hit.waitFor({ timeout: 15000 });
  await hit.click();
  await page.locator(".nb-bar").waitFor({ timeout: 15000 });
  await page.locator(".cell-block").first().waitFor({ timeout: 15000 });
  // Wait for THIS notebook: the one that was open is still on screen until the new one is read.
  await page.locator(".nb-bar, .cell-block").first().waitFor({ timeout: 15000 });
  await page.getByText(term === "py_demo" ? "Trips, in Python" : "Revenue by hour").first().waitFor({ timeout: 15000 });
  await page.waitForTimeout(300);
}

const outputsOf = (page) => page.locator(".cell-output").evaluateAll((els) => els.map((e) => e.getAttribute("data-state")));

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

  console.log("\n== S9 Python outputs, in order");
  await page.setViewportSize({ width: 1440, height: 900 });
  await openFromFiles(page, "py_demo");
  await page.getByRole("button", { name: "Run all" }).click();
  await page.locator(".cell-output[data-state='failed']").waitFor({ timeout: 30000 });
  const pyStates = await outputsOf(page);
  check("S9 python ok, SQL ok, SQL failed", JSON.stringify(pyStates) === JSON.stringify(["succeeded", "succeeded", "failed"]), pyStates.join(","));
  const first = page.locator(".cell-output").first();
  const order = await first.locator(".cell-output-text, .cell-output-grid, .cell-output-html, .cell-output-images").evaluateAll(
    (els) => els.map((e) => (e.className.includes("html") ? "html" : e.className.includes("grid") ? "table" : e.className.includes("images") ? "image" : "text")));
  check("S9 the outputs keep the order the cell produced them", JSON.stringify(order) === JSON.stringify(["text", "table", "html", "image", "text"]), order.join(","));
  check("S9 a NULL is shown as null, not as an empty string", (await first.locator("em.cell-null").count()) === 2);
  check("S9 the number columns are right aligned", (await first.locator("td.is-num").count()) >= 6);
  const frame = first.locator("iframe");
  check("S9 HTML is in a sandboxed frame", (await frame.count()) === 1 && /allow-scripts/.test((await frame.getAttribute("sandbox")) || "") && !/allow-same-origin/.test((await frame.getAttribute("sandbox")) || ""));
  await page.waitForTimeout(500);
  const frameH = (await frame.boundingBox())?.height ?? 0;
  check("S9 the frame grew to its content", frameH > 40 && frameH < 400, String(Math.round(frameH)));
  check("S9 the footer says who and when", /you@example\.com/.test(await first.locator(".cell-output-by").innerText()), await first.locator(".cell-output-by").innerText());
  check("S9 no horizontal overflow", !(await overflow(page)));
  await first.scrollIntoViewIfNeeded();
  await shot(page, "09-python-outputs-1440.png");

  console.log("\n== S10 SQL: no result set, and a failing statement");
  const ddl = page.locator(".cell-output").nth(1);
  check("S10 a statement with no result says OK", /^OK$/m.test(await ddl.innerText()) || /\bOK\b/.test(await ddl.innerText()), (await ddl.innerText()).slice(0, 80));
  const bad = page.locator(".cell-output[data-state='failed']");
  check("S10 the error names the statement that failed", /statement 2 of 3/.test(await bad.innerText()));
  check("S10 the error is not cut short", /cannot be found/.test(await bad.innerText()));
  await bad.scrollIntoViewIfNeeded();
  await shot(page, "10-sql-statement-error-1440.png");

  console.log("\n== S11 results survive a tab switch");
  await openFromFiles(page, "map");
  check("S11 the other notebook has its own results", (await outputsOf(page)).length === 2, (await outputsOf(page)).join(","));
  await openFromFiles(page, "py_demo");
  const back = await outputsOf(page);
  check("S11 the results are back after switching away and returning", JSON.stringify(back) === JSON.stringify(["succeeded", "succeeded", "failed"]), back.join(","));
  check("S11 the plot is back too", (await page.locator(".cell-output-plot").count()) === 1);
  await shot(page, "11-after-tab-switch-1440.png");

  console.log("\n== S12 results survive a reload");
  await page.waitForTimeout(600);                  // the write to storage is debounced
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.getByRole("textbox", { name: "Message the agent" }).waitFor({ timeout: 20000 });
  await openFromFiles(page, "py_demo");
  const reloaded = await outputsOf(page);
  check("S12 the results are back after a reload", JSON.stringify(reloaded) === JSON.stringify(["succeeded", "succeeded", "failed"]), reloaded.join(","));
  await shot(page, "12-after-reload-1440.png");

  console.log("\n== S13 the session chip");
  const chip = page.locator(".nb-session-chip");
  check("S13 the chip says the session is ready", /Session ready/.test(await chip.innerText()), await chip.innerText());
  await chip.click();
  const pop = page.locator(".nb-session-pop");
  check("S13 the menu explains it and offers Restart and Stop", /Variables stay between cells/.test(await pop.innerText())
    && (await pop.getByRole("menuitem", { name: "Restart session" }).isEnabled())
    && (await pop.getByRole("menuitem", { name: "Stop session" }).isEnabled()));
  await shot(page, "13-session-menu-1440.png");
  await page.keyboard.press("Escape");
  check("S13 Escape closes the menu", (await page.locator(".nb-session-pop").count()) === 0);

  console.log("\n== S14 a session cannot start: the cell still runs, and says what that costs");
  kernel.unavailable = "the session store could not be written (PERMISSION_DENIED). The app's service principal needs read and write on /Volumes/workspace/agent_scratch/kernel_sessions";
  await page.getByRole("button", { name: /Clear outputs/ }).click();
  const pycell = page.locator(".cell-block").nth(1);
  await pycell.hover();
  await pycell.getByRole("button", { name: /^Run/ }).first().click();
  await page.locator(".cell-output[data-state='succeeded']").waitFor({ timeout: 20000 });
  const notice = page.locator(".cell-output-text.is-notice").first();
  check("S14 the output says it ran as a one-shot and why", /one-shot/.test(await notice.innerText()) && /PERMISSION_DENIED/.test(await notice.innerText()), (await notice.innerText()).slice(0, 90));
  check("S14 the chip says one-shot runs", /One-shot runs/.test(await chip.innerText()), await chip.innerText());
  check("S14 no horizontal overflow", !(await overflow(page)));
  await pycell.scrollIntoViewIfNeeded();
  await shot(page, "14-session-fallback-1440.png");

  console.log("\n== S15 restart, and a session that replaced one that ended");
  kernel.unavailable = null;
  kernel.replaced = "the session ended after being idle";
  await chip.click();
  await page.getByRole("menuitem", { name: "Restart session" }).click();
  await page.waitForTimeout(300);
  await page.getByRole("button", { name: /Clear outputs/ }).click();
  await pycell.hover();
  await pycell.getByRole("button", { name: /^Run/ }).first().click();
  await page.locator(".cell-output[data-state='succeeded']").waitFor({ timeout: 20000 });
  const replaced = await page.locator(".cell-output-text.is-notice").first().innerText();
  check("S15 the output says a new session replaced the one that ended", /new session was started.*idle.*gone/s.test(replaced), replaced.slice(0, 100));
  check("S15 it is a session again, not a one-shot", /Session ready/.test(await chip.innerText()), await chip.innerText());
  await pycell.scrollIntoViewIfNeeded();
  await shot(page, "15-session-replaced-1440.png");

  console.log("\n== S16 nested and long values");
  const LONG = "A long sentence that keeps going so that it cannot fit in a table cell and has to be shortened. ".repeat(3).trim();
  kernel.result = {
    state: "succeeded", seconds: 0.8, warehouse: "Serverless session · as the app", finishedAt: NOW, ranBy: "you@example.com",
    outputs: [{ type: "table", columns: ["id", "scores", "profile", "notes"], types: ["int", "array", "struct", "string"],
      typeTexts: ["", "ARRAY<INT>", "STRUCT<name: STRING, age: INT>", ""],
      rows: [["1", '["10","20","30"]', '{"name":"Ada","age":"36"}', LONG], ["2", null, '{"name":"Bo","age":null}', "short"]] }],
  };
  await page.getByRole("button", { name: /Clear outputs/ }).click();
  await pycell.hover();
  await pycell.getByRole("button", { name: /^Run/ }).first().click();
  await page.locator(".cell-output[data-state='succeeded']").waitFor({ timeout: 20000 });
  const grid = page.locator(".cell-output-grid").first();
  check("S16 an array of numbers is shown as numbers", (await grid.innerText()).includes("[10,20,30]"));
  check("S16 a struct is shown as a value with its numbers as numbers", (await grid.innerText()).includes('{"name":"Ada","age":36}'));
  check("S16 the type is the tooltip", (await grid.locator(".cell-value.is-nested").first().getAttribute("title")) === "ARRAY<INT>");
  check("S16 the long value is shortened", !(await grid.innerText()).includes(LONG) && (await grid.innerText()).includes("…"));
  await shot(page, "16-nested-values-1440.png");
  await grid.getByRole("button", { name: "Expand" }).click();
  check("S16 Expand shows all of it", (await grid.innerText()).includes(LONG));
  check("S16 no horizontal overflow when expanded", !(await overflow(page)));
  await shot(page, "16b-nested-expanded-1440.png");

  console.log("\n== S17 a chart of a result");
  const days = ["2026-11-01", "2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06"];
  kernel.result = {
    state: "succeeded", seconds: 0.5, warehouse: "Serverless session · as the app", finishedAt: NOW, ranBy: "you@example.com",
    outputs: [{ type: "table", columns: ["day", "city", "rides"], types: ["date", "string", "int"],
      rows: days.flatMap((d, i) => [[d, "Oslo", String(40 + i * 7 + (i % 2) * 9)], [d, "Rome", String(70 - i * 5 + (i % 3) * 6)]]) }],
  };
  await page.getByRole("button", { name: /Clear outputs/ }).click();
  await pycell.hover();
  await pycell.getByRole("button", { name: /^Run/ }).first().click();
  await page.locator(".cell-output[data-state='succeeded']").waitFor({ timeout: 20000 });
  await page.getByRole("button", { name: "Chart", exact: true }).click();
  const svg = page.locator("svg.chart-svg");
  check("S17 a date column makes a line chart", /Line chart of rides by day/.test((await svg.getAttribute("aria-label")) ?? ""), (await svg.getAttribute("aria-label")) ?? "");
  await page.getByLabel("Group").selectOption({ label: "city" });
  check("S17 grouping by city draws two lines and a legend", (await page.locator("path.chart-line").count()) === 2 && (await page.locator(".chart-legend li").count()) === 2);
  check("S17 no horizontal overflow", !(await overflow(page)));
  await svg.scrollIntoViewIfNeeded();
  await shot(page, "17-chart-line-1440.png");
  await page.getByLabel("Type").selectOption("bar");
  check("S17 bars are drawn for each point", (await page.locator("rect.chart-bar").count()) === 12);
  await shot(page, "17b-chart-bar-1440.png");
  await page.waitForTimeout(600);
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.getByRole("textbox", { name: "Message the agent" }).waitFor({ timeout: 20000 });
  await openFromFiles(page, "py_demo");
  check("S17 the chart choice is back after a reload", (await page.locator("rect.chart-bar").count()) === 12 && (await page.getByLabel("Type").inputValue()) === "bar");
  await page.getByRole("button", { name: "Table", exact: true }).click();
  check("S17 Table brings the rows back", (await page.locator(".grid tbody tr").count()) === 12);

  console.log("\n== S18 widgets");
  kernel.result = {
    state: "succeeded", seconds: 0.4, warehouse: "Serverless session · as the app", finishedAt: NOW, ranBy: "you@example.com",
    outputs: [{ type: "text", stream: "stdout", text: "widgets declared\n" }],
    widgets: [
      { name: "city", type: "text", default: "Oslo", label: "City", choices: [], value: "Oslo" },
      { name: "size", type: "dropdown", default: "m", label: "Size", choices: ["s", "m", "l"], value: "m" },
      { name: "pick", type: "multiselect", default: "x", label: "Pick", choices: ["x", "y", "z"], value: "x" },
    ],
  };
  await page.getByRole("button", { name: /Clear outputs/ }).click();
  await pycell.hover();
  await pycell.getByRole("button", { name: /^Run/ }).first().click();
  await page.locator(".cell-output[data-state='succeeded']").waitFor({ timeout: 20000 });
  const bar = page.locator(".widget-bar");
  await bar.waitFor({ timeout: 5000 });
  check("S18 the bar shows what the cell declared", (await bar.locator(".widget-field").count()) === 3);
  check("S18 the bar says it does not re-run anything", /does not re-run any cell/.test(await bar.innerText()));
  await shot(page, "18-widgets-1440.png");
  const before = kernel.runs;
  await bar.getByLabel("City").fill("Rome");
  await bar.getByLabel("Size").selectOption("l");
  await bar.getByRole("checkbox", { name: "z" }).check();
  await page.waitForTimeout(300);
  check("S18 changing a widget runs nothing", kernel.runs === before);
  await page.getByRole("button", { name: /Clear outputs/ }).click();
  await pycell.hover();
  await pycell.getByRole("button", { name: /^Run/ }).first().click();
  await page.locator(".cell-output[data-state='succeeded']").waitFor({ timeout: 20000 });
  check("S18 the next run is sent the values", JSON.stringify(kernel.lastBody.widgets) === JSON.stringify({ city: "Rome", size: "l", pick: "x,z" }), JSON.stringify(kernel.lastBody.widgets));
  check("S18 the declaration is not drawn under the cell", !(await page.locator(".cell-output").first().innerText()).includes("InputWidget"));
  await page.waitForTimeout(400);
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.getByRole("textbox", { name: "Message the agent" }).waitFor({ timeout: 20000 });
  await openFromFiles(page, "py_demo");
  check("S18 the values are back after a reload", (await page.locator(".widget-bar").getByLabel("City").inputValue()) === "Rome");
  await page.locator(".widget-bar").getByRole("button", { name: "Reset" }).click();
  check("S18 Reset puts the defaults back", (await page.locator(".widget-bar").getByLabel("City").inputValue()) === "Oslo");
  await shot(page, "18b-widgets-reset-1440.png");
  kernel.result = { ...kernel.result, widgets: [] };
  await pycell.hover();
  await pycell.getByRole("button", { name: /^Run/ }).first().click();
  await page.waitForFunction(() => document.querySelectorAll(".widget-bar").length === 0, null, { timeout: 10000 });
  check("S18 a session that has no widgets removes the bar", (await page.locator(".widget-bar").count()) === 0);
  kernel.result = null;
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
