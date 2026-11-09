/** End-to-end test of the built GitHub Pages site (site/dist).
 *
 *   python3 site/build.py
 *   node tests/sites/e2e/site.e2e.mjs                 # every page, every width, both themes
 *   ONLY=home,tour node tests/sites/e2e/site.e2e.mjs  # a subset of pages
 *
 * For every page × viewport it asserts what a reader would notice, and saves a full-page screenshot to
 * tests/sites/e2e/screenshots/<page>--<width>-<theme>.png so the same state can be inspected by eye.
 * Results go to tests/sites/e2e/report.json. Exit code 1 if any assertion fails.
 *
 * Playwright is resolved from $PLAYWRIGHT_MODULE (a path to playwright/index.js, used by CI), then the
 * bare specifier, then apps/coding-agent/web/node_modules, so the site keeps building with python3 alone.
 */
import { createServer } from "node:http";
import { readFile, stat, mkdir, rm, writeFile } from "node:fs/promises";
import { dirname, extname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "..", "..", "..");
const DIST = join(ROOT, "site", "dist");
const SHOTS = join(HERE, "screenshots");
const BASE = "/opengenie/";

async function loadPlaywright() {
  const candidates = [process.env.PLAYWRIGHT_MODULE, "playwright",
    join(ROOT, "apps/coding-agent/web/node_modules/playwright/index.js")].filter(Boolean);
  for (const c of candidates) {
    try {
      const mod = await import(c.startsWith("/") ? pathToFileURL(c).href : c);
      return mod.chromium ? mod : mod.default;
    } catch { /* next */ }
  }
  throw new Error("playwright not found: run `npm ci` in apps/coding-agent/web");
}

/* Every page the site publishes, read from its own sitemap, so a new page is tested without an edit
   here; plus the 404, which Pages serves at any missing path. */
async function sitePages() {
  const xml = await readFile(join(DIST, "sitemap.xml"), "utf8");
  const paths = [...xml.matchAll(/<loc>https?:\/\/[^<]*?\/opengenie\/([^<]*)<\/loc>/g)].map((m) => "/" + m[1]);
  const name = (p) => p === "/" ? "home" : p.replace(/^\/|\/$/g, "").replace(/\//g, "_");
  return [...paths.map((p) => [name(p), p]), ["not-found", "/does/not/exist/"]];
}
const PAGES = await sitePages();
const VIEWPORTS = [
  { width: 1440, height: 900, theme: "light" },
  { width: 1024, height: 800, theme: "light" },
  { width: 768, height: 1024, theme: "light" },
  { width: 390, height: 844, theme: "light", mobile: true },
  { width: 1440, height: 900, theme: "dark" },
  { width: 390, height: 844, theme: "dark", mobile: true },
];

/* ------------------------------------------------------------------ a static server, like Pages */
const TYPES = { ".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "text/javascript",
  ".png": "image/png", ".jpg": "image/jpeg", ".svg": "image/svg+xml", ".json": "application/json",
  ".xml": "application/xml", ".txt": "text/plain", ".webmanifest": "application/manifest+json" };
function serve() {
  const server = createServer(async (req, res) => {
    const p = decodeURIComponent(new URL(req.url, "http://x").pathname);
    // GitHub Pages serves this project at /opengenie/; anything outside it is a 404, as there.
    if (!p.startsWith(BASE)) { res.writeHead(404); res.end(); return; }
    let file = join(DIST, p.slice(BASE.length));
    try {
      if ((await stat(file)).isDirectory()) file = join(file, "index.html");
      res.writeHead(200, { "content-type": TYPES[extname(file)] ?? "application/octet-stream" });
      res.end(await readFile(file));
    } catch {
      res.writeHead(404, { "content-type": TYPES[".html"] });
      res.end(await readFile(join(DIST, "404.html")));
    }
  });
  return new Promise((ok) => server.listen(0, "127.0.0.1", () => ok(server)));
}

/* ------------------------------------------------------------------ in-page audits */
function audit() {
  const out = { problems: [], h1: document.querySelectorAll("h1").length };
  const vw = document.documentElement.clientWidth;
  if (document.documentElement.scrollWidth > vw + 1)
    out.problems.push(`page scrolls sideways: ${document.documentElement.scrollWidth}px > ${vw}px`);

  // elements wider than the viewport that are not inside a deliberate scroller
  // inside a deliberate scroller (an ancestor that clips or scrolls); the element's own overflow does
  // not count, since an <svg> is overflow:hidden by default
  const scroller = (el) => { for (let e = el.parentElement; e; e = e.parentElement) {
    const ox = getComputedStyle(e).overflowX; if (ox === "auto" || ox === "scroll" || ox === "hidden") return e !== document.body && e !== document.documentElement; } return false; };
  for (const el of document.querySelectorAll("main *, header *, footer *")) {
    const r = el.getBoundingClientRect();
    if (r.width && (r.right > vw + 1 || r.left < -1) && !scroller(el) && getComputedStyle(el).position !== "fixed"
        && !el.closest(".sr, .skip, .site-nav:not(.is-open)"))
      { out.problems.push(`overflows viewport: <${el.tagName.toLowerCase()} class="${el.className}"> ${Math.round(r.left)}..${Math.round(r.right)}`); break; }
  }

  // clipped text: a text element whose content is wider than its box, with overflow hidden
  for (const el of document.querySelectorAll("main h1, main h2, main h3, main p, .btn, .badge, .card-foot, .site-nav a, figcaption")) {
    const cs = getComputedStyle(el);
    if (cs.overflow === "hidden" && el.scrollWidth > el.clientWidth + 1)
      out.problems.push(`clipped text: ${el.tagName} "${el.textContent.trim().slice(0, 40)}"`);
  }

  // images: loaded, described, sized
  for (const img of document.images) {
    if (!img.complete || !img.naturalWidth) out.problems.push(`image did not load: ${img.getAttribute("src")}`);
    if (!img.getAttribute("alt") && img.getAttribute("alt") !== "") out.problems.push(`image without alt: ${img.src}`);
  }

  // WCAG AA contrast for visible text
  // Chromium reports color-mix() results as `color(srgb r g b / a)` in 0..1 units.
  const rgb = (s) => { const n = (s.match(/[\d.]+/g) || []).map(Number);
    return s.startsWith("color(") ? [n[0] * 255, n[1] * 255, n[2] * 255, n[3] ?? 1] : n; };
  const lum = ([r, g, b]) => { const f = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
  const bgOf = (el) => { for (let e = el; e; e = e.parentElement) { const c = rgb(getComputedStyle(e).backgroundColor);
    if (c.length === 3 || (c.length === 4 && c[3] > 0.5)) return c.slice(0, 3); } return [255, 255, 255]; };
  let checked = 0;
  for (const el of document.querySelectorAll("main p, main li, main a, main h1, main h2, main h3, main small, main figcaption, main td, main th, .card-foot, .btn, .badge, .site-nav a, footer a, footer p")) {
    const r = el.getBoundingClientRect(); if (!r.width || !r.height || !el.textContent.trim()) continue;
    if (el.closest("pre, .code, .mermaid, svg")) continue;
    const cs = getComputedStyle(el); if (cs.visibility === "hidden" || cs.opacity === "0") continue;
    const fg = rgb(cs.color).slice(0, 3); const bg = bgOf(el);
    const [a, b] = [lum(fg), lum(bg)].sort((x, y) => y - x); const ratio = (a + 0.05) / (b + 0.05);
    const large = parseFloat(cs.fontSize) >= 24 || (parseFloat(cs.fontSize) >= 18.66 && +cs.fontWeight >= 700);
    checked++;
    if (ratio < (large ? 3 : 4.5)) { out.problems.push(`low contrast ${ratio.toFixed(2)}:1 on ${el.tagName} "${el.textContent.trim().slice(0, 30)}"`); if (out.problems.length > 12) break; }
  }
  out.contrastChecked = checked;

  // smallest body font
  out.minFont = Math.min(...[...document.querySelectorAll("main p, main li")].filter((e) => e.offsetParent && !e.matches(".eyebrow, .kicker")).map((e) => parseFloat(getComputedStyle(e).fontSize)), 99);
  if (out.minFont < 13) out.problems.push(`body text below 13px: ${out.minFont}px`);

  // markup that leaked into the reading text: an escaped entity or tag, or an unfilled template
  const text = document.body.innerText;
  for (const pat of [/&[a-z]+;/, /<\/?(strong|em|a|code|span)\b/, /\{\{\s*[\w-]+\s*\}\}/])
    { const m = text.match(pat); if (m) out.problems.push(`markup shown as text: "${text.slice(Math.max(0, m.index - 25), m.index + 25).replace(/\s+/g, " ")}"`); }

  // diagrams: rendered, and not empty
  for (const [i, d] of [...document.querySelectorAll("pre.mermaid")].entries()) {
    const svg = d.querySelector("svg"); const r = svg?.getBoundingClientRect();
    if (d.classList.contains("diagram-failed")) out.problems.push(`diagram ${i + 1} failed to render`);
    else if (!svg || r.width < 40 || r.height < 40) out.problems.push(`diagram ${i + 1} is empty`);
    else if (svg.querySelectorAll("text, foreignObject").length === 0) out.problems.push(`diagram ${i + 1} has no labels`);
    else { const vb = svg.viewBox?.baseVal; const scale = vb?.width ? r.width / vb.width : 1;
      // a phone shows a too-wide diagram whole, with a full-size control; anywhere else it must be legible
      const zoomable = d.closest("figure.diagram")?.classList.contains("is-zoomable") && d.closest("figure.diagram").querySelector(".diagram-open");
      if (scale < 0.7 && !zoomable) out.problems.push(`diagram ${i + 1} drawn at ${Math.round(scale * 100)}% scale: text too small to read`); }
  }

  out.links = [...new Set([...document.querySelectorAll("a[href]")].map((a) => a.href).filter((h) => h.startsWith(location.origin)))];
  return out;
}

function tapTargets() {
  const small = [];
  for (const el of document.querySelectorAll(".btn, .nav-toggle, .theme-switch button, .gh-link, .pager a")) {
    const r = el.getBoundingClientRect(); if (!r.width) continue;
    if (r.width < 24 || r.height < 24) small.push(`${el.className || el.tagName} ${Math.round(r.width)}×${Math.round(r.height)}`);
  }
  return small;
}

/* ------------------------------------------------------------------ run */
const { chromium } = await loadPlaywright();
const only = (process.env.ONLY ?? "").split(",").filter(Boolean);
const pages = only.length ? PAGES.filter(([n]) => only.includes(n)) : PAGES;
if (!only.length) await rm(SHOTS, { recursive: true, force: true });
await mkdir(SHOTS, { recursive: true });

const server = await serve();
const base = `http://127.0.0.1:${server.address().port}/opengenie`;
const browser = await chromium.launch();
const results = [];
const linkStatus = new Map();
let failures = 0;

for (const [name, path] of pages) {
  for (const vp of VIEWPORTS) {
    const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height },
      colorScheme: vp.theme, deviceScaleFactor: 1, isMobile: !!vp.mobile, hasTouch: !!vp.mobile });
    const page = await ctx.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
    page.on("console", (m) => { if (m.type() === "error") errors.push(`console: ${m.text()}`); });
    page.on("requestfailed", (r) => errors.push(`request failed: ${r.url()}`));
    const resp = await page.goto(base + path, { waitUntil: "networkidle" });
    await page.evaluate(() => document.fonts.ready);
    // lazy images: scroll through so every one is requested, then come back
    await page.evaluate(async () => { for (let y = 0; y < document.body.scrollHeight; y += 700) { window.scrollTo({ top: y, behavior: "instant" }); await new Promise((r) => setTimeout(r, 40)); } window.scrollTo({ top: 0, behavior: "instant" }); });
    // diagrams render one after another; wait until every one has finished or failed
    await page.waitForFunction(() => [...document.querySelectorAll("pre.mermaid")].every((d) =>
      d.getAttribute("data-processed") === "true" || d.classList.contains("diagram-failed")), null, { timeout: 30000 }).catch(() => {});
    await page.evaluate(() => Promise.all([...document.images].map((i) => { i.loading = "eager"; return i.decode().catch(() => {}); })));
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(150);

    const r = await page.evaluate(audit);
    const problems = [...errors.filter((e) => !(name === "not-found" && e.includes("404"))), ...r.problems];
    const status = resp.status();
    if (name === "not-found" ? status !== 404 : status !== 200) problems.push(`HTTP ${status}`);
    if (r.h1 !== 1) problems.push(`${r.h1} h1 elements`);
    const theme = await page.evaluate(() => document.documentElement.getAttribute("data-theme"));
    if (theme !== vp.theme) problems.push(`theme is ${theme}, expected ${vp.theme}`);
    if (vp.mobile) for (const s of await page.evaluate(tapTargets)) problems.push(`tap target too small: ${s}`);

    // the page sets scroll-behavior: smooth, so return to the top instantly and prove it before the fold shot
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
    if (await page.evaluate(() => window.scrollY) !== 0) problems.push("could not return to the top for the fold screenshot");
    const tag = `${name}--${vp.width}-${vp.theme}`;
    await page.screenshot({ path: join(SHOTS, `${tag}.png`), fullPage: true });
    await page.screenshot({ path: join(SHOTS, `${tag}--fold.png`), fullPage: false });

    // the mobile menu, once per page at phone width
    if (vp.mobile && vp.theme === "light") {
      await page.click("[data-nav-toggle]");
      const open = await page.evaluate(() => document.getElementById("site-nav")?.classList.contains("is-open"));
      if (!open) problems.push("mobile menu did not open");
      await page.screenshot({ path: join(SHOTS, `${name}--${vp.width}-menu.png`) });
      await page.keyboard.press("Escape");
      const closed = await page.evaluate(() => !document.getElementById("site-nav")?.classList.contains("is-open"));
      if (!closed) problems.push("mobile menu did not close on Escape");
    }
    for (const l of r.links) if (!linkStatus.has(l.split("#")[0])) linkStatus.set(l.split("#")[0], null);

    results.push({ page: name, path, ...vp, status, problems, contrastChecked: r.contrastChecked, minFont: r.minFont });
    failures += problems.length ? 1 : 0;
    console.log(`${problems.length ? "FAIL" : "ok  "} ${tag}${problems.length ? "\n      " + problems.join("\n      ") : ""}`);
    await ctx.close();
  }
}

// every internal link on every page resolves
const broken = [];
for (const url of linkStatus.keys()) {
  const res = await fetch(url);
  if (res.status !== 200) broken.push(`${res.status} ${url}`);
}
if (broken.length) { failures++; console.log("FAIL links\n      " + broken.join("\n      ")); }
else console.log(`ok   ${linkStatus.size} internal links resolve`);

// theme switch persists across navigation
{
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: "light" });
  const page = await ctx.newPage();
  await page.goto(base + "/");
  await page.click('[data-theme-choice-btn="dark"]');
  await page.goto(base + "/tour/");
  const t = await page.evaluate(() => document.documentElement.getAttribute("data-theme"));
  console.log(`${t === "dark" ? "ok  " : "FAIL"} theme choice persists across pages (${t})`);
  if (t !== "dark") failures++;
  await ctx.close();
}

await browser.close();
server.close();
await writeFile(join(HERE, "report.json"), JSON.stringify({ base: "site/dist", failures, broken, results }, null, 2));
console.log(`\n${results.length} page views, ${failures} failing`);
process.exit(failures ? 1 : 0);
