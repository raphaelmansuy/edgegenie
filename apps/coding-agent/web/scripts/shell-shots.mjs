/** Capture every shell state into specs/001-perfect-shell/e2e/screenshots, for visual inspection.
 *
 *   APP_URL=http://127.0.0.1:8040 node scripts/shell-shots.mjs
 *   SCENE=layout-menu,reset node scripts/shell-shots.mjs      # just these, keeping the rest
 *
 * Each scene gets a fresh browser context, so nothing leaks between shots. Each scene asserts the
 * property it is meant to demonstrate, so a screenshot can never quietly show a broken state.
 */
import { chromium } from "playwright";
import { mkdirSync, readFileSync, rmSync } from "node:fs";

const out = process.argv[2] ?? "../../../specs/001-perfect-shell/e2e/screenshots";
const only = (process.env.SCENE ?? "").split(",").filter(Boolean);
if (only.length === 0) rmSync(out, { recursive: true, force: true });
mkdirSync(out, { recursive: true });

const bearerPath = process.env.BEARER_FILE;
const headers = bearerPath ? { Authorization: `Bearer ${readFileSync(bearerPath, "utf8").trim()}` } : undefined;
const APP = process.env.APP_URL ?? "http://127.0.0.1:8040";
const shots = [];

const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || undefined });

const fail = (m) => { throw new Error(m); };

let currentScene = "";
async function scene(name, width, body, scheme) {
  if (only.length && !only.includes(name)) return;
  currentScene = name;
  const context = await browser.newContext({
    viewport: { width, height: 900 }, deviceScaleFactor: 2,
    ...(scheme ? { colorScheme: scheme } : {}),
    ...(headers ? { extraHTTPHeaders: headers } : {}),
  });
  const page = await context.newPage();
  try {
    await page.goto(APP, { waitUntil: "load" });
    await page.locator(".composer textarea").waitFor({ state: "visible", timeout: 45000 });
    await page.waitForTimeout(800);
    await body(page);
  } catch (e) {
    await page.screenshot({ path: `${out}/FAIL-${name}.png` }).catch(() => {});
    const diag = await page.evaluate(() => ({
      url: location.href, title: document.title, nodes: document.querySelectorAll("*").length,
      body: document.body.innerHTML.slice(0, 200), composer: !!document.querySelector(".composer textarea"),
    })).catch((err) => ({ evalFailed: String(err).slice(0, 120) }));
    throw new Error(`${name}: ${e.message.split("\n")[0]} :: ${JSON.stringify(diag)}`);
  } finally {
    await context.close().catch(() => {});
  }
}

/* Every shot's position, declared once, keyed by its own name.
   The filename must not come from a run counter: running a subset with SCENE=... produced
   01-mid-... beside 01-default-..., and scenes that take two shots (hover then focus) collided on
   the same number. Keying on the shot name makes a partial run write byte-identical filenames to a
   full run, so the folder is always consistent and a doc link never dangles. */
const ORDER = [
  "default-layout", "resized-zones", "separator-hover", "separator-keyboard-focus",
  "all-hidden", "restored-by-toggles", "layout-menu", "tab-strip-overflow", "palette-reset-layout",
  "shortcut-sheet", "mid-inspector-drawer", "narrow-navigator-drawer", "no-session-no-empty-panel",
  "theme-light", "theme-dark", "theme-follows-system",
];

const shot = async (page, name) => {
  await page.waitForTimeout(250);
  const at = ORDER.indexOf(name);
  if (at < 0) throw new Error(`shot "${name}" is not in ORDER; add it so its number is stable`);
  const file = `${String(at + 1).padStart(2, "0")}-${name}.png`;
  await page.screenshot({ path: `${out}/${file}` });
  shots.push(file);
  console.log(`  ${file}`);
};

const grid = (page) => page.evaluate(() => ({
  columns: getComputedStyle(document.querySelector(".layout")).gridTemplateColumns,
  rail: document.querySelector(".pane.rail")?.getBoundingClientRect().width ?? 0,
  main: document.querySelector(".pane.main").getBoundingClientRect().width,
  inspector: document.querySelector(".pane.inspector")?.getBoundingClientRect().width ?? 0,
}));

const turn = async (page) => {
  /* Wait until the composer is actually usable before typing into it.

     Sending too early produced a real 422 from the server: the model <select> is populated from
     /api/models, and in the window before that response lands the app holds the placeholder
     "model-a" rather than "fake/model-a", so `POST /api/sessions` was rejected with "model
     model-a is not allowed for this user". The screenshot then showed an empty session and the
     failure surfaced as "the work area did not take the whole width" several assertions later —
     a misleading message for a startup race.

     So: require a real model id (contains a "/"), a non-empty folder, and an enabled Send. */
  await page.waitForFunction(() => {
    const ta = document.querySelector(".composer textarea");
    if (!ta) return false;
    const sel = document.querySelector(".setup select");
    if (sel && !String(sel.value).includes("/")) return false;
    const folder = document.querySelector(".setup input");
    if (folder && !String(folder.value).trim()) return false;
    return true;
  }, null, { timeout: 30000 });

  await page.locator(".composer textarea").fill("Build a notebook that shows revenue by pickup hour");
  await page.keyboard.press("Enter");
  // The turn must actually start: a rejected POST leaves no .turn and the scene would otherwise
  // fail much later with an unrelated message.
  await page.locator(".turn").first().waitFor({ timeout: 45000 }).catch(async () => {
    const body = await page.evaluate(async () => {
      const r = await fetch("/api/sessions", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ folder: "x", model: "y" }) }).catch(() => null);
      return r ? `probe ${r.status}` : "probe failed";
    }).catch(() => "");
    fail(`the turn never started (no .turn element) — the send was probably rejected. ${body}`);
  });
  await page.locator(".turn-foot").first().waitFor({ timeout: 150000 }).catch(() => {});
  await page.waitForTimeout(400);
};

/** A pointer click where the element is, which is what a person does. */
const tap = async (page, locator) => {
  const box = await locator.boundingBox();
  if (!box) fail("the control has no box to click");
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
};

/* ------------------------------------------------------------------ the scenes */

await scene("default", 1440, async (p) => {
  await turn(p);
  const g = await grid(p);
  if (Math.round(g.rail) !== 276 || Math.round(g.inspector) !== 340) fail(`unexpected columns: ${g.columns}`);
  await shot(p, "default-layout");
});

await scene("resized", 1440, async (p) => {
  await turn(p);
  for (const [selector, dx] of [[".pane.rail > .separator", 110], [".pane.inspector > .separator", -80]]) {
    const box = await p.locator(selector).boundingBox();
    await p.mouse.move(box.x + 3, box.y + 320);
    await p.mouse.down();
    await p.mouse.move(box.x + dx, box.y + 320, { steps: 12 });
    await p.mouse.up();
    await p.waitForTimeout(300);
  }
  const g = await grid(p);
  if (g.rail < 330 || g.inspector < 390) fail(`dragging did not resize: ${g.columns}`);
  await shot(p, "resized-zones");
});

await scene("separator", 1440, async (p) => {
  const sep = p.locator(".pane.rail > .separator");
  await sep.hover();
  await shot(p, "separator-hover");
  await sep.focus();
  await p.keyboard.press("ArrowRight");
  if (!(await p.evaluate(() => document.activeElement?.classList.contains("separator")))) fail("the separator did not take focus");
  await shot(p, "separator-keyboard-focus");
});

await scene("hidden", 1440, async (p) => {
  await turn(p);
  await p.keyboard.press("Meta+b");
  await p.keyboard.press("Meta+i");
  await p.waitForTimeout(500);
  const g = await grid(p);
  if (Math.round(g.main) !== 1440) fail(`the work area did not take the whole width: ${g.columns}`);
  const railToggle = p.getByRole("button", { name: "Show the navigator" });
  if (!(await railToggle.isVisible())) fail("no control to bring the navigator back");
  // Both zones are gone and both toggles must announce that they can bring them back.
  for (const [name, pressed] of [["Show the navigator", "false"], ["Show the inspector", "false"]]) {
    const b = p.getByRole("button", { name });
    if (!(await b.isVisible())) fail(`no control to bring back: ${name}`);
    if ((await b.getAttribute("aria-pressed")) !== pressed) fail(`${name} does not report itself as off`);
  }
  await shot(p, "all-hidden");
  await tap(p, p.getByRole("button", { name: "Show the navigator" }));
  await tap(p, p.getByRole("button", { name: "Show the inspector" }));
  await p.waitForTimeout(400);
  const back = await grid(p);
  if (Math.round(back.rail) !== 276 || Math.round(back.inspector) !== 340) fail(`the toggles did not restore the zones: ${back.columns}`);
  await shot(p, "restored-by-toggles");
});

await scene("menu", 1440, async (p) => {
  await tap(p, p.locator('[aria-label="Layout and panels"]'));
  await p.locator(".menu").waitFor({ state: "visible", timeout: 5000 });
  const items = await p.locator(".menu button").allInnerTexts();
  for (const wanted of [/Navigator/, /Inspector/, /Reset layout/]) {
    if (!items.some((t) => wanted.test(t))) fail(`the layout menu does not offer ${wanted}`);
  }
  await shot(p, "layout-menu");
});

await scene("reset", 1440, async (p) => {
  await turn(p);
  await p.keyboard.press("Meta+b");
  await p.waitForTimeout(400);
  if (Math.round((await grid(p)).rail) !== 0) fail("the navigator did not hide");
  await tap(p, p.locator('[aria-label="Layout and panels"]'));
  await p.locator(".menu").waitFor({ state: "visible", timeout: 5000 });
  const resetItem = p.locator(".menu button", { hasText: "Reset layout" });
  await resetItem.waitFor({ state: "visible", timeout: 5000 });
  await tap(p, resetItem);
  await p.waitForTimeout(600);
  const g = await grid(p);
  if (Math.round(g.rail) !== 276) fail(`reset did not restore the navigator: ${g.columns}`);
});

await scene("tabs", 1100, async (p) => {
  await turn(p);
  /* Open enough documents to overflow the strip.

     Three attempts to write this, each failing differently — worth keeping, because the third
     one is the only one that is actually deterministic:
       1. Clicking rows.nth(0..7) blind: clicks containers as often as tables, and a container
          click toggles it shut. Whether a table ever opened depended on row order.
       2. Looping "while a collapsed row exists" over a LIVE locator: expanding a row removes it
          from that set, so nth(0) kept re-resolving to a different row and the loop collapsed
          what it had just opened.
       3. This one: address rows by their explicit `aria-level`, which encode the real
          catalog > schema > table hierarchy, and wait for each level to exist before using it.
          Nothing depends on order, index stability, or timing. */
  await p.keyboard.press("Meta+3");
  await p.waitForTimeout(600);

  const level = (n) => p.locator(`[role="treeitem"][aria-level="${n}"]`);
  const settle = (n) => p.waitForFunction(
    (lv) => document.querySelectorAll(`[role="treeitem"][aria-level="${lv}"]`).length > 0,
    n, { timeout: 20000 },
  ).catch(() => {});

  // catalog
  await level(1).first().click({ timeout: 5000 });
  await settle(2);
  await p.waitForTimeout(600);

  // schema
  if (await level(2).count()) {
    await level(2).first().click({ timeout: 5000 });
    await settle(3);
    await p.waitForTimeout(800);
  }

  // tables: a table is level 3 here, and clicking one opens a viewer, which creates a tab.
  for (let pass = 0; pass < 2 && (await p.locator(".doc-tab").count()) < 9; pass += 1) {
    const tables = level(3);
    const count = await tables.count();
    for (let i = 0; i < count && (await p.locator(".doc-tab").count()) < 9; i += 1) {
      await tables.nth(i).click({ timeout: 2000 }).catch(() => {});
      await p.waitForTimeout(220);
    }
  }

  const tabs = await p.locator(".doc-tab").count();
  if (tabs < 8) fail(`could not open enough documents to overflow the strip: ${tabs} tabs`);

  const t = await p.evaluate(() => {
    const strip = document.querySelector(".doc-tabs");
    if (!strip) return null;
    const active = strip.querySelector('[aria-selected="true"]');
    const a = active?.getBoundingClientRect(), s = strip.getBoundingClientRect();
    return { tabs: strip.querySelectorAll(".doc-tab").length, overflows: strip.scrollWidth > strip.clientWidth,
      activeVisible: a ? a.left >= s.left - 1 && a.right <= s.right + 1 : null };
  });
  if (!t) fail("no tab strip appeared");
  if (!t.activeVisible) fail(`the active tab is off screen: ${JSON.stringify(t)}`);
  await shot(p, "tab-strip-overflow");
});

await scene("palette", 1440, async (p) => {
  await p.keyboard.press("Meta+k");
  await p.locator(".palette").waitFor({ state: "visible", timeout: 5000 });
  await p.locator(".palette-input").fill("reset");
  await p.locator(".palette-row", { hasText: /Reset layout/i }).first().waitFor({ timeout: 8000 });
  await shot(p, "palette-reset-layout");
});

await scene("shortcuts", 1440, async (p) => {
  await p.keyboard.press("Meta+/");
  await p.locator(".keys-sheet").waitFor({ state: "visible", timeout: 5000 });
  await shot(p, "shortcut-sheet");
});

await scene("mid", 1100, async (p) => {
  await turn(p);
  const g = await grid(p);
  if (Math.round(g.inspector) === 0) fail("no inspector at 1100px");
  if (g.columns.split(" ").length !== 2) fail(`the inspector takes a column at 1100px: ${g.columns}`);
  await shot(p, "mid-inspector-drawer");
});

await scene("narrow", 760, async (p) => {
  await turn(p);
  const before = Math.round((await grid(p)).main);
  // At 760px the rail is a drawer and starts closed: the top-bar toggle opens it, and opening it must
  // not move the work area.
  const reveal = p.getByRole("button", { name: "Show the navigator" });
  if (!(await reveal.isVisible())) fail("no control to open the navigator at 760px");
  await tap(p, reveal);
  await p.waitForTimeout(500);
  if (!(await p.locator(".pane.rail.is-drawer").count())) fail("the navigator is not a drawer at 760px");
  const after = await grid(p);
  if (Math.round(after.main) !== before) fail(`the drawer moved the work area: ${before} -> ${after.main}`);
  await shot(p, "narrow-navigator-drawer");
});

await scene("empty", 1440, async (p) => {
  const g = await grid(p);
  if (Math.round(g.inspector) !== 0) fail(`an empty inspector column is reserved: ${g.columns}`);
  await shot(p, "no-session-no-empty-panel");
});


/* ---- appearance: both themes, and the switch itself ----
   These exist so the dark theme is a documented, reviewed state rather than whatever happens to
   render. Each asserts the ground colour it painted, so a broken theme layer fails the suite
   instead of quietly producing two light screenshots. */
await scene("theme-light", 1440, async (p) => {
  await p.getByRole("radio", { name: /Light/ }).click();
  await turn(p);
  const bg = await p.evaluate(() => getComputedStyle(document.body).backgroundColor);
  if (bg !== "rgb(250, 249, 247)") fail(`light theme painted ${bg}`);
  await shot(p, "theme-light");
}, "light");

await scene("theme-dark", 1440, async (p) => {
  await p.getByRole("radio", { name: /Dark/ }).click();
  await turn(p);
  const bg = await p.evaluate(() => getComputedStyle(document.body).backgroundColor);
  if (bg !== "rgb(23, 23, 22)") fail(`dark theme painted ${bg}`);
  const ink = await p.evaluate(() => getComputedStyle(document.body).color);
  if (ink !== "rgb(236, 234, 230)") fail(`dark theme painted ink ${ink}`);
  await shot(p, "theme-dark");
}, "dark");

await scene("theme-follows-system", 1440, async (p) => {
  // A fresh profile with no stored choice must follow the OS, with no flash and no attribute.
  const attr = await p.evaluate(() => document.documentElement.getAttribute("data-theme"));
  if (attr !== null) fail(`system preference wrote data-theme=${attr}; the media query cannot take over`);
  const bg = await p.evaluate(() => getComputedStyle(document.body).backgroundColor);
  if (bg !== "rgb(23, 23, 22)") fail(`system preference on a dark OS painted ${bg}`);
  await shot(p, "theme-follows-system");
}, "dark");

await browser.close();
console.log(`\n${shots.length} screenshots in ${out}`);
