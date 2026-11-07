/** Shell audit: measure every zone, its role and its behaviour. Feeds specs/001-perfect-shell.
 *
 *   APP_URL=http://127.0.0.1:8040 node scripts/shell-audit.mjs [outdir]
 *
 * Measures, per width: the rect of every zone, how the centre column is used, and whether the shell
 * does the things a top-tier app does — resizing, remembering, collapsing, restoring.
 */
import { chromium } from "playwright";
import { mkdirSync, readFileSync } from "node:fs";

const out = process.argv[2] ?? "/tmp/shell-audit";
mkdirSync(out, { recursive: true });
const bearer = process.env.BEARER_FILE ? readFileSync(process.env.BEARER_FILE, "utf8").trim() : "";
const APP = process.env.APP_URL ?? "http://127.0.0.1:8040";
const widths = (process.env.WIDTHS ?? "1600,1440,1180,900,760").split(",").map(Number);

const b = await chromium.launch({ executablePath: process.env.CHROME_PATH || undefined });
const rows = [];

for (const width of widths) {
  const p = await b.newPage({ viewport: { width, height: 900 },
    extraHTTPHeaders: bearer ? { Authorization: `Bearer ${bearer}` } : {} });
  await p.goto(APP, { waitUntil: "domcontentloaded" });
  await p.waitForTimeout(1200);

  const box = p.getByRole("textbox", { name: "Message the agent" });
  await box.fill("Build a notebook that shows revenue by pickup hour");
  await p.keyboard.press("Enter");
  // The shell can be measured without a turn; a slow or absent agent must not fail a layout audit.
  await p.locator(".turn").first().waitFor({ timeout: 20000 }).catch(() => {
    console.log(`  (${width}px: no turn appeared; measuring the shell as it is)`);
  });
  await p.locator(".turn-foot").first().waitFor({ timeout: 60000 }).catch(() => {});
  await p.waitForTimeout(400);

  const m = await p.evaluate(() => {
    const r = (sel) => {
      const el = document.querySelector(sel);
      if (!el) return null;
      const b = el.getBoundingClientRect();
      return { x: Math.round(b.left), y: Math.round(b.top), w: Math.round(b.width), h: Math.round(b.height) };
    };
    const app = r(".app");
    const rail = r(".pane.rail");
    const main = r(".pane.main");
    const insp = r(".pane.inspector");
    const strip = r(".strip");
    const tabs = r(".doc-tabs");
    const transcript = r(".transcript");
    const composer = r(".composer");
    const topbar = r(".topbar");
    // how much of the centre column the reading surface actually gets
    const readingShare = main && transcript ? +(transcript.h / main.h).toFixed(2) : null;
    // scroll containers and their content
    const scrollers = [];
    for (const el of document.querySelectorAll("body *")) {
      const s = getComputedStyle(el);
      if ((s.overflowY === "auto" || s.overflowY === "scroll") && el.scrollHeight > el.clientHeight + 2) {
        scrollers.push(`${el.className.toString().split(" ")[0]}:${el.scrollHeight}/${el.clientHeight}`);
      }
    }
    return {
      app, topbar, rail, main, insp, strip, tabs, transcript, composer, readingShare,
      scrollers: scrollers.slice(0, 6),
      // affordances that would exist for resizing
      splitters: document.querySelectorAll('.splitter, [role="separator"]').length,
      resizers: document.querySelectorAll(".resizer, [data-resize]").length,
      collapsed: document.querySelectorAll(".pane.rail, .pane.inspector").length,
      persisted: Object.keys(localStorage).filter((k) => /panel|width|layout|rail|insp/i.test(k)),
    };
  });

  // can the panels be resized by dragging their edge?
  const draggable = await p.evaluate(() => {
    const rail = document.querySelector(".pane.rail");
    if (!rail) return "no rail";
    const s = getComputedStyle(rail);
    return `resize:${s.resize}; cursor:${s.cursor}`;
  });

  // does the shell remember a collapsed panel across a reload?
  let remembers = null;
  if (width > 820) {
    await p.keyboard.press("Meta+b");
    await p.waitForTimeout(250);
    const hid = (await p.locator(".pane.rail").count()) === 0;
    await p.reload({ waitUntil: "domcontentloaded" });
    await p.waitForTimeout(1200);
    const backHidden = (await p.locator(".pane.rail").count()) === 0;
    remembers = { hid, stillHiddenAfterReload: backHidden, kept: hid && backHidden };
  }

  rows.push({ width, ...m, draggable, remembers });
  await p.screenshot({ path: `${out}/${width}-shell.png` });
  await p.close();
}
await b.close();

console.log("width | topbar | rail | main | inspector | strip | tabs | transcript | composer | reading% | splitters | remembers");
for (const r of rows) {
  const f = (v) => (v ? `${v.w}x${v.h}` : "—");
  console.log([
    String(r.width).padEnd(5), f(r.topbar).padEnd(9), f(r.rail).padEnd(9), f(r.main).padEnd(9),
    f(r.insp).padEnd(11), f(r.strip).padEnd(9), f(r.tabs).padEnd(8), f(r.transcript).padEnd(11),
    f(r.composer).padEnd(9), String(r.readingShare ?? "—").padEnd(8),
    String(r.splitters + r.resizers).padEnd(8),
    r.remembers ? String(r.remembers.kept) : "n/a",
  ].join(" | "));
}
const anySplit = rows.some((r) => r.splitters + r.resizers > 0);
const anyRemember = rows.some((r) => r.remembers?.kept);
console.log(`\nresizable panels: ${anySplit ? "yes" : "NO"}`);
console.log(`panel state survives reload: ${anyRemember ? "yes" : "NO"}`);
console.log(`localStorage keys about layout: ${JSON.stringify(rows[0]?.persisted ?? [])}`);
console.log(`scrollers at 1440: ${JSON.stringify(rows.find((r) => r.width === 1440)?.scrollers ?? [])}`);

// Machine-checkable gate: specs/001-perfect-shell SH-A1, SH-B1. Fails the run when a capability
// that is supposed to exist has quietly disappeared.
const missing = [];
if (!anySplit) missing.push("no resizable zone (SH-A1)");
if (!anyRemember) missing.push("layout does not survive a reload (SH-B1)");
if (missing.length) {
  console.log(`\nFAIL: ${missing.join("; ")}`);
  process.exit(1);
}
console.log("\nPASS: resizable and remembered");
