/** Genie Code parity scenes. Every scene asserts what it shows before the picture is taken.
 *
 *   APP_URL=http://127.0.0.1:8062 node scripts/parity-e2e.mjs
 *
 * Needs the app running with a real workspace token (scripts/dev-token.sh 8062) and the seeded
 * notebook `parity_demo` (SQL cells: ok, a table, a failing query).
 */
import { check, finish, launch, openNotebook, shot } from "./parity-lib.mjs";

const { browser, page: p, errors } = await launch(1440, 900);
await openNotebook(p);
/** Scroll ONLY the dock's own scroller to the start of turn n (scrollIntoView would move the page too). */
const scrollDockTo = (n) => p.evaluate((n) => {
  const body = document.querySelector(".dock-body");
  const el = body.querySelectorAll(".turn")[n];
  body.scrollTo({ top: el.getBoundingClientRect().top - body.getBoundingClientRect().top + body.scrollTop - 6, behavior: "instant" });
}, n);

/* 01 · the notebook toolbar and the cell controls */
console.log("\n== 01 notebook toolbar");
check("toolbar shows Run all and what it will do", await p.getByRole("button", { name: /Run all/ }).isVisible()
  && /can run/.test(await p.locator(".nb-bar-status").innerText()), await p.locator(".nb-bar-status").innerText());
check("each cell offers Ask and Run, by name", (await p.getByRole("button", { name: /^Ask the agent about cell/ }).count()) >= 4
  && (await p.locator(".cell-run-act").count()) >= 3);
await shot(p, "01-notebook-toolbar.png");

/* 02 · the seam between two cells */
console.log("\n== 02 seam");
const seam = p.locator(".cell-insert").nth(1);
await seam.hover();
check("hovering the gap shows Code, Text and Generate", await seam.getByRole("button", { name: /generate with the agent/ }).isVisible()
  && await seam.getByRole("button", { name: /: code/ }).isVisible() && await seam.getByRole("button", { name: /: text/ }).isVisible());
await shot(p, "02-insert-seam.png");

/* 03 · Run all runs in order and stops at the first failure */
console.log("\n== 03 run all");
await p.getByRole("button", { name: /Run all/ }).click();
await p.locator(".cell-output[data-state='failed']").waitFor({ timeout: 90000 });
await p.waitForTimeout(500);
const states = await p.locator(".cell-output").evaluateAll((els) => els.map((e) => e.getAttribute("data-state")));
check("the three SQL cells ran in order and the last failed", JSON.stringify(states) === JSON.stringify(["succeeded", "succeeded", "failed"]), states.join(","));
check("the toolbar reports the outcome", /2 ran · 1 failed/.test(await p.locator(".nb-bar-status").innerText()), await p.locator(".nb-bar-status").innerText());
check("the compute label names the warehouse", /warehouse/i.test(await p.locator(".nb-bar-compute").innerText()), await p.locator(".nb-bar-compute").innerText());
check("the failure offers a one-click fix", await p.getByRole("button", { name: /Fix with agent/ }).isVisible());
await p.locator(".cell-block").nth(3).scrollIntoViewIfNeeded();
const runAllBox = await p.getByRole("button", { name: /Run all/ }).boundingBox();
check("Run all stays in view while the cells scroll", runAllBox && runAllBox.y >= 0 && runAllBox.y < 200, JSON.stringify(runAllBox));
const docBar = await p.locator(".doc-bar").boundingBox();
check("and so does the document bar", docBar && docBar.y >= 0 && docBar.y < 120, JSON.stringify(docBar));
await shot(p, "03-run-all-failed.png");

/* 04 · the inline prompt, opened with the keyboard like Genie Code */
console.log("\n== 04 inline prompt (⌘I)");
await p.locator(".cell-block").nth(2).locator(".cm-content").click();
await p.keyboard.press("Meta+i");
const prompt = p.locator(".cell-prompt.is-edit");
await prompt.waitFor({ timeout: 5000 });
check("⌘I opens a prompt on the focused cell, focused and labelled", await prompt.getByRole("textbox").evaluate((el) => el === document.activeElement)
  && /cell 3/.test(await prompt.getByRole("textbox").getAttribute("placeholder")));
check("it offers the four quick actions", (await prompt.locator(".cell-chip").count()) === 5, `${await prompt.locator(".cell-chip").count()} chips`);
await p.keyboard.type("add a limit of 3 rows");
await p.locator(".cell-block").nth(2).scrollIntoViewIfNeeded();
await shot(p, "04-cell-prompt.png");

/* 05 · sending it binds the message to that cell and opens the conversation */
console.log("\n== 05 send");
await p.keyboard.press("Enter");
await p.locator(".turn-foot").first().waitFor({ timeout: 60000 }).catch(() => {});
await p.waitForTimeout(600);
check("the prompt closed", (await p.locator(".cell-prompt").count()) === 0);
const ctxChip = await p.locator(".dock-context-value").innerText();
check("the dock is bound to the cell, and says so", /parity_demo · cell 3/.test(ctxChip), ctxChip);
const sent = await p.locator(".turn .prompt, .turn-prompt, .you-text, .turn-you").first().innerText().catch(() => "");
check("a conversation started", (await p.locator(".dock-body .turn, .dock-body [class*=turn]").count()) > 0);
check("the message says which cell and what to leave alone", /Change only cell 3/.test(await p.locator(".dock-body").innerText()));
await scrollDockTo(0);
await shot(p, "05-prompt-sent.png");

/* 07 · fix with agent quotes the engine */
console.log("\n== 07 fix with agent");
await p.getByRole("button", { name: /Fix with agent/ }).click();
await p.waitForTimeout(1500);
const body = await p.locator(".dock-body").innerText();
check("the message carries the engine's own words", /Cell 4 failed/.test(body) && /TABLE_OR_VIEW_NOT_FOUND/.test(body));
check("and binds to cell 4", /cell 4/.test(await p.locator(".dock-context-value").innerText()));
await p.locator(".turn-foot").nth(1).waitFor({ timeout: 60000 }).catch(() => {});
await scrollDockTo(1);
await shot(p, "07-fix-with-agent.png");

/* 08 · insert a generated cell in a seam */
console.log("\n== 08 generate between cells");
const seam2 = p.locator(".cell-insert").nth(0);
await seam2.hover();
await seam2.getByRole("button", { name: /generate with the agent/ }).click();
const ins = p.locator(".cell-prompt.is-insert");
await ins.waitFor({ timeout: 5000 });
check("a prompt opens in the gap, with its own placeholder", /Describe the cell to add after cell 1/.test(await ins.getByRole("textbox").getAttribute("placeholder")));
await ins.getByRole("textbox").fill("chart trips by hour");
await p.locator(".cell-block").nth(0).scrollIntoViewIfNeeded();
await shot(p, "08-generate-cell.png");
await p.keyboard.press("Escape");
check("Escape closes it without sending", (await p.locator(".cell-prompt").count()) === 0);

await finish(browser, errors);
