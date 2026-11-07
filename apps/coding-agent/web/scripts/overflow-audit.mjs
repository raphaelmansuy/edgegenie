/** Overflow audit: find every element whose content spills past its own box.
 *
 *   APP_URL=http://127.0.0.1:8040 node scripts/overflow-audit.mjs [outdir]
 *
 * Checks, for every visible element: horizontal overflow (scrollWidth > clientWidth) on a box that
 * does not scroll, text taller than its clipped box, children outside the parent's rectangle, and
 * elements sticking out of the window. Prints a table and exits non-zero when anything spills.
 */
import { chromium } from "playwright";
import { mkdirSync, readFileSync } from "node:fs";

const out = process.argv[2] ?? "/tmp/genie-overflow";
mkdirSync(out, { recursive: true });
const bearer = process.env.BEARER_FILE ? readFileSync(process.env.BEARER_FILE, "utf8").trim() : "";

const widths = (process.env.WIDTHS ?? "1480,1180,900").split(",").map(Number);

const audit = () => {
  const problems = [];
  const seen = new Set();

  /** The rectangle an element is actually allowed to paint in, after every clipping ancestor. */
  const visibleBox = (el) => {
    let box = { left: 0, top: 0, right: window.innerWidth, bottom: window.innerHeight };
    for (let a = el.parentElement; a; a = a.parentElement) {
      const st = getComputedStyle(a);
      const clips = st.overflow !== "visible" || st.contain.includes("paint");
      if (!clips) continue;
      const r = a.getBoundingClientRect();
      box = {
        left: Math.max(box.left, r.left + a.clientLeft),
        top: Math.max(box.top, r.top + a.clientTop),
        right: Math.min(box.right, r.left + a.clientLeft + a.clientWidth),
        bottom: Math.min(box.bottom, r.top + a.clientTop + a.clientHeight),
      };
      // A scroll container is meant to hold more than it shows: that is not a spill.
      if (st.overflowX !== "visible" || st.overflowY !== "visible") return null;
    }
    return box;
  };
  const all = Array.from(document.querySelectorAll("*"));
  for (const el of all) {
    const style = getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity) === 0) continue;
    // Visually-hidden text is 1px on purpose: it is for screen readers, not for people to read.
    if (el.classList.contains("sr-only")) continue;
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    const scrollsX = style.overflowX === "auto" || style.overflowX === "scroll";
    const scrollsY = style.overflowY === "auto" || style.overflowY === "scroll";
    const name = `${el.tagName.toLowerCase()}${el.className && typeof el.className === "string" ? `.${el.className.trim().split(/\s+/).join(".")}` : ""}`;
    const text = (el.textContent ?? "").trim().slice(0, 40);
    const add = (kind, detail) => {
      const key = `${kind}|${name}|${detail}`;
      if (seen.has(key)) return;
      seen.add(key);
      problems.push({ kind, name, detail, text });
    };
    if (el.scrollWidth > el.clientWidth + 1 && !scrollsX && style.textOverflow !== "ellipsis") {
      add("horizontal", `${el.scrollWidth} > ${el.clientWidth}`);
    }
    if (el.scrollHeight > el.clientHeight + 1 && !scrollsY && style.overflowY === "hidden") {
      add("clipped-y", `${el.scrollHeight} > ${el.clientHeight}`);
    }
    const box = visibleBox(el);
    if (box && (r.right > box.right + 1 || r.left < box.left - 1
        || r.bottom > box.bottom + 1 || r.top < box.top - 1)) {
      add("outside-box", `element ${Math.round(r.left)}..${Math.round(r.right)} × ${Math.round(r.top)}..${Math.round(r.bottom)}`
        + ` vs ${Math.round(box.left)}..${Math.round(box.right)} × ${Math.round(box.top)}..${Math.round(box.bottom)}`);
    }
    // A control must sit inside the shape it belongs to. "Near enough" is how a × ends up hanging
    // off a tab: it was a sibling of the tab, so it was outside the tab's own rounded border.
    const ownShape = el.closest(".doc-tab, .ctx-chip, .tree-row, .pill, .btn, .rail-tab, .palette-row");
    if (ownShape && ownShape !== el && ownShape.contains(el)) {
      const sr = ownShape.getBoundingClientRect();
      const st2 = getComputedStyle(ownShape);
      const inset = 0.5;
      if (r.right > sr.right - inset || r.left < sr.left + inset
          || r.bottom > sr.bottom - inset || r.top < sr.top + inset) {
        if (st2.overflow === "visible") {
          add("outside-its-shape",
            `${name} ${Math.round(r.left)}..${Math.round(r.right)} escapes ${ownShape.className.split(" ")[0]} ${Math.round(sr.left)}..${Math.round(sr.right)}`);
        }
      }
    }

    // children outside the parent's padded box (text escaping a card, a badge over a border)
    const parent = el.parentElement;
    if (parent) {
      const ps = getComputedStyle(parent);
      if (ps.overflow === "visible") {
        const pr = parent.getBoundingClientRect();
        if (pr.width > 0 && el.offsetParent === parent &&
            (r.right > pr.right + 1.5 || r.left < pr.left - 1.5)) {
          add("escapes-parent", `child ${Math.round(r.left)}..${Math.round(r.right)} vs parent ${Math.round(pr.left)}..${Math.round(pr.right)}`);
        }
      }
    }
  }
  return problems;
};

const b = await chromium.launch({ executablePath: process.env.CHROME_PATH || undefined });
const report = [];
for (const width of widths) {
  const p = await b.newPage({
    viewport: { width, height: 940 }, deviceScaleFactor: 1,
    extraHTTPHeaders: bearer ? { Authorization: `Bearer ${bearer}` } : {},
  });
  await p.goto(process.env.APP_URL ?? "http://127.0.0.1:8040", { waitUntil: "domcontentloaded" });
  await p.waitForTimeout(1500);

  // the empty state first
  report.push({ width, view: "home", problems: await p.evaluate(audit) });
  await p.screenshot({ path: `${out}/${width}-home.png` });

  // then a finished turn with tool calls, a grid and evidence
  const box = p.getByRole("textbox", { name: "Message the agent" });
  await box.fill("Build a notebook that shows revenue by pickup hour");
  await p.keyboard.press("Enter");
  // Real agent: a turn takes a while. Audit whatever is on screen either way — during streaming
  // is exactly when a long line is most likely to escape.
  await p.locator(".turn").first().waitFor({ timeout: 60000 });
  await p.locator(".turn-foot").first().waitFor({ timeout: 240000 }).catch(() => {
    console.log(`  (${width}px: the turn was still running; auditing the streaming state)`);
  });
  await p.waitForTimeout(600);
  report.push({ width, view: "turn", problems: await p.evaluate(audit) });
  await p.screenshot({ path: `${out}/${width}-turn.png` });

  // a document open, with long paths and the tab strip.
  // On a narrow window the rail starts closed (it is a drawer there), so open it first.
  if (!(await p.getByRole("tab", { name: /Files/i }).isVisible())) {
    await p.getByRole("button", { name: "Show the navigator" }).click();
    await p.locator(".pane.rail").waitFor({ state: "visible" });
  }
  await p.getByRole("tab", { name: /Files/i }).click();
  await p.getByPlaceholder("Search notebooks and files…").fill("taxi");
  await p.locator(".result").first().click({ timeout: 30000 });
  /* Read-only viewer (.cell) or editable notebook (.cell-block): a document is one or the other
     depending on whether a session exists. Asserting only the old class stopped covering the
     surface users actually edit. */
  await p.locator(".cell, .cell-block").first().waitFor({ timeout: 30000 });
  report.push({ width, view: "document", problems: await p.evaluate(audit) });
  await p.screenshot({ path: `${out}/${width}-document.png` });
  /* The editor and the transcript share the centre pane, so anything that needs `.turn` must run
     with no document open. Closing here is what makes the audit order-independent. */
  await p.keyboard.press("Meta+w");
  await p.waitForTimeout(400);

  // Close any overlay the previous step opened, so each check starts from the same state.
  await p.keyboard.press("Escape");
  await p.waitForTimeout(150);

  // The worst case a real agent produces: an answer with an unbroken 300-character token.
  // Injected into the transcript so this is checked deterministically, not only when a model happens
  // to emit one.
  await p.evaluate(() => {
    const host = document.querySelector(".answer") ?? document.querySelector(".transcript");
    if (!host) return;
    const bad = `db_dbx_run_notebook(path=/Users/raphael.mansuy@gmail.com/agent_scratch/${"x".repeat(240)}, timeout=45)`;
    const el = document.createElement("p");
    el.className = "injected-long";
    el.textContent = `Ran ${bad} then ${"y".repeat(200)}`;
    host.appendChild(el);
  });
  report.push({ width, view: "long-token", problems: await p.evaluate(audit) });
  await p.screenshot({ path: `${out}/${width}-long-token.png` });

  // an overlay panel is not a missing panel: record what it looks like when opened
  if (width <= 1180) {
    /* The inspector is an overlay below 1180, opened on demand. Guard on the button EXISTING: it is
       absent when the pane is already open, and absent when there is no session to describe. */
    const open = p.getByRole("button", { name: "Show the inspector" });
    if (await open.count() > 0 && await p.locator(".pane.inspector").count() === 0) {
      await open.click();
      await p.locator(".pane.inspector").waitFor({ state: "visible", timeout: 15000 }).catch(() => {});
    }
    report.push({ width, view: "inspector-overlay", problems: await p.evaluate(audit) });
    await p.screenshot({ path: `${out}/${width}-inspector.png` });
    await p.keyboard.press("Escape");
  }
  if (width <= 820) {
    report.push({ width, view: "drawer", problems: await p.evaluate(audit) });
    await p.screenshot({ path: `${out}/${width}-drawer.png` });
    await p.keyboard.press("Escape");
  }

  // overlays
  await p.keyboard.press("Meta+k");
  await p.locator(".palette").waitFor({ timeout: 5000 });
  await p.locator(".palette-input").fill("sam");
  await p.waitForTimeout(600);
  report.push({ width, view: "palette", problems: await p.evaluate(audit) });
  await p.screenshot({ path: `${out}/${width}-palette.png` });
  await p.keyboard.press("Escape");
  await p.keyboard.press("Meta+/");
  await p.locator(".keys-sheet").waitFor({ timeout: 5000 });
  report.push({ width, view: "shortcuts", problems: await p.evaluate(audit) });
  await p.screenshot({ path: `${out}/${width}-keys.png` });
  await p.close();
}
await b.close();

let total = 0;
for (const r of report) {
  if (!r.problems.length) continue;
  console.log(`\n=== ${r.width}px · ${r.view}: ${r.problems.length}`);
  for (const p of r.problems) {
    total += 1;
    console.log(`  ${p.kind.padEnd(14)} ${p.name.slice(0, 46).padEnd(46)} ${p.detail}  «${p.text}»`);
  }
}
console.log(`\nTOTAL: ${total} overflow problem(s) across ${report.length} checks`);
process.exit(total ? 1 : 0);
