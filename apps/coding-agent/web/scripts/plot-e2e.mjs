/** Notebook plot scenes: a Python cell that printed text and left a matplotlib figure.
 *
 *   node scripts/plot-e2e.mjs
 *
 * Mocks workspace + python-runs so the pictures do not need a warehouse. Screenshots land in
 * specs/007-ux-ui-improve/e2e/screenshot/ (70–74), continuing that folder's numbering.
 */
import { chromium } from "playwright";
import { mkdirSync, readFileSync } from "node:fs";
import { spawn } from "node:child_process";
import { setTimeout as sleep } from "node:timers/promises";

const out = new URL("../../../../specs/007-ux-ui-improve/e2e/screenshot/", import.meta.url).pathname;
mkdirSync(out, { recursive: true });
const app = new URL("../../", import.meta.url).pathname;
const port = Number(process.env.PORT || 8096);
const base = `http://127.0.0.1:${port}`;
const plotPng = readFileSync(new URL("./fixtures/kpi-plot.png", import.meta.url));
const PLOT_B64 = plotPng.toString("base64");

const NOTEBOOK = {
  objectId: "1", path: "/Users/you/kpi_plots", name: "kpi_plots", kind: "notebook",
  language: "PYTHON", size: 800, truncated: false, modifiedAt: 1, version: "v1", text: "",
  cells: [
    { index: 1, kind: "markdown", language: "markdown", source: "# KPI summary", truncated: false },
    {
      index: 2, kind: "code", language: "python", truncated: false,
      source: [
        "print('KPI Summary')",
        "print(kpi_df.to_string(index=False))",
        "fig, axes = plt.subplots(1, 3, figsize=(11, 3.2))",
        "for ax, (title, value, unit) in zip(axes, kpis):",
        "    ax.text(0.5, 0.6, value, ha='center', fontsize=28, fontweight='bold')",
        "    ax.text(0.5, 0.3, title, ha='center', fontsize=11)",
        "    ax.set_xticks([]); ax.set_yticks([])",
        "plt.tight_layout()",
        "plt.show()",
      ].join("\n"),
    },
  ],
};

const KPI_TEXT = [
  "KPI Summary",
  " total_trips  avg_trip_distance_miles  avg_fare_amount_usd  total_fare_amount_usd",
  "       21932                     2.85                12.35             270832.28",
].join("\n");

const PY_RESULT = {
  state: "succeeded", seconds: 25.5, warehouse: "Serverless · as the app",
  output: KPI_TEXT + "\n", images: [PLOT_B64],
};

const start = spawn(process.env.PYTHON || `${app}.venv/bin/python`, ["-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", String(port)], {
  cwd: app,
  env: {
    ...process.env, APP_AGENT_MODE: "fake", APP_DEMO_SCENARIO: "notebook",
    APP_DEV_USER: "you@example.com", APP_DEFAULT_MODEL: "fake/model-a",
    APP_ALLOWED_MODELS: '["fake/model-a","fake/model-b"]', APP_PYTHON_RUN: "true",
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
  await page.route("**/api/me", async (route) => {
    // Fulfilled outright: route.fetch() under a match can hang the first paint, and the only thing
    // this scene needs from /api/me is pythonRun.enabled so the Run button works.
    await route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify({
        user: "you@example.com", home: "/Users/you", scratch: "/Users/you/agent_scratch",
        workspace: { host: "", orgId: "" }, tokenScopes: [], demo: true,
        pythonRun: { enabled: true, reason: "Runs on serverless compute as the app, not as you." },
      }),
    });
  });
  await page.route("**/api/workspace**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const json = (body) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    if (path.endsWith("/roots")) return json({ roots: [{ path: "/Users/you", name: "My home", kind: "directory" }] });
    if (path.endsWith("/search")) {
      return json({ root: "/Users/you", complete: true, results: [
        { path: NOTEBOOK.path, name: "kpi_plots", kind: "notebook", language: "PYTHON" },
      ] });
    }
    if (path.endsWith("/object")) return json(NOTEBOOK);
    if (path.endsWith("/version")) return json({ path: url.searchParams.get("path"), version: "v1", modifiedAt: 1 });
    if (path.endsWith("/fence")) return json({ verdict: "allow", reason: "inside the working folder", approval: null });
    if (route.request().method() === "GET") {
      return json({ root: "/Users/you", node: {
        path: "/Users/you", name: "you", kind: "directory", hasChildren: true,
        children: [{ path: NOTEBOOK.path, name: "kpi_plots", kind: "notebook", language: "PYTHON", hasChildren: false }],
      } });
    }
    return route.continue();
  });
  await page.route("**/api/notebook/python-runs**", async (route) => {
    const method = route.request().method();
    if (method === "POST") {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ handle: "plot-1" }) });
    }
    if (method === "GET") {
      return route.fulfill({
        status: 200, contentType: "application/json",
        body: JSON.stringify({ state: "done", seconds: 25.5, results: { "1": PY_RESULT } }),
      });
    }
    if (method === "DELETE") {
      return route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
    }
    return route.continue();
  });
}

async function openNotebook(page) {
  await page.goto(base, { waitUntil: "domcontentloaded" });
  const box = page.getByRole("textbox", { name: "Message the agent" });
  await box.waitFor({ timeout: 20000 });
  // A short message: the fake agent finishes a turn; the notebook content comes from the workspace mock.
  await box.fill("hi");
  await page.keyboard.press("Meta+Enter");
  try {
    await page.locator(".turn-foot").first().waitFor({ timeout: 30000 });
  } catch (err) {
    await page.screenshot({ path: `${out}FAIL-open.png` }).catch(() => {});
    console.log("open failed — body:\n", (await page.locator("body").innerText()).slice(0, 800));
    throw err;
  }
  await page.getByRole("tab", { name: /Files/i }).click();
  const search = page.getByPlaceholder("Search notebooks and files");
  await search.fill("kpi");
  const hit = page.locator(".result").first();
  await hit.waitFor({ timeout: 15000 });
  await hit.click();
  await page.locator(".nb-bar").waitFor({ timeout: 15000 });
  await page.locator(".cell-block").nth(1).waitFor({ timeout: 15000 });
  const dismiss = page.getByRole("button", { name: "Dismiss" });
  if (await dismiss.count()) await dismiss.first().click();
  // The plot is the subject. The assistant and inspector steal width and crop the third KPI card.
  const hideAssistant = page.locator(".shell-toggle[aria-label='Hide the assistant']");
  if (await hideAssistant.count()) await hideAssistant.click();
  const hideInspector = page.locator(".shell-toggle[aria-label='Hide the inspector']");
  if (await hideInspector.count()) await hideInspector.click();
  await page.waitForTimeout(300);
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

  console.log("\n== 70 idle python cell");
  check("70 Run is offered on the Python cell", await page.locator(".cell-block").nth(1).getByRole("button", { name: /Run cell/ }).isEnabled());
  await page.locator(".cell-block").nth(1).scrollIntoViewIfNeeded();
  await shot(page, "70-plot-idle.png");

  console.log("\n== 71 plot under the cell");
  await page.locator(".cell-block").nth(1).getByRole("button", { name: /Run cell/ }).click();
  await page.locator(".cell-output-plot").waitFor({ timeout: 15000 });
  const summary = await page.locator(".cell-output-when").first().innerText();
  check("71 the bar names the plot", /1 plot/.test(summary), summary);
  check("71 printed text is under the cell", /KPI Summary/.test(await page.locator(".cell-output-text").innerText()));
  check("71 the PNG is an image with real pixels", await page.locator(".cell-output-plot").evaluate((img) => img.naturalWidth > 100));
  const plotBox = await page.locator(".cell-output-plot").boundingBox();
  check("71 the full figure fits without clipping its width", Boolean(plotBox && plotBox.width >= 520), JSON.stringify(plotBox));
  await page.locator(".cell-output-figure").evaluate((el) => el.scrollIntoView({ block: "center" }));
  await shot(page, "71-plot-done.png");

  console.log("\n== 72 download control");
  await page.locator(".cell-output-figure").hover();
  await page.getByRole("button", { name: /Download plot/ }).waitFor({ timeout: 3000 });
  check("72 Download PNG is offered on hover", await page.getByRole("button", { name: /Download plot/ }).isVisible());
  await page.locator(".cell-output-figure").evaluate((el) => el.scrollIntoView({ block: "center" }));
  await shot(page, "72-plot-download.png");

  console.log("\n== 74 narrow");
  await page.setViewportSize({ width: 860, height: 900 });
  await page.waitForTimeout(300);
  check("74 no horizontal overflow", !(await overflow(page)));
  const box = await page.locator(".cell-output-plot").boundingBox();
  check("74 the plot stays inside the notebook", Boolean(box && box.width > 200 && box.width < 820), JSON.stringify(box));
  await page.locator(".cell-output").first().scrollIntoViewIfNeeded();
  await shot(page, "74-plot-narrow.png");
} finally {
  await context.close();
}

const dark = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2, colorScheme: "dark" });
await dark.addInitScript(() => localStorage.setItem("coding-agent:theme:v1", "dark"));
const dpage = await dark.newPage();
dpage.on("pageerror", (e) => errors.push(String(e)));
await install(dpage);
try {
  console.log("\n== 73 dark");
  await openNotebook(dpage);
  await dpage.locator(".cell-block").nth(1).getByRole("button", { name: /Run cell/ }).click();
  await dpage.locator(".cell-output-plot").waitFor({ timeout: 15000 });
  check("73 dark has no horizontal overflow", !(await overflow(dpage)));
  const theme = await dpage.evaluate(() => document.documentElement.getAttribute("data-theme"));
  check("73 the document is dark", theme === "dark", theme || "(none)");
  await dpage.locator(".cell-output").first().scrollIntoViewIfNeeded();
  await shot(dpage, "73-plot-dark.png");
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
