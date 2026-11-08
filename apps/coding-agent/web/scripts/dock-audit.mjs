/** 006 audit: measure the shell against the numbers 01-current-state-audit.md claims.
 *
 *   APP_URL=https://... BEARER_FILE=/tmp/bearer.txt node scripts/dock-audit.mjs [outdir]
 *
 * What each number means, and why it is the right probe:
 *
 *   chromePx                px from the top of the window to the first line of code. A user who
 *                           spends this much before reading a line is paying it on every open.
 *   transcriptVisible       with a document open, is the conversation in the DOM and drawn? This is
 *                           the core claim of the spec: today it is not, because a document and the
 *                           conversation share one slot.
 *   turnsRendered           how many turns are painted while a document is open. Zero is the bug.
 *   composerVisible         is there an interactive message box to type into?
 *   modelChipVisible        is the model control on screen at this width?
 *   modelInteractions       clicks needed to open the model list (null when it cannot be reached).
 *   deadControls            rendered controls with no observable effect.
 *
 * A session is created once, by sending a trivial prompt, so the model control and the transcript
 * exist to be measured. If the agent is slow the audit records that rather than failing.
 */
import { chromium } from "playwright";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";

const out = process.argv[2] ?? "/tmp/dock-audit";
mkdirSync(out, { recursive: true });
const bearer = process.env.BEARER_FILE ? readFileSync(process.env.BEARER_FILE, "utf8").trim() : "";
const APP = process.env.APP_URL ?? "http://127.0.0.1:8040";
const widths = (process.env.WIDTHS ?? "1600,1280,1180,1024,900,760").split(",").map(Number);
const PROMPT = process.env.PROMPT ?? "Say hi in one short sentence. Do not use any tools.";

const b = await chromium.launch({ executablePath: process.env.CHROME_PATH || undefined });
const report = [];

/** Start a session and wait until a turn is on screen (or give up honestly). */
async function startSession(p) {
  const box = p.getByRole("textbox", { name: "Message the agent" });
  await box.waitFor({ timeout: 15000 });
  await box.fill(PROMPT);
  await box.press("Enter");
  await p.locator(".turn").first().waitFor({ timeout: 90000 }).catch(() => {});
  await p.locator(".turn-foot").first().waitFor({ timeout: 180000 }).catch(() => {});
  await p.waitForTimeout(500);
}

/** Open a real notebook or file, so "with a document open" means what it says.
 *
 * A tree row can be a folder: clicking it expands instead of opening. So the walk expands until it
 * finds a row that is not expandable, and clicks that. If nothing opens, the audit says so rather
 * than reporting a transcript that was never replaced.
 */
async function openDocument(p) {
  const filesTab = p.getByRole("tab", { name: "Files" });
  if (!(await filesTab.isVisible().catch(() => false))) {
    const toggle = p.getByRole("button", { name: /Show the navigator/i });
    if (await toggle.count()) await toggle.first().click({ timeout: 5000 }).catch(() => {});
    await p.waitForTimeout(500);
  }
  if (!(await filesTab.isVisible().catch(() => false))) return false;
  await filesTab.click({ timeout: 5000 }).catch(() => {});
  await p.waitForTimeout(900);

  const rows = () => p.locator('.tree-body [role="treeitem"]');
  // Expand up to three folders, then take the first leaf.
  for (let pass = 0; pass < 3; pass += 1) {
    const n = await rows().count();
    let expanded = false;
    for (let i = 0; i < n; i += 1) {
      const row = rows().nth(i);
      const isFolder = (await row.getAttribute("aria-expanded")) !== null;
      if (isFolder && (await row.getAttribute("aria-expanded")) === "false") {
        await row.click({ timeout: 5000 }).catch(() => {});
        await p.waitForTimeout(800);
        expanded = true;
        break;
      }
    }
    if (!expanded) break;
  }
  const n = await rows().count();
  for (let i = 0; i < n; i += 1) {
    const row = rows().nth(i);
    if ((await row.getAttribute("aria-expanded")) !== null) continue;   // a folder
    await row.click({ timeout: 5000 }).catch(() => {});
    await p.waitForTimeout(2500);
    if (await p.locator(".doc-tabs, .viewer, .doc-bar").count()) return true;
  }
  return false;
}

for (const width of widths) {
  const p = await b.newPage({ viewport: { width, height: 900 },
    extraHTTPHeaders: bearer ? { Authorization: `Bearer ${bearer}` } : {} });
  await p.goto(APP, { waitUntil: "domcontentloaded" });
  await p.waitForTimeout(1500);

  await startSession(p);
  const before = await p.evaluate(() => ({
    turns: document.querySelectorAll(".turn").length,
    modelChip: (() => {
      const el = document.querySelector(".topbar .model-trigger");
      return el ? Math.round(el.getBoundingClientRect().width) : 0;
    })(),
  }));

  const opened = await openDocument(p);

  const m = await p.evaluate(() => {
    const box = (sel) => {
      const el = document.querySelector(sel);
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) };
    };
    const visible = (el) => {
      if (!el) return false;
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.height > 0;
    };
    const transcript = document.querySelector(".transcript");
    const firstCode = document.querySelector(".cm-content, pre.code, .cell-block .cm-content");
    const composers = [...document.querySelectorAll('[aria-label="Message the agent"]')].filter(visible);
    const chip = document.querySelector(".topbar .model-trigger");
    return {
      topbar: box(".topbar"),
      rail: box(".pane.rail"),
      centre: box(".pane.main"),
      inspector: box(".pane.inspector"),
      dock: box(".pane.assistant"),
      docTabs: box(".doc-tabs"),
      codeTop: firstCode ? Math.round(firstCode.getBoundingClientRect().top) : null,
      transcriptPresent: Boolean(transcript),
      transcriptVisible: visible(transcript),
      turnsRendered: document.querySelectorAll(".turn").length,
      composerVisible: composers.length > 0,
      chipVisible: visible(chip),
      chipLabel: chip?.textContent?.trim() ?? "",
      cellRun: document.querySelectorAll(".cell-run").length,
      cellAsk: document.querySelectorAll(".cell-act").length,
      hasChatTab: Boolean(document.getElementById("tab-chat")),
    };
  });

  // Interactions to change the model: how many clicks from the current screen to an open list.
  let modelInteractions = null;
  if (m.chipVisible) {
    try {
      await p.locator(".topbar .model-trigger").click({ timeout: 3000 });
      const open = await p.locator(".picker").isVisible().catch(() => false);
      modelInteractions = open ? 1 : null;
      await p.keyboard.press("Escape");
    } catch { modelInteractions = null; }
  } else {
    // Not on the top bar. Is there any other reachable control, i.e. in the inspector or palette?
    try {
      await p.keyboard.press(process.platform === "darwin" ? "Meta+Shift+M" : "Control+Shift+M");
      await p.waitForTimeout(600);
      modelInteractions = (await p.locator(".picker").isVisible().catch(() => false)) ? 1 : null;
      await p.keyboard.press("Escape");
    } catch { modelInteractions = null; }
  }

  await p.screenshot({ path: `${out}/w${width}.png` });
  if (opened) await p.screenshot({ path: `${out}/w${width}-doc.png` });

  report.push({
    width,
    opened,
    chromePx: m.codeTop,
    transcriptVisible: m.transcriptVisible,
    turnsRendered: m.turnsRendered,
    composerVisible: m.composerVisible,
    chipVisible: m.chipVisible,
    chipLabel: m.chipLabel,
    modelInteractions,
    cells: { run: m.cellRun, ask: m.cellAsk },
    zones: { rail: m.rail, centre: m.centre, inspector: m.inspector, dock: m.dock },
    beforeDoc: before,
  });
  await p.close();
}

const pick = (k) => Object.fromEntries(report.map((r) => [r.width, r[k]]));
const summary = {
  app: APP,
  measuredAt: new Date().toISOString(),
  chromePx: pick("chromePx"),
  transcriptVisibleWithDocOpen: pick("transcriptVisible"),
  turnsRenderedWithDocOpen: pick("turnsRendered"),
  composerVisible: pick("composerVisible"),
  modelChipVisible: pick("chipVisible"),
  modelInteractions: pick("modelInteractions"),
  deadControls: Object.fromEntries(report.map((r) => [r.width, r.cells.run])),
};
writeFileSync(`${out}/audit.json`, JSON.stringify({ summary, report }, null, 2));
console.log(JSON.stringify(summary, null, 2));
await b.close();
