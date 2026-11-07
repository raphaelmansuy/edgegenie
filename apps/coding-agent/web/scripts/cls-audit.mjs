/** Cumulative Layout Shift audit.
 *
 *   APP_URL=http://127.0.0.1:8040 node scripts/cls-audit.mjs
 *
 * CLS is the share of the viewport that visibly moves without a user input. It is measured here
 * with a PerformanceObserver on `layout-shift`, wired in with `addInitScript` so it is installed
 * before the first byte of the document — an observer added after load misses the shifts that
 * matter most (the ones during startup).
 *
 * Thresholds are the Core Web Vitals ones: 0.1 is "needs improvement", 0.25 is "poor". The target
 * here is 0, because an IDE-class shell has no excuse for reflowing: every zone has a known width
 * and nothing above it is asynchronous.
 *
 * Each scenario is measured in a fresh context with an empty cache, because a warm cache hides
 * startup shift, which is exactly the shift worth finding.
 */
import { chromium } from "playwright";
import { readFileSync } from "node:fs";

const APP = process.env.APP_URL ?? "http://127.0.0.1:8040";
const bearer = process.env.BEARER_FILE ? readFileSync(process.env.BEARER_FILE, "utf8").trim() : "";

const COLLECTOR = `
  window.__cls = { value: 0, entries: [] };
  try {
    new PerformanceObserver((list) => {
      for (const e of list.getEntries()) {
        // A shift right after an input is the user's own doing and is excluded from CLS by
        // definition; counting it would blame the app for the user typing.
        if (e.hadRecentInput) continue;
        window.__cls.value += e.value;
        window.__cls.entries.push({
          value: Math.round(e.value * 10000) / 10000,
          at: Math.round(e.startTime),
          sources: (e.sources || []).map((s) => ({
            node: s.node ? (s.node.nodeName || "?").toLowerCase() +
              (s.node.className ? "." + String(s.node.className).split(" ").filter(Boolean).slice(0, 2).join(".") : "") : "?",
            moved: s.previousRect && s.currentRect
              ? { dx: Math.round(s.currentRect.x - s.previousRect.x),
                  dy: Math.round(s.currentRect.y - s.previousRect.y),
                  dw: Math.round(s.currentRect.width - s.previousRect.width),
                  dh: Math.round(s.currentRect.height - s.previousRect.height) }
              : null,
          })),
        });
      }
    }).observe({ type: "layout-shift", buffered: true });
  } catch {}
`;

const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || undefined });
const results = [];

async function measure(name, width, body, opts = {}) {
  const context = await browser.newContext({
    viewport: { width, height: 900 },
    colorScheme: opts.scheme ?? "light",
    ...(bearer ? { extraHTTPHeaders: { Authorization: `Bearer ${bearer}` } } : {}),
  });
  const page = await context.newPage();
  await page.addInitScript(COLLECTOR);
  await page.goto(APP, { waitUntil: "load" });
  // Let startup settle, then act. 2.5s is longer than any of our fetches on a warm backend and
  // gives the observer a clean window to blame the right frame.
  await page.waitForTimeout(2500);
  if (body) await body(page);
  await page.waitForTimeout(1200);
  const r = await page.evaluate(() => ({
    cls: Math.round(window.__cls.value * 10000) / 10000,
    entries: window.__cls.entries,
  }));
  results.push({ name, width, ...r });
  await context.close();
}

const openFirstSession = async (p) => {
  const row = p.locator(".rail-item").first();
  if (await row.count()) {
    await row.click();
    await p.locator(".pane.inspector, .transcript").first().waitFor({ timeout: 20000 }).catch(() => {});
  }
};

await measure("home", 1440);
await measure("home-dark", 1440, null, { scheme: "dark" });
await measure("home-narrow", 760);
await measure("session", 1440, openFirstSession);
await measure("session-dark", 1440, openFirstSession, { scheme: "dark" });
await measure("files-tab", 1440, async (p) => {
  await p.getByRole("tab", { name: /Files/i }).click();
  await p.waitForTimeout(800);
});
await measure("catalog-tab", 1440, async (p) => {
  await p.getByRole("tab", { name: /Catalog/i }).click();
  await p.waitForTimeout(800);
});
await measure("palette", 1440, async (p) => {
  await p.keyboard.press("Meta+k");
  await p.locator(".palette").waitFor({ timeout: 8000 }).catch(() => {});
});
await measure("hide-rail", 1440, async (p) => {
  // A deliberate layout change is still a shift; it must be one clean jump, not three.
  await p.keyboard.press("Meta+b");
  await p.waitForTimeout(700);
});

await browser.close();

const BUDGET = 0;
let failed = 0;
console.log("\nscenario            width   CLS     verdict");
console.log("-".repeat(52));
for (const r of results) {
  const ok = r.cls <= BUDGET;
  if (!ok) failed += 1;
  console.log(
    `${r.name.padEnd(19)} ${String(r.width).padEnd(7)} ${r.cls.toFixed(4).padEnd(7)} ${ok ? "ok" : "SHIFT"}`,
  );
  if (!ok) {
    for (const e of r.entries) {
      console.log(`    +${e.value} at ${e.at}ms`);
      for (const s of e.sources) {
        const m = s.moved;
        console.log(`      ${s.node}${m ? `  dx${m.dx} dy${m.dy} dw${m.dw} dh${m.dh}` : ""}`);
      }
    }
  }
}
console.log(`\nworst: ${Math.max(...results.map((r) => r.cls)).toFixed(4)}  (budget ${BUDGET})`);
process.exit(failed ? 1 : 0);
