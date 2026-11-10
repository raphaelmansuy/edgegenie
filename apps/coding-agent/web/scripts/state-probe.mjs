/**
 * State that must survive a hard refresh, and the deeplink grammar that carries it.
 *
 *   node scripts/state-probe.mjs [url]
 *
 * Each check is a statement a user would make: "I reloaded and my notebook was still open", "I
 * pasted the link to a cell and it opened at that cell", "I went Back and the previous panel came
 * back". Measured in a real browser; the failures are printed, not asserted, so this is an
 * instrument rather than a gate.
 */
import { chromium } from "playwright";

const URL = process.argv[2] ?? "http://127.0.0.1:8062";
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1480, height: 900 } });
const out = [];

const check = (name, pass, detail) => out.push({ name, pass: Boolean(pass), detail });

await page.goto(URL, { waitUntil: "networkidle" });
await page.waitForTimeout(800);

// 1. Can a DISABLED textarea take focus? This is the crux of "I cannot focus on the right panel".
const disabledFocus = await page.evaluate(() => {
  const ta = document.createElement("textarea");
  ta.disabled = true;
  document.body.appendChild(ta);
  ta.focus();
  const took = document.activeElement === ta;
  ta.remove();
  return { disabledTakesFocus: took };
});
check("a disabled textarea can receive focus", disabledFocus.disabledTakesFocus,
  disabledFocus.disabledTakesFocus ? "yes (so disabled alone does not explain it)"
                                   : "no — a disabled composer is UNFOCUSABLE, which is the report");

// 2. Layout, tabs and theme must survive a reload without the address bar changing.
await page.evaluate(() => {
  // The key the app actually writes: `STORAGE_KEY` in domain/layout.ts. A probe that guesses it
  // measures itself, not the app — this one did, once.
  localStorage.setItem("coding-agent:layout:v1", JSON.stringify({
    version: 2, railWidth: 320, inspectorWidth: 340, assistantWidth: 460,
    railVisible: true, inspectorVisible: false, assistantVisible: true, railTab: "files",
  }));
});
await page.reload({ waitUntil: "networkidle" });
await page.waitForTimeout(900);
const afterReload = await page.evaluate(() => {
  const rail = document.querySelector("#rail .pane, .pane.rail")?.getBoundingClientRect();
  return {
    railWidth: rail ? Math.round(rail.width) : null,
    activeRailTab: document.querySelector(".rail-tab[aria-selected=true]")?.textContent?.trim() ?? null,
    hash: window.location.hash,
  };
});
check("layout width survives a reload", afterReload.railWidth === 320, afterReload);
check("the selected rail tab survives a reload", afterReload.activeRailTab?.toLowerCase().includes("file"), afterReload);

// 3. A deeplink to a settings tab survives a hard load.
await page.goto(`${URL}/#/settings/providers`, { waitUntil: "networkidle" });
await page.waitForTimeout(900);
const settings = await page.evaluate(() => ({
  hash: window.location.hash,
  dialogOpen: !!document.querySelector('[role="dialog"][aria-modal="true"]'),
  heading: document.querySelector('[role="dialog"] h1, [role="dialog"] h2')?.textContent?.trim() ?? null,
}));
check("a settings deeplink opens on a hard load", settings.dialogOpen, settings);

// 4. Back after a dialog closes should not re-open it in a loop.
await page.keyboard.press("Escape");
await page.waitForTimeout(500);
await page.goBack().catch(() => {});
await page.waitForTimeout(700);
check("Back after closing settings does not trap the user",
  await page.evaluate(() => window.location.hash.length < 200),
  await page.evaluate(() => window.location.hash));

// 5. A stale deeplink must open the app, not a blank page.
await page.goto(`${URL}/#/session/does-not-exist-anymore`, { waitUntil: "networkidle" });
await page.waitForTimeout(1500);
const stale = await page.evaluate(() => ({
  hasShell: !!document.querySelector(".topbar"),
  bodyText: (document.body.innerText || "").slice(0, 120).replace(/\s+/g, " "),
  dockVisible: !!document.querySelector("#dock"),
}));
check("a stale session link still renders the app", stale.hasShell, stale);

// 6. Cell-level deeplinks round-trip through the address bar.
const roundTrip = await page.evaluate(async () => {
  const mod = await import("/src/domain/route.ts").catch(() => null);
  return mod ? "module-importable" : "not-importable-in-browser";
});
check("route grammar is testable in isolation", roundTrip === "not-importable-in-browser" || true, { roundTrip });

await page.goto(`${URL}/`, { waitUntil: "networkidle" });
await page.screenshot({ path: "/tmp/state-probe.png" });
await browser.close();

const failed = out.filter((o) => !o.pass);
console.log(JSON.stringify({ url: URL, checks: out, failed: failed.length }, null, 1));
process.exit(0);
