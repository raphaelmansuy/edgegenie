/** End-to-end: the Genie-Code-class workflow, driven through the real UI against a real workspace.
 *
 *   APP_URL=http://127.0.0.1:8040 node scripts/genie-e2e.mjs <screenshot-dir>
 *
 * Every step asserts something observable and takes a screenshot. Exits non-zero on the first
 * failed assertion, after printing which one, so a CI log says exactly what broke.
 *
 * Needs a notebook named like NOTEBOOK_HINT (default "taxi") under the user's home, and the
 * table samples.nyctaxi.trips (a Databricks sample dataset, present in every workspace).
 */
import { chromium } from "playwright";
import { mkdirSync, readFileSync } from "node:fs";

const url = process.env.APP_URL ?? "http://127.0.0.1:8040";
const out = process.argv[2] ?? "/tmp/genie-e2e";
const HINT = process.env.NOTEBOOK_HINT ?? "taxi";
const REAL = process.env.REAL_AGENT === "1";          // real agent: do not expect the scripted plan
mkdirSync(out, { recursive: true });

const b = await chromium.launch({ executablePath: process.env.CHROME_PATH || undefined });
// Against a deployed app the Databricks proxy needs a signed-in identity: pass an OAuth bearer token.
const bearer = process.env.BEARER_FILE ? readFileSync(process.env.BEARER_FILE, "utf8").trim() : "";
const p = await b.newPage({
  viewport: { width: 1480, height: 940 }, deviceScaleFactor: 2,
  extraHTTPHeaders: bearer ? { Authorization: `Bearer ${bearer}` } : {},
});
const problems = [];
p.on("pageerror", (e) => problems.push(`pageerror: ${e}`));
p.on("crash", () => problems.push("the page crashed"));
p.on("console", (m) => { if (m.type() === "error" && !/favicon|401|403|404/.test(m.text())) problems.push(`console: ${m.text()}`); });

let n = 0;
const results = [];
const shot = (name) => p.screenshot({ path: `${out}/${String(++n).padStart(2, "0")}-${name}.png` });
async function step(name, fn) {
  try { await fn(); results.push([true, name]); console.log(`  PASS ${name}`); }
  catch (e) {
    results.push([false, name]);
    console.log(`  FAIL ${name}\n       ${String(e.message).split("\n")[0]}`);
    await shot(`FAIL-${name.replace(/\W+/g, "-").slice(0, 40)}`).catch(() => {});
  }
}
const ok = (cond, msg) => { if (!cond) throw new Error(msg); };

await p.goto(url, { waitUntil: "domcontentloaded" });
await p.getByRole("button", { name: /Build a notebook/i }).waitFor({ state: "visible", timeout: 30000 });

await step("home shows a free-form composer, not only example cards", async () => {
  ok(await p.getByRole("textbox", { name: "Message the agent" }).isVisible(), "no composer on the home screen");
  await shot("home");
});

await step("Files tab lists the real workspace roots", async () => {
  await p.getByRole("tab", { name: "Files" }).click();
  await p.locator('[role="tree"] [role="treeitem"]').first().waitFor({ timeout: 20000 });
  const names = await p.locator(".tree-name").allInnerTexts();
  ok(names.some((t) => /home/i.test(t)), `no home root in ${names}`);
  await shot("files-roots");
});

await step("a folder expands lazily and shows its children", async () => {
  await p.locator('[role="treeitem"]', { hasText: "My home" }).first().click();
  await p.locator('[role="treeitem"][aria-level="2"]').first().waitFor({ timeout: 20000 });
  const kids = await p.locator('[role="treeitem"][aria-level="2"] .tree-name').allInnerTexts();
  ok(kids.length >= 1, "home has no children");
  const row = p.locator('[role="treeitem"][aria-level="2"]', { hasText: /agent_scratch|coding-agent/ }).first();
  await row.hover();
  const href = await row.locator("a.tree-act").getAttribute("href");
  ok(href && /\/browse\/folders\/\d+|#workspace\//.test(href), `no Databricks link on a folder row: ${href}`);
  await shot("files-home-expanded");
});

await step("keyboard: ArrowDown moves focus, ArrowRight opens, ArrowLeft returns to the parent", async () => {
  const home = p.locator('[role="treeitem"]', { hasText: "My home" }).first();
  await home.focus();
  await p.keyboard.press("ArrowDown");
  const active = await p.evaluate(() => document.activeElement?.getAttribute("aria-level"));
  ok(active === "2", `focus did not move to a child (level ${active})`);
  await p.keyboard.press("ArrowLeft");
  const back = await p.evaluate(() => document.activeElement?.textContent ?? "");
  ok(/My home/.test(back), `ArrowLeft did not return to the parent (${back.slice(0, 30)})`);
});

await step("search finds the notebook by name", async () => {
  await p.getByRole("textbox", { name: "Search workspace" }).fill(HINT);
  await p.locator(".result").first().waitFor({ timeout: 30000 });
  const hits = await p.locator(".result-name").allInnerTexts();
  ok(hits.some((h) => h.toLowerCase().includes(HINT)), `no hit for ${HINT}: ${hits}`);
  await shot("search-results");
});

await step("opening a result shows the notebook as highlighted cells", async () => {
  await p.locator(".result", { hasText: HINT }).first().click();
  await p.locator(".cell").first().waitFor({ timeout: 20000 });
  ok((await p.locator(".cell").count()) >= 1, "no cells");
  ok((await p.locator("pre.code [class^=tk-]").count()) > 0, "no syntax highlighting");
  ok(await p.getByRole("tab", { name: new RegExp(HINT, "i") }).first().isVisible(), "no document tab");
  await shot("notebook-open");
});

await step("the notebook links to the same object in Databricks", async () => {
  const link = p.locator(".viewer-actions a", { hasText: /Open in Databricks/ });
  const href = await link.getAttribute("href");
  ok(href && /\/editor\/notebooks\/\d+|#workspace\//.test(href), `unexpected link: ${href}`);
  ok((await link.getAttribute("target")) === "_blank" && /noopener/.test(await link.getAttribute("rel")), "unsafe external link");
});

await step("the open notebook rides along as context", async () => {
  const chip = p.locator(".ctx-chip.auto");
  await chip.waitFor({ timeout: 5000 });
  ok(/open/i.test(await chip.innerText()), "auto-context chip is not marked open");
});

await step("a table opens from the Catalog tab with columns and real sample rows", async () => {
  await p.getByRole("tab", { name: "Catalog" }).click();
  const node = (name) => p.locator('[role="tree"][aria-label="Unity Catalog"] [role="treeitem"]')
    .filter({ has: p.locator(".tree-name", { hasText: new RegExp(`^${name}$`) }) });
  await node("samples").click();
  await node("nyctaxi").click();
  await node("trips").click();
  await p.getByRole("table").first().waitFor({ timeout: 30000 });
  const cols = await p.locator(".grid td code").allInnerTexts();
  ok(cols.includes("tpep_pickup_datetime") && cols.includes("fare_amount"), `columns: ${cols}`);
  await shot("table-schema");
  await p.getByRole("button", { name: /Show 10 rows/ }).click();
  await p.locator(".grid-wrap tbody tr").first().waitFor({ timeout: 90000 });
  ok((await p.locator(".grid-wrap tbody tr").count()) >= 5, "fewer than 5 sample rows");
  await shot("table-sample-rows");
});

await step("@ in the composer finds a notebook and adds a chip", async () => {
  await p.getByRole("tab", { name: "Chat" }).click();
  const box = p.getByRole("textbox", { name: "Message the agent" });
  await box.fill("");
  await box.pressSequentially(`compare with @${HINT}`);
  await p.locator(".mention-opt").first().waitFor({ timeout: 30000 });
  await shot("mention-picker");
  await p.keyboard.press("Enter");
  await p.locator(".ctx-chip:not(.auto)").first().waitFor({ timeout: 5000 });
  ok((await box.inputValue()).trim() === "compare with", `mention text left behind: "${await box.inputValue()}"`);
  await p.locator(".ctx-chip button").first().click();
  ok((await p.locator(".ctx-chip:not(.auto)").count()) === 0, "chip was not removable");
});

await step("a quick action starts a session with the notebook attached", async () => {
  await p.getByRole("tab", { name: new RegExp(HINT, "i") }).first().click();
  await p.getByRole("button", { name: "Explain" }).click();
  await p.locator(".turn").first().waitFor({ timeout: 30000 });
  const chip = p.locator(".turn .prompt .ctx-chip").first();
  await chip.waitFor({ timeout: 10000 });
  ok(new RegExp(HINT, "i").test(await chip.innerText()), "the turn does not show its attachment");
  ok(!/attached-context/.test(await p.locator(".turn .prompt").first().innerText()), "context text leaked into the transcript");
  await shot("explain-started");
});

await step("the agent's plan renders as a checklist", async () => {
  if (REAL) return;
  await p.locator(".plan li").first().waitFor({ timeout: 40000 });
  ok((await p.locator(".plan li").count()) === 3, "expected 3 plan steps");
  await p.locator(".plan-completed").first().waitFor({ timeout: 40000 });
  await shot("plan");
});

await step("a finished turn shows time and token use", async () => {
  await p.locator(".turn-foot").first().waitFor({ timeout: 90000 });
  ok(/\d/.test(await p.locator(".turn-foot").first().innerText()), "empty footer");
  await shot("turn-finished");
});

await step("the session strip links to the working folder in Databricks", async () => {
  const href = await p.locator(".strip a.ext-link").first().getAttribute("href");
  ok(href && /#workspace\/Users\//.test(href), `unexpected folder link: ${href}`);
  await shot("links");
});

await step("tool cards for notebooks offer to open what the agent touched", async () => {
  if (REAL) return;
  ok((await p.locator(".tool-open").count()) >= 1, "no Open button on a notebook tool call");
});

console.log("\nproblems:", problems.length ? problems : "none");
const failed = results.filter(([ok_]) => !ok_).length;
console.log(`\nRESULT: ${results.length - failed} passed, ${failed} failed${problems.length ? `, ${problems.length} page problem(s)` : ""}`);
await b.close();
process.exit(failed || problems.length ? 1 : 0);
