/** Screenshoot the shell at several widths, one page per width, so each can be inspected.
 *
 *   APP_URL=http://127.0.0.1:8060 node scripts/dock-shots.mjs <outdir>
 *
 * It drives the app the way a person would: send a prompt, open a file, pick a cell, hide the dock.
 * A screenshot that was produced by setting DOM state is a drawing of the feature, not the feature.
 */
import { chromium } from "playwright";
import { mkdirSync, readFileSync } from "node:fs";

const out = process.argv[2] ?? "/tmp/dock-shots";
mkdirSync(out, { recursive: true });
const APP = process.env.APP_URL ?? "http://127.0.0.1:8060";
const bearer = process.env.BEARER_FILE ? readFileSync(process.env.BEARER_FILE, "utf8").trim() : "";
const widths = (process.env.WIDTHS ?? "1600,1300,1024,760").split(",").map(Number);
const PROMPT = process.env.PROMPT ?? "Build a notebook that shows revenue by month. Do not use any tools.";

const b = await chromium.launch({ executablePath: process.env.CHROME_PATH || undefined });

async function shot(p, name) {
  await p.waitForTimeout(450);
  await p.screenshot({ path: `${out}/${name}.png` });
  console.log(`  ${name}.png`);
}

for (const width of widths) {
  const p = await b.newPage({ viewport: { width, height: 900 }, deviceScaleFactor: 2,
    extraHTTPHeaders: bearer ? { Authorization: `Bearer ${bearer}` } : {} });
  await p.goto(APP, { waitUntil: "domcontentloaded" });
  await p.waitForTimeout(1800);

  // 1. fresh load: the dock's empty state
  await shot(p, `w${width}-01-empty`);

  // 2. send a prompt from the dock's composer, so a session exists
  const dockBox = p.locator('.pane.assistant [aria-label="Message the assistant"] textarea, .composer.is-dock textarea');
  if (await dockBox.count()) {
    await dockBox.first().fill(PROMPT);
    await dockBox.first().press("Enter");
    await p.locator(".pane.assistant .turn").first().waitFor({ timeout: 60000 }).catch(() => {});
    await p.locator(".pane.assistant .turn-foot").first().waitFor({ timeout: 120000 }).catch(() => {});
  }
  await shot(p, `w${width}-02-chat`);

  // 3. open a document: the transcript must STAY on screen (this is the spec's whole claim)
  let opened = false;
  const filesTab = p.getByRole("tab", { name: "Files" });
  if (!(await filesTab.isVisible().catch(() => false))) {
    await p.getByRole("button", { name: /Show the navigator/i }).first().click().catch(() => {});
    await p.waitForTimeout(400);
  }
  if (await filesTab.isVisible().catch(() => false)) {
    await filesTab.click().catch(() => {});
    await p.waitForTimeout(900);
    // expand until a leaf is available, then click it
    for (let pass = 0; pass < 3; pass += 1) {
      const rows = p.locator('.rail .tree-body [role="treeitem"]');
      const n = await rows.count();
      let did = false;
      for (let i = 0; i < n; i += 1) {
        const row = rows.nth(i);
        if ((await row.getAttribute("aria-expanded")) === "false") {
          await row.click({ timeout: 4000 }).catch(() => {});
          await p.waitForTimeout(700);
          did = true;
          break;
        }
      }
      if (!did) break;
    }
    const rows = p.locator('.rail .tree-body [role="treeitem"]');
    const n = await rows.count();
    for (let i = 0; i < n; i += 1) {
      const row = rows.nth(i);
      if ((await row.getAttribute("aria-expanded")) !== null) continue;
      await row.click({ timeout: 4000 }).catch(() => {});
      await p.waitForTimeout(1600);
      if (await p.locator(".doc-tabs").count()) { opened = true; break; }
    }
  }
  await shot(p, `w${width}-03-document${opened ? "" : "-none"}`);

  // 4. open the model picker from the composer's control
  const inline = p.locator(".composer.is-dock .model-trigger, .pane.assistant .model-trigger").first();
  if (await inline.count()) {
    await inline.click({ timeout: 5000 }).catch(() => {});
    await p.waitForTimeout(700);
    await shot(p, `w${width}-04-model`);
    await p.keyboard.press("Escape");
    await p.waitForTimeout(300);
  }

  // 5. hide the dock, then show it again: one key, both directions
  await p.keyboard.press("Meta+j");
  await p.waitForTimeout(500);
  await shot(p, `w${width}-05-dock-hidden`);
  await p.keyboard.press("Meta+j");
  await p.waitForTimeout(500);

  // 6. files list view, with a breadcrumb and the columns
  if (await filesTab.isVisible().catch(() => false)) {
    await filesTab.click().catch(() => {});
    await p.waitForTimeout(400);
    const listBtn = p.getByRole("button", { name: "List view" });
    if (await listBtn.count()) {
      await listBtn.first().click().catch(() => {});
      await p.waitForTimeout(900);
      await shot(p, `w${width}-06-files-list`);
    }
  }

  const m = await p.evaluate(() => {
    const r = (sel) => {
      const el = document.querySelector(sel);
      if (!el) return null;
      const b = el.getBoundingClientRect();
      return { x: Math.round(b.x), y: Math.round(b.y), w: Math.round(b.width), h: Math.round(b.height) };
    };
    const vis = (sel) => {
      const el = document.querySelector(sel);
      if (!el) return false;
      const b = el.getBoundingClientRect();
      return b.width > 0 && b.height > 0;
    };
    return {
      width: window.innerWidth,
      dock: r(".pane.assistant"),
      centre: r(".pane.main"),
      rail: r(".pane.rail"),
      inspector: r(".pane.inspector"),
      turnsInDock: document.querySelectorAll(".pane.assistant .turn").length,
      transcriptVisible: vis(".transcript"),
      // Any visible trigger counts: the chip in the top bar OR the inline control in a composer.
      modelVisible: [...document.querySelectorAll(".model-trigger")]
        .some((e) => e.getBoundingClientRect().width > 0),
      modelTriggers: [...document.querySelectorAll(".model-trigger")]
        .filter((e) => e.getBoundingClientRect().width > 0).length,
      chromePx: (() => {
        const el = document.querySelector(".cm-content, pre.code, .doc-bar");
        return el ? Math.round(el.getBoundingClientRect().top) : null;
      })(),
      overflow: document.documentElement.scrollWidth > window.innerWidth + 1,
    };
  });
  console.log(JSON.stringify(m));
  await p.close();
}

await b.close();
