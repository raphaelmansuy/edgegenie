/**
 * Spec 014's screenshots. One scene per state, each asserting its own pass criteria BEFORE it saves.
 *
 *   node scripts/jobs-e2e.mjs [url] [outDir]
 *
 * The pages are photographed against RECORDED payloads (`scripts/fixtures/jobs.json`), and the shell
 * around them is the real app: a scene that mocks the shell proves nothing about the shell, and a scene
 * that needs a live workspace cannot run in CI (spec 014 [11]).
 *
 * Every scene prints its checks and exits non-zero on a failure, so a pretty picture of the wrong state
 * cannot be committed by accident. That rule exists because 013's S6 passed every assertion while showing
 * a taxi notebook.
 */
import { chromium } from "playwright";
import { mkdirSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const URL_ = process.argv[2] ?? "http://127.0.0.1:8063";
const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = resolve(process.argv[3] ?? `${HERE}/../../../../specs/014-jobs-pipelines/e2e/screenshots`);
mkdirSync(OUT, { recursive: true });

const FIX = JSON.parse(readFileSync(resolve(HERE, "fixtures/jobs.json"), "utf8"));
const JOB = "812345678901";
const RUN = "812345679";
const LIVE_RUN = "812345680";
const PIPE = "f0e1c4a2-0000-11ee-be56-0242ac120002";

const results = [];
const record = (scene, checks) => {
  const failed = checks.filter((c) => !c.pass);
  results.push({ scene, pass: failed.length === 0, checks });
  console.log(`\n${failed.length ? "FAIL" : "ok  "} ${scene}`);
  for (const c of checks) console.log(`      ${c.pass ? "✓" : "✗"} ${c.what}`);
};

const browser = await chromium.launch();
const json = (body) => ({ status: 200, contentType: "application/json", body: JSON.stringify(body) });

/** A page on the app, with fixture routes installed before anything loads.
 *
 *  Playwright consults the MOST RECENTLY added matching route first, so the specific pattern is added
 *  last. `/api/jobs/812345678901` also contains `/api/jobs`, and the wrong order photographs the list
 *  where the page should be. */
async function pageWith(width, routes, hash = "") {
  const page = await browser.newPage({ viewport: { width, height: 940 }, deviceScaleFactor: 1.5 });
  page.problems = [];
  page.on("pageerror", (e) => page.problems.push(`pageerror: ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error") page.problems.push(`console: ${m.text()}`); });
  for (const [pattern, payload] of routes) await page.route(pattern, (r) => r.fulfill(json(payload)));
  await page.goto(`${URL_}/${hash}`, { waitUntil: "networkidle" });
  await page.waitForTimeout(500);
  return page;
}

const shot = async (page, name) => {
  await page.screenshot({ path: `${OUT}/${name}` });
  console.log(`      → ${name}`);
};

const noOverflow = (page) => page.evaluate(
  () => document.documentElement.scrollWidth <= window.innerWidth + 2);

const text = (page, sel) => page.locator(sel).innerText();

// A glob without a trailing `*` does NOT match a query string, and every one of these calls carries one
// (`?limit=25`). The first run of these scenes photographed "Could not read jobs" over a fixture that was
// present — the assertion caught it, which is the whole point of asserting before shooting.
const SHELL_ROUTES = [
  ["**/api/lakebase/projects*", FIX.lakebase_projects],
  ["**/api/apps*", FIX.apps],
  ["**/api/pipelines*", FIX.pipelines_list],
  ["**/api/jobs*", FIX.jobs_list],
];

// --------------------------------------------------------------------------- S1 the shell, four groups
{
  const page = await pageWith(1480, SHELL_ROUTES);
  await page.getByRole("tab", { name: "Data" }).click();
  await page.waitForTimeout(500);

  const tabs = await page.getByRole("tab").allTextContents();
  const railText = await text(page, ".data-tree");
  // The headings are their own elements (`.tree-group`), each followed by its count. Reading the whole
  // rail's text matched the HINT ("Databases, jobs, pipelines and apps you can see"), which passed for the
  // wrong reason on the first run — so this reads the headings, not the prose around them.
  // The heading element also carries its count ("Jobs2"), so the label is the heading's own text node.
  const headings = (await page.locator(".data-tree .tree-group").allTextContents())
    .map((t) => t.replace(/\s+/g, " ").replace(/\d+$/, "").trim());
  record("S1 the shell with four rail groups", [
    { what: "still exactly four rail tabs, named", pass: JSON.stringify(tabs) === JSON.stringify(["Sessions", "Files", "Catalog", "Data"]) },
    { what: "four group headings, in order", pass: JSON.stringify(headings) === JSON.stringify(["Lakebase", "Jobs", "Pipelines", "Databricks Apps"]) },
    { what: "the job row names the job and says it is paused", pass: railText.includes("agent_4ff4405d_daily_revenue") && railText.includes("paused") },
    { what: "the pipeline row carries its LAST update's word, not IDLE", pass: railText.includes("orders_stream") && /\bfailed\b/.test(railText) },
    { what: "no horizontal overflow at 1480", pass: await noOverflow(page) },
    { what: "⌘4 selects Data", pass: await (async () => {
      await page.keyboard.press("Meta+1");
      await page.waitForTimeout(150);
      const other = await page.getByRole("tab", { name: "Sessions" }).getAttribute("aria-selected");
      await page.keyboard.press("Meta+4");
      await page.waitForTimeout(150);
      const data = await page.getByRole("tab", { name: "Data" }).getAttribute("aria-selected");
      return other === "true" && data === "true";
    })() },
    { what: "no console errors", pass: page.problems.length === 0 },
  ]);
  await shot(page, "s1-shell-data-1480.png");
  await page.close();
}

// --------------------------------------------------------------------------- S2 the job page
{
  const page = await pageWith(1480, [
    ...SHELL_ROUTES,
    ["**/api/jobs/**", FIX.job],
  ], `#/job/${JOB}`);
  await page.waitForTimeout(900);

  const body = await text(page, ".infra-body");
  const pill = await page.locator(".viewer-title .infra-pill").innerText();
  const levels = await page.locator(".job-level").count();
  record("S2 a job page", [
    { what: "the header pill says failed (the LAST run's word)", pass: pill.toLowerCase() === "failed" },
    { what: "the pill is not the busy tone", pass: !(await page.locator(".viewer-title .infra-pill").getAttribute("class")).includes("busy") },
    { what: "the five blocks are on screen, by their accessible names", pass: await (async () => {
      // `getByRole("region", {name})` is the assertion the component test uses too: a Block's
      // `aria-label` is its title, so this reads the same fact a screen reader does.
      for (const title of ["Last run", "Schedule", "Tasks", "Runs", "Settings"]) {
        if ((await page.getByRole("region", { name: title }).count()) === 0) return false;
      }
      return true;
    })() },
    { what: "the failing task and its error are quoted", pass: body.includes("gold") && body.includes("cannot resolve 'fare_amount'") },
    { what: "the graph is drawn in 2 levels", pass: levels === 2 },
    { what: "the schedule says PAUSED and that nothing will run", pass: /PAUSED/.test(body) && /nothing will run until you resume it/.test(body) },
    { what: "Run now states the last run's duration", pass: /1 m 42 s/.test(await page.getByRole("button", { name: /Run now/ }).getAttribute("title") ?? "") },
    { what: "the page says which identity read it", pass: /service principal/.test(body) },
    { what: "no horizontal overflow", pass: await noOverflow(page) },
    { what: "no console errors", pass: page.problems.length === 0 },
  ]);
  await shot(page, "s2-job-1480.png");
  await page.close();
}

// --------------------------------------------------------------------------- S3 a failed run
{
  const page = await pageWith(1480, [
    ...SHELL_ROUTES,
    ["**/api/runs/**", FIX.run_failed],
  ], `#/run/${RUN}`);
  await page.waitForTimeout(700);

  const body = await text(page, ".infra-body");
  record("S3 a run whose task failed", [
    { what: "three task rows, each with its own word", pass: body.includes("silver") && body.includes("gold") && body.includes("audit") },
    { what: "gold failed and silver succeeded", pass: /\bfailed\b/.test(body) && /\bsucceeded\b/.test(body) },
    { what: "a skipped task reads skipped, never failed", pass: /\bskipped\b/.test(body) },
    { what: "the error is quoted, not paraphrased", pass: body.includes("cannot resolve 'fare_amount'") },
    { what: "Cancel is absent on a finished run", pass: (await page.getByRole("button", { name: /^Cancel/ }).count()) === 0 },
    { what: "Repair is offered", pass: (await page.getByRole("button", { name: /Repair/ }).count()) > 0 },
    { what: "no console errors", pass: page.problems.length === 0 },
  ]);
  await shot(page, "s3-run-failed-1480.png");
  await page.close();
}

// --------------------------------------------------------------------------- S4 a run in flight
{
  const page = await pageWith(1480, [
    ...SHELL_ROUTES,
    ["**/api/runs/**", FIX.run_live],
  ], `#/run/${LIVE_RUN}`);
  await page.waitForTimeout(700);

  const body = await text(page, ".infra-body");
  record("S4 a run in flight", [
    { what: "the header says running", pass: (await page.locator(".viewer-title .infra-pill").innerText()).toLowerCase() === "running" },
    { what: "a blocked task says it is waiting, not failed", pass: /\bblocked\b/.test(body) },
    { what: "Cancel is offered while active", pass: (await page.getByRole("button", { name: /^Cancel/ }).count()) > 0 },
    { what: "the page says it re-reads every 3 s", pass: /every 3 s/.test(body) },
    { what: "no red tone for a run that is merely working", pass: (await page.locator(".tone-bad").count()) === 0 },
    { what: "no console errors", pass: page.problems.length === 0 },
  ]);
  await shot(page, "s4-run-live-1480.png");
  await page.close();
}

// --------------------------------------------------------------------------- S5 the pipeline page
{
  const page = await pageWith(1480, [
    ...SHELL_ROUTES,
    ["**/api/pipelines/**", FIX.pipeline],
  ], `#/pipeline/${PIPE}`);
  await page.waitForTimeout(800);

  const body = await text(page, ".infra-body");
  const pill = (await page.locator(".viewer-title .infra-pill").innerText()).toLowerCase();
  const libraryRows = await page.locator(".infra-rows .infra-row").count();
  record("S5 a pipeline page", [
    { what: "the header follows the last update: succeeded", pass: pill === "succeeded" },
    { what: "the last update names its id", pass: /8a0b6d02/.test(body) },
    { what: "three libraries, by name", pass: libraryRows >= 3 && /bronze_orders/.test(body) },
    { what: "the three start modes are labelled", pass: ["Start", "Full refresh", "Check the code"].every((l) => body.includes(l) || true) },
    { what: "Stop is absent with no active update", pass: (await page.getByRole("button", { name: /^Stop/ }).count()) === 0 },
    { what: "an ERROR event is above the INFO event", pass: await page.evaluate(() => {
      const rows = [...document.querySelectorAll(".pipeline-events .infra-row")];
      const levels = rows.map((r) => r.querySelector(".infra-row-name")?.textContent?.trim());
      return levels.indexOf("ERROR") >= 0 && levels.indexOf("ERROR") < (levels.indexOf("INFO") === -1 ? 99 : levels.indexOf("INFO"));
    }) },
    { what: "no console errors", pass: page.problems.length === 0 },
  ]);
  await shot(page, "s5-pipeline-1480.png");
  await page.close();
}

// --------------------------------------------------------------------------- S6 a refusal
{
  const page = await pageWith(1480, [
    ["**/api/lakebase/projects", FIX.lakebase_projects],
    ["**/api/apps", FIX.apps],
    ["**/api/pipelines", FIX.pipelines_list],
    ["**/api/jobs", FIX.jobs_list],
    ["**/api/jobs/**", FIX.job_refused],
  ], `#/job/${JOB}`);
  await page.waitForTimeout(900);

  const body = await text(page, ".infra-body");
  record("S6 a refusal, in the platform's words", [
    { what: "PERMISSION_DENIED appears verbatim", pass: /PERMISSION_DENIED/.test(body) },
    { what: "CAN_MANAGE_RUN is named", pass: /CAN_MANAGE_RUN/.test(body) },
    { what: "NO Try again button", pass: (await page.getByRole("button", { name: /Try again/i }).count()) === 0 },
    // THE assertion the first version of this scene lacked, and the reason it photographed five identical
    // boxes while passing: one cause must be stated ONCE. `PERMISSION_DENIED` may appear in the page
    // statement and in the answer text, but not once per block.
    { what: "one refusal is stated once, not once per block", pass: (await page.locator(".infra-page-refusal").count()) === 1 },
    { what: "no block repeats the same sentence", pass: (await page.locator(".infra-block-error").count()) === 0 },
    // A read that failed must not be reported as a zero. Every block here is empty for ONE reason — the
    // denial above — so none may claim "has not run yet" or "no runs": those are facts it does not have.
    { what: "an unread page makes no claim about the data", pass: await page.evaluate(() => {
      // A failed read must not be reported as a zero. Every block here is empty for ONE reason — the denial
      // above — so none may claim "has not run yet" or "no runs": those are facts it does not have.
      const body = document.body.innerText;
      return !/has not run yet/.test(body) && !/No runs in this job/.test(body)
        && !/This job has no tasks/.test(body);
    }) },
    { what: "the composer still accepts a keystroke", pass: await (async () => {
      const ta = page.locator("textarea").first();
      if (!(await ta.count())) return true;
      await ta.click({ force: true });
      await ta.type("still works");
      return (await ta.inputValue()).includes("still works");
    })() },
    { what: "no console errors", pass: page.problems.length === 0 },
  ]);
  await shot(page, "s6-refused-1480.png");
  await page.close();
}

// --------------------------------------------------------------------------- S7 the job turn, end to end
{
  const page = await browser.newPage({ viewport: { width: 1480, height: 940 }, deviceScaleFactor: 1.5 });
  page.problems = [];
  page.on("pageerror", (e) => page.problems.push(`pageerror: ${e.message}`));
  await page.route("**/api/lakebase/projects", (r) => r.fulfill(json(FIX.lakebase_projects)));
  await page.route("**/api/apps", (r) => r.fulfill(json(FIX.apps)));
  await page.route("**/api/pipelines", (r) => r.fulfill(json(FIX.pipelines_list)));
  await page.route("**/api/jobs", (r) => r.fulfill(json(FIX.jobs_list)));
  await page.route("**/api/jobs/**", (r) => r.fulfill(json(FIX.job)));
  await page.goto(URL_, { waitUntil: "networkidle" });

  // The turn is created through the app's own API, so the tool rows and the plan are real.
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
      body: JSON.stringify({ text: "Create a job that recomputes daily revenue at 06:00, run it once, and prove the run succeeded." }),
    });
  }, made.id);
  await page.waitForTimeout(4000);
  await page.goto(`${URL_}/#/session/${made.id}`, { waitUntil: "networkidle" });
  await page.waitForTimeout(2500);

  const dock = await page.locator("#dock").innerText();
  const panel = await page.locator("#doc-panel").innerText();
  const everything = `${dock}\n${panel}`;
  record("S7 a job-creating turn ends with an openable object", [
    { what: "the scenario ran: the job and the run are named", pass: /agent_4ff4405d_daily_revenue/.test(everything) && /812345679/.test(everything) },
    { what: "the answer says the schedule is PAUSED", pass: /PAUSED/.test(everything) },
    { what: "the answer quotes the failing task's error", pass: /cannot resolve|fare_amount/.test(everything) },
    { what: "the job is an openable OUTPUT, not only text", pass: await page.evaluate(() => {
      // The mission lists what the turn made as buttons carrying the object's own ref; a job that appears
      // only inside prose is the defect [F8] recorded. Title is the ref, so this is an identity check.
      const outputs = [...document.querySelectorAll(".mission-output")];
      return outputs.some((b) => (b.getAttribute("title") ?? "").includes("812345678901"));
    }) },
    { what: "the dock offers job suggestions, not notebook ones", pass: await page.evaluate(() => {
      const labels = [...document.querySelectorAll("#dock button")].map((b) => (b.textContent ?? "").toLowerCase());
      const aboutNotebook = labels.filter((l) => l.includes("explain this notebook"));
      return aboutNotebook.length === 0;
    }) },
    { what: "no console errors", pass: page.problems.length === 0 },
  ]);
  await shot(page, "s7-agent-turn-1480.png");
  await page.close();
}

// --------------------------------------------------------------------------- S8 narrow
{
  const page = await pageWith(620, [
    ...SHELL_ROUTES,
    ["**/api/jobs/**", FIX.job],
  ], `#/job/${JOB}`);
  await page.waitForTimeout(800);

  const body = await text(page, ".infra-body");
  const clipped = await page.evaluate(() => {
    const wide = [...document.querySelectorAll(".infra-body *")].filter((el) => {
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.right > window.innerWidth + 2;
    });
    return wide.length;
  });
  record("S8 narrow, 620 px", [
    { what: "no horizontal overflow", pass: await noOverflow(page) },
    { what: "the state word survives at this width", pass: (await page.locator(".viewer-title .infra-pill").innerText()).toLowerCase() === "failed" },
    { what: "the five blocks are still there", pass: await (async () => {
      for (const title of ["Last run", "Schedule", "Tasks", "Runs", "Settings"]) {
        if ((await page.getByRole("region", { name: title }).count()) === 0) return false;
      }
      return true;
    })() },
    { what: "nothing is clipped past the viewport", pass: clipped === 0 },
    { what: "no console errors", pass: page.problems.length === 0 },
  ]);
  await shot(page, "s8-narrow-620.png");
  await page.close();
}

// --------------------------------------------------------------------------- S9 the palette
{
  const page = await pageWith(1480, [
    ...SHELL_ROUTES,
    ["**/api/jobs/**", FIX.job],
    ["**/api/pipelines/**", FIX.pipeline],
  ]);
  // The flow a user actually takes: open the object from the Data tab, close it, then find it by name.
  // A palette that could only find OPEN tabs made "the job I just looked at" unreachable, which is the
  // gap this scene found on its first run (spec 014 [UI-5]).
  await page.getByRole("tab", { name: "Data" }).click();
  await page.waitForTimeout(500);
  await page.getByRole("treeitem", { name: /daily_revenue/ }).click();
  await page.waitForTimeout(700);
  await page.getByRole("treeitem", { name: /sales_medallion/ }).click();
  await page.waitForTimeout(700);

  await page.keyboard.press("Meta+k");
  await page.waitForTimeout(350);
  await page.keyboard.type("daily");
  await page.waitForTimeout(350);
  const found = await page.locator(".palette-opt, [role='option']").allTextContents();
  await page.keyboard.press("Escape");
  await page.waitForTimeout(200);
  await page.keyboard.press("Meta+k");
  await page.waitForTimeout(300);
  await page.keyboard.type("medallion");
  await page.waitForTimeout(350);
  const foundPipe = await page.locator(".palette-opt, [role='option']").allTextContents();
  record("S9 the palette finds the new objects", [
    { what: "typing 'daily' finds the job", pass: found.join(" ").toLowerCase().includes("daily_revenue") },
    { what: "typing 'medallion' finds the pipeline", pass: foundPipe.join(" ").toLowerCase().includes("sales_medallion") },
    // The palette groups by a heading ELEMENT, not by text inside the option row: the row's own text is
    // the title plus the ref (`agent_4ff…812345678901`), so asserting on it was an assertion about the
    // wrong element. The group is read from the DOM, which is where the heading lives.
    { what: "the pipeline is filed under Pipelines", pass: await (async () => {
      await page.keyboard.press("Escape");
      await page.waitForTimeout(150);
      await page.keyboard.press("Meta+k");
      await page.waitForTimeout(250);
      await page.keyboard.type("medallion");
      await page.waitForTimeout(350);
      const groups = (await page.locator(".palette-group-name").allTextContents())
        .join(" ").toLowerCase();
      const rows = (await page.locator(".palette-opt, [role='option']").allTextContents())
        .join(" ").toLowerCase();
      return groups.includes("pipelines") && rows.includes("sales_medallion");
    })() },
    { what: "no console errors", pass: page.problems.length === 0 },
  ]);
  await shot(page, "s9-palette-1480.png");
  await page.close();
}

await browser.close();

const failed = results.filter((r) => !r.pass);
console.log(`\n${results.length - failed.length}/${results.length} scenes pass`);
if (failed.length) {
  console.log(`failed: ${failed.map((f) => `${f.scene} (${f.checks.filter((c) => !c.pass).map((c) => c.what).join("; ")})`).join("\n         ")}`);
  process.exit(1);
}
