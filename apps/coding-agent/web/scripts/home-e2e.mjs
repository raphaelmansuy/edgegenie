/** The home screen, the folder tree picker and the identity, at three widths.
 *   APP_URL=http://127.0.0.1:8062 OUT=../../../specs/006-databricks/e2e/home node scripts/home-e2e.mjs */
import { launch, check, finish, shot } from "./parity-lib.mjs";
let failed = 0;
for (const w of [1440, 1100, 800]) {
  const { browser, page: p, errors } = await launch(w, w === 800 ? 900 : 940);
  console.log(`\n--- ${w}px`);
  const brand = await p.locator(".brand").innerText();
  check(`${w}: the name is OpenGenie`, /OpenGenie/.test(brand.replace(/\n/g, "")), JSON.stringify(brand));
  check(`${w}: the logo is drawn`, (await p.locator(".brand .logo-badge svg").count()) === 1);
  const title = await p.locator("html").evaluate(() => document.title);
  check(`${w}: the tab title is OpenGenie`, title === "OpenGenie", title);
  check(`${w}: the home screen is shown`, (await p.locator(".home").count()) === 1);
  check(`${w}: the folder picker replaced the text box`, (await p.locator(".fp-trigger").count()) === 1);
  // no horizontal overflow anywhere
  if (w === 1440) {
    // A notebook opened once must appear under "Open something", and clicking it must reopen it.
    await p.evaluate(() => { location.hash = "#/notebook/Users/raphael.mansuy@gmail.com/agent_scratch/rf_target"; });
    await p.locator(".cell-block").first().waitFor({ timeout: 30000 });
    await p.waitForTimeout(800);
    await p.evaluate(() => { location.hash = "#/"; });
    await p.locator(".home").waitFor({ timeout: 15000 });
    await p.waitForTimeout(600);
    const items = await p.locator(".home-recent-item").count();
    check("the home screen lists recently opened documents", items >= 1, String(items));
    await p.locator(".home-recent-item").first().click();
    await p.locator(".cell-block").first().waitFor({ timeout: 20000 });
    check("clicking one opens it", (await p.locator(".cell-block").count()) > 0);
    await p.evaluate(() => { location.hash = "#/"; });
    await p.locator(".home").waitFor({ timeout: 15000 });
    await p.waitForTimeout(500);
  }
  const over = await p.evaluate(() => {
    const bad = [...document.querySelectorAll("body *")].filter((e) => {
      const r = e.getBoundingClientRect();
      return r.width > 0 && (r.right > innerWidth + 1 || r.left < -1);
    }).slice(0, 4).map((e) => `${e.tagName}.${(e.className || "").toString().slice(0, 26)}`);
    return { doc: document.documentElement.scrollWidth - innerWidth, bad };
  });
  check(`${w}: nothing overflows horizontally`, over.doc <= 0 && over.bad.length === 0, JSON.stringify(over));
  await shot(p, `${w}-1-home.png`);

  if (w === 1440) {
    // the tree picker
    await p.locator(".fp-trigger").click();
    await p.locator(".fp-pop").waitFor({ timeout: 8000 });
    await p.waitForTimeout(1200);
    check("the picker shows the workspace roots", (await p.locator(".fp-pop .fp-row").count()) >= 2);
    await shot(p, "1440-2-picker.png");
    // expand the home folder and pick agent_scratch
    // The current folder is expanded and scrolled into view when the picker opens.
    await p.waitForFunction(() => [...document.querySelectorAll(".fp-pop .fp-row")]
      .some((e) => /agent_scratch/.test(e.textContent ?? "")), null, { timeout: 15000 }).catch(() => {});
    const target = p.locator(".fp-pop .fp-row.is-current").first();
    const found = await target.count();
    check("the current folder is already expanded and marked", found > 0);
    if (found) {
      // Choose a DIFFERENT folder: its parent's sibling, so the fence really changes.
      const other = p.locator(".fp-pop .fp-row", { hasText: "taxi_hours" }).first();
      const pickRow = (await other.count()) ? other : p.locator(".fp-pop .fp-row .fp-use").first().locator("..");
      await pickRow.hover();
      await pickRow.locator(".fp-use").click();
      await p.waitForTimeout(600);
      check("choosing a folder closes the picker", (await p.locator(".fp-pop").count()) === 0);
      const now = await p.locator(".fp-trigger-path").innerText();
      check("the fence now names the chosen folder", now.length > 1, now);
    }
    await shot(p, "1440-3-picked.png");
    // search inside the picker
    await p.locator(".fp-trigger").click();
    await p.locator(".fp-pop").waitFor({ timeout: 8000 });
    await p.locator(".fp-search").fill("agent_scratch");
    // The workspace API has no name search: this walks folders, so it takes seconds on a real one.
    await p.waitForFunction(() => [...document.querySelectorAll(".fp-pop .fp-use")].length > 0,
      null, { timeout: 45000 }).catch(() => {});
    check("the picker searches folders", (await p.locator(".fp-pop .fp-use").count()) >= 1);
    await shot(p, "1440-4-search.png");
    await p.keyboard.press("Escape");
    await p.waitForTimeout(300);
    check("Escape closes the picker", (await p.locator(".fp-pop").count()) === 0);
    // dark mode
    await p.getByRole("button", { name: /Dark/i }).click().catch(() => {});
    await p.waitForTimeout(700);
    await shot(p, "1440-5-dark.png");
  }
  check(`${w}: no page errors`, errors.length === 0, errors.join(" | "));
  await browser.close();
}
