/**
 * Reproduces the reported defect: with a session open, can the user type into the assistant?
 *
 * The hypothesis, from reading `AssistantDock.canSend`:
 *
 *     canSend = status !== "archived" && !requiresResume && (!hasSession || conn === "live")
 *
 * so ANY connection state other than "live" disables the textarea — including the momentary
 * "connecting" that every page load starts in, and "reconnecting", which the SSE hook never leaves
 * on its own if the reconnect itself is refused (a 404 for a deleted session, a 409 for a cursor
 * ahead of the journal). A disabled textarea cannot be typed into, which is the report.
 *
 *   node scripts/focus-repro.mjs [url]
 */
import { chromium } from "playwright";

const URL = process.argv[2] ?? "http://127.0.0.1:8062";
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1480, height: 900 } });

const report = { url: URL, observations: [] };
const see = (name, o) => report.observations.push({ name, ...o });

await page.goto(URL, { waitUntil: "networkidle" });

// Create a session through the app's own API, which is what the UI does on the first message.
const created = await page.evaluate(async () => {
  const r = await fetch("/api/sessions", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ folder: "/Users/raphael.mansuy@gmail.com/agent_scratch" }),
  });
  return { status: r.status, body: await r.json().catch(() => null) };
});
see("create session", created);
const id = created.body?.id;
if (!id) { console.log(JSON.stringify(report, null, 1)); await browser.close(); process.exit(0); }

await page.goto(`${URL}/#/session/${id}`, { waitUntil: "domcontentloaded" });

// Sample the composer every 200 ms for 4 s, so the CONNECTING window and the settled state are both
// visible. A field that is briefly disabled on load is already wrong: a user who starts typing at
// once loses the first characters.
const samples = [];
for (let i = 0; i < 20; i += 1) {
  samples.push(await page.evaluate(() => {
    const ta = document.querySelector(".assistant .composer textarea");
    const pill = document.querySelector(".dock-head .pill");
    return {
      t: Math.round(performance.now()),
      exists: !!ta,
      disabled: ta?.disabled ?? null,
      pill: pill?.textContent?.trim() ?? null,
      state: document.querySelector(".dock-head .dock-state-word")?.textContent?.trim() ?? null,
    };
  }));
  await page.waitForTimeout(200);
}
see("composer over 4 s after load", {
  samples,
  everDisabled: samples.some((s) => s.disabled === true),
  settledDisabled: samples.at(-1)?.disabled,
  pills: [...new Set(samples.map((s) => s.pill).filter(Boolean))],
});

// Does typing work in the settled state?
const ta = page.locator(".assistant .composer textarea");
await ta.click({ force: true }).catch(() => {});
await page.keyboard.type("can i type?");
see("type in settled state", await page.evaluate(() => ({
  value: document.querySelector(".assistant .composer textarea")?.value ?? null,
  active: document.activeElement?.tagName,
})));

// Now break the stream the way a deploy or a sleeping laptop does, and watch what the user gets.
await page.evaluate(() => {
  // Everything the app has open, closed: this is what a proxy timeout looks like to EventSource.
  window.__closed = true;
});
await page.context().setOffline(true);
await page.waitForTimeout(600);
see("offline", await page.evaluate(() => ({
  pill: document.querySelector(".dock-head .pill")?.textContent?.trim() ?? null,
  disabled: document.querySelector(".assistant .composer textarea")?.disabled ?? null,
})));
await page.context().setOffline(false);
await page.waitForTimeout(3000);
see("back online", await page.evaluate(() => ({
  pill: document.querySelector(".dock-head .pill")?.textContent?.trim() ?? null,
  disabled: document.querySelector(".assistant .composer textarea")?.disabled ?? null,
  value: document.querySelector(".assistant .composer textarea")?.value ?? null,
  anyRetryControl: [...document.querySelectorAll("button")].map((b) => b.textContent?.trim())
    .filter((t) => /retry|reconnect|try again|restore/i.test(t ?? "")),
})));

// Is there ANY way back that the UI offers? A reconnect button, a clickable pill, a retry?
see("recovery affordances", await page.evaluate(() => {
  const pill = document.querySelector(".dock-head .pill");
  return {
    pillIsButton: pill ? ["BUTTON", "A"].includes(pill.tagName) : null,
    pillRole: pill?.getAttribute("role") ?? null,
    pillTabIndex: pill instanceof HTMLElement ? pill.tabIndex : null,
    text: document.querySelector(".dock-head")?.textContent?.replace(/\s+/g, " ").trim().slice(0, 200) ?? null,
  };
}));

await page.screenshot({ path: "/tmp/focus-repro.png", fullPage: false });
await browser.close();
console.log(JSON.stringify(report, null, 1));
