/** The new notebook controls at other widths and in the dark theme.
 *   APP_URL=http://127.0.0.1:8062 node scripts/parity-widths-e2e.mjs
 */
import { check, finish, launch, openNotebook, shot } from "./parity-lib.mjs";

const cases = [
  { w: 1440, scheme: "dark", tag: "12-dark" },
  { w: 1024, scheme: "light", tag: "13-w1024" },
  { w: 760, scheme: "light", tag: "14-w760" },
];
let lastErrors = [];
for (const c of cases) {
  console.log(`\n== ${c.tag} (${c.w}px, ${c.scheme})`);
  const { browser, page: p, errors } = await launch(c.w, 900, c.scheme);
  if (c.w < 900) {
    // At this width the navigator is a drawer: open it, choose the notebook, and it closes.
    await p.getByRole("button", { name: "Show the navigator" }).click().catch(() => {});
    await p.getByRole("tab", { name: /Files/i }).waitFor({ timeout: 8000 });
  }
  await openNotebook(p).catch(async () => { await p.waitForTimeout(500); });
  await p.locator(".cell-block").first().waitFor({ timeout: 30000 });
  await p.locator(".cell-run-act").first().click();
  await p.locator(".cell-output").first().waitFor({ timeout: 60000 });
  await p.waitForFunction(() => !document.querySelector(".cell-output[data-state='running']"), null, { timeout: 60000 });
  await p.locator(".cell-block").nth(2).getByRole("button", { name: /^Ask the agent about cell 3/ }).click();
  await p.locator(".cell-prompt.is-edit").waitFor();
  const over = await p.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  check("no horizontal overflow", over <= 0, `${over}px`);
  const bar = await p.locator(".nb-bar").boundingBox();
  const kids = await p.locator(".nb-bar > *").evaluateAll((els) => els.map((e) => { const r = e.getBoundingClientRect(); return r.right; }));
  check("the notebook toolbar fits its row", kids.every((r) => r <= bar.x + bar.width + 1), `${Math.round(Math.max(...kids))} vs ${Math.round(bar.x + bar.width)}`);
  const pb = await p.locator(".cell-prompt.is-edit").boundingBox();
  check("the cell prompt is inside the window", pb.x >= 0 && pb.x + pb.width <= c.w, JSON.stringify(pb));
  await p.locator(".cell-block").nth(2).scrollIntoViewIfNeeded();
  await shot(p, `${c.tag}-cell-prompt.png`);
  lastErrors = lastErrors.concat(errors);
  await browser.close();
}
const { browser, errors } = await launch(1440, 900);
await finish(browser, lastErrors.concat(errors));
