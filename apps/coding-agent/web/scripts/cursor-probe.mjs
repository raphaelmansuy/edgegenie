/** Where is the caret, and what has focus, before and after each thing that could move it? Prints a table.
 *   APP_URL=http://127.0.0.1:8062 node scripts/cursor-probe.mjs */
import { execFileSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import { launch } from "./parity-lib.mjs";
const PATH = "/Users/raphael.mansuy@gmail.com/agent_scratch/update_demo";
const put = (t) => { writeFileSync("/tmp/ud.sql", t); execFileSync("databricks", ["workspace", "import", PATH, "--file", "/tmp/ud.sql", "--format", "SOURCE", "--language", "SQL", "--overwrite"]); };
put("-- Databricks notebook source\n-- MAGIC %md\n-- MAGIC # Update demo\n\n-- COMMAND ----------\n\nselect 1 as one,\n  2 as two,\n  3 as three\nfrom dual\n\n-- COMMAND ----------\n\nselect 4 as four\n");
const { browser, page: p } = await launch(1440, 900);
await p.locator("textarea").last().fill("hello");
await p.keyboard.press("Enter");
await p.waitForTimeout(4000);
await p.goto(`${process.env.APP_URL ?? "http://127.0.0.1:8062"}/#/notebook${PATH}`);
await p.reload();
await p.locator(".cell-block").first().waitFor({ timeout: 30000 });
await p.waitForTimeout(1500);
const state = () => p.evaluate(() => {
  const a = document.activeElement;
  const cell = a?.closest(".cell-block");
  const sel = window.getSelection();
  const line = sel?.anchorNode ? (sel.anchorNode.nodeType === 3 ? sel.anchorNode.parentElement : sel.anchorNode).closest?.(".cm-line") : null;
  const lines = line ? [...line.parentElement.children] : [];
  const scroller = document.querySelector(".editor-surface .cells, .viewer-body, .doc-panel");
  return {
    focusIn: cell ? `cell ${cell.dataset.cell}` : (a?.tagName + "." + (a?.className || "").toString().slice(0, 20)),
    caret: line ? `line ${lines.indexOf(line) + 1} col ${sel.anchorOffset}` : "—",
    scrollTop: Math.round(document.querySelector(".cells")?.closest(".editor-surface")?.scrollTop ?? document.scrollingElement.scrollTop),
  };
});
const rows = [];
const note = async (what) => rows.push([what, JSON.stringify(await state())]);
const saveMenu = async () => { await p.getByRole("button", { name: "Allow once" }).click({ timeout: 2500 }).catch(() => {}); await p.waitForTimeout(5500); };

// code cell, caret in the middle of line 2 of cell 2
const cell2 = p.locator(".cell-block").nth(1);
await cell2.locator(".cm-line").nth(1).click();
await p.keyboard.press("End"); await p.keyboard.press("ArrowLeft"); await p.keyboard.press("ArrowLeft");
await p.keyboard.type("X");
await note("typed X in cell 2 line 2");
await p.keyboard.press("Meta+s"); await saveMenu();
await note("after ⌘S (keyboard)");
await p.keyboard.type("Y");
await note("typing again after the save");
await p.getByRole("button", { name: /^Save/ }).click({ timeout: 2000 }).catch(() => rows.push(["Save button", "disabled?"]));
await saveMenu();
await note("after clicking the Save button");
await p.keyboard.type("Z");
await note("typing after Save-button save");

// run a cell from the keyboard
await p.keyboard.press("Shift+Enter"); await p.waitForTimeout(4000);
await note("after Shift+Enter (run and advance?)");

// external change while a caret is in a cell
await cell2.locator(".cm-line").nth(0).click();
await note("clicked cell 2 line 1");
put("-- Databricks notebook source\n-- MAGIC %md\n-- MAGIC # Update demo\n\n-- COMMAND ----------\n\nselect 1 as one,\n  2 as two,\n  3 as three\nfrom dual\n\n-- COMMAND ----------\n\nselect 4 as four\n\n-- COMMAND ----------\n\nselect 5 as five\n");
await p.getByRole("button", { name: /reload/i }).first().click(); await p.waitForTimeout(2500);
await note("after an outside change was adopted");
console.log("mounts:", JSON.stringify(await p.evaluate(() => window.__m)));
console.log(rows.map((r) => r.join("  |  ")).join("\n"));
await browser.close();
