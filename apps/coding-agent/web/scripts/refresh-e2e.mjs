/** Every shape of "the agent wrote it" must reach the screen.
 *   APP_URL=http://127.0.0.1:8062 OUT=../../../specs/006-databricks/e2e/refresh node scripts/refresh-e2e.mjs */
import { execFileSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import { launch, check, finish, shot } from "./parity-lib.mjs";
const BASE = "/Users/raphael.mansuy@gmail.com/agent_scratch";
const REPO = "/Users/raphael.mansuy@gmail.com/rf_demo";
const mkdir = (path) => execFileSync("databricks", ["workspace", "mkdirs", path]);
const write = (path, text, language = "PYTHON") => {
  writeFileSync("/tmp/rf.txt", text);
  execFileSync("databricks", ["workspace", "import", path, "--file", "/tmp/rf.txt", "--format", "SOURCE", "--language", language, "--overwrite"]);
};
const nb = (title) => `# Databricks notebook source\n# MAGIC %md\n# MAGIC # ${title}\n\n# COMMAND ----------\n\nprint("one")\n`;
mkdir(REPO);
write(`${BASE}/rf_target`, nb("Target"), "PYTHON");
write(`${REPO}/rf_open`, nb("In a repo"), "PYTHON");

const { browser, page: p, errors } = await launch(1440, 900);
await p.locator("textarea").last().fill("hello"); await p.keyboard.press("Enter"); await p.waitForTimeout(3500);
const go = async (path) => { await p.evaluate((h) => { location.hash = h; }, `#/notebook${path}`); await p.locator(".cell-block").first().waitFor({ timeout: 30000 }); await p.waitForTimeout(1200); };
const cells = () => p.locator(".cell-block").count();
const body = () => p.evaluate(() => [...document.querySelectorAll(".cm-content")].map((e) => e.innerText).join("\n"));

// ---- 1. a notebook the agent rewrites while it is open
console.log("\n1. the open notebook is rewritten");
await go(`${BASE}/rf_target`);
const n0 = await cells();
write(`${BASE}/rf_target`, nb("Target") + "\n# COMMAND ----------\n\nprint(\"two\")\n");
await p.evaluate(() => window.dispatchEvent(new Event("focus")));
// Regaining focus is what makes the app look again. The import lands a moment after the command
// returns and the write only bumps modified_at once it does, so look a few times, as a person
// tabbing back to the window would.
for (let i = 0; i < 10 && (await cells()) === n0; i++) {
  await p.evaluate(() => window.dispatchEvent(new Event("focus")));
  await p.waitForTimeout(1500);
}
check("the new cell appeared", (await cells()) === n0 + 1, `${n0} -> ${await cells()}`);
check("the banner says what changed", (await p.locator(".agent-banner").count()) === 1);
await shot(p, "01-notebook-adopted.png");

// ---- 2. a plain file the agent rewrites while it is open
console.log("\n2. the open FILE is rewritten");
const putFile = (path, text) => { writeFileSync("/tmp/rf.md", text); execFileSync("databricks", ["workspace", "import", path, "--file", "/tmp/rf.md", "--format", "AUTO", "--overwrite"]); };
putFile(`${BASE}/rf_notes.md`, "# one\n");
await p.evaluate(() => { location.hash = "#/file/Users/raphael.mansuy@gmail.com/agent_scratch/rf_notes.md"; });
await p.locator(".editor-surface .cm-content").first().waitFor({ timeout: 30000 });
await p.waitForTimeout(1200);
putFile(`${BASE}/rf_notes.md`, "# one\n\n## two\n");
for (let i = 0; i < 8; i++) {
  await p.evaluate(() => window.dispatchEvent(new Event("focus")));
  await p.waitForTimeout(1200);
  if ((await p.evaluate(() => document.querySelector(".editor-surface .cm-content")?.innerText ?? "")).includes("two")) break;
}
const text = await p.evaluate(() => document.querySelector(".editor-surface .cm-content")?.innerText ?? "");
check("the file on screen changed", text.includes("two"), JSON.stringify(text.slice(0, 60)));
check("…and it says why", (await p.getByText(/updated by the agent/i).count()) > 0);
await shot(p, "02-file-adopted.png");

// ---- 3. one file, two spellings: one tab, one document
console.log("\n3. /Workspace/... and /... are the same document");
await go(`${BASE}/rf_target`);
const tabs = () => p.evaluate(() => [...document.querySelectorAll(".doc-tab")].map((e) => e.textContent?.trim()));
const before3 = await tabs();
await p.evaluate(() => { location.hash = "#/notebook/Workspace/Users/raphael.mansuy@gmail.com/agent_scratch/rf_target"; });
await p.waitForTimeout(2500);
const after3 = await tabs();
check("opening the other spelling did not add a tab", after3.length === before3.length, `${JSON.stringify(before3)} -> ${JSON.stringify(after3)}`);
check("the notebook is on screen", (await p.locator(".cell-block").count()) > 0);

// ---- 4. the agent writes a DIFFERENT file than the one open  [[scenario:elsewhere]]
console.log("\n4. the agent writes a different file");
await p.getByRole("button", { name: /^New$|\+ New/ }).first().click().catch(() => {});
await p.waitForTimeout(1500);
await go(`${BASE}/rf_target`);
check("no banner before the write", (await p.locator(".wrote-elsewhere").count()) === 0);
await p.locator("textarea").last().fill("Add a KPI [[scenario:elsewhere]]");
await p.locator("textarea").last().press("Enter");
for (let i = 0; i < 20 && (await p.locator(".wrote-elsewhere").count()) === 0; i++) await p.waitForTimeout(2000);
const banner4 = await p.locator(".wrote-elsewhere").textContent().catch(() => "");
check("the centre says the agent wrote another file", /a different file/i.test(banner4), JSON.stringify(banner4));
check("…naming it", /taxi_hours/.test(banner4), JSON.stringify(banner4));
await shot(p, "04-wrote-elsewhere.png");
// one click opens it
await p.locator(".wrote-elsewhere button", { hasText: "Open it" }).click().catch(() => {});
await p.waitForTimeout(3000);
const tabs4 = await p.evaluate(() => [...document.querySelectorAll(".doc-tab")].map((e) => e.textContent?.trim()));
check("Open it opens the written file", tabs4.some((t) => t?.includes("taxi_hours_with_kpi")), JSON.stringify(tabs4));
await shot(p, "05-opened-elsewhere.png");

await finish(browser, errors);
