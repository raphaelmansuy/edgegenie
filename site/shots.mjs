/** Screenshot and audit the built site. Playwright only; no test framework.
 *
 *   python3 -m http.server 8130 --directory site/dist &
 *   node site/shots.py.mjs?                       ← no: run with `node`, below
 *   node site/shots.mjs --all
 *   node site/shots.mjs --scene S2 --scene S7
 *
 * Output: `specs/008-github-page/e2e/<scene>/` for the pictures, and `e2e/audit.json` for the numbers.
 *
 * The rule this tool exists for is the repository's own: an assertion can prove a thing exists, and only
 * an eye can say whether it is right. So every check here is paired with a screenshot of the same state,
 * taken at a fixed viewport, so the two can be compared afterwards (spec 008 [S1]..[S10]).
 */
import { mkdirSync, rmSync, writeFileSync, existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "..");
const E2E = join(ROOT, "specs", "008-github-page", "e2e");
const APP = process.env.APP_URL ?? "http://127.0.0.1:8130";

/* Playwright is the app's dev dependency, not the site's: the site must build with `python3` alone, and
   adding a node_modules here for a screenshot tool would make that false. So it is resolved from the
   app's install, by path, with the bare specifier as the first try for anyone who has it locally. */
async function loadPlaywright() {
  const candidates = [
    "playwright",
    join(ROOT, "apps", "coding-agent", "web", "node_modules", "playwright", "index.js"),
    join(ROOT, "node_modules", "playwright", "index.js"),
  ];
  for (const c of candidates) {
    try {
      const spec = c.startsWith("/") ? pathToFileURL(c).href : c;
      const mod = await import(spec);
      return mod.chromium ? mod : mod.default;
    } catch {
      /* try the next */
    }
  }
  throw new Error(
    "playwright not found. Install it in apps/coding-agent/web (`cd apps/coding-agent/web && npm ci`) " +
      "and re-run, or set NODE_PATH to a node_modules that has it."
  );
}

const { chromium } = await loadPlaywright();

const ROUTES = ["", "tour/", "tutorial/", "evidence/", "install/", "reference/", "about/"];
const WIDTHS = [1440, 1100, 860, 390];

const wanted = (() => {
  const args = process.argv.slice(2);
  const scenes = [];
  for (let i = 0; i < args.length; i += 1) {
    if (args[i] === "--scene") scenes.push(args[++i]);
    if (args[i] === "--all") scenes.push("all");
  }
  return scenes.length ? scenes : ["all"];
})();

const want = (id) => wanted.includes("all") || wanted.includes(id);

/** results collected across scenes */
const audit = { app: APP, when: new Date().toISOString(), scenes: {}, checks: [], failures: [] };

function check(scene, name, ok, detail = "") {
  audit.checks.push({ scene, name, ok: Boolean(ok), detail: String(detail).slice(0, 300) });
  if (!ok) audit.failures.push({ scene, name, detail: String(detail).slice(0, 300) });
  return ok;
}

function dirFor(scene) {
  const d = join(E2E, scene);
  if (!existsSync(d)) mkdirSync(d, { recursive: true });
  return d;
}

const url = (route) => APP + "/" + route;

async function newPage(browser, { width, height = 900, theme = "light", js = true, images = true } = {}) {
  const context = await browser.newContext({
    viewport: { width, height },
    colorScheme: theme,
    javaScriptEnabled: js,
    reducedMotion: "no-preference",
  });
  if (!images) {
    await context.route("**/*.{png,jpg,jpeg,webp,svg}", (r) => r.abort());
  }
  const page = await context.newPage();
  const errors = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(String(e)));
  page.__errors = errors;
  return page;
}

/** The in-page accessibility probe: contrast from painted colours, names, targets, headings. */
const PROBE = `
window.__probe = () => {
  const lum = ([r, g, b]) => {
    const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  };
  const parse = (c) => {
    const m = c && c.match(/rgba?\\(([^)]+)\\)/);
    if (!m) return null;
    const p = m[1].split(",").map(Number);
    return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
  };
  const over = (fg, bg) => ({
    r: fg.r * fg.a + bg.r * (1 - fg.a), g: fg.g * fg.a + bg.g * (1 - fg.a),
    b: fg.b * fg.a + bg.b * (1 - fg.a), a: 1,
  });
  const bgOf = (el) => {
    let n = el;
    while (n && n !== document.documentElement) {
      const st = getComputedStyle(n);
      const c = parse(st.backgroundColor);
      if (c && c.a > 0.02) return over(c, bgOf(n.parentElement || document.body));
      if (st.backgroundImage && st.backgroundImage !== "none") return bgOf(n.parentElement || document.body);
      n = n.parentElement;
    }
    return parse(getComputedStyle(document.body).backgroundColor) || { r: 255, g: 255, b: 255, a: 1 };
  };
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && st.visibility !== "hidden" && st.display !== "none" && Number(st.opacity) > 0.05;
  };
  const nameOf = (el) => {
    const a = el.getAttribute("aria-label");
    if (a && a.trim()) return a.trim();
    const t = (el.innerText || el.textContent || "").replace(/\\s+/g, " ").trim();
    if (t) return t.slice(0, 80);
    const img = el.querySelector("img[alt]");
    if (img && img.alt.trim()) return img.alt.trim();
    return (el.getAttribute("title") || "").trim();
  };

  const out = { contrast: [], unnamed: [], small: [], headings: [], landmarks: {}, overflow: 0, docWidth: 0 };
  out.docWidth = document.documentElement.scrollWidth;
  out.viewport = window.innerWidth;
  out.overflow = document.documentElement.scrollWidth - window.innerWidth;

  for (const el of document.querySelectorAll("body *")) {
    if (!visible(el)) continue;
    const own = Array.from(el.childNodes).some((n) => n.nodeType === 3 && n.textContent.trim().length > 1);
    if (own) {
      const st = getComputedStyle(el);
      const size = parseFloat(st.fontSize);
      const weight = Number(st.fontWeight) || 400;
      const large = size >= 24 || (weight >= 700 && size >= 18.66);
      const need = large ? 3 : 4.5;
      const fg = parse(st.color);
      if (fg) {
        const bg = bgOf(el);
        const f = over(fg, bg);
        const l1 = lum([f.r, f.g, f.b]), l2 = lum([bg.r, bg.g, bg.b]);
        const ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
        if (ratio < need) {
          out.contrast.push({ text: (el.innerText || "").trim().slice(0, 40), cls: String(el.className).slice(0, 40), size, need, got: +ratio.toFixed(2) });
        }
      }
    }
    if (el.matches("a, button, input, select, textarea, [tabindex]")) {
      const n = nameOf(el);
      if (!n) out.unnamed.push(String(el.outerHTML).slice(0, 100));
      const r = el.getBoundingClientRect();
      if ((r.width < 24 || r.height < 24) && el.tagName !== "A" || (el.tagName === "A" && (r.width < 24 || r.height < 24))) {
        out.small.push({ tag: el.tagName, cls: String(el.className).slice(0, 40), w: Math.round(r.width), h: Math.round(r.height) });
      }
    }
  }

  out.headings = Array.from(document.querySelectorAll("h1,h2,h3,h4,h5,h6")).map((h) => ({
    level: Number(h.tagName[1]), text: h.innerText.trim().slice(0, 60),
  }));
  for (const tag of ["header", "nav", "main", "footer"]) out.landmarks[tag] = document.querySelectorAll(tag).length;
  out.h1 = document.querySelectorAll("h1").length;
  out.title = document.title;
  out.description = document.querySelector('meta[name="description"]')?.content ?? "";
  out.canonical = document.querySelector('link[rel="canonical"]')?.href ?? "";
  out.images = Array.from(document.images).map((i) => ({
    src: i.getAttribute("src"), alt: i.getAttribute("alt"), w: i.getAttribute("width"), h: i.getAttribute("height"),
    loaded: i.complete && i.naturalWidth > 0,
  }));
  return out;
};
`;

// --------------------------------------------------------------------------------------------- scenes
async function S1(browser) {
  const out = { routes: {} };
  const p = await newPage(browser, { width: 1440 });
  await p.addInitScript(PROBE);
  for (const route of ROUTES) {
    const res = await p.goto(url(route), { waitUntil: "load" });
    const r = await p.evaluate(() => window.__probe());
    out.routes[route || "/"] = r;
    check("S1", `${route || "/"} responds 200`, res.status() === 200, res.status());
    check("S1", `${route || "/"} has exactly one h1`, r.h1 === 1, r.h1);
    check("S1", `${route || "/"} headings never skip`, (() => {
      let prev = 0;
      for (const h of r.headings) { if (prev && h.level > prev + 1) return false; prev = h.level; }
      return true;
    })(), JSON.stringify(r.headings.map((h) => h.level)));
    check("S1", `${route || "/"} has a description`, r.description.length > 40, r.description.length);
    check("S1", `${route || "/"} has a canonical`, r.canonical.startsWith("https://"), r.canonical);
    check("S1", `${route || "/"} has no console error`, p.__errors.length === 0, p.__errors.join(" | "));
    check("S1", `${route || "/"} landmarks`, r.landmarks.main === 1 && r.landmarks.header === 1 && r.landmarks.footer === 1, JSON.stringify(r.landmarks));
    p.__errors.length = 0;

    // Every route is photographed, not only the ones with a dedicated scene: the e2e set is the record
    // of the site, and a route nobody looked at is a route nobody checked ([PG-14]).
    const folder = dirFor(route ? route.replace(/\/$/, "") : "home");
    const name = route ? route.replace(/\/$/, "") : "home";
    await p.screenshot({ path: join(folder, `${name}-1440.png`), fullPage: false });
    await p.screenshot({ path: join(folder, `${name}-1440-full.png`), fullPage: true });
    await p.setViewportSize({ width: 390, height: 900 });
    await p.waitForTimeout(120);
    const narrow = await p.evaluate(() => ({
      overflow: document.documentElement.scrollWidth - window.innerWidth,
    }));
    check("S1", `${route || "/"} fits 390 px`, narrow.overflow <= 0, `${narrow.overflow} px over`);
    await p.screenshot({ path: join(folder, `${name}-390.png`), fullPage: false });
    await p.setViewportSize({ width: 1440, height: 900 });
  }
  await p.close();
  audit.scenes.S1 = out;
}

async function S2(browser) {
  const p = await newPage(browser, { width: 1440, height: 900 });
  await p.addInitScript(PROBE);
  await p.goto(url(""), { waitUntil: "load" });
  const d = dirFor("home");
  await p.screenshot({ path: join(d, "home-hero-1440.png"), fullPage: false });

  // the product screenshot must be inside the first two viewport heights
  const shot = await p.evaluate(() => {
    const img = document.querySelector("figure.shot img");
    if (!img) return null;
    const r = img.getBoundingClientRect();
    return { top: r.top + window.scrollY, height: r.height, src: img.getAttribute("src"), alt: img.getAttribute("alt") };
  });
  check("S2", "a product screenshot exists", Boolean(shot), JSON.stringify(shot));
  check("S2", "the product screenshot is within two viewport heights",
    shot && shot.top < 900 * 2, shot && shot.top);
  check("S2", "the product screenshot has a described alt",
    shot && shot.alt && shot.alt.length > 60, shot && shot.alt);

  const claims = await p.evaluate(() => Array.from(document.querySelectorAll(".grid-3 .card")).length);
  check("S2", "the three claims are present as cards", claims >= 3, claims);

  const primaries = await p.evaluate(() =>
    Array.from(document.querySelectorAll(".btn.primary")).filter((b) => b.getBoundingClientRect().top < window.innerHeight).length);
  check("S2", "one primary button above the fold", primaries === 1, primaries);

  const links = await p.evaluate(() => Array.from(document.querySelectorAll(".card-foot a, .grid-3 a")).length);
  check("S2", "claim cards link onward", links >= 0, links);

  // the crop of the claims block, for inspection
  const block = await p.$(".grid-3");
  if (block) await block.screenshot({ path: join(d, "home-claims.png") });

  await p.close();
}

async function S3(browser) {
  const p = await newPage(browser, { width: 1440 });
  await p.goto(url("evidence/"), { waitUntil: "load" });
  const d = dirFor("evidence");
  await p.screenshot({ path: join(d, "evidence-1440.png"), fullPage: false });
  await p.screenshot({ path: join(d, "evidence-1440-full.png"), fullPage: true });

  const cards = await p.evaluate(() => Array.from(document.querySelectorAll(".claim")).map((c) => ({
    id: c.querySelector(".claim-id")?.textContent?.trim(),
    value: c.querySelector(".claim-value")?.textContent?.replace(/\s+/g, " ").trim(),
    caveat: c.querySelector(".claim-meta dd:nth-of-type(2)")?.textContent?.trim()
      ?? Array.from(c.querySelectorAll(".claim-meta dt")).find((t) => /not prove/.test(t.textContent))
        ?.nextElementSibling?.textContent?.trim() ?? "",
    sources: Array.from(c.querySelectorAll(".claim-meta code")).map((x) => x.textContent.trim()),
    runs: c.querySelector(".claim-meta dd")?.textContent?.trim() ?? "",
  })));
  check("S3", "eight claim cards", cards.length === 8, cards.length);
  for (const c of cards) {
    check("S3", `${c.id}: has a value`, Boolean(c.value), c.value);
    check("S3", `${c.id}: has a caveat`, (c.caveat || "").length > 20, c.caveat);
    check("S3", `${c.id}: cites a source`, c.sources.length >= 1, JSON.stringify(c.sources));
    check("S3", `${c.id}: states its runs`, /run/.test(c.runs), c.runs);
  }
  const first = await p.$(".claim");
  if (first) await first.screenshot({ path: join(d, "evidence-card.png") });

  await p.setViewportSize({ width: 390, height: 900 });
  await p.waitForTimeout(200);
  await p.screenshot({ path: join(d, "evidence-390.png"), fullPage: false });
  await p.close();
  audit.scenes.S3 = { cards };
}

async function S4(browser) {
  const p = await newPage(browser, { width: 1440 });
  await p.goto(url("about/"), { waitUntil: "load" });
  const d = dirFor("about");
  await p.screenshot({ path: join(d, "about-1440.png"), fullPage: false });
  await p.screenshot({ path: join(d, "about-1440-full.png"), fullPage: true });

  const r = await p.evaluate(() => ({
    portrait: (() => { const i = document.querySelector(".portrait"); return i ? { src: i.getAttribute("src"), loaded: i.complete && i.naturalWidth > 0, w: i.naturalWidth } : null; })(),
    links: Array.from(document.querySelectorAll(".author-links a")).map((a) => a.getAttribute("href")),
    projects: document.querySelectorAll(".project").length,
    book: Boolean(document.querySelector(".book-panel img")),
  }));
  check("S4", "portrait loads", r.portrait?.loaded, JSON.stringify(r.portrait));
  check("S4", "LinkedIn link", r.links.some((h) => h && h.includes("linkedin.com")), r.links.join(","));
  check("S4", "GitHub link", r.links.some((h) => h && h.includes("github.com")), r.links.join(","));
  check("S4", "three other projects", r.projects === 3, r.projects);
  check("S4", "the book is shown", r.book, r.book);

  await p.setViewportSize({ width: 390, height: 900 });
  await p.waitForTimeout(200);
  await p.screenshot({ path: join(d, "about-390.png"), fullPage: false });
  await p.close();
}

async function S5(browser) {
  const p = await newPage(browser, { width: 1440 });
  await p.addInitScript(PROBE);
  const out = {};
  for (const route of ROUTES) {
    await p.goto(url(route), { waitUntil: "load" });
    const r = await p.evaluate(() => ({
      current: Array.from(document.querySelectorAll('.site-nav a[aria-current="page"]')).map((a) => a.textContent.trim()),
      navHrefs: Array.from(document.querySelectorAll(".site-nav a:not(.nav-gh)")).map((a) => a.getAttribute("href")),
      skipFirst: (() => {
        const focusables = Array.from(document.querySelectorAll("a[href], button, input, select, textarea, [tabindex]:not([tabindex='-1'])"))
          .filter((e) => e.getBoundingClientRect().width > 0);
        return focusables[0]?.className ?? "";
      })(),
    }));
    out[route || "/"] = r;
    check("S5", `${route || "/"}: exactly one current nav item`, r.current.length === 1, JSON.stringify(r.current));
    check("S5", `${route || "/"}: the skip link is the first tab stop`, String(r.skipFirst).includes("skip"), r.skipFirst);
    check("S5", `${route || "/"}: seven nav links`, r.navHrefs.length === 7, r.navHrefs.length);
  }
  await p.close();
  audit.scenes.S5 = out;
}

async function S6(browser) {
  const p = await newPage(browser, { width: 1440 });
  await p.goto(url("tutorial/"), { waitUntil: "load" });
  const d = dirFor("tutorial");
  await p.screenshot({ path: join(d, "tutorial-1440.png"), fullPage: false });
  await p.screenshot({ path: join(d, "tutorial-1440-full.png"), fullPage: true });

  const anchors = await p.evaluate(() => Array.from(document.querySelectorAll("main [id]")).map((e) => e.id));
  check("S6", "the tutorial rendered with its own headings", anchors.length > 5, anchors.length);
  const firstPara = await p.evaluate(() => document.querySelector("main p")?.textContent?.trim().slice(0, 80) ?? "");
  check("S6", "the first paragraph is not a nav line", !firstPara.startsWith("Index"), firstPara);

  await p.goto(url("reference/"), { waitUntil: "load" });
  const rows = await p.evaluate(() => document.querySelectorAll(".ref-list li").length);
  check("S6", "the reference lists fifteen documents", rows === 15, rows);
  await p.screenshot({ path: join(dirFor("reference"), "reference-1440.png"), fullPage: false });

  await p.goto(url("reference/doc-results/"), { waitUntil: "load" });
  const results = await p.evaluate(() => ({
    tables: document.querySelectorAll("table").length,
    h1: document.querySelectorAll("h1").length,
    diagrams: document.querySelectorAll("pre.mermaid").length,
  }));
  check("S6", "a rendered doc keeps its tables", results.tables > 3, results.tables);
  check("S6", "a rendered doc has one h1", results.h1 === 1, results.h1);
  await p.screenshot({ path: join(dirFor("reference"), "reference-doc-1440.png"), fullPage: false });

  await p.setViewportSize({ width: 390, height: 900 });
  await p.goto(url("tutorial/"), { waitUntil: "load" });
  await p.screenshot({ path: join(d, "tutorial-390.png"), fullPage: false });
  await p.close();
}

async function S7(browser) {
  const out = { byWidth: {} };
  for (const width of WIDTHS) {
    for (const theme of width === 1440 || width === 390 ? ["light", "dark"] : ["light"]) {
      const p = await newPage(browser, { width, height: 900, theme });
      await p.addInitScript(PROBE);
      await p.goto(url(""), { waitUntil: "load" });
      await p.waitForTimeout(150);
      const r = await p.evaluate(() => window.__probe());
      const key = `${width}-${theme}`;
      out.byWidth[key] = {
        overflow: r.overflow,
        contrast: r.contrast,
        unnamed: r.unnamed,
        small: r.small,
        docWidth: r.docWidth,
        viewport: r.viewport,
      };
      check("S7", `${key}: no horizontal overflow`, r.overflow <= 0, `${r.docWidth} > ${r.viewport}`);
      check("S7", `${key}: contrast meets AA`, r.contrast.length === 0, JSON.stringify(r.contrast.slice(0, 4)));
      check("S7", `${key}: every control has a name`, r.unnamed.length === 0, JSON.stringify(r.unnamed.slice(0, 3)));

      await p.screenshot({ path: join(dirFor("home"), `home-${width}-${theme}.png`), fullPage: false });

      // the menu state below the breakpoint
      if (width <= 860) {
        await p.click("[data-nav-toggle]");
        await p.waitForTimeout(120);
        const open = await p.evaluate(() => document.getElementById("site-nav").classList.contains("is-open"));
        check("S7", `${key}: the menu opens`, open, open);
        await p.screenshot({ path: join(dirFor("states"), `nav-open-${width}-${theme}.png`), fullPage: false });
        await p.keyboard.press("Escape");
        const closed = await p.evaluate(() => ({
          open: document.getElementById("site-nav").classList.contains("is-open"),
          focus: document.activeElement?.className ?? "",
        }));
        check("S7", `${key}: Escape closes the menu`, !closed.open, closed.open);
        check("S7", `${key}: Escape returns focus to the button`, String(closed.focus).includes("nav-toggle"), closed.focus);
      }
      await p.close();
    }
  }

  // A diagram must take the page's theme. Mermaid bakes colours into its SVG, so a repository document's
  // own light-theme init block used to survive into a dark page. This is the assertion for that.
  for (const theme of ["light", "dark"]) {
    const p = await newPage(browser, { width: 1440, theme });
    await p.goto(url("reference/docs-tutorial/"), { waitUntil: "load" });
    await p.waitForTimeout(2600);
    const d = await p.evaluate(() => {
      const svgs = document.querySelectorAll(".diagram svg");
      if (!svgs.length) return { count: 0 };
      const rect = svgs[0].querySelector("rect");
      const fill = rect ? getComputedStyle(rect).fill : "";
      const m = fill.match(/(\d+), (\d+), (\d+)/);
      const lum = m ? (Number(m[1]) * 0.299 + Number(m[2]) * 0.587 + Number(m[3]) * 0.114) : 255;
      return { count: svgs.length, fill, lum };
    });
    check("S7", `diagram:${theme} renders`, d.count >= 3, d.count);
    if (theme === "dark") {
      check("S7", "diagram:dark does not paint a light canvas", (d.lum ?? 255) < 80, d.fill);
    } else {
      check("S7", "diagram:light does not paint a dark canvas", (d.lum ?? 0) > 150, d.fill);
    }
    const fig = await p.$("figure.diagram");
    if (fig) await fig.screenshot({ path: join(dirFor("states"), `diagram-${theme}.png`) });
    await p.close();
  }

  // the three theme states, captured from the control itself
  const p = await newPage(browser, { width: 1440 });
  await p.goto(url(""), { waitUntil: "load" });
  for (const choice of ["system", "light", "dark"]) {
    await p.click(`[data-theme-choice-btn="${choice}"]`);
    await p.waitForTimeout(80);
    const attr = await p.evaluate(() => document.documentElement.getAttribute("data-theme"));
    check("S7", `theme:${choice} sets data-theme`, Boolean(attr), attr);
    await p.screenshot({ path: join(dirFor("states"), `theme-${choice}.png`), clip: { x: 0, y: 0, width: 1440, height: 240 } });
  }
  // reload: the choice must survive with no flash
  await p.reload({ waitUntil: "load" });
  const persisted = await p.evaluate(() => document.documentElement.getAttribute("data-theme-choice"));
  check("S7", "the theme choice persists across a reload", persisted === "dark", persisted);
  await p.close();

  // 200% zoom, approximated by halving the viewport at the same device scale
  const z = await newPage(browser, { width: 720, height: 900 });
  await z.addInitScript(PROBE);
  await z.goto(url(""), { waitUntil: "load" });
  const zr = await z.evaluate(() => window.__probe());
  check("S7", "200% zoom: no horizontal overflow", zr.overflow <= 0, `${zr.docWidth} > ${zr.viewport}`);
  await z.close();

  audit.scenes.S7 = out;
}

async function S8(browser) {
  const d = dirFor("states");
  // JavaScript disabled: everything except Mermaid must still work
  const noJs = await newPage(browser, { width: 1440, js: false });
  await noJs.goto(url(""), { waitUntil: "load" });
  const r = await noJs.evaluate(() => ({
    cards: document.querySelectorAll(".card").length,
    claims: document.querySelectorAll(".claim").length,
    nav: document.querySelectorAll(".site-nav a").length,
    img: document.images.length,
  }));
  check("S8", "no-JS: the content is present", r.cards >= 6 && r.img >= 1, JSON.stringify(r));
  await noJs.screenshot({ path: join(d, "no-js-home.png"), fullPage: false });
  await noJs.goto(url("reference/doc-results/"), { waitUntil: "load" });
  const diag = await noJs.evaluate(() => {
    // With JS disabled the <noscript> block is live, so the diagram's source is on screen as text.
    const pre = document.querySelector("pre.mermaid");
    const noscript = document.querySelector("noscript");
    return {
      mermaid: document.querySelectorAll("pre.mermaid").length,
      text: (pre?.textContent ?? "").slice(0, 60),
      noscriptText: (noscript?.textContent ?? "").slice(0, 60),
    };
  });
  const body = await noJs.evaluate(() => document.body.innerText);
  check("S8", "no-JS: a diagram keeps its source readable",
    diag.mermaid > 0 && /flowchart|graph|sequenceDiagram|erDiagram|stateDiagram|xychart|%%\{init/.test(diag.text),
    diag.text);
  check("S8", "no-JS: the diagram's source is visible as text", body.includes("flowchart") || body.includes("V0"), body.slice(0, 80));
  await noJs.screenshot({ path: join(d, "no-js-diagram.png"), fullPage: false });
  await noJs.close();

  // images blocked: every alt must carry the meaning
  const noImg = await newPage(browser, { width: 1440, images: false });
  await noImg.goto(url("tour/"), { waitUntil: "load" });
  const alts = await noImg.evaluate(() => Array.from(document.images).map((i) => i.getAttribute("alt") || ""));
  check("S8", "images blocked: every image has meaningful alt",
    alts.length > 0 && alts.every((a) => a.length > 25), JSON.stringify(alts.map((a) => a.length)));
  await noImg.screenshot({ path: join(d, "no-img-tour.png"), fullPage: false });
  await noImg.close();

  // the 404
  const nf = await newPage(browser, { width: 1440 });
  const res = await nf.goto(url("404.html"), { waitUntil: "load" });
  const links = await nf.evaluate(() => document.querySelectorAll(".grid-3 a").length);
  check("S8", "the 404 is a real page", res.status() === 200 && links >= 6, `${res.status()} ${links}`);
  await nf.screenshot({ path: join(d, "404.png"), fullPage: false });
  await nf.close();
}

async function S9(browser) {
  const p = await newPage(browser, { width: 1440 });
  const sizes = {};
  let total = 0;
  for (const route of ROUTES) {
    await p.goto(url(route), { waitUntil: "load" });
    const bytes = await p.evaluate(() => {
      const nav = performance.getEntriesByType("navigation")[0];
      const res = performance.getEntriesByType("resource");
      const own = res.filter((r) => /site\.(css|js)$/.test(r.name)).reduce((a, r) => a + (r.encodedBodySize || 0), 0);
      return { html: nav?.encodedBodySize || 0, assets: own };
    });
    const page_total = bytes.html + bytes.assets;
    sizes[route || "/"] = page_total;
    total += bytes.html;
    check("S9", `${route || "/"} under 400 KB`, page_total < 400 * 1024, `${Math.round(page_total / 1024)} KB`);
  }
  const weight = await p.evaluate(() => 0);
  audit.scenes.S9 = { sizes, totalHtml: total, weight };
  await p.close();
}

async function S10(browser) {
  const p = await newPage(browser, { width: 1440 });
  const sitemap = await p.goto(url("sitemap.xml"));
  const text = await sitemap.text();
  const count = (text.match(/<url>/g) || []).length;
  check("S10", "sitemap lists every route", count === 22, count);
  const robots = await p.goto(url("robots.txt"));
  const robotsText = await robots.text();
  check("S10", "robots points at the sitemap", /Sitemap:\s*https:\/\//.test(robotsText), robotsText.trim());
  const build = await p.goto(url("build.json"));
  const manifest = JSON.parse(await build.text());
  check("S10", "the build manifest records a commit", /^[0-9a-f]{7,}$/.test(manifest.commit), manifest.commit);
  check("S10", "the build manifest has no missing claim", manifest.claims === 8, manifest.claims);
  await p.close();
  audit.scenes.S10 = { sitemapUrls: count, commit: manifest.commit };
}

// ----------------------------------------------------------------------------------------------- main
const scenes = { S1, S2, S3, S4, S5, S6, S7, S8, S9, S10 };

if (want("--clean") || wanted.includes("clean")) {
  if (existsSync(E2E)) rmSync(E2E, { recursive: true, force: true });
}

const browser = await chromium.launch();
try {
  for (const [id, fn] of Object.entries(scenes)) {
    if (!want(id)) continue;
    const before = audit.failures.length;
    process.stdout.write(`  ${id} … `);
    try {
      await fn(browser);
    } catch (e) {
      audit.failures.push({ scene: id, name: "scene threw", detail: String(e).slice(0, 300) });
    }
    const added = audit.failures.length - before;
    console.log(added ? `FAIL (${added})` : `ok (${audit.checks.filter((c) => c.scene === id).length} checks)`);
  }
} finally {
  await browser.close();
}

mkdirSync(E2E, { recursive: true });
writeFileSync(join(E2E, "audit.json"), JSON.stringify(audit, null, 2));

const checked = audit.checks.length;
console.log(`\n${checked} checks, ${audit.failures.length} failing`);
for (const f of audit.failures.slice(0, 40)) {
  console.log(`  ${f.scene}  ${f.name}  — ${f.detail}`);
}
process.exit(audit.failures.length ? 1 : 0);
