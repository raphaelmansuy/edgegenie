/** Run works: SQL and Python cells, one at a time and all together, with the identity stated.
 *
 *   APP_URL=http://127.0.0.1:8062 NOTEBOOK=pyrun_demo node scripts/run-e2e.mjs
 *
 * Needs the app on a real workspace (scripts/dev-token.sh 8062 with APP_LLM_ADMINS set to the dev user)
 * and the notebook `pyrun_demo` (python cells: setup, a Spark table, a printed value, a failing cell).
 * Python runs on real serverless compute, so this takes about a minute. Screenshots:
 * specs/006-databricks/e2e/run-works.
 */
import { mkdirSync } from "node:fs";
import { check, finish, launch, openNotebook, shot as baseShot } from "./parity-lib.mjs";

const OUT = process.env.OUT ?? "../../../specs/006-databricks/e2e/run-works";
mkdirSync(OUT, { recursive: true });
const shot = (p, f) => baseShot(p, f, { path: `${OUT}/${f}` });

const { browser, page: p, errors } = await launch(1440, 900);
await openNotebook(p, "pyrun_demo");

if (process.env.AS === "reader") {
  /* The same notebook, for a user the app does not list as an administrator. */
  console.log("\n== 05 a user who may not run Python is told why, and nothing is offered that cannot work");
  const run = p.getByRole("button", { name: "Run cell 3" });
  check("Run is disabled on a Python cell", await run.isDisabled());
  check("and says why, in words", /administrators/.test((await run.getAttribute("title")) ?? "") && /not as you/.test((await run.getAttribute("title")) ?? ""), await run.getAttribute("title"));
  check("Run all is disabled", await p.getByRole("button", { name: /Run all/ }).isDisabled());
  check("the bar says nothing can run", /no cell here can run/.test(await p.locator(".nb-bar-status").innerText()), await p.locator(".nb-bar-status").innerText());
  check("no Python chip is shown", (await p.getByText("Python · as the app").count()) === 0);
  await shot(p, "05-reader-python-disabled.png");
  await finish(browser, errors);
}
const cell = (n) => p.locator(`.cell-block[data-cell="${n}"]`);
const waitDone = async (n, ms = 180000) => {
  await cell(n).locator(".cell-state").filter({ hasNotText: /running/ }).first().waitFor({ timeout: ms });
};

console.log("\n== 01 before running: Python is offered, and says what it will do");
const run3 = p.getByRole("button", { name: "Run cell 3" });
check("Run is enabled on a Python cell", await run3.isEnabled());
check("its title says it is not as you", /not as you/.test((await run3.getAttribute("title")) ?? ""));
check("Run all is enabled", await p.getByRole("button", { name: /Run all/ }).isEnabled());
check("the bar names the Python identity", await p.getByText("Python · as the app").isVisible());
check("the bar counts the cells that can run", /4 cells can run/.test(await p.locator(".nb-bar-status").innerText()), await p.locator(".nb-bar-status").innerText());
await shot(p, "01-python-run-enabled.png");

console.log("\n== 02 one cell: it runs the Python above it first");
await cell(4).hover();
await p.getByRole("button", { name: "Run cell 4" }).click();
await cell(4).locator(".cell-output").waitFor({ timeout: 15000 });
check("a run in flight says what it waits for", /serverless|running|starting|waiting/i.test(await cell(4).locator(".cell-output-msg").innerText()), await cell(4).locator(".cell-output-msg").innerText());
await shot(p, "02-running.png");
await waitDone(4);
const out4 = await cell(4).locator(".cell-output-text").innerText();
check("it used a variable made by cell 2", /double the rate: 25\.0/.test(out4), out4);
check("it shows the last expression", /12\.0/.test(out4));
check("it says where it ran", /Serverless · as the app/.test(await cell(4).locator(".cell-output-where").innerText()));
check("the cell above was not given an output of its own", (await cell(2).locator(".cell-output").count()) === 0);
await shot(p, "03-one-cell-done.png");

console.log("\n== 03 Run all");
await p.getByRole("button", { name: /Run all/ }).click();
for (const n of [2, 3, 4, 5]) await waitDone(n);
check("cell 2 printed", /setup ok/.test(await cell(2).locator(".cell-output-text").innerText()));
const rows = await cell(3).locator(".cell-output-grid tbody tr").count();
check("cell 3 shows the Spark table", rows === 6, `${rows} rows`);
check("cell 3 has its columns", /pickup_hour/.test(await cell(3).locator("thead").innerText()));
check("cell 5 failed, with the engine's words", /NameError/.test(await cell(5).locator(".cell-output-msg").innerText()));
check("and not the wrapper's frames", !/wrapper|exec\(/.test(await cell(5).locator(".cell-output-msg").innerText()));
check("the bar summarises it", /3 ran · 1 failed/.test(await p.locator(".nb-bar-status").innerText()), await p.locator(".nb-bar-status").innerText());
await p.locator(".cell-block").nth(2).scrollIntoViewIfNeeded();
await shot(p, "04-run-all-done.png");
check("Fix with agent is offered on the failure", await cell(5).getByRole("button", { name: /Fix with agent/ }).isVisible());

await finish(browser, errors);
