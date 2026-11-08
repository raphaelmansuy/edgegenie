/** A notebook that is open is changed by someone else (what the assistant's write looks like to the
 *  editor). The editor must show the new cells, say so, and Undo must put the old ones back.
 *
 *   APP_URL=http://127.0.0.1:8062 node scripts/external-update-e2e.mjs
 * Needs the databricks CLI (it plays the part of the writer). Screenshots: specs/006-databricks/e2e/update-open-notebook.
 */
import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { check, finish, launch } from "./parity-lib.mjs";

const PATH = "/Users/raphael.mansuy@gmail.com/agent_scratch/update_demo";
const OUT = "../../../specs/006-databricks/e2e/update-open-notebook";
mkdirSync(OUT, { recursive: true });
const cli = (...a) => execFileSync("databricks", a, { encoding: "utf8" });
const put = (text) => { writeFileSync("/tmp/update_demo.sql", text); cli("workspace", "import", PATH, "--file", "/tmp/update_demo.sql", "--format", "SOURCE", "--language", "SQL", "--overwrite"); };
const base = "-- Databricks notebook source\n-- MAGIC %md\n-- MAGIC # Update demo\n\n-- COMMAND ----------\n\nselect 1 as one\n";
put(base);

const { browser, page: p, errors } = await launch(1440, 900);
await p.goto(`${process.env.APP_URL ?? "http://127.0.0.1:8062"}/#/notebook${PATH}`);
await p.locator(".cell-block").first().waitFor({ timeout: 30000 });
const cells = () => p.locator(".cell-block").count();
check("opens with 2 cells", (await cells()) === 2, String(await cells()));

console.log("\n== 01 someone else appends a cell; the user presses Reload");
put(base + "\n-- COMMAND ----------\n\nselect 2 as two\n");
await p.getByRole("button", { name: /reload/i }).first().click();
await p.locator(".agent-banner").waitFor({ timeout: 15000 }).then(() => check("the banner says it changed", true), () => check("the banner says it changed", false));
check("3 cells now", (await cells()) === 3, String(await cells()));
check("the banner names what changed", /1 cell added/.test(await p.locator(".agent-banner").innerText()));
check("the new cell is marked", (await p.locator(".cell-block.is-agent-changed").count()) === 1);
await p.waitForTimeout(800);
await p.screenshot({ path: `${OUT}/external-1-updated.png` });

console.log("\n== 02 Undo puts it back, on disk too");
await p.getByRole("button", { name: "Undo" }).click();
await p.getByRole("button", { name: "Allow once" }).click({ timeout: 5000 }).catch(() => {});   // no session in this run: the fence asks
await p.waitForTimeout(7000);
check("2 cells again", (await cells()) === 2, String(await cells()));
check("and it was saved", !cli("workspace", "export", PATH, "--format", "SOURCE").includes("select 2 as two"));
await p.screenshot({ path: `${OUT}/external-2-undone.png` });

console.log("\n== 03 unsaved edits are never overwritten");
await p.locator(".cm-content").first().click();
await p.keyboard.type(" -- mine");
await p.waitForTimeout(500);
check("typing marks it unsaved", !(await p.getByRole("button", { name: /^Save/ }).isDisabled()));
put(base + "\n-- COMMAND ----------\n\nselect 3 as three\n");
await p.getByRole("button", { name: /reload/i }).first().click();
await p.getByRole("alertdialog", { name: /changed/i }).waitFor({ timeout: 15000 }).then(() => check("asks instead of overwriting", true), () => check("asks instead of overwriting", false));
await p.screenshot({ path: `${OUT}/external-3-dirty-choice.png` });
await p.getByRole("button", { name: "Take the new version" }).click();
await p.waitForTimeout(800);
check("their cells are shown", (await cells()) === 3, String(await cells()));
await finish(browser, errors);
