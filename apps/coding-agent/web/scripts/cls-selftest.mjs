/** Proves the CLS instrument is not lying.
 *
 * A CLS audit that reports 0.0000 everywhere is worthless unless the measurement can be shown to
 * detect shift. This script:
 *   1. injects a deliberate 60px shift (spacer above the transcript) and asserts it is measured —
 *      if this reports 0, the observer is broken and every other CLS number in this repo is void;
 *   2. asserts the stress conditions are real: the throttled, latency-injected load must be
 *      measurably slower than the warm one, otherwise cls-stress.mjs is testing nothing.
 */
import { chromium } from "playwright";

const APP = process.env.APP_URL ?? "http://127.0.0.1:8040";
const COLLECTOR = `
  window.__cls = { value: 0 };
  new PerformanceObserver((list) => {
    for (const e of list.getEntries()) if (!e.hadRecentInput) window.__cls.value += e.value;
  }).observe({ type: "layout-shift", buffered: true });
`;

const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || undefined });
let problems = 0;

// --- 1. the observer must see a known shift -----------------------------------------------
{
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  await page.addInitScript(COLLECTOR);
  await page.goto(APP, { waitUntil: "load" });
  await page.waitForTimeout(2500);
  const before = await page.evaluate(() => window.__cls.value);
  await page.evaluate(() => {
    // Push everything below the strip down by 60px. A shift of 60 * 1440 over a 1440x900 viewport
    // is 60/900 ≈ 0.067, comfortably above the noise floor.
    const s = document.createElement("div");
    s.style.cssText = "height:60px";
    const main = document.querySelector("main") ?? document.body;
    main.parentElement.insertBefore(s, main);
  });
  await page.waitForTimeout(600);
  const after = await page.evaluate(() => window.__cls.value);
  const delta = after - before;
  console.log(`instrument: injected 60px shift -> measured +${delta.toFixed(4)}`);
  if (delta < 0.04) {
    problems += 1;
    console.log("  FAIL: the observer did not register a deliberate shift; CLS numbers are not trustworthy");
  } else {
    console.log("  ok: the observer detects real shift");
  }
  await ctx.close();
}

// --- 2. the stress conditions must actually be slower -------------------------------------
{
  const warm = async () => {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await ctx.newPage();
    const t0 = Date.now();
    await page.goto(APP, { waitUntil: "load" });
    await page.locator(".composer textarea").waitFor();
    await page.waitForTimeout(900);
    const ms = Date.now() - t0;
    await ctx.close();
    return ms;
  };
  const stressed = async () => {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await ctx.newPage();
    await page.route("**/*", async (route) => {
      // Every request, not just the API: a cold production load fetches the bundle and the fonts
      // over the network too, and it is the late-arriving bundle that causes startup shift.
      await new Promise((r) => setTimeout(r, 300));
      return route.continue();
    });
    const cdp = await ctx.newCDPSession(page);
    await cdp.send("Emulation.setCPUThrottlingRate", { rate: 6 });
    const t0 = Date.now();
    await page.goto(APP, { waitUntil: "load" });
    await page.locator(".composer textarea").waitFor();
    await page.waitForTimeout(900);
    const ms = Date.now() - t0;
    await ctx.close();
    return ms;
  };
  const w = await warm();
  const s = await stressed();
  console.log(`conditions: warm ${w}ms vs throttled+latency ${s}ms`);
  if (s < w * 1.5) {
    problems += 1;
    console.log("  FAIL: the stress conditions are not biting; a pass there means nothing");
    console.log(`  (warm ${w}ms, stressed ${s}ms, ratio ${(s / w).toFixed(2)}x, need 1.5x)`);
  } else {
    console.log("  ok: stress conditions are measurably hostile");
  }
}

await browser.close();
console.log(problems ? `\n${problems} problem(s) with the measurement itself` : "\nthe instrument is sound");
process.exit(problems ? 1 : 0);
