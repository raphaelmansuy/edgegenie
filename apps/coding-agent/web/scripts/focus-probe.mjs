/**
 * Focus / keyboard / scroll probe. Not a test: an instrument.
 *
 * Reproduces the reported defect — "I cannot focus on the right panel to edit and ask a new command"
 * — and measures, for every panel, whether the keyboard can reach it, whether a shortcut can reach
 * it, whether focus stays where the user put it, and whether Escape has one meaning.
 *
 *   node scripts/focus-probe.mjs [url]
 *
 * Prints one JSON object. Every field is measured in a real browser against a running app; nothing
 * here is inferred from reading the code.
 */
import { chromium } from "playwright";

const URL = process.argv[2] ?? "http://127.0.0.1:8062";

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1480, height: 900 } });
const out = { url: URL, steps: [] };

const step = (name, data) => out.steps.push({ name, ...data });

// Everything the probe needs to know about the document, in one evaluate: the panel geometry and
// which of them can actually take focus.
const panels = async () =>
  page.evaluate(() => {
    const q = (s) => document.querySelector(s);
    const box = (el) => {
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) };
    };
    const composer = q(".assistant .composer textarea");
    const composerBox = q(".assistant .composer-box");
    return {
      rail: box(q("#rail") ?? q(".pane.rail")),
      main: box(q("#doc-panel") ?? q("main")),
      dock: box(q("#dock")),
      inspector: box(q(".pane.inspector")),
      dockComposer: composer ? {
        ...box(composer),
        disabled: composer.disabled,
        readOnly: composer.readOnly,
        tabIndex: composer.tabIndex,
      } : null,
      composerRing: composerBox ? getComputedStyle(composerBox).borderColor : null,
      // The pill that says the stream is not live, which is what the screenshot showed.
      connPill: q(".dock-head .pill")?.textContent?.trim() ?? null,
      dockState: q(".dock-head .dock-state-word")?.textContent?.trim() ?? null,
      scroll: {
        doc: { sh: document.documentElement.scrollHeight, ch: document.documentElement.clientHeight },
        body: { sh: document.body.scrollHeight, ch: document.body.clientHeight },
      },
    };
  });

await page.goto(URL, { waitUntil: "networkidle" });
await page.waitForTimeout(1200);

// ---------------------------------------------------------------- 1. the start screen
step("load", { panels: await panels() });

// ---------------------------------------------------------------- 2. can focus reach the dock composer?
const reach = await page.evaluate(() => {
  const ta = document.querySelector(".assistant .composer textarea");
  if (!ta) return { found: false };
  ta.focus();
  return {
    found: true,
    focused: document.activeElement === ta,
    activeTag: document.activeElement?.tagName,
    activeClass: document.activeElement?.className,
    disabled: ta.disabled,
  };
});
step("focus dock composer by clicking/script", reach);

// Type and see whether the value lands: a disabled textarea takes focus in some browsers and
// silently drops every keystroke.
await page.keyboard.type("hello");
const typed = await page.evaluate(() => {
  const ta = document.querySelector(".assistant .composer textarea");
  return { value: ta?.value ?? null, disabled: ta?.disabled ?? null };
});
step("typing into dock composer", typed);

// ---------------------------------------------------------------- 3. the shortcut that claims it can
await page.evaluate(() => document.querySelector(".assistant .composer textarea")?.blur());
await page.keyboard.press("Meta+l");
await page.waitForTimeout(200);
step("Meta+L (focus the message box) then type", await page.evaluate(() => {
  const ta = document.querySelector(".assistant .composer textarea");
  return { active: document.activeElement?.className ?? document.activeElement?.tagName, value: ta?.value ?? null };
}));

// ---------------------------------------------------------------- 4. is there a session yet?
const sessions = await page.evaluate(async () => {
  const r = await fetch("/api/sessions");
  try { return await r.json(); } catch { return { status: r.status }; }
});
step("sessions", { count: Array.isArray(sessions) ? sessions.length : null, raw: Array.isArray(sessions) ? undefined : sessions });

// Open the most recent session if there is one, so the dock has a live stream to report on.
const first = Array.isArray(sessions) && sessions[0]?.id;
if (first) {
  await page.goto(`${URL}/#/session/${first}`, { waitUntil: "networkidle" });
  await page.waitForTimeout(2500);
  step("session opened", { id: first, panels: await panels() });

  const tryType = await page.evaluate(() => {
    const ta = document.querySelector(".assistant .composer textarea");
    ta?.focus();
    return { focused: document.activeElement === ta, disabled: ta?.disabled };
  });
  step("focus composer with a session open", tryType);
  await page.keyboard.type("second message");
  step("typing with a session open", await page.evaluate(() => ({
    value: document.querySelector(".assistant .composer textarea")?.value ?? null,
  })));
}

// ---------------------------------------------------------------- 5. Escape's precedence
await page.keyboard.press("Escape");
step("Escape with focus in the dock", await page.evaluate(() => ({
  active: document.activeElement?.className ?? document.activeElement?.tagName,
  dockPresent: !!document.querySelector("#dock"),
})));

// ---------------------------------------------------------------- 6. tab order across panels
await page.evaluate(() => document.body.focus());
const order = [];
for (let i = 0; i < 30; i += 1) {
  await page.keyboard.press("Tab");
  order.push(await page.evaluate(() => {
    const a = document.activeElement;
    if (!a) return "none";
    const pane = a.closest("#dock") ? "dock" : a.closest("#rail") ? "rail"
      : a.closest("main") || a.closest("#doc-panel") ? "main"
      : a.closest(".pane.inspector") ? "inspector" : "chrome";
    return `${pane}:${a.tagName.toLowerCase()}${a.className ? "." + String(a.className).split(" ")[0] : ""}`;
  }));
}
step("tab order", { order: [...new Set(order)], detail: order });

await browser.close();
console.log(JSON.stringify(out, null, 1));
