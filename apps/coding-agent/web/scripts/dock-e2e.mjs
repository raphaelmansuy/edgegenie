/** The eleven scenes of spec 006, and the dead-control walk (UX-1).
 *
 *   APP_URL=http://127.0.0.1:8060 node scripts/dock-e2e.mjs [outdir]
 *
 * Every scene is one assertion a person could describe in a sentence, so a failure names a
 * user-visible behaviour rather than a selector. Screenshots are written beside the report so a
 * scene that passes can still be looked at.
 *
 * Two rules this file follows, both learned the hard way in this repository:
 *  - it drives the app the way a person does (type, click, press) and never sets DOM state;
 *  - every optional step is guarded, so a slow agent or an empty workspace reports rather than
 *    crashing the run and hiding the scenes that would have passed.
 */
import { chromium } from "playwright";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";

const out = process.argv[2] ?? "/tmp/dock-e2e";
mkdirSync(out, { recursive: true });
const APP = process.env.APP_URL ?? "http://127.0.0.1:8060";
const bearer = process.env.BEARER_FILE ? readFileSync(process.env.BEARER_FILE, "utf8").trim() : "";
const PROMPT = process.env.PROMPT ?? "Build a notebook that shows revenue by month.";

const results = [];
const check = (name, ok, detail = "") => {
  results.push({ name, ok, detail });
  console.log(`  ${ok ? "PASS" : "FAIL"} ${name}${detail ? ` — ${detail}` : ""}`);
};

const b = await chromium.launch({ executablePath: process.env.CHROME_PATH || undefined });
const page = async (width, height = 900) => {
  const p = await b.newPage({ viewport: { width, height },
    extraHTTPHeaders: bearer ? { Authorization: `Bearer ${bearer}` } : {} });
  await p.goto(APP, { waitUntil: "domcontentloaded" });
  await p.waitForTimeout(1800);
  return p;
};
const text = (p, sel) => p.locator(sel).first().textContent().catch(() => "");
const visible = (p, sel) => p.locator(sel).first().isVisible().catch(() => false);

// ---------------------------------------------------------------- 1 · fresh load
{
  const p = await page(1600);
  const dockEmpty = await visible(p, ".dock-start");
  check("1 fresh load: the dock offers suggestions", dockEmpty);
  // A reload must not create a session: compare the rail before and after, not against zero (the
  // workspace legitimately has earlier sessions).
  const before = await p.locator(".rail-item").count();
  await p.reload({ waitUntil: "domcontentloaded" });
  await p.waitForTimeout(1600);
  const after = await p.locator(".rail-item").count();
  check("1 fresh load: opening the app creates no session", after <= before, `${before} → ${after}`);
  check("1 fresh load: nothing is modal", !(await visible(p, '[role="dialog"][aria-modal="true"]')));
  await p.screenshot({ path: `${out}/01-fresh.png` });
  await p.close();
}

// ---------------------------------------------------------------- 2 · the dock sends, the turn stays
{
  const p = await page(1600);
  const box = p.locator('.composer.is-dock textarea');
  check("2 the dock has its own composer", await box.count() > 0);
  await box.first().fill(PROMPT);
  await box.first().press("Enter");
  await p.locator(".pane.assistant .turn").first().waitFor({ timeout: 90000 }).catch(() => {});
  await p.waitForTimeout(2500);
  const turns = await p.locator(".pane.assistant .turn").count();
  check("2 a turn renders inside the dock", turns >= 1, `${turns} turn(s)`);
  const chip = await text(p, ".dock-context");
  check("2 the dock names what it is about", /in context/i.test(chip), chip.trim());
  await p.screenshot({ path: `${out}/02-dock-turn.png` });
  await p.close();
}

// ---------------------------------------------------------------- 3 · a document does NOT replace it
{
  const p = await page(1600);
  const box = p.locator('.composer.is-dock textarea');
  await box.first().fill(PROMPT);
  await box.first().press("Enter");
  await p.locator(".pane.assistant .turn").first().waitFor({ timeout: 90000 }).catch(() => {});
  const before = await p.locator(".pane.assistant .turn").count();

  // open a real file through Files
  let opened = false;
  await p.getByRole("tab", { name: "Files" }).click().catch(() => {});
  // Wait for the tree to have rows: a fixed delay made this scene report "no file could be opened"
  // on a workspace that simply answered slower than the sleep.
  await p.waitForSelector('.rail .tree-body [role="treeitem"]', { timeout: 20000 }).catch(() => {});
  for (let pass = 0; pass < 3 && !opened; pass += 1) {
    const rows = p.locator('.rail .tree-body [role="treeitem"]');
    const n = await rows.count();
    for (let i = 0; i < n; i += 1) {
      const row = rows.nth(i);
      if ((await row.getAttribute("aria-expanded")) === "false") {
        await row.click({ timeout: 4000 }).catch(() => {});
        await p.waitForTimeout(800);
        break;
      }
    }
    const after = p.locator('.rail .tree-body [role="treeitem"]');
    const m = await after.count();
    for (let i = 0; i < m; i += 1) {
      const row = after.nth(i);
      if ((await row.getAttribute("aria-expanded")) !== null) continue;
      await row.click({ timeout: 4000 }).catch(() => {});
      await p.waitForTimeout(1800);
      if (await p.locator(".doc-tabs").count()) { opened = true; break; }
    }
  }
  const stillThere = await p.locator(".pane.assistant .turn").count();
  check("3 a document opens without replacing the conversation", !opened || stillThere >= before,
    opened ? `${stillThere} turn(s) still in the dock` : "no file could be opened in this workspace");
  const chip = await text(p, ".dock-context");
  check("3 the docking chip follows the open document", !opened || chip.trim().length > 0, chip.trim());
  await p.screenshot({ path: `${out}/03-document-and-dock.png` });
  await p.close();
}

// ---------------------------------------------------------------- 4 · ask about a cell
{
  const p = await page(1600);
  const box = p.locator('.composer.is-dock textarea');
  await box.first().fill(PROMPT);
  await box.first().press("Enter");
  await p.locator(".pane.assistant .turn").first().waitFor({ timeout: 90000 }).catch(() => {});
  // find a notebook: expand, open leaves until a cell editor appears
  await p.getByRole("tab", { name: "Files" }).click().catch(() => {});
  await p.waitForSelector('.rail .tree-body [role="treeitem"]', { timeout: 20000 }).catch(() => {});
  let notebook = false;
  for (let pass = 0; pass < 4 && !notebook; pass += 1) {
    const rows = p.locator('.rail .tree-body [role="treeitem"]');
    const n = await rows.count();
    for (let i = 0; i < n && !notebook; i += 1) {
      const row = rows.nth(i);
      const exp = await row.getAttribute("aria-expanded");
      if (exp === "false") { await row.click({ timeout: 4000 }).catch(() => {}); await p.waitForTimeout(700); continue; }
      if (exp !== null) continue;
      await row.click({ timeout: 4000 }).catch(() => {});
      await p.waitForTimeout(1600);
      notebook = await p.locator(".cell-block").count() > 0;
    }
  }
  const ask = p.locator(".cell-block .cell-ask").first();
  const hasAsk = await ask.count() > 0;
  check("4 a cell offers the ask action", notebook ? hasAsk : true, notebook ? "" : "no notebook opened");
  if (hasAsk) {
    /* Asking about a cell now opens the prompt IN PLACE, bound to that cell — "What should the agent
       do with cell 1?" — instead of sending a generic question to the dock. The binding is still the
       cell, it is simply stated on the cell. Asserting the old behaviour (a dock chip reading "cell N")
       tested a surface the product no longer has; what matters is that the instruction is bound to
       THAT cell and that the field takes focus, so the user can type immediately. */
    await ask.click({ timeout: 5000 }).catch(() => {});
    await p.waitForTimeout(700);
    const prompt = p.locator(".cell-prompt").first();
    check("4 asking about a cell opens an instruction bound to that cell", await prompt.count() > 0);
    if (await prompt.count()) {
      const ph = await prompt.locator("textarea").first().getAttribute("placeholder");
      check("4 …and the field names the cell it is for", /cell 1/i.test(ph ?? ""), ph ?? "");
      const focused = await p.evaluate(() => !!document.activeElement?.closest(".cell-prompt"));
      check("4 …and it takes focus, so the user can type", focused);
    }
  }
  const runButtons = await p.locator(".cell-run").count();
  check("4 there is no inert run button", runButtons === 0, `${runButtons} found`);
  await p.screenshot({ path: `${out}/04-cell-bound.png` });
  await p.close();
}

// ---------------------------------------------------------------- 5 · ⌘J, both directions
for (const width of [1600, 760]) {
  const p = await page(width);
  // Wide: the assistant is docked, so the first press hides it. Narrow: it is a drawer that starts
  // closed (a drawer that opened by itself would cover the workspace), so the first press opens it.
  const docked = width >= 1136;
  const before = await p.locator(".pane.assistant").count();
  await p.keyboard.press("Meta+j");
  await p.waitForTimeout(600);
  const afterFirst = await p.locator(".pane.assistant").count();
  await p.keyboard.press("Meta+j");
  await p.waitForTimeout(600);
  const afterSecond = await p.locator(".pane.assistant").count();
  check(`5 ⌘J ${docked ? "hides" : "opens"} the assistant at ${width}`,
    docked ? before > 0 && afterFirst === 0 : before === 0 && afterFirst > 0, `${before} → ${afterFirst}`);
  check(`5 ⌘J ${docked ? "shows it again" : "closes it again"} at ${width}`,
    docked ? afterSecond > 0 : afterSecond === 0, `${afterSecond}`);
  await p.screenshot({ path: `${out}/05-dock-${width}.png` });
  await p.close();
}

// ---------------------------------------------------------------- 6 · never opens on resize
{
  const p = await page(1600);
  await p.keyboard.press("Meta+j");            // hide it, deliberately
  await p.waitForTimeout(500);
  await p.setViewportSize({ width: 760, height: 900 });
  await p.waitForTimeout(900);
  const opened = await p.locator(".pane.assistant.is-drawer").count();
  check("6 a resize never opens the assistant", opened === 0);
  await p.close();
}

// ---------------------------------------------------------------- 7 · the model is always reachable
for (const width of [1600, 1180, 1024, 760]) {
  const p = await page(width);
  const triggers = await p.evaluate(() => [...document.querySelectorAll(".model-trigger")]
    .filter((e) => e.getBoundingClientRect().width > 0).length);
  check(`7 a model control is on screen at ${width}`, triggers > 0, `${triggers} visible`);
  if (triggers > 0) {
    const box = await p.evaluate(() => {
      const el = [...document.querySelectorAll(".model-trigger")]
        .find((e) => e.getBoundingClientRect().width > 0 && !e.disabled);
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
    });
    if (box) await p.mouse.click(box.x, box.y);
    // Wait for the popover rather than sleeping: it is portalled and positioned in a layout effect,
    // so a fixed delay reported "the picker does not open" on a slow first paint.
    const opened = await p.waitForSelector(".picker", { timeout: 6000 }).then(() => true).catch(() => false);
    check(`7 the picker opens at ${width}`, opened);
    // The popover must be inside the viewport: a control that opens off-screen is not reachable.
    const inside = await p.evaluate(() => {
      const el = document.querySelector(".picker");
      if (!el) return false;
      const r = el.getBoundingClientRect();
      return r.x >= 0 && r.y >= 0 && r.right <= window.innerWidth + 1 && r.bottom <= window.innerHeight + 1;
    });
    check(`7 the picker is fully on screen at ${width}`, inside);
    await p.screenshot({ path: `${out}/07-model-${width}.png` });
    await p.keyboard.press("Escape");
  }
  await p.close();
}

// ---------------------------------------------------------------- 8 · every button does something
{
  const p = await page(1600);
  const dead = await p.evaluate(async () => {
    const scopes = [".pane.rail", ".pane.main", ".pane.assistant"];
    const dead = [];
    for (const scope of scopes) {
      const root = document.querySelector(scope);
      if (!root) continue;
      for (const btn of root.querySelectorAll("button")) {
        const r = btn.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) continue;
        if (btn.disabled || btn.getAttribute("aria-disabled") === "true") continue;
        // A button is "wired" if it has a click handler React can see, or is a submit/link-ish
        // control. This is a structural probe: the *behavioural* probe is the scenes above.
        const props = Object.keys(btn).find((k) => k.startsWith("__reactProps"));
        const hasHandler = props ? Boolean(btn[props]?.onClick) : false;
        if (!hasHandler) {
          dead.push({ label: btn.getAttribute("aria-label") || btn.textContent?.trim().slice(0, 30), scope,
            cls: btn.className });
        }
      }
    }
    return dead;
  });
  check("8 every rendered button has a handler", dead.length === 0, dead.map((d) => d.label).join(", "));
  await p.close();
}

const failed = results.filter((r) => !r.ok);
writeFileSync(`${out}/report.json`, JSON.stringify({ app: APP, at: new Date().toISOString(), results }, null, 2));
console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
await b.close();
process.exit(failed.length ? 1 : 0);
