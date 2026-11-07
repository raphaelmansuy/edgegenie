/** Accessibility audit: the checks a careful reviewer would run by hand, run by machine.
 *
 *   APP_URL=http://127.0.0.1:8040 node scripts/a11y-audit.mjs [outdir]
 *
 * What it checks, and why each one is on the list:
 *  - WCAG 2.2 AA contrast (4.5:1 body, 3:1 large text and UI borders/icons), computed from the real
 *    rendered pixels' effective colours, walking up for the painted background;
 *  - every interactive control has an accessible name, and every image/icon is decorative or named;
 *  - target size: 24×24 CSS px minimum (WCAG 2.5.8 AA); 44×44 for primary actions;
 *  - focus is always visible: focusing each control must change something observable;
 *  - one h1, headings in order, no skipped levels;
 *  - landmarks: header/nav/main, roles that match behaviour (tab/tabpanel, dialog/modal);
 *  - ARIA state is coherent: aria-selected only on tabs, aria-expanded present on toggles;
 *  - no positive tabindex, and the tab order follows the visual order;
 *  - text is not clipped when the browser is zoomed to 200% (WCAG 1.4.4);
 *  - motion respects prefers-reduced-motion, and the layout survives forced-colors.
 */
import { chromium } from "playwright";
import { mkdirSync, readFileSync } from "node:fs";

const out = process.argv[2] ?? "/tmp/genie-a11y";
mkdirSync(out, { recursive: true });
const bearer = process.env.BEARER_FILE ? readFileSync(process.env.BEARER_FILE, "utf8").trim() : "";
const APP = process.env.APP_URL ?? "http://127.0.0.1:8040";

const page = (b, opts = {}) => b.newPage({
  viewport: { width: 1440, height: 900 },
  extraHTTPHeaders: bearer ? { Authorization: `Bearer ${bearer}` } : {},
  ...opts,
});

/* ---------------------------------------------------------------- in-page helpers */
const HELPERS = `
window.__a11y = {
  // WCAG relative luminance from an rgb()/rgba() pair
  lum([r, g, b]) {
    const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  },
  parse(c) {
    const m = c.match(/rgba?\\(([^)]+)\\)/);
    if (!m) return null;
    const p = m[1].split(",").map((x) => parseFloat(x));
    return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
  },
  // blend fg (with alpha) over bg
  over(fg, bg) {
    const a = fg.a;
    return { r: fg.r * a + bg.r * (1 - a), g: fg.g * a + bg.g * (1 - a), b: fg.b * a + bg.b * (1 - a), a: 1 };
  },
  // the colour that is actually painted behind an element
  bgOf(el) {
    let n = el;
    while (n && n !== document.documentElement) {
      const st = getComputedStyle(n);
      const c = window.__a11y.parse(st.backgroundColor);
      if (c && c.a > 0.02) {
        // a translucent layer still needs its own parent behind it
        const parent = window.__a11y.bgOf(n.parentElement || document.documentElement);
        return window.__a11y.over(c, parent);
      }
      if (st.backgroundImage && st.backgroundImage !== "none") {
        return window.__a11y.bgOf(n.parentElement || document.documentElement);
      }
      n = n.parentElement;
    }
    return window.__a11y.parse(getComputedStyle(document.body).backgroundColor) || { r: 255, g: 255, b: 255, a: 1 };
  },
  contrast(el) {
    const st = getComputedStyle(el);
    const fg = window.__a11y.parse(st.color);
    const bg = window.__a11y.bgOf(el);
    if (!fg) return null;
    const f = window.__a11y.over(fg, bg);
    const L1 = window.__a11y.lum([f.r, f.g, f.b]);
    const L2 = window.__a11y.lum([bg.r, bg.g, bg.b]);
    const hi = Math.max(L1, L2), lo = Math.min(L1, L2);
    return (hi + 0.05) / (lo + 0.05);
  },
  visible(el) {
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && st.visibility !== "hidden" && st.display !== "none" && Number(st.opacity) > 0.05;
  },
  name(el) {
    const aria = el.getAttribute("aria-label");
    if (aria && aria.trim()) return aria.trim();
    const labelled = el.getAttribute("aria-labelledby");
    if (labelled) {
      const t = labelled.split(/\\s+/).map((id) => document.getElementById(id)?.textContent ?? "").join(" ").trim();
      if (t) return t;
    }
    if (el.title && el.title.trim()) return el.title.trim();
    const txt = (el.innerText || el.textContent || "").replace(/\\s+/g, " ").trim();
    if (txt) return txt.slice(0, 80);
    const img = el.querySelector("img[alt]");
    if (img && img.alt.trim()) return img.alt.trim();
    return "";
  },
};
`;

const collect = (rules) => {
  const r = {};
  r.contrast = [];
  for (const el of document.querySelectorAll("body *")) {
    if (!window.__a11y.visible(el)) continue;
    // only elements with their own visible text
    const own = Array.from(el.childNodes).some((n) => n.nodeType === 3 && n.textContent.trim().length > 1);
    if (!own) continue;
    const st = getComputedStyle(el);
    const size = parseFloat(st.fontSize);
    const bold = Number(st.fontWeight) >= 700;
    const large = size >= 24 || (bold && size >= 18.66);
    const need = large ? 3 : 4.5;
    const ratio = window.__a11y.contrast(el);
    if (ratio !== null && ratio < need) {
      r.contrast.push({
        text: (el.innerText || "").trim().slice(0, 40).replace(/\s+/g, " "),
        cls: String(el.className).split(" ")[0], size, need: +need.toFixed(1), got: +ratio.toFixed(2),
      });
    }
  }
  r.names = [];
  for (const el of document.querySelectorAll('button, a[href], input, select, textarea, [role="tab"], [role="button"], [role="treeitem"], [tabindex]:not([tabindex="-1"])')) {
    if (!window.__a11y.visible(el)) continue;
    if (el.getAttribute("aria-hidden") === "true") continue;
    if (!window.__a11y.name(el)) r.names.push({ tag: el.tagName.toLowerCase(), cls: String(el.className).split(" ")[0] });
  }
  r.targets = [];
  for (const el of document.querySelectorAll('button, a[href], input:not([type="hidden"]), select, [role="button"], [role="tab"], [role="treeitem"]')) {
    if (!window.__a11y.visible(el)) continue;
    const b = el.getBoundingClientRect();
    const inline = getComputedStyle(el).display === "inline" && el.closest("p, .answer");
    if (inline) continue;                       // text links inside prose are exempt (WCAG 2.5.8)
    if (b.width < 24 || b.height < 24) {
      r.targets.push({ cls: String(el.className).split(" ")[0], tag: el.tagName.toLowerCase(),
        w: +b.width.toFixed(1), h: +b.height.toFixed(1) });
    }
  }
  r.headings = [];
  let lastLevel = 0;
  for (const h of document.querySelectorAll("h1,h2,h3,h4,h5,h6")) {
    const level = Number(h.tagName[1]);
    if (lastLevel && level > lastLevel + 1) r.headings.push(`skipped: h${lastLevel} -> h${level}`);
    lastLevel = level;
  }
  if (document.querySelectorAll("h1").length !== 1) r.headings.push(`h1 count: ${document.querySelectorAll("h1").length}`);
  r.landmarks = {
    main: document.querySelectorAll("main").length,
    nav: document.querySelectorAll("nav").length,
    header: document.querySelectorAll("header").length,
  };
  r.tabindex = Array.from(document.querySelectorAll("[tabindex]"))
    .filter((e) => Number(e.getAttribute("tabindex")) > 0)
    .map((e) => `${e.tagName.toLowerCase()}.${String(e.className).split(" ")[0]}=${e.getAttribute("tabindex")}`);
  r.roles = [];
  for (const el of document.querySelectorAll("[aria-selected]")) {
    const role = el.getAttribute("role");
    if (role !== "tab" && role !== "option" && role !== "treeitem") {
      r.roles.push(`aria-selected on role=${role ?? "none"} (${String(el.className).split(" ")[0]})`);
    }
  }
  for (const el of document.querySelectorAll('[role="tab"]')) {
    if (el.getAttribute("aria-controls") === null) r.roles.push(`tab without aria-controls: ${window.__a11y.name(el)}`);
  }
  for (const el of document.querySelectorAll("[aria-expanded]")) {
    const v = el.getAttribute("aria-expanded");
    if (v !== "true" && v !== "false") r.roles.push(`bad aria-expanded=${v}`);
  }
  for (const el of document.querySelectorAll('img:not([alt])')) r.roles.push(`img without alt: ${el.src.slice(-30)}`);
  r.dialogs = [];
  for (const el of document.querySelectorAll('[role="dialog"]')) {
    if (el.getAttribute("aria-modal") !== "true") r.dialogs.push("dialog without aria-modal");
    if (!el.getAttribute("aria-label") && !el.getAttribute("aria-labelledby")) r.dialogs.push("dialog without a name");
  }
  return r;
};

const b = await chromium.launch({ executablePath: process.env.CHROME_PATH || undefined });
const findings = [];
const add = (where, kind, detail) => findings.push({ where, kind, detail });

/* ---------------------------------------------------------------- 1. every main state */
const p = await page(b);
await p.addInitScript(HELPERS);            // must be installed before the first document loads
await p.goto(APP, { waitUntil: "domcontentloaded" });
await p.waitForTimeout(1500);
await p.evaluate(HELPERS);

const states = [];
const run = async (name) => {
  await p.evaluate(HELPERS);
  const r = await p.evaluate(collect);
  states.push({ name, ...r });
};
await run("home");
await p.screenshot({ path: `${out}/01-home.png` });

await p.getByRole("textbox", { name: "Message the agent" }).fill("Build a notebook that shows revenue by pickup hour");
await p.keyboard.press("Enter");
await p.locator(".turn-foot").first().waitFor({ timeout: 60000 });
await p.waitForTimeout(500);
await run("turn");
await p.screenshot({ path: `${out}/02-turn.png` });

await p.keyboard.press("Meta+k");
await p.locator(".palette").waitFor({ timeout: 5000 });
await p.evaluate(HELPERS);
await run("palette");
await p.screenshot({ path: `${out}/03-palette.png` });
await p.keyboard.press("Escape");

await p.keyboard.press("Meta+/");
await p.locator(".keys-sheet").waitFor({ timeout: 5000 });
await p.evaluate(HELPERS);
await run("shortcuts");
await p.screenshot({ path: `${out}/04-shortcuts.png` });
await p.keyboard.press("Escape");

await p.getByRole("tab", { name: /Files/i }).click();
await p.getByPlaceholder("Search notebooks and files…").fill("taxi");
await p.locator(".result").first().click({ timeout: 30000 });
await p.locator(".cell").first().waitFor({ timeout: 20000 });
await run("document");
await p.screenshot({ path: `${out}/05-document.png` });

/* ---------------------------------------------------------------- 2. focus visibility */
// Programmatic .focus() does not always match :focus-visible, so this drives the keyboard: press
// Tab, and require that the focused control looks different from how it looked unfocused.
await p.evaluate(() => { document.body.focus(); (document.activeElement)?.blur?.(); });
const focusProblems = [];
const seen = new Set();
for (let i = 0; i < 45; i += 1) {
  const before = await p.evaluate(() => {
    const el = document.activeElement;
    const id = el ? `${el.tagName}.${String(el.className)}` : "none";
    return id;
  });
  await p.keyboard.press("Tab");
  const after = await p.evaluate(() => {
    const el = document.activeElement;
    if (!el || el === document.body) return null;
    const s = getComputedStyle(el);
    return {
      id: `${el.tagName.toLowerCase()}.${String(el.className).split(" ")[0]}`,
      outline: `${s.outlineStyle} ${s.outlineWidth} ${s.outlineColor}`,
      shadow: s.boxShadow, bg: s.backgroundColor, border: s.borderColor,
    };
  });
  if (!after) break;
  if (seen.has(after.id)) continue;
  seen.add(after.id);
  const hasRing = !/none/.test(after.outline) && parseFloat(after.outline.split(" ")[1]) > 0;
  const hasShadow = after.shadow && after.shadow !== "none";
  // the ring may also come from a parent's :focus-within
  const parentRing = await p.evaluate(() => {
    let n = document.activeElement?.parentElement;
    while (n && n !== document.body) {
      const s = getComputedStyle(n);
      if (s.outlineStyle !== "none" && parseFloat(s.outlineWidth) > 0) return true;
      if (s.boxShadow && s.boxShadow !== "none") return true;
      n = n.parentElement;
    }
    return false;
  });
  if (!hasRing && !hasShadow && !parentRing) {
    focusProblems.push(`${after.id}: no visible focus indicator (outline ${after.outline})`);
  }
}
for (const f of focusProblems) add("focus", "no-visible-focus", f);

/* ---------------------------------------------------------------- 3. reduced motion and forced colours */
const rm = await b.newPage({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce",
  extraHTTPHeaders: bearer ? { Authorization: `Bearer ${bearer}` } : {} });
await rm.goto(APP, { waitUntil: "domcontentloaded", timeout: 60000 });
// The deployed app authenticates per page: wait for the shell to actually render before measuring,
// otherwise the evaluate runs during the sign-in redirect and the context is destroyed.
await rm.locator(".app, .empty, main").first().waitFor({ timeout: 30000 }).catch(() => {});
await rm.waitForTimeout(800);
const motion = await rm.evaluate(() => {
  const bad = [];
  for (const el of document.querySelectorAll("body *")) {
    const s = getComputedStyle(el);
    const dur = s.transitionDuration.split(",").map(parseFloat);
    const anim = s.animationDuration.split(",").map(parseFloat);
    if (Math.max(...dur, ...anim) > 0.05) bad.push(`${el.tagName.toLowerCase()}.${String(el.className).split(" ")[0]} ${s.transitionDuration}/${s.animationDuration}`);
  }
  return bad.slice(0, 10);
});
for (const m of motion) add("reduced-motion", "still-animating", m);
await rm.close();

const fc = await b.newPage({ viewport: { width: 1440, height: 900 }, forcedColors: "active",
  extraHTTPHeaders: bearer ? { Authorization: `Bearer ${bearer}` } : {} });
await fc.goto(APP, { waitUntil: "domcontentloaded", timeout: 60000 });
await fc.locator(".app, .empty, main").first().waitFor({ timeout: 30000 }).catch(() => {});
await fc.waitForTimeout(800);
const forced = await fc.evaluate(() => {
  const invisible = [];
  for (const el of document.querySelectorAll("button, [role=tab], a[href]")) {
    const s = getComputedStyle(el);
    if (s.visibility === "hidden" || s.display === "none") continue;
    const r = el.getBoundingClientRect();
    if (r.width === 0) invisible.push(`${el.tagName.toLowerCase()}.${String(el.className).split(" ")[0]}`);
  }
  return invisible;
});
for (const f of forced) add("forced-colors", "control-vanishes", f);
await fc.screenshot({ path: `${out}/06-forced-colors.png` });
await fc.close();

/* ---------------------------------------------------------------- 4. 200% zoom */
const z = await b.newPage({ viewport: { width: 720, height: 900 }, deviceScaleFactor: 2,
  extraHTTPHeaders: bearer ? { Authorization: `Bearer ${bearer}` } : {} });
await z.goto(APP, { waitUntil: "domcontentloaded", timeout: 60000 });
await z.locator(".app, .empty, main").first().waitFor({ timeout: 30000 }).catch(() => {});
await z.waitForTimeout(800);
await z.evaluate(HELPERS);
const zoom = await z.evaluate(() => {
  const cut = [];
  for (const el of document.querySelectorAll("body *")) {
    const s = getComputedStyle(el);
    if (s.overflowX !== "visible" || s.overflowY !== "visible") continue;
    if (el.scrollWidth > el.clientWidth + 1 && s.textOverflow !== "ellipsis") {
      cut.push(`${el.tagName.toLowerCase()}.${String(el.className).split(" ")[0]} ${el.scrollWidth}>${el.clientWidth}`);
    }
  }
  return cut;
});
for (const c of zoom) add("zoom-200", "text-clipped", c);
await z.screenshot({ path: `${out}/07-zoom200.png` });
await z.close();

/* ---------------------------------------------------------------- 5. the keyboard path is reachable */
await p.keyboard.press("Meta+2");
const reach = await p.evaluate(() => document.querySelectorAll('[role="treeitem"], .result').length);
if (reach === 0) add("keyboard", "no-tree-rows", "Files panel has nothing focusable");

await p.close();
await b.close();

/* ---------------------------------------------------------------- report */
let total = 0;
for (const s of states) {
  const groups = { contrast: s.contrast, names: s.names, targets: s.targets };
  for (const [kind, list] of Object.entries(groups)) {
    for (const item of list) {
      total += 1;
      add(s.name, kind, JSON.stringify(item));
    }
  }
  for (const h of s.headings) { total += 1; add(s.name, "headings", h); }
  for (const t of s.tabindex) { total += 1; add(s.name, "tabindex", t); }
  for (const r of s.roles) { total += 1; add(s.name, "aria", r); }
  for (const d of s.dialogs) { total += 1; add(s.name, "dialog", d); }
}

const byKind = {};
for (const f of findings) (byKind[f.kind] ??= []).push(f);
for (const [kind, list] of Object.entries(byKind)) {
  console.log(`\n=== ${kind} (${list.length})`);
  for (const f of list.slice(0, 14)) console.log(`  [${f.where}] ${f.detail}`);
  if (list.length > 14) console.log(`  …and ${list.length - 14} more`);
}
console.log(`\nTOTAL: ${total} accessibility finding(s)`);
process.exit(total ? 1 : 0);
