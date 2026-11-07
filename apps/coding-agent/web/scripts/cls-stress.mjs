/** CLS under conditions that actually break layouts.
 *
 * The plain audit runs a warm local server. Production is not that: the bundle is fetched over the
 * internet, the API answers with latency, and a laptop on battery is slower than CI. This runs the
 * same measurement with:
 *   - a cold cache on every navigation (no bundle, no fonts, no API responses reused);
 *   - a 400ms added latency on every API call, so data arrives well after first paint;
 *   - 4x CPU throttling, so rendering is slow enough for shifts to be observable.
 *
 * A layout that only survives a warm cache is not stable; it is lucky.
 *
 *   APP_URL=... node scripts/cls-stress.mjs
 */
import { chromium } from "playwright";
import { readFileSync } from "node:fs";

const APP = process.env.APP_URL ?? "http://127.0.0.1:8040";
const bearer = process.env.BEARER_FILE ? readFileSync(process.env.BEARER_FILE, "utf8").trim() : "";

const COLLECTOR = `
  window.__cls = { value: 0, entries: [] };
  const desc = (n) => {
    if (!n) return "?";
    if (n.nodeType === 3) {
      const p = n.parentElement;
      return "text in " + (p ? p.nodeName.toLowerCase() +
        (p.className ? "." + String(p.className).split(" ").filter(Boolean).slice(0, 2).join(".") : "") : "?");
    }
    return (n.nodeName || "?").toLowerCase() +
      (n.className ? "." + String(n.className).split(" ").filter(Boolean).slice(0, 2).join(".") : "");
  };
  try {
    new PerformanceObserver((list) => {
      for (const e of list.getEntries()) {
        if (e.hadRecentInput) continue;
        window.__cls.value += e.value;
        window.__cls.entries.push({ value: e.value, at: e.startTime,
          sources: (e.sources || []).map((s) => ({ node: desc(s.node),
            prev: s.previousRect ? [s.previousRect.x, s.previousRect.y] : null,
            cur: s.currentRect ? [s.currentRect.x, s.currentRect.y] : null })) });
      }
    }).observe({ type: "layout-shift", buffered: true });
  } catch {}
`;

const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || undefined });
const results = [];

async function stress(name, width, scheme = "light") {
  const context = await browser.newContext({
    viewport: { width, height: 900 },
    colorScheme: scheme,
    ...(bearer ? { extraHTTPHeaders: { Authorization: `Bearer ${bearer}` } } : {}),
  });
  const page = await context.newPage();
  // Cache-control on every request: the CDN path in production is not warm either.
  await page.route("**/*", async (route) => {
    const t = route.request().resourceType();
    if (t === "fetch" || t === "xhr") {
      await new Promise((r) => setTimeout(r, 400));   // server latency
      return route.continue({ headers: { ...route.request().headers(), "cache-control": "no-cache" } });
    }
    return route.continue({ headers: { ...route.request().headers(), "cache-control": "no-cache" } });
  });
  const cdp = await context.newCDPSession(page);
  await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 });
  await page.addInitScript(COLLECTOR);
  await page.goto(APP, { waitUntil: "load" });
  await page.waitForTimeout(4000);   // enough for the 400ms-latency responses to land
  const r = await page.evaluate(() => ({ cls: window.__cls.value, entries: window.__cls.entries }));
  results.push({ name: `${name}${scheme === "dark" ? " (dark)" : ""}`, width, ...r });
  await context.close();
}

await stress("cold + 400ms latency + 4x CPU", 1440);
await stress("cold + 400ms latency + 4x CPU", 1440, "dark");
await stress("cold + 400ms latency + 4x CPU", 760);
await browser.close();

let worst = 0;
let failed = 0;
console.log("\nstress scenario                         width   CLS");
console.log("-".repeat(60));
for (const r of results) {
  worst = Math.max(worst, r.cls);
  const ok = r.cls <= 0.01;      // a little slack under hostile conditions, still far under 0.1
  if (!ok) failed += 1;
  console.log(`${r.name.padEnd(39)} ${String(r.width).padEnd(7)} ${r.cls.toFixed(4)}${ok ? "" : "  SHIFT"}`);
  if (!ok) {
    for (const e of r.entries) {
      console.log(`    +${e.value.toFixed(4)} @${Math.round(e.at)}ms`);
      for (const s of e.sources) console.log(`      ${s.node} prev=${JSON.stringify(s.prev)} cur=${JSON.stringify(s.cur)}`);
    }
  }
}
console.log(`\nworst: ${worst.toFixed(4)}  (budget 0.01 under stress)`);
process.exit(failed ? 1 : 0);
