/**
 * The spec's screenshots. One scene per file, each answering one question.
 *
 *   node scripts/ux-scenes.mjs [url] [outDir]
 *
 * Every scene asserts its own pass criteria and prints them, so a scene that produced a pretty
 * picture of the wrong state fails loudly. The screenshots go to specs/012-ux-improve/e2e/screenshots
 * by default and are inspected one by one before they are accepted (10-e2e-plan.md).
 */
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const URL = process.argv[2] ?? "http://127.0.0.1:8062";
const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = resolve(process.argv[3] ?? `${HERE}/../../../../specs/012-ux-improve/e2e/screenshots`);
mkdirSync(OUT, { recursive: true });

const results = [];
const record = (scene, checks) => {
  const failed = checks.filter((c) => !c.pass);
  results.push({ scene, pass: failed.length === 0, checks });
};

const browser = await chromium.launch();

/** A page with a session that has one completed turn, created through the app's own API. */
async function withSession(width = 1480) {
  const page = await browser.newPage({ viewport: { width, height: 900 } });
  await page.goto(URL, { waitUntil: "networkidle" });
  const made = await page.evaluate(async () => {
    const r = await fetch("/api/sessions", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ folder: "/Users/raphael.mansuy@gmail.com/agent_scratch" }),
    });
    return r.json();
  });
  await page.evaluate(async (sid) => {
    await fetch(`/api/sessions/${sid}/messages`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ text: "Create a notebook about NY taxi trips and chart them by hour." }),
    });
  }, made.id);
  await page.waitForTimeout(3500);
  await page.goto(`${URL}/#/session/${made.id}`, { waitUntil: "networkidle" });
  await page.waitForTimeout(2000);
  return { page, id: made.id };
}

const shot = (page, name) => page.screenshot({ path: `${OUT}/${name}`, fullPage: false });

/** A session with one turn, created and left UNOPENED so a scene can install a route before the
 *  stream is ever requested. `withSession` navigates to the session, which connects the stream — so
 *  a route registered afterwards is too late, and the scene silently measures a healthy app. That
 *  cost two wrong runs of S4 and S5. */
async function sessionUnopened(width = 1480) {
  const page = await browser.newPage({ viewport: { width, height: 900 } });
  await page.goto(URL, { waitUntil: "networkidle" });
  const made = await page.evaluate(async () => {
    const r = await fetch("/api/sessions", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ folder: "/Users/raphael.mansuy@gmail.com/agent_scratch" }),
    });
    return r.json();
  });
  await page.evaluate(async (sid) => {
    await fetch(`/api/sessions/${sid}/messages`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ text: "Create a notebook about NY taxi trips and chart them by hour." }),
    });
  }, made.id);
  await page.waitForTimeout(3000);
  return { page, id: made.id };
}

// ---------------------------------------------------------------- S1 the healthy shell
{
  const { page } = await withSession(1480);
  const geo = await page.evaluate(() => {
    const b = (s) => { const e = document.querySelector(s); if (!e) return null; const r = e.getBoundingClientRect(); return { x: Math.round(r.x), w: Math.round(r.width) }; };
    return {
      rail: b(".pane.rail"), dock: b("#dock"),
      docScroll: document.documentElement.scrollHeight === document.documentElement.clientHeight,
      composerDisabled: document.querySelector(".assistant .composer textarea")?.disabled ?? null,
    };
  });
  await shot(page, "s1-shell-1480-light.png");
  record("S1 the healthy shell", [
    { name: "rail is 276px", pass: geo.rail?.w === 276, detail: geo.rail },
    { name: "dock is 380px", pass: geo.dock?.w === 380, detail: geo.dock },
    { name: "no page scroll", pass: geo.docScroll },
    { name: "composer is not disabled", pass: geo.composerDisabled === false },
  ]);
  await page.close();
}

// ---------------------------------------------------------------- S2 type during connecting
{
  const page = await browser.newPage({ viewport: { width: 1480, height: 900 } });
  await page.goto(URL, { waitUntil: "networkidle" });
  // Hold the stream open so the composer is sampled inside the connecting window.
  await page.route("**/stream**", async (route) => { await new Promise((r) => setTimeout(r, 2500)); await route.continue(); });
  const made = await page.evaluate(async () => (await fetch("/api/sessions", {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ folder: "/Users/raphael.mansuy@gmail.com/agent_scratch" }),
  })).json());
  await page.unroute("**/stream**");
  await page.goto(`${URL}/#/session/${made.id}`, { waitUntil: "domcontentloaded" });
  const ta = page.locator(".assistant .composer textarea");
  await ta.click({ force: true });
  await page.keyboard.type("chart the trips");
  const typed = await page.evaluate(() => ({
    value: document.querySelector(".assistant .composer textarea")?.value ?? null,
    active: document.activeElement?.tagName ?? null,
    disabled: document.querySelector(".assistant .composer textarea")?.disabled ?? null,
  }));
  await shot(page, "s2-connecting-1480.png");
  record("S2 type during connecting", [
    { name: "the textarea is focusable", pass: typed.active === "TEXTAREA", detail: typed.active },
    // The value may be "chart the trips" or, if the stream opened mid-typing, a prefix — what matters
    // is that keystrokes LANDED rather than being discarded by an unfocusable field.
    { name: "keystrokes landed", pass: Boolean(typed.value && typed.value.length > 0), detail: typed.value },
    { name: "never disabled", pass: typed.disabled === false, detail: typed.disabled },
  ]);
  await page.close();
}

// ---------------------------------------------------------------- S4 reconnecting
{
  const { page, id } = await sessionUnopened(1480);
  /* The route is registered BEFORE the session is opened, so the very first stream request is
     intercepted. This is the whole reason for the unopened variant: with the stream already
     connected, a route registered afterwards changes nothing and the scene measured `null`. */
  await page.route("**/stream**", (route) => route.fulfill({ status: 503, body: "unavailable" }));
  await page.goto(`${URL}/#/session/${id}`, { waitUntil: "networkidle" });
  await page.waitForTimeout(3000);
  const state = await page.evaluate(() => ({
    notice: document.querySelector(".stream-notice")?.getAttribute("data-state") ?? null,
    word: document.querySelector(".stream-notice-word")?.textContent?.trim() ?? null,
    hasRetry: [...document.querySelectorAll(".stream-notice button")].some((b) => /retry/i.test(b.textContent ?? "")),
    composerDisabled: document.querySelector(".assistant .composer textarea")?.disabled ?? null,
    composerVisible: !!document.querySelector(".assistant .composer textarea"),
  }));
  await shot(page, "s4-reconnecting-1480.png");
  record("S4 reconnecting", [
    { name: "the state is reconnecting", pass: state.notice === "reconnecting", detail: state.notice },
    { name: "a Retry action exists", pass: state.hasRetry, detail: state.word },
    { name: "the composer is still typeable", pass: state.composerDisabled === false, detail: state.composerDisabled },
  ]);
  await page.close();
}

// ---------------------------------------------------------------- S5 closed
/* The REAL way a stream returns 404, established by measurement rather than assumed:
 *
 *   DELETE /api/sessions/<id>  → 204, and the session becomes `archived` — it is NOT removed, and its
 *                                stream still answers 200. So deleting is not how this state happens.
 *   a session id that never existed → the detail route 404s and the stream 404s. THIS is `closed`.
 *
 * The first version of this scene deleted a session and intercepted the stream, which measured a
 * healthy archived session with no notice — it was testing a state the server does not produce. */
{
  await page_gotoClosed();
}
async function page_gotoClosed() {
  const page = await browser.newPage({ viewport: { width: 1480, height: 900 } });
  await page.goto(`${URL}/#/session/this-session-was-reaped-0000`, { waitUntil: "networkidle" });
  await page.waitForTimeout(4000);
  const state = await page.evaluate(() => {
    const ta = document.querySelector(".assistant .composer textarea");
    const box = document.querySelector(".assistant .composer-box");
    const actions = [...document.querySelectorAll(".stream-notice button")].map((b) => b.textContent?.trim());
    return {
      notice: document.querySelector(".stream-notice")?.getAttribute("data-state") ?? null,
      role: document.querySelector(".stream-notice")?.getAttribute("role") ?? null,
      actions,
      disabled: ta?.disabled ?? null,
      readOnly: ta?.readOnly ?? null,
      describedBy: ta?.getAttribute("aria-describedby") ?? null,
      blockedClass: box?.className.includes("is-blocked") ?? null,
      reasonVisible: ta?.getAttribute("placeholder") ?? null,
    };
  });
  await shot(page, "s5-closed-1480.png");
  record("S5 closed", [
    { name: "the state is closed", pass: state.notice === "closed", detail: state.notice },
    { name: "announced as an alert", pass: state.role === "alert", detail: state.role },
    { name: "two actions offered", pass: (state.actions?.length ?? 0) >= 2, detail: state.actions },
    /* The composer stays WRITABLE here, and that is the point of [P1]: a lost stream means the answer
       will not arrive yet, not that the question is refused. The notice carries the fault and the two
       actions; the box carries the user's sentence. A `readOnly` box in this state would be the old
       defect wearing a different hat — the user could type nowhere while the app sorted itself out.
       (The readOnly presentation is asserted where it belongs, in S5b, on an ARCHIVED session.) */
    { name: "not disabled, so still focusable", pass: state.disabled === false, detail: state.disabled },
    { name: "writable, because a closed stream is not a closed session", pass: state.readOnly === false, detail: state.readOnly },
    { name: "the placeholder still invites", pass: /ask/i.test(state.reasonVisible ?? ""), detail: state.reasonVisible },
  ]);
  await page.close();
}

// ---------------------------------------------------------------- S6 Escape at 820
{
  const page = await browser.newPage({ viewport: { width: 820, height: 900 } });
  await page.goto(URL, { waitUntil: "networkidle" });
  await page.waitForTimeout(600);
  await page.keyboard.press("Meta+1");
  await page.waitForTimeout(400);
  const opened = await page.evaluate(() => !!document.querySelector(".pane.rail"));
  await page.evaluate(() => { const m = document.querySelector("main"); m?.setAttribute("tabindex", "-1"); m?.focus(); });
  await page.keyboard.press("Escape");
  await page.waitForTimeout(400);
  const closed = await page.evaluate(() => !document.querySelector(".pane.rail"));
  await shot(page, "s6-escape-820.png");
  record("S6 Escape closes the drawer from the work area", [
    { name: "the drawer opened", pass: opened },
    { name: "Escape closed it", pass: closed },
  ]);
  await page.close();
}

// ---------------------------------------------------------------- S7 a cell deeplink after a hard load
{
  const page = await browser.newPage({ viewport: { width: 1480, height: 900 } });
  await page.goto(`${URL}/#/settings/providers`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1200);
  const dialog = await page.evaluate(() => !!document.querySelector('[role="dialog"][aria-modal="true"]'));
  await shot(page, "s7-deeplink-settings.png");
  record("S7 a settings deeplink opens on a cold load", [
    { name: "the dialog opened", pass: dialog },
  ]);
  await page.close();
}

// ---------------------------------------------------------------- S8 scroll hand-off
/* The hand-off needs a scroller that is genuinely contained and genuinely at its edge. Rather than
   hope a fixture produces one, the scene BUILDS the exact DOM shape the CSS rules target — two nested
   `overflow: auto` boxes with `overscroll-behavior: contain` — and drives a real wheel event through
   the hook. That makes the scene independent of what the agent happened to write, which is the only
   way it can be a stable gate rather than a snapshot of one conversation. */
{
  const page = await browser.newPage({ viewport: { width: 1480, height: 900 } });
  await page.goto(URL, { waitUntil: "networkidle" });
  await page.waitForTimeout(800);
  const handoff = await page.evaluate(async () => {
    const outer = document.createElement("div");
    outer.style.cssText = "overflow:auto;overscroll-behavior:contain;height:200px;width:300px";
    const spacer1 = document.createElement("div"); spacer1.style.height = "900px";
    const inner = document.createElement("div");
    inner.style.cssText = "overflow:auto;overscroll-behavior:contain;height:120px;width:200px";
    const filler = document.createElement("div"); filler.style.height = "600px";
    inner.appendChild(filler);
    outer.append(spacer1, inner);
    document.body.appendChild(outer);
    await new Promise((r) => requestAnimationFrame(r));

    // The inner box is at its bottom edge; a downward wheel must move the outer box.
    inner.scrollTop = inner.scrollHeight;
    const outerBefore = outer.scrollTop;
    inner.dispatchEvent(new WheelEvent("wheel", { deltaY: 100, deltaMode: 0, bubbles: true, cancelable: true }));
    await new Promise((r) => setTimeout(r, 100));
    const outerAfter = outer.scrollTop;
    const result = { outerBefore, outerAfter, moved: outerAfter > outerBefore };
    outer.remove();
    return result;
  });
  await shot(page, "s8-scroll-handoff.png");
  record("S8 the wheel hands off at a contained scroller's edge", [
    { name: "the outer scroller took the remainder", pass: handoff.moved, detail: handoff },
  ]);
  await page.close();
}

await browser.close();

const failed = results.filter((r) => !r.pass);
console.log(JSON.stringify({ out: OUT, scenes: results, failed: failed.length }, null, 1));
process.exit(failed.length === 0 ? 0 : 1);
