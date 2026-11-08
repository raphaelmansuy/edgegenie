/** LaTeX in markdown, end to end: typeset, never clunky, never eating the answer.
 *   APP_URL=http://127.0.0.1:8062 node scripts/math-e2e.mjs
 * Screenshots: specs/007-ux-ui-improve/e2e/screenshot/ */
import { mkdirSync } from "node:fs";
const OUT = new URL("../../../../specs/007-ux-ui-improve/e2e/screenshot/", import.meta.url).pathname;
process.env.OUT = OUT;
mkdirSync(OUT, { recursive: true });
const { launch, shot } = await import("./parity-lib.mjs");

let failed = 0;
const ok = (n, c, d = "") => { console.log(`  ${c ? "PASS" : "FAIL"} ${n}${d ? ` — ${d}` : ""}`); if (!c) failed++; };
const { browser, page: p, errors } = await launch(1440, 1000);
await p.locator(".home").waitFor({ timeout: 40000 });
await p.locator("textarea").last().fill("Calculate pi. [[scenario:math]]");
await p.keyboard.press("Enter");
await p.waitForTimeout(6000);
for (let i = 0; i < 14 && (await p.evaluate(() => document.querySelector(".session-chip")?.textContent)) !== "ready"; i++) await p.waitForTimeout(1500);
await p.waitForTimeout(2500);

const m = await p.evaluate(() => {
  const q = (s) => document.querySelectorAll(s).length;
  /* Scope to the CONVERSATION. `Markdown` renders `.answer` in two places — a turn's reply and a
     notebook cell's rendered markdown — so a bare `.answer` here read the notebook cell that the
     notebook scenario had just written, and every money/KaTeX assertion was made against the wrong
     element (measured: two `.answer` nodes, the first outside `#dock`). */
  const answer = document.querySelector("#dock .answer");
  const ps = [...(answer?.querySelectorAll("p") ?? [])];
  return {
    katex: q(".katex"), display: q(".math-block"), inline: q(".math-inline"),
    sources: q(".math-source"), invalid: q(".math-invalid"),
    // the two dollar amounts must still be prose, and the code block must not contain KaTeX
    literalDollars: /A price of \$5 and \$10 is/.test(answer?.textContent ?? ""),
    codeHasKatex: (answer?.querySelector("pre")?.querySelectorAll(".katex").length ?? 0) > 0,
    codeText: answer?.querySelector("pre")?.textContent ?? "",
    /* Rhythm is measured as "how much taller is this paragraph than its own line count allows", not as
       an absolute height: a 139-character paragraph in a 380 px dock is three lines, and three lines at
       21.5 px is 65 px — correct. Comparing raw heights flagged the right paragraph for the wrong
       reason. */
    rhythm: ps.map((el) => {
      const h = el.getBoundingClientRect().height;
      const lh = parseFloat(getComputedStyle(el).lineHeight) || 19;
      const lines = Math.max(1, Math.round(h / lh));
      return { h: Math.round(h), lh: Math.round(lh * 10) / 10, lines, perLine: Math.round((h / lines) * 10) / 10 };
    }),
  };
});
console.log("  measure:", JSON.stringify(m));
ok("display math is typeset", m.display >= 1 && m.katex >= 1);
ok("inline math is typeset", m.inline >= 4);
ok("no formula failed to typeset", m.invalid === 0);
ok("no raw TeX is left on screen for a valid formula", m.sources === 0, `${m.sources} source nodes`);
ok("money is not math", m.literalDollars);
ok("a fenced block keeps its dollars as code", !m.codeHasKatex && m.codeText.includes("$$this is code"), m.codeText.slice(0, 40));
ok("no page errors", errors.length === 0, errors.join(" | "));
await shot(p, "53-math-in-dock.png");

/* Rhythm: each paragraph's height must be its line count times its line-height. A formula that pushes a
   line apart shows up as a per-line height well above the declared line-height. */
const bad = m.rhythm.filter((r) => r.perLine > r.lh * 1.35);
ok("no paragraph is torn apart by an inline formula", bad.length === 0, JSON.stringify(m.rhythm));

// dark mode: the glyphs must take the theme's ink, not KaTeX's black
await p.getByRole("button", { name: /^Dark$/i }).click().catch(() => {});
await p.waitForTimeout(900);
const dark = await p.evaluate(() => {
  const k = document.querySelector(".math-block .katex");
  /* Scope to the CONVERSATION. `Markdown` renders `.answer` in two places — a turn's reply and a
     notebook cell's rendered markdown — so a bare `.answer` here read the notebook cell that the
     notebook scenario had just written, and every money/KaTeX assertion was made against the wrong
     element (measured: two `.answer` nodes, the first outside `#dock`). */
  const answer = document.querySelector("#dock .answer");
  return { katex: k ? getComputedStyle(k).color : "none", answer: answer ? getComputedStyle(answer).color : "none" };
});
ok("math inherits the theme's ink in dark mode", dark.katex === dark.answer, JSON.stringify(dark));
await shot(p, "54-math-dark.png");

// a narrow column: a wide display formula must scroll, not widen the panel
await p.getByRole("button", { name: /^Light$/i }).click().catch(() => {});
await p.setViewportSize({ width: 1100, height: 900 });
await p.waitForTimeout(1600);
// At this width the dock may become a focus column or a drawer: make sure it is on screen before
// measuring, or the block is legitimately absent and the check tests nothing.
if ((await p.locator("#dock").count()) === 0) {
  const show = p.getByRole("button", { name: /Show the assistant/i }).first();
  if (await show.count()) { await show.click({ force: true }); await p.waitForTimeout(900); }
}
await p.locator(".dock-body").evaluate((el) => { el.scrollTop = el.scrollHeight; }).catch(() => {});
await p.waitForTimeout(400);
const narrow = await p.evaluate(() => {
  const blk = document.querySelector(".math-block");
  const body = document.querySelector(".dock-body");
  if (!blk || !body) return { ok: false, why: "missing", hasBlk: !!blk, hasBody: !!body };
  return { scrolls: blk.scrollWidth > blk.clientWidth, overflowX: getComputedStyle(blk).overflowX,
    bodyOverflow: body.scrollWidth - body.clientWidth };
});
ok("a wide formula scrolls inside its own box", narrow.scrolls ? narrow.overflowX === "auto" : true, JSON.stringify(narrow));
ok("…and never widens the panel", (narrow.bodyOverflow ?? 0) <= 1, JSON.stringify(narrow));
await shot(p, "55-math-narrow.png");

/* A `.md` FILE opens rendered, not as source (MD-7). This is the case the deployed agent produced:
   a document whose whole point was its formulas, shown as raw `$$…$$` in an editor. */
await p.setViewportSize({ width: 1440, height: 950 });
await p.evaluate(() => { location.hash = "#/file/Users/raphael.mansuy@gmail.com/agent_scratch/leibniz_pi_explanation.md"; });
await p.waitForTimeout(4000);
const md = await p.evaluate(() => {
  const root = document.querySelector(".md-preview");
  return { preview: !!root, toggle: document.querySelector(".preview-toggle")?.textContent ?? "",
    katex: root?.querySelectorAll(".katex").length ?? 0,
    raw: (root?.textContent.match(/\$/g) || []).length };
});
ok("a .md file opens rendered", md.preview, JSON.stringify(md));
ok("…its formulas are typeset", md.katex >= 10, String(md.katex));
ok("…and no raw dollar is left", md.raw === 0, String(md.raw));
await shot(p, "59-md-file.png");
// the toggle reaches the source in one click, and back
await p.locator(".preview-toggle").click();
await p.waitForTimeout(900);
ok("the bar toggles to the source", (await p.locator(".editor-surface .cm-editor").count()) > 0);
await p.locator(".preview-toggle").click();
await p.waitForTimeout(900);
ok("…and back to the rendered document", (await p.locator(".md-preview").count()) > 0);

await browser.close();
console.log(failed ? `\n${failed} failed` : "\nall passed");
process.exit(failed ? 1 : 0);
