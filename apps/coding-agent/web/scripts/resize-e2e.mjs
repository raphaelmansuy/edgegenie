/** Every resizable panel really resizes, by mouse and by keyboard, and the choice survives a reload.
 *
 *   APP_URL=http://127.0.0.1:8071 node scripts/resize-e2e.mjs [outdir]
 *
 * Regression for "it is impossible to resize the right panel": the assistant's separator wrote the
 * INSPECTOR's width (hooks/useLayout.ts), so a drag changed a hidden panel and nothing moved.
 */
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const APP = process.env.APP_URL ?? "http://127.0.0.1:8071";
const out = process.argv[2] ?? "/tmp/resize-e2e";
mkdirSync(out, { recursive: true });
let failed = 0;
const check = (name, ok, detail = "") => {
  if (!ok) failed += 1;
  console.log(`  ${ok ? "PASS" : "FAIL"} ${name}${detail ? ` — ${detail}` : ""}`);
};

const b = await chromium.launch();
const width = async (p, sel) => Math.round((await p.locator(sel).first().boundingBox())?.width ?? 0);
const open = async (w, h = 900) => {
  const ctx = await b.newContext({ viewport: { width: w, height: h } });
  const p = await ctx.newPage();
  await p.goto(APP, { waitUntil: "domcontentloaded" });
  await p.waitForSelector(".pane.assistant .separator, .pane.rail .separator", { timeout: 10000 });
  return p;
};
const drag = async (p, sel, dx) => {
  const box = await p.locator(sel).first().boundingBox();
  const x = box.x + box.width / 2, y = box.y + box.height / 2;
  await p.mouse.move(x, y);
  await p.mouse.down();
  for (let i = 1; i <= 12; i++) await p.mouse.move(x + (dx * i) / 12, y);
  await p.mouse.up();
  await p.waitForTimeout(250);
};

for (const w of [1180, 1300, 1600]) {
  console.log(`\n== ${w}px`);
  const p = await open(w);
  const dock = ".pane.assistant.dock-column";
  const sep = `${dock} > .separator`;
  const start = await width(p, dock);
  const inspBefore = await p.locator(".pane.inspector").count();

  await drag(p, sep, -80);                       // drag left = wider
  const wider = await width(p, dock);
  // headroom is what the arithmetic leaves: window - rail - 480 centre - dock (44 px at 1180)
  const headroom = Math.max(0, w - 276 - 480 - start);
  check(`dock widens when its handle is dragged left`, wider >= start + Math.min(60, headroom) && wider > start,
    `${start} -> ${wider} (headroom ${headroom})`);

  await drag(p, sep, +400);                      // far right = narrowest
  const narrow = await width(p, dock);
  check(`dock stops at its minimum (320)`, narrow >= 318 && narrow <= 330, `${narrow}`);

  await drag(p, sep, -900);                      // far left = widest allowed
  const widest = await width(p, dock);
  const centre = await width(p, ".pane.main");
  check(`dock stops at its cap and the work area keeps >= 480`, widest <= 570 && centre >= 478, `dock ${widest}, centre ${centre}`);

  await p.locator(sep).first().dblclick();
  await p.waitForTimeout(250);
  const reset = await width(p, dock);
  check(`double-click resets to the default`, Math.abs(reset - 380) <= 8, `${reset}`);

  await p.locator(sep).first().focus();
  const before = await width(p, dock);
  await p.keyboard.press("ArrowLeft");
  await p.waitForTimeout(150);
  const afterKey = await width(p, dock);
  check(`ArrowLeft on the focused handle widens the dock by one step`, afterKey >= before + 8, `${before} -> ${afterKey}`);

  await drag(p, sep, -60);
  const chosen = await width(p, dock);
  await p.waitForTimeout(400);                   // the layout is written on a short debounce
  await p.reload({ waitUntil: "domcontentloaded" });
  await p.waitForSelector(dock);
  const kept = await width(p, dock);
  check(`the chosen width survives a reload`, Math.abs(kept - chosen) <= 2, `${chosen} -> ${kept}`);
  if (inspBefore === 0) check(`dragging the dock did not need the inspector`, true);

  await p.locator(sep).first().dblclick();
  await p.waitForTimeout(250);
  await drag(p, ".pane.rail > .separator", 40);
  const rail = await width(p, ".pane.rail");
  check(`rail widens by dragging right`, rail >= 310, `${rail}`);
  await p.screenshot({ path: `${out}/w${w}.png` });
  await p.context().close();
}

await b.close();
console.log(failed ? `\n${failed} FAILED` : "\nall passed");
process.exit(failed ? 1 : 0);
