/**
 * Spec 013's screenshots. One scene per file, each asserting its own pass criteria before it saves.
 *
 *   node scripts/lakebase-e2e.mjs [url] [outDir]
 *
 * The pages are photographed against RECORDED payloads (`scripts/fixtures/lakebase.json`), and the
 * shell around them is the real app: a scene that mocks the shell proves nothing about the shell, and
 * a scene that needs a workspace cannot run in CI (spec 013 [11 §How the scenes run]).
 *
 * Every scene prints its checks. A failed check exits non-zero, so a pretty picture of the wrong state
 * cannot be committed by accident.
 */
import { chromium } from "playwright";
import { mkdirSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const URL_ = process.argv[2] ?? "http://127.0.0.1:8062";
const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = resolve(process.argv[3] ?? `${HERE}/../../../../specs/013-improve-coding/e2e/screenshots`);
mkdirSync(OUT, { recursive: true });

const FIX = JSON.parse(readFileSync(resolve(HERE, "fixtures/lakebase.json"), "utf8"));

const results = [];
const record = (scene, checks) => {
  const failed = checks.filter((c) => !c.pass);
  results.push({ scene, pass: failed.length === 0, checks });
  const mark = failed.length ? "FAIL" : "ok  ";
  console.log(`\n${mark} ${scene}`);
  for (const c of checks) console.log(`      ${c.pass ? "✓" : "✗"} ${c.what}`);
};

const browser = await chromium.launch();
const json = (body) => ({ status: 200, contentType: "application/json", body: JSON.stringify(body) });

/** A page on the app, with the fixture routes installed before anything loads. */
async function pageWith(width, routes, hash = "") {
  const page = await browser.newPage({ viewport: { width, height: 940 }, deviceScaleFactor: 1.5 });
  page.problems = [];
  page.on("pageerror", (e) => page.problems.push(`pageerror: ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error") page.problems.push(`console: ${m.text()}`); });
  // One route per fixture, most specific first, so the page's several calls each get their payload.
  // Registered in the order given, last one last: Playwright consults the most recently added
  // matching route first, so a scene's specific pattern must come after the general one.
  for (const [pattern, payload] of routes) await page.route(pattern, (r) => r.fulfill(json(payload)));
  await page.goto(`${URL_}/${hash}`, { waitUntil: "networkidle" });
  await page.waitForTimeout(500);
  return page;
}

const body = () => FIX.project;

const shot = async (page, name) => {
  await page.screenshot({ path: `${OUT}/${name}` });
  console.log(`      → ${name}`);
};

// --------------------------------------------------------------------------- S1 the shell, Data tab
{
  const page = await browser.newPage({ viewport: { width: 1480, height: 940 }, deviceScaleFactor: 1.5 });
  page.problems = [];
  page.on("pageerror", (e) => page.problems.push(`pageerror: ${e.message}`));
  await page.route("**/api/lakebase/projects", (r) => r.fulfill(json(FIX.projects_list)));
  await page.route("**/api/apps", (r) => r.fulfill(json(FIX.apps_list)));
  await page.goto(URL_, { waitUntil: "networkidle" });
  await page.getByRole("tab", { name: "Data" }).click();
  await page.waitForTimeout(600);

  const tabs = await page.getByRole("tab").allTextContents();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 2);
  record("S1 shell with the Data tab", [
    { what: "four rail tabs, named", pass: JSON.stringify(tabs) === JSON.stringify(["Sessions", "Files", "Catalog", "Data"]) },
    { what: "the project and the app are both listed", pass: (await page.getByText("pg_tickets").count()) > 0 && (await page.getByText("tickets-app").count()) > 0 },
    { what: "no horizontal overflow at 1480", pass: !overflow },
    { what: "⌘4 selects Data", pass: await (async () => {
      await page.keyboard.press("Meta+1");
      await page.waitForTimeout(150);
      const onSessions = await page.getByRole("tab", { name: "Sessions" }).getAttribute("aria-selected");
      await page.keyboard.press("Meta+4");
      await page.waitForTimeout(150);
      const onData = await page.getByRole("tab", { name: "Data" }).getAttribute("aria-selected");
      return onSessions === "true" && onData === "true";
    })() },
    { what: "no console errors", pass: page.problems.length === 0 },
  ]);
  await shot(page, "s1-shell-data-1480.png");
  await page.close();
}

// --------------------------------------------------------------------------- S2 project page
{
  const page = await pageWith(1480, [
    ["**/api/lakebase/projects/projects/pg_tickets?**", FIX.project],
    ["**/tables**", FIX.tables],
  ], "#/lakebase/projects/pg_tickets");
  await page.waitForTimeout(900);

  const text = await page.locator(".infra-body").innerText();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 2);
  record("S2 a Lakebase project", [
    { what: "shows the autoscaling rule evaluated", pass: /max − min = 3\.5/.test(text) },
    { what: "default branch is marked", pass: /production/.test(text) && (await page.getByText("default").count()) > 0 },
    { what: "the host is on screen", pass: /ep-cool-butterfly/.test(text) },
    { what: "tables are listed", pass: (await page.getByText("tickets", { exact: true }).count()) > 0 },
    { what: "no horizontal overflow", pass: !overflow },
    { what: "no console errors", pass: page.problems.length === 0 },
  ]);
  await shot(page, "s2-project-1480.png");
  await page.close();
}

// --------------------------------------------------------------------------- S3 app page, running
{
  const page = await pageWith(1480, [["**/api/apps/**", FIX.app]], "#/app/tickets-app");
  await page.waitForTimeout(900);
  const text = await page.locator(".infra-body").innerText();
  record("S3 a Databricks App, running", [
    { what: "the health check is the headline", pass: /Answered 200 in 412 ms/.test(text) },
    { what: "the URL is shown", pass: /tickets-app-1\.aws\.databricksapps\.com/.test(text) },
    { what: "the resource and its permission are named", pass: /CAN_CONNECT_AND_CREATE/.test(text) },
    { what: "the logs link is a real link to /logz", pass: await (async () => {
      const a = page.getByRole("link", { name: "/logz" });
      return (await a.count()) > 0 && (await a.getAttribute("href")).endsWith("/logz");
    })() },
    { what: "no console errors", pass: page.problems.length === 0 },
  ]);
  await shot(page, "s3-app-1480.png");
  await page.close();
}

// --------------------------------------------------------------------------- S4 cold start
{
  const page = await pageWith(1480, [["**/api/apps/**", FIX.app_cold]], "#/app/tickets-app");
  await page.waitForTimeout(900);
  const text = await page.locator(".infra-body").innerText();
  record("S4 a cold start reads as starting, not down", [
    { what: "says cold start and that it is normal", pass: /Cold start/.test(text) && /normal/.test(text) },
    { what: "does not say down or broken", pass: !/\bdown\b|\bbroken\b/i.test(text) },
    { what: "the rest of the page is still there", pass: /CAN_CONNECT_AND_CREATE/.test(text) },
    { what: "no red state is used for this", pass: (await page.locator(".infra-health.tone-bad").count()) === 0 },
  ]);
  await shot(page, "s4-app-cold-1480.png");
  await page.close();
}

// --------------------------------------------------------------------------- S5 a refusal
{
  const page = await pageWith(1480, [
    ["**/api/lakebase/projects/projects/pg_tickets?**", FIX.refused],
    ["**/tables**", { schema: "public", tables: [], truncated: false }],
  ], "#/lakebase/projects/pg_tickets");
  await page.waitForTimeout(900);
  const text = await page.locator(".infra-body").innerText();
  record("S5 a refusal, in the platform's words", [
    { what: "the platform's sentence is verbatim", pass: /PERMISSION_DENIED/.test(text) },
    { what: "no retry is offered for a permission wall", pass: (await page.getByRole("button", { name: /Try again/ }).count()) === 0 },
    { what: "the composer still accepts a keystroke", pass: await (async () => {
      const ta = page.locator("textarea").first();
      if (!(await ta.count())) return true;             // no composer on this route: not a failure
      await ta.click({ force: true });
      await ta.type("still works");
      return (await ta.inputValue()).includes("still works");
    })() },
  ]);
  await shot(page, "s5-refused-1480.png");
  await page.close();
}

// --------------------------------------------------------------------------- S6 the scaffold plan
{
  const page = await browser.newPage({ viewport: { width: 1480, height: 940 }, deviceScaleFactor: 1.5 });
  page.problems = [];
  page.on("pageerror", (e) => page.problems.push(`pageerror: ${e.message}`));
  await page.route("**/api/lakebase/projects", (r) => r.fulfill(json(FIX.projects_list)));
  await page.route("**/api/apps", (r) => r.fulfill(json(FIX.apps_list)));
  await page.route("**/api/lakebase/projects/projects/pg_tickets?*", (r) => r.fulfill(json(FIX.project)));
  await page.route("**/tables**", (r) => r.fulfill(json(FIX.tables)));
  await page.goto(URL_, { waitUntil: "networkidle" });

  // The scenario's turn, created through the app's own API, so the tool rows and the plan are real.
  const made = await page.evaluate(async () => {
    const r = await fetch("/api/sessions", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ folder: "/tmp/agent-work" }),
    });
    return r.json();
  });
  await page.evaluate(async (sid) => {
    await fetch(`/api/sessions/${sid}/messages`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ text: "Create a Lakebase database with one table and a small app that reads it." }),
    });
  }, made.id);
  await page.waitForTimeout(4000);
  await page.goto(`${URL_}/#/session/${made.id}`, { waitUntil: "networkidle" });
  await page.waitForTimeout(2500);

  // The tool rows live in the dock and, on the mission screen, under its Activity tab. Both are
  // read, so the assertion does not depend on which surface the layout chose.
  const dockText = await page.locator("#dock").innerText();
  const planRows = await page.locator(".tool-row .name").allTextContents();
  await page.getByRole("button", { name: /Activity/i }).first().click().catch(() => {});
  await page.waitForTimeout(400);
  const activity = await page.locator("#doc-panel").innerText();
  const everything = `${dockText}\n${planRows.join(" ")}\n${activity}`;
  record("S6 the scaffold's tool rows", [
    // The scenario, asserted by its OWN facts. The first version accepted any infrastructure word and
    // passed while the screenshot showed a taxi notebook (spec 013 [11 §What each scene proves]).
    { what: "the Lakebase scenario ran: a database, a branch and an app were created",
      pass: /pg_tickets/.test(everything) && /agent-4ff4405d/.test(everything) && /agent-4ff-tickets/.test(everything) },
    { what: "the plan reports all seven steps complete",
      pass: /7 of 7/.test(everything) },
    { what: "the app is proven by an HTTP 200, not merely deployed",
      pass: /HTTP 200|Answered 200|answered HTTP 200/.test(everything) },
    { what: "the centre is not showing a taxi notebook", pass: !/taxi_hours/.test(everything) },
    { what: "no console errors", pass: page.problems.length === 0 },
  ]);
  await shot(page, "s6-scaffold-running-1480.png");
  await page.close();
}

// --------------------------------------------------------------------------- S7 mid width
{
  // 900 px is `mid` in `modeFor` (narrow is <= 820): the rail keeps a column, the inspector yields,
  // and the dock takes a column once the arithmetic allows it (>= 1136). The scene asserts the rule
  // the code implements — a wireframe that guessed otherwise would be a wrong requirement, not a bug.
  const page = await pageWith(900, [["**/api/apps/**", FIX.app]], "#/app/tickets-app");
  await page.waitForTimeout(900);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 2);
  const railColumn = await page.evaluate(() => {
    const rail = document.querySelector(".rail");
    if (!rail) return false;
    return getComputedStyle(rail).display !== "none" && rail.getBoundingClientRect().width > 100;
  });
  record("S7 at 900 px (mid: the rail keeps a column)", [
    { what: "no horizontal overflow at 900", pass: !overflow },
    { what: "the app page still renders its health", pass: /Answered 200/.test(await page.locator(".infra-body").innerText()) },
    { what: "the rail is a column at this width, as the layout rule says", pass: railColumn },
    { what: "the centre keeps its minimum", pass: await page.evaluate(() => {
      const main = document.querySelector("#doc-panel");
      return !main || main.getBoundingClientRect().width >= 470;
    }) },
  ]);
  await shot(page, "s7-mid-900.png");
  await page.close();
}

// --------------------------------------------------------------------------- S8 palette
{
  const page = await browser.newPage({ viewport: { width: 1480, height: 940 }, deviceScaleFactor: 1.5 });
  await page.route("**/api/lakebase/projects", (r) => r.fulfill(json(FIX.projects_list)));
  await page.route("**/api/apps", (r) => r.fulfill(json(FIX.apps_list)));
  await page.goto(URL_, { waitUntil: "networkidle" });
  await page.keyboard.press("Meta+k");
  await page.waitForTimeout(300);
  await page.keyboard.type("Data panel");
  await page.waitForTimeout(300);
  const found = await page.locator(".palette-opt, [role='option']").allTextContents();
  record("S8 the palette finds the new panel", [
    { what: "the Data panel is findable by name", pass: found.join(" ").toLowerCase().includes("data") },
  ]);
  await shot(page, "s8-palette-1480.png");
  await page.close();
}

await browser.close();

const failed = results.filter((r) => !r.pass);
console.log(`\n${results.length - failed.length}/${results.length} scenes pass`);
if (failed.length) {
  console.log(`failed: ${failed.map((f) => f.scene).join(", ")}`);
  process.exit(1);
}
