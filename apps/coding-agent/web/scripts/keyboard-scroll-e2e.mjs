/** The notebook must stay under the user's hands: scrolling, caret, focus and keys.
 *   APP_URL=http://127.0.0.1:8062 node scripts/keyboard-scroll-e2e.mjs */
import { execFileSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import { launch, check, finish, shot } from "./parity-lib.mjs";
// Screenshots: OUT=../../../specs/006-databricks/e2e/keyboard-scroll node scripts/keyboard-scroll-e2e.mjs
const BASE = "/Users/raphael.mansuy@gmail.com/agent_scratch";
const TALL = `${BASE}/tall_demo`;
const put = (path, text) => { writeFileSync("/tmp/kb.sql", text); execFileSync("databricks", ["workspace", "import", path, "--file", "/tmp/kb.sql", "--format", "SOURCE", "--language", "SQL", "--overwrite"]); };
const tall = (n, tag = "") => "-- Databricks notebook source\n-- MAGIC %md\n-- MAGIC # Tall demo\n-- MAGIC Forty cells so that there is something to scroll.\n" +
  Array.from({ length: n }, (_, i) => `\n-- COMMAND ----------\n\nselect ${i + 1} as cell_${i + 1}, '${i === 0 ? tag : "x"}' as tag\n  , 'line two of cell ${i + 1}' as note\n`).join("");
put(TALL, tall(40));
put(`${BASE}/update_demo`, "-- Databricks notebook source\n-- MAGIC %md\n-- MAGIC # Update demo\n\n-- COMMAND ----------\n\nselect 1 as one\n");

const { browser, page: p, errors } = await launch(1440, 900);
await p.locator("textarea").last().fill("hello");
await p.keyboard.press("Enter");
await p.waitForTimeout(3500);                                  // a session, so saves go straight to the scratch folder
const go = async (path) => { await p.evaluate((h) => { location.hash = h; }, `#/notebook${path}`); await p.locator(".cell-block").first().waitFor({ timeout: 30000 }); await p.waitForTimeout(1500); };
await go(TALL);

const st = () => p.evaluate(() => {
  const cells = document.querySelector(".cells");
  let sp = cells;
  while (sp && !/(auto|scroll)/.test(getComputedStyle(sp).overflowY)) sp = sp.parentElement;
  const a = document.activeElement, cell = a?.closest(".cell-block");
  const sel = getSelection();
  return {
    scroll: Math.round(sp?.scrollTop ?? -1), max: Math.round((sp?.scrollHeight ?? 0) - (sp?.clientHeight ?? 0)),
    doc: document.scrollingElement.scrollTop,
    cells: document.querySelectorAll(".cell-block").length,
    cell: cell ? Number(cell.dataset.cell) : 0,
    command: !!a?.classList?.contains("cell-block"),
    inText: !!a?.closest?.(".cm-content"),
    caret: sel?.anchorNode ? sel.anchorOffset : -1,
  };
});
// Coming back from the Databricks UI (an edit made elsewhere) is what asks the app to look again.
const ping = () => p.evaluate(() => window.dispatchEvent(new Event("focus")));
const wheel = async (dy, n = 1) => { await p.mouse.move(700, 500); for (let i = 0; i < n; i++) { await p.mouse.wheel(0, dy); await p.waitForTimeout(40); } await p.waitForTimeout(200); };

// ---- 1. scrolling while the notebook changes under the user's hands
console.log("\n1. scroll while the assistant writes");
await wheel(300, 6);
let s0 = await st();
check("the notebook scrolls with the wheel", s0.scroll > 800 && s0.max > 2000, JSON.stringify(s0));
let monotonic = true, last = s0.scroll;
for (let round = 1; round <= 3; round++) {
  const write = new Promise((res) => setTimeout(() => { put(TALL, tall(40 + round, `v${round}`)); res(); }, 100));
  for (let i = 0; i < 6; i++) { await ping(); await wheel(120); const now = (await st()).scroll; if (now < last - 4) monotonic = false; last = now; }
  await write;
  for (let i = 0; i < 4; i++) { await ping(); await p.waitForTimeout(600); }
  await p.waitForFunction((n) => document.querySelectorAll(".cell-block").length >= n, 41 + round, null, { timeout: 25000 }).catch(() => {});
  const s = await st();
  check(`round ${round}: still scrolling after the outside write (was ${last})`, s.scroll >= last - 6, JSON.stringify(s));
  check(`round ${round}: the new cell arrived`, s.cells >= 41 + round, `cells=${s.cells}`);
  last = s.scroll;
}
check("the wheel was never fought (scrollTop never jumped back)", monotonic);
await wheel(-100, 2);
const afterUp = await st();
check("and scrolls back up", afterUp.scroll < last, `${last} -> ${afterUp.scroll}`);
await shot(p, "01-scrolled-after-writes.png");

// ---- 2. caret survives an outside change elsewhere in the notebook
console.log("\n2. caret and focus survive an adoption");
await p.locator(".cell-block").nth(20).locator(".cm-line").nth(0).click();
await p.keyboard.press("End");
const caretBefore = await st();
check("caret is in cell 21", caretBefore.cell === 21 && caretBefore.inText, JSON.stringify(caretBefore));
put(TALL, tall(45, "changed-top"));
await ping();
await p.waitForFunction(() => document.querySelectorAll(".cell-block").length >= 46, null, { timeout: 25000 }).catch(() => {});
const caretAfter = await st();
check("focus is still in cell 21's text after the adoption", caretAfter.cell === 21 && caretAfter.inText, JSON.stringify(caretAfter));
check("caret did not move", caretAfter.caret === caretBefore.caret, `${caretBefore.caret} -> ${caretAfter.caret}`);
check("the page did not scroll", Math.abs(caretAfter.scroll - caretBefore.scroll) <= 6, `${caretBefore.scroll} -> ${caretAfter.scroll}`);
await p.keyboard.type("Q");
const typed = await p.locator(".cell-block").nth(20).locator(".cm-content").innerText();
check("typing continues in the same cell", typed.includes("Q"), typed.slice(0, 40));
await shot(p, "02-caret-after-adoption.png");

// ---- 3. keyboard: edit / command modes
console.log("\n3. keyboard model");
await p.keyboard.press("Escape");
let k = await st();
check("Esc leaves the text and selects the cell (command mode)", k.command && k.cell === 21, JSON.stringify(k));
await p.keyboard.press("ArrowDown"); await p.waitForTimeout(300);
k = await st(); check("↓ selects the next cell", k.command && k.cell === 22, JSON.stringify(k));
await p.keyboard.press("k");
k = await st(); check("k selects the previous cell", k.cell === 21);
const n0 = k.cells;
await p.keyboard.press("b"); await p.waitForTimeout(400);
k = await st(); check("b adds a cell below and puts the caret in it", k.cells === n0 + 1 && k.cell === 22 && k.inText, JSON.stringify(k));
await p.keyboard.type("select 'new'");
await p.keyboard.press("Escape"); await p.keyboard.press("Escape");   // the first closes the completion list
await p.keyboard.press("d"); await p.keyboard.press("d"); await p.waitForTimeout(400);
k = await st(); check("d d deletes the cell and selects its neighbour", k.cells === n0 && k.command, JSON.stringify(k));
await p.keyboard.press("z"); await p.waitForTimeout(400);
k = await st(); check("z brings the deleted cell back", k.cells === n0 + 1, JSON.stringify(k));
check("…with the text that was typed", (await p.locator(".cell-block").nth(21).locator(".cm-content").innerText()).includes("new"));
await p.keyboard.press("Enter"); await p.waitForTimeout(400);
k = await st(); check("Enter goes back into the text", k.inText && k.cell === 22, JSON.stringify(k));
await p.keyboard.press("Escape");
await p.keyboard.press("Alt+ArrowUp"); await p.waitForTimeout(400);
k = await st(); check("Alt+↑ moves the cell up and keeps it selected", k.command && k.cell === 21, JSON.stringify(k));
await p.keyboard.press("Alt+ArrowDown");
await p.keyboard.press("d"); await p.keyboard.press("d");
await shot(p, "03-command-mode.png");

// ---- 4. run chords
console.log("\n4. run chords");
await p.locator(".cell-block").nth(2).locator(".cm-line").nth(0).click();
await p.keyboard.press("Shift+Enter"); await p.waitForTimeout(400);
k = await st(); check("Shift+Enter runs and moves to the next cell's text", k.cell === 4 && k.inText, JSON.stringify(k));
await p.keyboard.press("Meta+Enter");
k = await st(); check("⌘Enter runs and stays", k.cell === 4 && k.inText, JSON.stringify(k));
const n1 = k.cells;
await p.keyboard.press("Alt+Enter"); await p.waitForTimeout(400);
k = await st(); check("Alt+Enter runs and inserts a cell below", k.cells === n1 + 1 && k.cell === 5, JSON.stringify(k));
await p.waitForTimeout(6000);
check("the cells ran (a result is shown)", (await p.locator(".cell-output, .cell-output-wrap").count()) >= 2);
await p.keyboard.press("Escape"); await p.keyboard.press("d"); await p.keyboard.press("d");

// ---- 5. mouse: markdown
console.log("\n5. markdown with the mouse");
await p.evaluate(() => document.querySelector(".cells").closest(".editor-surface")?.querySelectorAll("*").forEach(() => 0));
await p.mouse.move(700, 500); await p.mouse.wheel(0, -20000); await p.waitForTimeout(500);
const md = p.locator(".cell-block.is-md").first();
await md.locator(".cell-rendered").click();
k = await st(); check("one click selects the markdown cell, it does not start editing", k.command && k.cell === 1, JSON.stringify(k));
await md.locator(".cell-rendered").dblclick();
await p.waitForTimeout(500);
k = await st(); check("double-click edits it", k.inText && k.cell === 1, JSON.stringify(k));
await p.keyboard.press("Escape");
await p.waitForTimeout(300);
check("Esc renders it again", (await md.locator(".cell-rendered").count()) === 1);

// ---- 6. save keeps the caret
console.log("\n6. save keeps the caret");
await p.locator(".cell-block").nth(8).locator(".cm-line").nth(0).click();
await p.keyboard.press("End"); await p.keyboard.type("--a");
const preSave = await st();
await p.keyboard.press("Meta+s");
await p.waitForTimeout(6000);
let post = await st();
check("⌘S: caret and focus stay", post.cell === preSave.cell && post.inText && post.caret === preSave.caret, `${JSON.stringify(preSave)} -> ${JSON.stringify(post)}`);
await p.keyboard.type("b");
await p.getByRole("button", { name: /^Save/ }).click({ timeout: 3000 }).catch(() => {});
await p.waitForTimeout(6000);
post = await st();
check("the Save button does not take the caret", post.inText && post.cell === preSave.cell, JSON.stringify(post));
await p.keyboard.type("c");
const txt = await p.locator(".cell-block").nth(8).locator(".cm-content").innerText();
check("typing carries on after saving", txt.includes("--abc"), txt.slice(0, 80));

// ---- 7. the place is remembered per document
console.log("\n7. place is remembered");
await p.mouse.move(700, 500); await p.mouse.wheel(0, 20000); await p.waitForTimeout(300); await p.mouse.wheel(0, -1500); await p.waitForTimeout(600);
await p.locator(".cell-block").nth(30).scrollIntoViewIfNeeded();
await p.locator(".cell-block").nth(30).locator(".cm-line").nth(0).click();
await p.keyboard.press("End");
await p.waitForTimeout(500);
const here = await st();
await go(`${BASE}/update_demo`);
await go(TALL);
await p.waitForTimeout(1200);
const back = await st();
check("back in the notebook: same cell", back.cell === here.cell && back.inText, `${JSON.stringify(here)} -> ${JSON.stringify(back)}`);
check("back in the notebook: same scroll", Math.abs(back.scroll - here.scroll) < 60, `${here.scroll} -> ${back.scroll}`);
check("back in the notebook: same caret", back.caret === here.caret, `${here.caret} -> ${back.caret}`);
await shot(p, "07-restored.png");

check("the app shell itself never scrolled", (await st()).doc === 0, String((await st()).doc));
await finish(browser, errors);
