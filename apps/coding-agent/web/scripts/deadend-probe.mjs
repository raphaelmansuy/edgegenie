/**
 * The dead end. A session whose stream cannot open never recovers, by construction.
 *
 * `useSessionStream` opens ONE EventSource per session and relies on the browser to reconnect it.
 * When the response is not a 200 (a deleted session is 404, a replay cursor ahead of the journal is
 * 409), the browser marks the source CLOSED and stops retrying. `onerror` sets "reconnecting", and
 * nothing ever moves it back: the only calls to `open()` are `visibilitychange` (which requires
 * readyState === CLOSED, so it does retry — once per tab switch) and `online`.
 *
 * Meanwhile four controls are gated on `conn === "live"`:
 *   the composer (`canSend`), "Restore agent", "Stop work", the inline approval buttons.
 *
 * So the user sees "reconnecting…", a disabled message box, and no control that names the way out —
 * which is the reported defect, on the screen the screenshot captured.
 *
 *   node scripts/deadend-probe.mjs [url]
 */
import { chromium } from "playwright";

const URL = process.argv[2] ?? "http://127.0.0.1:8062";
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1480, height: 900 } });
const out = {};

// 1. Find or make a session with at least one turn, so RunStatus renders its controls.
await page.goto(URL, { waitUntil: "networkidle" });
const made = await page.evaluate(async () => {
  const r = await fetch("/api/sessions", {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ folder: "/Users/raphael.mansuy@gmail.com/agent_scratch" }),
  });
  return r.json();
});
const id = made.id;
out.session = id;

// Put a turn in it so the dock has a transcript and RunStatus shows.
await page.evaluate(async (sid) => {
  await fetch(`/api/sessions/${sid}/messages`, {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ text: "Say READY." }),
  });
}, id);
await page.waitForTimeout(3000);

// 2. Open it, confirm the healthy state.
await page.goto(`${URL}/#/session/${id}`, { waitUntil: "networkidle" });
await page.waitForTimeout(2500);
const healthy = await page.evaluate(() => {
  const ta = document.querySelector(".assistant .composer textarea");
  const buttons = [...document.querySelectorAll(".run-status button")];
  return {
    pill: document.querySelector(".dock-head .pill")?.textContent?.trim() ?? null,
    textareaDisabled: ta?.disabled ?? null,
    runStatusButtons: buttons.map((b) => ({ text: b.textContent?.trim(), disabled: b.disabled })),
  };
});
out.healthy = healthy;

// 3. Break the stream for good: the session stops existing server-side. This is what a redeploy, a
//    reaper sweep, or a session opened in a second tab after archival all produce.
const deleted = await page.evaluate(async (sid) => {
  const r = await fetch(`/api/sessions/${sid}`, { method: "DELETE" });
  return r.status;
}, id);
out.deleted = deleted;

// 4. Force the source to reconnect, the only way a user can: switch away and back.
await page.evaluate(() => {
  Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true });
  document.dispatchEvent(new Event("visibilitychange"));
});
await page.waitForTimeout(300);
await page.evaluate(() => {
  Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
  document.dispatchEvent(new Event("visibilitychange"));
});
await page.waitForTimeout(3000);

out.afterBreak = await page.evaluate(() => {
  const ta = document.querySelector(".assistant .composer textarea");
  const buttons = [...document.querySelectorAll(".run-status button")];
  const pill = document.querySelector(".dock-head .pill");
  return {
    pill: pill?.textContent?.trim() ?? null,
    textareaDisabled: ta?.disabled ?? null,
    // What a user can still DO. Anything that would get them out of this state is the point.
    runStatusButtons: buttons.map((b) => ({ text: b.textContent?.trim(), disabled: b.disabled })),
    dockText: document.querySelector(".dock-head")?.textContent?.replace(/\s+/g, " ").trim().slice(0, 160) ?? null,
    // Is there ANY control anywhere whose name suggests recovery?
    recoveryControls: [...document.querySelectorAll("button, a[role=button]")]
      .map((b) => b.textContent?.trim() ?? "")
      .filter((t) => /retry|reconnect|reload|try again|restore|refresh|start over|new conversation/i.test(t)),
    // Can the user still send? Measure it, do not infer it.
    canType: (() => { if (!ta) return null; ta.focus(); return document.activeElement === ta; })(),
  };
});

// 5. A brand-new session from the same screen: is that a way out?
out.newSessionReachable = await page.evaluate(() => {
  const b = document.querySelector(".dock-new");
  return b ? { present: true, disabled: b.disabled, label: b.getAttribute("aria-label") } : { present: false };
});

await page.screenshot({ path: "/tmp/deadend.png" });
await browser.close();
console.log(JSON.stringify(out, null, 1));
