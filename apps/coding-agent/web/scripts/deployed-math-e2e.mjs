/** 007 math on the DEPLOYED app: the markdown file the agent wrote, plus a live answer.
 *   DATABRICKS_TOKEN=... APP_URL=... node scripts/deployed-math-e2e.mjs */
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
const APP = process.env.APP_URL, TOKEN = process.env.DATABRICKS_TOKEN;
const OUT = new URL("../../../../specs/007-ux-ui-improve/e2e/screenshot/", import.meta.url).pathname;
mkdirSync(OUT, { recursive: true });
const MD = process.env.MD ?? "/Users/raphael.mansuy@gmail.com/agent_scratch/leibniz_pi_explanation.md";
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 950 }, deviceScaleFactor: 2, extraHTTPHeaders: { Authorization: `Bearer ${TOKEN}` } });
const p = await ctx.newPage();
const errors = [];
p.on("pageerror", (e) => errors.push(String(e)));
let failed = 0;
const ok = (n, c, d = "") => { console.log(`  ${c ? "PASS" : "FAIL"} ${n}${d ? ` — ${d}` : ""}`); if (!c) failed++; };

// 1. a markdown FILE with formulas, opened from a link
await p.goto(`${APP}/#/file${MD}`, { waitUntil: "load" });
await p.locator(".home, .md-preview, .editor-surface").first().waitFor({ timeout: 60000 });
await p.waitForTimeout(4500);
const md = await p.evaluate(() => {
  const root = document.querySelector(".md-preview");
  return { preview: !!root, katex: root?.querySelectorAll(".katex").length ?? 0,
    blocks: root?.querySelectorAll(".math-block").length ?? 0,
    raw: (root?.textContent.match(/\$/g) || []).length,
    toggle: document.querySelector(".preview-toggle")?.textContent ?? "" };
});
ok("a deployed .md file opens rendered", md.preview, JSON.stringify(md));
ok("…its formulas are typeset", md.katex >= 10, String(md.katex));
ok("…no raw dollar is left", md.raw === 0, String(md.raw));
await p.screenshot({ path: `${OUT}/60-deployed-md-math.png` });

// 2. the source toggle works both ways
await p.locator(".preview-toggle").click();
/* CodeMirror is a LAZY chunk: on the deployed app the first switch to source downloads ~650 KB, so a
   fixed 1.2 s wait measured the gap before the editor mounted. Wait for the surface, then settle. */
await p.locator(".cm-editor").waitFor({ timeout: 20000 }).catch(() => {});
ok("the bar shows the source on demand", (await p.locator(".cm-editor").count()) > 0);
await p.locator(".preview-toggle").click();
await p.locator(".md-preview").waitFor({ timeout: 8000 }).catch(() => {});
ok("…and returns to the rendered document", (await p.locator(".md-preview").count()) > 0);

// 3. the ink follows the theme
const inks = await p.evaluate(() => {
  const k = document.querySelector(".md-preview .katex");
  const a = document.querySelector(".md-preview .answer");
  return { katex: k ? getComputedStyle(k).color : null, text: a ? getComputedStyle(a).color : null };
});
ok("math takes the document's ink", inks.katex === inks.text, JSON.stringify(inks));
ok("no page errors", errors.length === 0, errors.join(" | ").slice(0, 160));
await browser.close();
console.log(failed ? `\n${failed} failed` : "\nall passed");
