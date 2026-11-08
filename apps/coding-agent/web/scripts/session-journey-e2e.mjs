/** The coding-session journey from a document, at the widths where the assistant is a drawer.
 *
 *   APP_URL=http://127.0.0.1:8062 W=1100 node scripts/session-journey-e2e.mjs
 *
 * 1. In a notebook, type a request in ITS composer and send.   -> the conversation must appear.
 * 2. Close the drawer.                                        -> the notebook shows a status strip and
 *                                                                the topbar a chip, never nothing.
 * 3. "Show conversation" / the chip brings the thread back.
 * Screenshots: specs/006-databricks/e2e/session-journey.
 */
import { check, finish, launch, shot as baseShot } from "./parity-lib.mjs";
import { mkdirSync } from "node:fs";
const W = Number(process.env.W ?? 1100);
const OUT = process.env.OUT ?? "../../../specs/006-databricks/e2e/session-journey";
mkdirSync(OUT, { recursive: true });
const shot = (p, f) => baseShot(p, f, { path: `${OUT}/${f}` });
const { browser, page: p, errors } = await launch(W, 760);
await p.goto(`${process.env.APP_URL ?? "http://127.0.0.1:8062"}/#/notebook/Users/raphael.mansuy@gmail.com/agent_scratch/parity_demo`);
await p.locator(".cell-block").first().waitFor({ timeout: 30000 });

console.log(`\n== 01 send from the notebook's composer at ${W}px`);
await p.locator("textarea").last().fill("Update this notebook to add a chart");
await p.keyboard.press("Enter");
await p.getByRole("complementary", { name: /assistant/i }).or(p.locator(".pane.assistant")).first()
  .waitFor({ timeout: 8000 }).then(() => check("the conversation appears", true), () => check("the conversation appears", false));
await p.getByText("Update this notebook to add a chart").first().waitFor({ state: "attached", timeout: 8000 }).then(() => check("the thread shows the request", true), () => check("the thread shows the request", false));
await shot(p, `${W}-1-conversation-opens.png`);

check("the notebook is not dimmed", (await p.locator(".drawer-scrim:not(.is-clear)").count()) === 0);
if (W >= 860) check("the notebook sits beside the conversation, not under it", await p.evaluate(() => {
  const n = document.querySelector(".doc-panel")?.getBoundingClientRect(), d = document.querySelector(".pane.assistant")?.getBoundingClientRect();
  return Boolean(n && d && n.right <= d.left + 1);
}));
if (W >= 860) {
  await p.getByRole("button", { name: "Show the navigator" }).click();
  await p.locator("nav.rail.is-drawer").waitFor({ timeout: 4000 }).then(() => check("the navigator comes back as a drawer", true), () => check("the navigator comes back as a drawer", false));
  check("the conversation is still beside the notebook", await p.locator(".pane.assistant.dock-column").isVisible());
  await shot(p, `${W}-1b-navigator-drawer.png`);
  await p.getByRole("button", { name: "Hide the navigator" }).click();
}
console.log("\n== 02 close it: the notebook still shows the session");
await p.getByRole("button", { name: "Hide the assistant" }).first().click();
await p.waitForTimeout(500);
check("a status strip is on the notebook", await p.locator(".session-peek").isVisible());
check("the topbar chip is there", await p.locator(".session-chip").isVisible());
await shot(p, `${W}-2-strip.png`);

console.log("\n== 03 one click brings the thread back");
await p.getByRole("button", { name: "Show conversation" }).click();
await p.locator(".pane.assistant").waitFor({ timeout: 5000 }).then(() => check("the thread is back", true), () => check("the thread is back", false));
await finish(browser, errors);
