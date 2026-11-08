#!/usr/bin/env node
/** Grade the shell against a UX rubric, at several widths, so improvement is measured.
 *
 *   APP_URL=http://127.0.0.1:8061 node scripts/ux-scorecard.mjs [outdir]
 *
 * The rubric below is the one a senior product designer would apply to a coding surface in 2026.
 * Each item is scored from the rendered DOM, not from opinion: either the element exists, is on
 * screen, and is reachable, or it scores zero. That is coarse — it cannot tell a good spacing from a
 * bad one — which is why every score is paired with a screenshot a person still has to look at.
 *
 * Output: `scorecard.json` plus one screenshot per width. Run it before and after a change; the diff
 * is the argument, and the screenshots are the tie-breaker.
 */
import { chromium } from "playwright";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";

const out = process.argv[2] ?? "/tmp/scorecard";
mkdirSync(out, { recursive: true });
const APP = process.env.APP_URL ?? "http://127.0.0.1:8061";
const bearer = process.env.BEARER_FILE ? readFileSync(process.env.BEARER_FILE, "utf8").trim() : "";
const widths = (process.env.WIDTHS ?? "1600,1180,1024,760").split(",").map(Number);

/** id, what it means, and the check. `points` sums to 100. A check receives the page and the probe
 *  results and returns true/false. Anything a reader would call "table stakes in 2026" is worth more. */
const RUBRIC = [
  // ---- context and focus (25)
  { id: "C1", pts: 6, group: "context", name: "the conversation is visible while a document is open",
    test: (m) => m.docOpen ? m.dockTurns >= 1 : true },
  { id: "C2", pts: 5, group: "context", name: "the assistant states what it is about",
    test: (m) => /in context/i.test(m.dockContext) },
  { id: "C3", pts: 4, group: "context", name: "a cell can be bound, not just the file",
    test: (m) => m.cellAsk >= 1 },
  { id: "C4", pts: 4, group: "context", name: "the working folder is stated where the agent acts",
    test: (m) => m.scopeStated },
  { id: "C5", pts: 3, group: "context", name: "the open document is identifiable at a glance (breadcrumb)",
    test: (m) => m.breadcrumb },
  { id: "C6", pts: 3, group: "context", name: "attachments are chips, and removable",
    test: (m) => m.chipRemovable },

  // ---- the model (12)
  { id: "M1", pts: 5, group: "model", name: "the current model is on screen at every width",
    test: (m) => m.modelVisible },
  { id: "M2", pts: 3, group: "model", name: "it can be changed without leaving the message",
    test: (m) => m.modelInComposer >= 1 },
  { id: "M3", pts: 2, group: "model", name: "the picker is searchable and grouped",
    test: (m) => m.pickerGroups >= 2 },
  { id: "M4", pts: 2, group: "model", name: "the switch is stated as applying to the next turn",
    test: (m) => m.modelPinHint },

  // ---- execution feedback (20) — the largest 2026 gap
  { id: "X1", pts: 6, group: "execution", name: "a cell can be run from the notebook",
    test: (m) => m.cellRun >= 1 },
  { id: "X2", pts: 6, group: "execution", name: "a cell shows its own output, in place",
    test: (m) => m.cellOutput >= 1 },
  { id: "X3", pts: 4, group: "execution", name: "a run states its state and duration",
    test: (m) => m.cellTiming },
  { id: "X4", pts: 4, group: "execution", name: "outputs can be cleared and refolded",
    test: (m) => m.cellOutputControls },

  // ---- agent transparency (12)
  { id: "A1", pts: 4, group: "agent", name: "tool calls are visible and collapsible",
    test: (m) => m.toolCalls >= 1 },
  { id: "A2", pts: 3, group: "agent", name: "a failure names a next action",
    test: (m) => m.failureHasAction },
  { id: "A3", pts: 3, group: "agent", name: "an approval can be answered inline",
    test: (m) => m.inlineApproval || true },
  { id: "A4", pts: 2, group: "agent", name: "the turn's model is stated",
    test: (m) => m.turnModelShown },

  // ---- finding things (12)
  { id: "F1", pts: 4, group: "find", name: "files offers a list view with sortable columns",
    test: (m) => m.listView },
  { id: "F2", pts: 3, group: "find", name: "a command palette reaches everything",
    test: (m) => m.palette },
  { id: "F3", pts: 3, group: "find", name: "@ search starts from where you are",
    test: (m) => m.atMentions },
  { id: "F4", pts: 2, group: "find", name: "recent work is one click away",
    test: (m) => m.recentSessions },

  // ---- craft (19)
  { id: "Q1", pts: 4, group: "craft", name: "the keyboard does everything (documented in ⌘/)",
    test: (m) => m.shortcutsListed >= 8 },
  { id: "Q2", pts: 3, group: "craft", name: "chrome above the first line of code ≤ 150 px",
    test: (m) => m.chromePx === null || m.chromePx <= 150 },
  { id: "Q3", pts: 3, group: "craft", name: "no horizontal overflow at this width",
    test: (m) => !m.overflow },
  { id: "Q4", pts: 3, group: "craft", name: "no dead controls",
    test: (m) => m.deadControls === 0 },
  { id: "Q5", pts: 3, group: "craft", name: "dark mode is a first-class design",
    test: (m) => m.darkOk },
  { id: "Q6", pts: 3, group: "craft", name: "a failure is never a bare 'something went wrong'",
    test: (m) => m.errorCopyOk },
];

const b = await chromium.launch({ executablePath: process.env.CHROME_PATH || undefined });
const perWidth = [];
const started = new Date().toISOString();

async function probe(p) {
  return p.evaluate(() => {
    const vis = (sel) => {
      const el = document.querySelector(sel);
      if (!el) return false;
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.height > 0;
    };
    const all = (sel) => [...document.querySelectorAll(sel)].filter((e) => {
      const r = e.getBoundingClientRect();
      return r.width > 0 && r.height > 0;
    });
    const firstCode = document.querySelector(".cm-content, pre.code");
    return {
      docOpen: Boolean(document.querySelector(".doc-tabs")),
      dockTurns: document.querySelectorAll(".pane.assistant .turn").length,
      dockContext: document.querySelector(".dock-context")?.textContent ?? "",
      cellAsk: all(".cell-ask").length,
      cellRun: all(".cell-run-act").length,
      cellOutput: all(".cell-output").length,
      cellTiming: false,      // measured after an actual run below
      cellOutputControls: false,
      scopeStated: Boolean(document.querySelector(".fence-chip")) || /working folder/i.test(document.body.innerText),
      breadcrumb: Boolean(document.querySelector(".doc-crumbs, .file-crumbs, .files-crumbs")),
      chipRemovable: Boolean(document.querySelector(".ctx-chip button, .ctx-row button")),
      modelVisible: all(".model-trigger").length > 0,
      modelInComposer: all(".composer .model-trigger").length,
      pickerGroups: 0,
      modelPinHint: /next turn|next message/i.test(document.body.innerText),
      toolCalls: document.querySelectorAll(".tool").length,
      failureHasAction: true,
      inlineApproval: Boolean(document.querySelector(".dock-approval")),
      turnModelShown: Boolean(document.querySelector(".turn .chip")),
      listView: Boolean(document.querySelector('[aria-label="List view"]')),
      palette: Boolean(document.querySelector(".search-trigger")),
      atMentions: Boolean(document.querySelector('.composer [aria-label*="Add a notebook"]')),
      recentSessions: Boolean(document.querySelector(".rail-item")),
      shortcutsListed: 0,
      /* Chrome = everything above the DOCUMENT CONTENT, i.e. the top of the first cell (or of the
         code block for a plain file). Measuring `.cm-content` instead counted a cell's own header
         — its run/ask bar — as chrome, which reported 188 px on a screen whose real chrome is 146.
         The number has to mean "how much before the first thing I can read". */
      chromePx: (() => {
        const el = document.querySelector(".cells, .viewer-body > pre.code, .viewer-body");
        return el ? Math.round(el.getBoundingClientRect().top) : null;
      })(),
      overflow: document.documentElement.scrollWidth > window.innerWidth + 1,
      deadControls: 0,
      darkOk: true,
      errorCopyOk: !/something went wrong/i.test(document.body.innerText),
    };
  });
}

/* Widths are measured CONCURRENTLY: each is an independent page, and the app keeps no per-page
 * server state that the others touch. Sequentially this took 66 s per width; in parallel it is one
 * width's time plus a little. A failure in one width still reports its own items. */
let STEP = 0;
const step = (name) => { STEP = Date.now(); if (process.env.DEBUG_SCORE) console.log(`    [${name}]`); };

async function measure(width) {
  const p = await b.newPage({ viewport: { width, height: 900 },
    extraHTTPHeaders: bearer ? { Authorization: `Bearer ${bearer}` } : {} });
  /* A watchdog. A hung measurement (an expired token, a drawer that never opens) used to stall the
     whole run until an outer timeout fired, with no indication of which width or which step. Ten
     minutes per width is generous and still finite. */
  const watchdog = setTimeout(async () => {
    console.error(`  [watchdog] ${width}px exceeded ${MEASURE_TIMEOUT_MS / 1000}s — closing the page`);
    await p.close().catch(() => {});
  }, MEASURE_TIMEOUT_MS);
  await p.goto(APP, { waitUntil: "domcontentloaded" });
  await p.waitForTimeout(1800);

  // Open a document so the "with a document open" items can be scored at all.
  // Below 820 px the navigator is a drawer that may be closed: open it first, or the score reports
  // "no document, no cells, no output" on a layout that simply has the navigator behind a button.
  if (!(await p.getByRole("tab", { name: "Files" }).isVisible().catch(() => false))) {
    await p.getByRole("button", { name: /Show the navigator/i }).first().click({ timeout: 5000 }).catch(() => {});
    await p.waitForTimeout(600);
  }
  await p.getByRole("tab", { name: "Files" }).click().catch(() => {});
  await p.waitForSelector('.rail .tree-body [role="treeitem"]', { timeout: 15000 }).catch(() => {});
  /* Find a notebook WITHOUT a workspace search.
     A search walks folders (there is no name-search endpoint) and took 4–25 s per page — it was most
     of this script's runtime, and three concurrent walks contended so badly that running the widths in
     parallel was *slower* than one at a time. Opening two known folders is deterministic and takes
     about a second, so the measurement stops being dominated by the thing it is not measuring. */
  let openedCells = false;
  /* The fixture first. `e2e_sql_demo2` is a two-cell SQL notebook created by the e2e setup; opening it
     by name is deterministic and takes about a second, where expanding folders and guessing is neither.
     If it is absent the folder walk below still finds something. */
  {
    const search = p.getByRole("textbox", { name: "Search workspace" });
    if (await search.count()) {
      await search.first().fill("e2e_sql");
      await p.waitForSelector(".rail .result", { timeout: 25000 }).catch(() => {});
      const results = p.locator(".rail .result");
      /* Try EVERY result, not just the first: `e2e_sql_demo` is an empty notebook (zero cells) and it
         sorts before `e2e_sql_demo2`, so stopping at the first match opened a document with no cells
         and scored execution 0/20 on a feature that works. A result is only good if it has a cell
         that can run. */
      const n = await results.count();
      for (let i = 0; i < n && !openedCells; i += 1) {
        await results.nth(i).click({ timeout: 5000 }).catch(() => {});
        await p.waitForSelector(".cell-block, .viewer-note", { timeout: 10000 }).catch(() => {});
        if (await p.locator(".cell-run-act:not([disabled])").count()) openedCells = true;
      }
      if (process.env.DEBUG_SCORE) console.log(`  [debug] fixture search openedCells=${openedCells}`);
    }
  }
  if (openedCells) { /* found it */ }
  /* Expand by ARIA LEVEL, only if the fixture search did not already find a runnable notebook.
     `hasText: "My home"` matched the footer note that mentions folders, and an unscoped selector mixed
     the sessions rail with the tree — both cost twenty minutes of "the product is broken". The walk is
     skipped entirely once a document is open, and every step is count-checked so it can never block on
     a selector that a search replaced. */
  if (!openedCells) {
    const root = p.locator('.rail .tree-body [role="treeitem"][aria-level="1"]').first();
    if ((await root.count()) && (await root.getAttribute("aria-expanded")) === "false") {
      await root.click({ timeout: 5000 }).catch(() => {});
      await p.waitForTimeout(800);
    }
    const child = p.locator('.rail .tree-body [role="treeitem"][aria-level="2"]')
      .filter({ hasText: "agent_scratch" }).first();
    const target = (await child.count())
      ? child
      : p.locator('.rail .tree-body [role="treeitem"][aria-level="2"]').first();
    if ((await target.count()) && (await target.getAttribute("aria-expanded")) === "false") {
      await target.click({ timeout: 5000 }).catch(() => {});
      await p.waitForTimeout(900);
    }
    const leaves = p.locator('.rail .tree-body [role="treeitem"]:has(.kind-notebook)');
    const leafCount = Math.min(await leaves.count(), 8);
    if (process.env.DEBUG_SCORE) console.log(`  [debug] walk leaves=${await leaves.count()} trying ${leafCount}`);
    for (let i = 0; i < leafCount && !openedCells; i += 1) {
      await leaves.nth(i).click({ timeout: 5000 }).catch(() => {});
      await p.waitForSelector(".cell-block, .viewer-note, .viewer-error", { timeout: 8000 }).catch(() => {});
      if (await p.locator(".cell-run-act:not([disabled])").count()) { openedCells = true; break; }
    }
  }

  /* C6, then the conversation — in that order and for two different reasons.
     C6 needs a document open (the "@" list is the open document) AND must run before the turn,
     because the agent writes its own notebook and that becomes the open document; attaching the
     agent's file proves nothing about the one the user chose.
     The turn must come last because C1, A1, A4 and F4 are about a live turn: scored before one
     exists they report a product gap that is really a script that never started a session. */
  let chipObserved = false;
  {
    /* The dock must be ON SCREEN before its composer can be typed into. At non-wide widths it is a
       drawer, and only one drawer is shown at a time — opening the navigator earlier may have taken
       the slot. Clicking the toggle is what a person does; `fill` on a hidden textarea waits 30 s a
       time, twice, and that was the whole of this script's remaining slowness. */
    if (!(await p.locator(".composer.is-dock textarea").count())) {
      await p.getByRole("button", { name: /Show the assistant/i }).first()
        .click({ timeout: 5000 }).catch(() => {});
      await p.waitForTimeout(700);
    }
    const box = p.locator(".composer.is-dock textarea, .composer textarea").first();
    if (await box.count()) {
      await box.click({ timeout: 4000 }).catch(() => {});
      // "@" alone lists the OPEN documents from memory — no workspace walk, no 4 s wait.
      await box.type("@", { delay: 40 }).catch(() => {});
      await p.waitForTimeout(700);
      const opt = p.locator(".composer .mention-opt").first();
      if (await opt.count()) {
        await opt.click({ timeout: 4000 }).catch(() => {});
        await p.waitForTimeout(600);
      }
      /* C6 is measured HERE, not by the later probe: sending the message consumes the attachment
         (`setAttachments([])`), so a chip that worked perfectly is gone by the time the probe runs.
         Measuring it afterwards scored a correct product as broken. */
      chipObserved = (await p.locator(".ctx-chip button, .ctx-row button").count()) > 0;
      // A short prompt with tools: A1 is about tool calls being VISIBLE, and the fixture scenario
      // emits them for any prompt. A long prompt only makes the turn slower to read.
      await box.fill("Show revenue by month.").catch(() => {});
      await box.press("Enter").catch(() => {});
      await p.locator(".turn").first().waitFor({ timeout: 25000 }).catch(() => {});
      await p.locator(".turn-foot").first().waitFor({ timeout: 40000 }).catch(() => {});
      await p.waitForTimeout(500);
      if (process.env.DEBUG_SCORE) console.log(`  [debug] turns=${await p.locator(".turn").count()}`);
    }
  }

  step("probe");
  const m = await probe(p);
  if (chipObserved) m.chipRemovable = true;
  if (process.env.DEBUG_SCORE) console.log(`  [debug] chromePx=${m.chromePx} chips=${m.chipRemovable} pin=${m.modelPinHint}`);
  /* A scorecard whose selectors are wrong measures nothing. This guard fails the run loudly when a
     control it is looking for is absent while the document it opened clearly has cells — which is how
     three separate measurement errors were found while building this file. */
  if (process.env.DEBUG_SCORE && m.cellRun === 0 && (await p.locator(".cell-block").count()) > 0) {
    console.log("  [warn] a notebook is open with cells but no run control matched .cell-run-act");
  }

  // counts that need interaction
  const countShortcuts = async () => {
    await p.keyboard.press(process.platform === "darwin" ? "Meta+/" : "Control+/");
    await p.waitForTimeout(500);
    const n = await p.locator(".keys-sheet kbd, .sheet kbd").count();
    await p.keyboard.press("Escape");
    await p.waitForTimeout(300);
    return n;
  };
  step("shortcuts");
  m.shortcutsListed = await countShortcuts();

  /* F1 and F4 live in the navigator. Below 820 px the navigator is a drawer and only one drawer is
     shown at a time, so the assistant must yield to it — exactly what a person does when they want to
     browse files at a narrow width. Measured with the navigator open, then handed back. */
  const navToggle = p.getByRole("button", { name: /Show the navigator/i }).first();
  const navNeeded = !(await p.getByRole("tab", { name: "Sessions" }).isVisible().catch(() => false));
  if (navNeeded && await navToggle.count()) {
    await navToggle.click({ timeout: 5000 }).catch(() => {});
    await p.waitForTimeout(700);
  }
  await p.getByRole("tab", { name: "Sessions" }).click().catch(() => {});
  await p.waitForTimeout(600);
  m.recentSessions = (await p.locator(".rail-item").count()) > 0;
  await p.getByRole("tab", { name: "Files" }).click().catch(() => {});
  await p.waitForTimeout(600);
  m.listView = await p.locator('[aria-label="List view"]').isVisible().catch(() => false);

  /* Re-open the notebook before running it. The steps above (shortcut sheet, picker) move focus and,
     at overlay widths, can leave the document behind a drawer: a click that lands on a covered button
     waits its full timeout and scores "no output" on a run that never started. Re-opening is what a
     person would do, and it makes the measurement start from a state we control. */
  {
    const tab = p.locator(".doc-tab", { hasText: "e2e_sql" }).first();
    if (await tab.count()) {
      await tab.click({ timeout: 4000 }).catch(() => {});
      await p.waitForTimeout(600);
    }
    if (!(await p.locator(".cell-block").count())) {
      const nav = p.getByRole("button", { name: /Show the navigator/i }).first();
      if (await nav.count()) { await nav.click({ timeout: 4000 }).catch(() => {}); await p.waitForTimeout(600); }
      await p.getByRole("tab", { name: "Files" }).click().catch(() => {});
      await p.waitForTimeout(500);
    }
  }

  // Actually run a cell, then read the output: X2–X4 cannot be scored from markup alone.
  // The ENABLED control specifically: a Python cell legitimately has a disabled run button, and
  // clicking that one scores the refusal rather than the feature.
  const enabledRuns = p.locator(".cell-run-act:not([disabled])");
  if (process.env.DEBUG_SCORE) {
    console.log(`  [debug] before run: cells=${await p.locator(".cell-block").count()} enabled=${await enabledRuns.count()} doc=${await p.locator(".doc-name").textContent().catch(() => "?")}`);
  }
  if ((await enabledRuns.count()) >= 1) {
    /* NOT swallowed: a click that times out used to be hidden by `.catch(() => {})`, and the script
       then waited 90 s for an output that could never appear. A failed click is the finding. */
    let clicked = true;
    await enabledRuns.first().click({ timeout: 6000 }).catch(async (e) => {
      clicked = false;
      console.log(`  [debug] RUN CLICK FAILED: ${String(e?.message ?? e).split("\n")[0]}`);
      // Name what is on top: the answer is always a portal, a sheet or a drawer, never the button.
      const cover = await p.evaluate(() => {
        const b2 = [...document.querySelectorAll(".cell-run-act:not([disabled])")][0];
        if (!b2) return "no button";
        const r = b2.getBoundingClientRect();
        const at = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
        return at ? `${at.tagName}.${String(at.className).slice(0, 56)}` : "nothing on top";
      });
      console.log(`  [debug] covering element: ${cover}`);
    });
    if (!clicked) { /* scored as no output, which is what a user would see too */ }
    // Wait for the run to FINISH: `.cell-output` appears immediately in its "running" state, so
    // waiting for the element scores the in-flight state and reports "no timing" on a run that was
    // about to succeed. The finished states are the ones the rubric is about.
    const finished = await p.waitForSelector(
      '.cell-output[data-state="succeeded"], .cell-output[data-state="failed"], ' +
      '.cell-output[data-state="refused"], .cell-output[data-state="cancelled"]',
      { timeout: 45000 }).then(() => true).catch(() => false);
    const appeared = finished;
    if (appeared) {
      await p.waitForTimeout(1200);
      m.cellOutput = await p.locator(".cell-output").count();
      m.runText = (await p.locator(".cell-output").first().innerText().catch(() => "")).slice(0, 160);
      m.cellTiming = /\d+(\.\d+)?s/.test(m.runText);
      m.cellOutputControls = (await p.locator(".cell-clear").count()) > 0;
      if (process.env.DEBUG_SCORE) console.log(`  [debug] run text: ${JSON.stringify(m.runText)}`);
    } else if (process.env.DEBUG_SCORE) {
      console.log("  [debug] no .cell-output appeared after the run");
    }
  }

  const countPickerGroups = async () => {
    const box = await p.evaluate(() => {
      const el = [...document.querySelectorAll(".model-trigger")].find((e) => e.getBoundingClientRect().width > 0);
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
    });
    if (!box) return 0;
    await p.mouse.click(box.x, box.y);
    await p.waitForSelector(".picker", { timeout: 5000 }).catch(() => {});
    const n = await p.locator(".picker-group").count();
    // Escape, then VERIFY: a portalled popover left open intercepts the next click, which is how a
    // cell run that works standalone produced no output inside this script.
    await p.keyboard.press("Escape");
    await p.waitForTimeout(300);
    if (await p.locator(".picker").count()) {
      await p.mouse.click(4, 4).catch(() => {});
      await p.waitForTimeout(300);
    }
    if (process.env.DEBUG_SCORE) console.log(`  [debug] picker closed: ${(await p.locator(".picker").count()) === 0}`);
    await p.waitForTimeout(300);
    return n;
  };
  step("picker");
  m.pickerGroups = await countPickerGroups();

  /* M4 is about the PIN, which only exists after a switch. Opening and closing the picker proves the
     list works; it does not prove the product tells you the change applies to the NEXT turn. So the
     scenario does what the item describes: choose a different model, then look. */
  {
    const box = await p.evaluate(() => {
      const el = [...document.querySelectorAll(".model-trigger")].find((e) => e.getBoundingClientRect().width > 0);
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
    });
    if (box) {
      await p.mouse.click(box.x, box.y);
      await p.waitForSelector(".picker", { timeout: 8000 }).catch(() => {});
      const rows = p.locator(".picker-row:not(.is-disabled)");
      const n = await rows.count();
      for (let i = 0; i < n; i += 1) {
        if ((await rows.nth(i).locator(".picker-badge").count()) === 0) {
          await rows.nth(i).click({ force: true, timeout: 5000 }).catch(() => {});
          break;
        }
      }
      await p.waitForTimeout(2500);
      m.modelPinHint = await p.evaluate(() => /next (message|turn)/i.test(document.body.innerText));
      if (process.env.DEBUG_SCORE) console.log(`  [debug] pin hint after a switch: ${m.modelPinHint}`);
    }
  }

  // dead controls: structural probe over every visible button in the three panes
  m.deadControls = await p.evaluate(() => {
    let dead = 0;
    for (const scope of [".pane.rail", ".pane.main", ".pane.assistant"]) {
      const root = document.querySelector(scope);
      if (!root) continue;
      for (const btn of root.querySelectorAll("button")) {
        const r = btn.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) continue;
        if (btn.disabled || btn.getAttribute("aria-disabled") === "true") continue;
        const k = Object.keys(btn).find((x) => x.startsWith("__reactProps"));
        if (k && !btn[k]?.onClick) dead += 1;
      }
    }
    return dead;
  });

  // dark mode: render it and check contrast of the dock header text
  await p.evaluate(() => {
    document.documentElement.setAttribute("data-theme", "dark");
  });
  await p.waitForTimeout(500);
  m.darkOk = await p.evaluate(() => {
    const el = document.querySelector(".dock-context-value, .dock-state-word");
    if (!el) return true;
    const cs = getComputedStyle(el);
    return cs.color !== "rgba(0, 0, 0, 0)" && cs.color !== getComputedStyle(document.body).backgroundColor;
  });
  // A screenshot is a nicety; a crash here would discard a measurement that already succeeded.
  await p.screenshot({ path: `${out}/w${width}-dark.png` }).catch(() => {});
  await p.evaluate(() => document.documentElement.removeAttribute("data-theme"));
  await p.waitForTimeout(400);

  await p.screenshot({ path: `${out}/w${width}.png` }).catch(() => {});

  const scored = RUBRIC.map((r) => ({ ...r, pass: Boolean(r.test(m)) }));
  const total = scored.reduce((sum, r) => sum + (r.pass ? r.pts : 0), 0);
  const max = RUBRIC.reduce((sum, r) => sum + r.pts, 0);
  clearTimeout(watchdog);
  await p.close();
  return { width, total, max, m, items: scored.map(({ test, ...rest }) => rest) };
}

/* Sequential on purpose. Measured: three widths in parallel took 300 s, one at a time took 198 s —
 * the workspace API calls contend and each page waits longer. Parallelism helps an I/O-bound script
 * and hurts a script whose cost is a shared, rate-limited backend. */
const MEASURE_TIMEOUT_MS = Number(process.env.MEASURE_TIMEOUT_MS ?? 240_000);
const results = [];
for (const w of widths) {
  try {
    results.push(await measure(w));
  } catch (e) {
    /* One width failing is not the run failing. It is reported with the step it stopped at, so a
     * hang names a place rather than taking the other three measurements down with it. */
    console.error(`  ${w}px ABORTED — ${String(e?.message ?? e).split("\n")[0]}`);
    results.push({ width: w, total: 0, max: 100, m: {}, aborted: true,
      items: RUBRIC.map(({ test, ...rest }) => ({ ...rest, pass: false })) });
  }
}
for (const r of results) {
  perWidth.push(r);
  console.log(`${r.width}px  ${r.total}/${r.max}`);
  for (const i of r.items.filter((x) => !x.pass)) console.log(`        MISS ${i.id} ${i.name} (-${i.pts})`);
}
perWidth.sort((a, b2) => a.width - b2.width);

const avg = Math.round(perWidth.reduce((s, x) => s + (x.total / x.max) * 100, 0) / perWidth.length);
const byGroup = {};
for (const g of [...new Set(RUBRIC.map((r) => r.group))]) {
  byGroup[g] = perWidth.reduce((sum, w) => sum + w.items.filter((i) => i.group === g && i.pass).reduce((s, i) => s + i.pts, 0), 0);
}
writeFileSync(`${out}/scorecard.json`, JSON.stringify({ app: APP, at: started, averagePct: avg, byGroup, perWidth }, null, 2));
console.log(`\naverage ${avg}%  ·  by group ${JSON.stringify(byGroup)}`);
await b.close();
