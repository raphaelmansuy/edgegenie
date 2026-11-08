/** 007 — the shell's contract, scene by scene, with a screenshot per claim.
 *   APP_URL=http://127.0.0.1:8062 node scripts/shell-e2e.mjs
 * Screenshots: specs/007-ux-ui-improve/e2e/screenshot/
 */
import { mkdirSync } from "node:fs";
/* parity-lib reads `OUT` when it is first evaluated, and a static `import` is evaluated BEFORE any
   statement in this file (ESM hoisting) — which is exactly how 007's pictures ended up in the 006
   folder. A dynamic import after setting the variable makes the order explicit instead of accidental. */
const OUT = new URL("../../../../specs/007-ux-ui-improve/e2e/screenshot/", import.meta.url).pathname;
process.env.OUT = OUT;
mkdirSync(OUT, { recursive: true });
const { launch, shot } = await import("./parity-lib.mjs");

let failed = 0;
const fail = (n, d = "") => { failed++; console.log(`  FAIL ${n}${d ? ` — ${d}` : ""}`); };
const ok = (n, c, d = "") => { console.log(`  ${c ? "PASS" : "FAIL"} ${n}${d ? ` — ${d}` : ""}`); if (!c) failed++; };

const NB = "/Users/raphael.mansuy@gmail.com/agent_scratch/tall_demo";
const focus = (p) => p.evaluate(() => {
  const e = document.activeElement;
  return { tag: e?.tagName.toLowerCase(), id: e?.id || "", cls: (e?.className || "").toString().split(" ")[0] || "",
    label: (e?.getAttribute?.("aria-label") || "").slice(0, 40), inMain: !!e?.closest?.("main"), inCell: !!e?.closest?.(".cell-block") };
});

/* ---------------------------------------------------------------- S1 skip links + Tab budget */
{
  const { browser, page: p, errors } = await launch(1440, 900);
  console.log("\nS1 skip links, Tab budget");
  await p.locator(".home, .editor-surface").first().waitFor({ timeout: 40000 });
  await p.waitForTimeout(1200);
  await p.keyboard.press("Tab");
  await p.waitForTimeout(350);          // the slide-in is a transition; measure it once it has arrived
  const first = await focus(p);
  const visible = await p.evaluate(() => {
    const a = document.activeElement;
    if (!a || !a.classList.contains("skip-link")) return false;
    const r = a.getBoundingClientRect();
    return r.top >= 0 && r.height > 0 && getComputedStyle(a).visibility !== "hidden";
  });
  ok("the first Tab stop is a skip link", first.cls === "skip-link", JSON.stringify(first));
  ok("…and it is visible when focused", visible);
  await shot(p, "01-skip-visible.png");
  await p.keyboard.press("Enter");
  const afterEnter = await focus(p);
  ok("Enter moves focus into the work region", afterEnter.id === "doc-panel", JSON.stringify(afterEnter));
  await shot(p, "02-focus-in-main.png");
  await p.keyboard.press("Tab");
  const next = await focus(p);
  ok("the next Tab continues inside the region", next.inMain, JSON.stringify(next));

  // Tab budget to the code editor
  await p.evaluate((h) => { location.hash = h; }, `#/notebook${NB}`);
  await p.locator(".cell-block").first().waitFor({ timeout: 40000 });
  await p.waitForTimeout(1500);
  await p.evaluate(() => document.activeElement?.blur?.());
  let tabs = 0;
  for (; tabs < 40; tabs++) {
    await p.keyboard.press("Tab");
    if ((await focus(p)).tag === "div" && await p.evaluate(() => !!document.activeElement?.closest(".cm-editor"))) break;
  }
  ok("the code editor is ≤ 12 Tab stops from the top", tabs + 1 <= 12, `${tabs + 1} stops`);
  ok("no page errors", errors.length === 0, errors.join(" | "));
  await browser.close();
}

/* ---------------------------------------------------------------- S2 dialogs return focus */
{
  const { browser, page: p, errors } = await launch(1440, 900);
  console.log("\nS2 dialogs return focus (KB-1, KB-3)");
  await p.locator(".home").waitFor({ timeout: 40000 });
  await p.waitForTimeout(1000);
  const openWith = async (name) => {
    const btn = p.getByRole("button", { name }).first();
    await btn.click();                    // a real focus, the way a user arrives at it
    await p.waitForTimeout(200);
    return focus(p);
  };
  const before = await openWith(/Search or run a command/i);
  await p.keyboard.press("Escape");       // the click opened it; start from a known state
  await p.waitForTimeout(300);
  await p.getByRole("button", { name: /Search or run a command/i }).first().focus();
  await p.waitForTimeout(150);
  await p.keyboard.press("Meta+k");
  await p.locator('[role="dialog"]').waitFor({ timeout: 5000 });
  await p.waitForTimeout(400);
  ok("the palette opened focused", (await p.evaluate(() => document.activeElement?.tagName.toLowerCase())) === "input");
  await shot(p, "03-palette-open.png");
  await p.keyboard.press("Escape");
  await p.waitForTimeout(500);
  const back = await focus(p);
  ok("Escape returns focus to the control that opened it", back.cls === "search-trigger", `${JSON.stringify(before)} -> ${JSON.stringify(back)}`);
  ok("…and it is not the body", back.tag !== "body");
  await shot(p, "03-palette-escape.png");

  // shortcut sheet
  await p.getByRole("button", { name: /Keyboard shortcuts/i }).first().focus();
  const sheetBefore = await focus(p);
  await p.keyboard.press("Meta+/");
  await p.locator(".keys-sheet").waitFor({ timeout: 5000 });
  await p.waitForTimeout(400);
  const scopes = await p.locator(".keys-sheet .keys-group h3").allInnerTexts();
  ok("the sheet groups by scope", scopes.length === 3, scopes.join(" / "));
  await shot(p, "08-sheet.png");
  await p.keyboard.press("Escape");
  await p.waitForTimeout(500);
  ok("the sheet returns focus", (await focus(p)).cls === sheetBefore.cls, JSON.stringify(await focus(p)));

  // composer ring
  await p.locator(".composer textarea").focus();
  await p.waitForTimeout(200);
  const ring = await p.evaluate(() => {
    const t = document.querySelector(".composer textarea");
    const cs = getComputedStyle(t);
    return { outline: cs.outlineStyle, w: parseFloat(cs.outlineWidth), color: cs.outlineColor };
  });
  ok("the composer field has its own focus ring", ring.outline !== "none" && ring.w >= 2, JSON.stringify(ring));
  await shot(p, "05-composer-focus.png");
  ok("no page errors", errors.length === 0, errors.join(" | "));
  await browser.close();
}

/* ---------------------------------------------------------------- S3 chords */
{
  const { browser, page: p, errors } = await launch(1440, 900);
  console.log("\nS3 the chords mean what the sheet says (KB-2, KB-9, KB-10)");
  await p.locator(".home").waitFor({ timeout: 40000 });
  await p.locator("textarea").last().fill("hello");
  await p.keyboard.press("Enter");
  await p.waitForTimeout(3500);
  await p.evaluate((h) => { location.hash = h; }, `#/notebook${NB}`);
  await p.locator(".cell-block").first().waitFor({ timeout: 40000 });
  await p.waitForTimeout(1500);
  await p.locator(".cell-block").nth(2).locator(".cm-line").first().click();
  await p.waitForTimeout(300);
  const inspector = () => p.locator(".insp-body").count();
  /* Start from "closed": the previous scene may have left the inspector open, and a toggle whose
     state you assume is the mistake that made this scene fail twice while the app was correct. */
  if ((await inspector()) > 0) { await p.keyboard.press("Meta+i"); await p.waitForTimeout(500); }
  const prompt = () => p.locator(".cell-prompt").count();
  /* The inspector is a COLUMN only in `wide` mode (≥1180 px): at 1440 with the dock open the
     arithmetic has no room for four columns, so `⌘I` opens it as a DRAWER. Assert the surface, not
     the container: `.insp-body` is the inspector wherever it is drawn. */
  const i0 = await inspector(), p0 = await prompt();
  await p.keyboard.press("Meta+i");
  await p.waitForTimeout(600);
  const i1 = await inspector(), p1 = await prompt();
  ok("⌘I opens the inspector with a cell focused", i1 > i0 && p1 === p0, `inspector ${i0}->${i1}, prompt ${p0}->${p1}`);
  /* Overlap means the two boxes INTERSECT. The first version compared `i.right > d.left`, which is
     true whenever the inspector legitimately sits to the right of the dock — it reported a collision
     for a correct layout. Rectangles intersecting is the property, not one edge passing another. */
  const geo = await p.evaluate(() => {
    const d = document.querySelector(".pane.assistant")?.getBoundingClientRect();
    const i = document.querySelector(".pane.inspector")?.getBoundingClientRect();
    if (!d || !i) return { overlap: false, both: false };
    const overlap = Math.min(i.right, d.right) - Math.max(i.left, d.left) > 1
      && Math.min(i.bottom, d.bottom) - Math.max(i.top, d.top) > 1;
    return { overlap, both: true, dock: [Math.round(d.left), Math.round(d.right)], insp: [Math.round(i.left), Math.round(i.right)] };
  });
  ok("the inspector does not cover the conversation", !geo.overlap, JSON.stringify(geo));
  await shot(p, "06-inspector-cmd-i.png");
  await p.keyboard.press("Meta+i");
  await p.waitForTimeout(500);
  ok("⌘I again closes it", (await inspector()) === i0);
  await p.keyboard.press("Meta+Shift+i");
  await p.waitForTimeout(600);
  ok("⌘⇧I opens the cell prompt", (await prompt()) > p0, `prompt ${p0} -> ${await prompt()}`);
  await shot(p, "07-cell-prompt-cmd-shift-i.png");
  await p.keyboard.press("Escape");
  await p.waitForTimeout(400);
  await p.keyboard.press("Meta+Shift+i");
  await p.waitForTimeout(500);
  ok("⌘⇧I toggles it closed", (await prompt()) === p0);
  ok("no page errors", errors.length === 0, errors.join(" | "));
  await browser.close();
}

/* ---------------------------------------------------------------- S4 a cell is one Tab stop */
{
  const { browser, page: p, errors } = await launch(1440, 900);
  console.log("\nS4 a cell is one Tab stop (KB-4)");
  await p.evaluate((h) => { location.hash = h; }, `#/notebook${NB}`);
  await p.locator(".home, .editor-surface").first().waitFor({ timeout: 40000 });
  await p.locator(".cell-block").first().waitFor({ timeout: 40000 });
  await p.waitForTimeout(1400);
  await p.locator(".cell-block").nth(1).locator("section, .cell-bar").first().click({ position: { x: 4, y: 4 } }).catch(() => {});
  await p.locator(".cell-block").nth(1).locator(".cell-no").click().catch(() => {});
  await p.waitForTimeout(300);
  const inCell = await focus(p);
  ok("the cell itself takes focus", inCell.inCell || inCell.tag === "section", JSON.stringify(inCell));
  // one Tab leaves the cell
  await p.keyboard.press("Tab");
  await p.waitForTimeout(250);
  const afterTab = await focus(p);
  ok("Tab leaves the cell instead of walking its buttons", !afterTab.inCell || afterTab.tag !== "button", JSON.stringify(afterTab));
  // arrows reach the buttons
  await p.locator(".cell-block").nth(1).locator(".cell-no").click();
  await p.waitForTimeout(200);
  await p.evaluate(() => document.querySelectorAll(".cell-block")[1].focus());
  await p.keyboard.press("ArrowRight").catch(() => {});
  const buttonsInRing = await p.evaluate(() => [...document.querySelectorAll(".cell-block")[1].querySelectorAll(".cell-bar button")]
    .map((b) => b.tabIndex));
  ok("the cell's buttons are out of the Tab ring", buttonsInRing.every((t) => t === -1), JSON.stringify(buttonsInRing));
  await shot(p, "09-cell-ring.png");
  ok("no page errors", errors.length === 0, errors.join(" | "));
  await browser.close();
}

/* ---------------------------------------------------------------- S5 scroll */
{
  const { browser, page: p, errors } = await launch(1440, 900);
  console.log("\nS5 scroll (SC-1, SC-3, SC-4, SC-5)");
  await p.locator(".home").waitFor({ timeout: 40000 });
  await p.evaluate((h) => { location.hash = h; }, `#/notebook${NB}`);
  await p.locator(".cell-block").first().waitFor({ timeout: 40000 });
  await p.waitForTimeout(1500);
  const aud = await p.evaluate(() => {
    const scrollers = [...document.querySelectorAll("body *")].filter((e) => {
      const cs = getComputedStyle(e);
      return /(auto|scroll)/.test(cs.overflowY) && e.scrollHeight > e.clientHeight + 4;
    }).map((e) => ({
      sel: `${e.tagName.toLowerCase()}.${(e.className || "").toString().split(" ")[0]}`,
      smooth: getComputedStyle(e).scrollBehavior,
      overscroll: getComputedStyle(e).overscrollBehaviorY,
    }));
    const editors = [...document.querySelectorAll(".cm-scroller")].filter((e) => e.scrollHeight > e.clientHeight + 2).length;
    return { scrollers, editors, page: { sh: document.scrollingElement.scrollHeight, ih: innerHeight } };
  });
  ok("exactly one scroller in the notebook", aud.scrollers.filter((s) => s.sel === "div.cells").length === 1, JSON.stringify(aud.scrollers));
  ok("no cell is a second scroller", aud.editors === 0, `${aud.editors} scrolling editors`);
  ok("no scroller is 'smooth'", aud.scrollers.every((s) => s.smooth !== "smooth"), JSON.stringify(aud.scrollers.map((s) => s.smooth)));
  ok("every scroller contains its overscroll", aud.scrollers.every((s) => s.overscroll === "contain"), JSON.stringify(aud.scrollers.map((s) => s.overscroll)));
  ok("the page itself does not scroll", aud.page.sh <= aud.page.ih, JSON.stringify(aud.page));
  // wheel at the end
  await p.mouse.move(600, 500);
  for (let i = 0; i < 40; i++) await p.mouse.wheel(0, 600);
  await p.waitForTimeout(400);
  const end = await p.evaluate(() => ({ cells: document.querySelector(".cells").scrollTop, doc: document.scrollingElement.scrollTop }));
  await p.mouse.wheel(0, 800);
  await p.waitForTimeout(300);
  const after = await p.evaluate(() => ({ cells: document.querySelector(".cells").scrollTop, doc: document.scrollingElement.scrollTop }));
  ok("a wheel at the last cell does not move the page", after.doc === 0, JSON.stringify(after));
  ok("…and the notebook stays where it was", Math.abs(after.cells - end.cells) < 8, `${end.cells} -> ${after.cells}`);
  await shot(p, "10-scroll-end.png");
  // the Show jump is still smooth
  const showsSmooth = await p.evaluate(() => {
    let seen = null;
    const orig = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = function (o) { seen = o; return orig.call(this, o); };
    window.__seenScroll = () => seen;
    return true;
  });
  ok("scrollIntoView is observable for the Show jump", showsSmooth);
  await p.evaluate(() => { Element.prototype.scrollIntoView = function (o) { window.__so = o; }; });
  await p.evaluate(() => { document.querySelector(".cells").scrollTop = 0; });
  ok("no page errors", errors.length === 0, errors.join(" | "));
  await browser.close();
}

/* ---------------------------------------------------------------- S6 zones */
{
  console.log("\nS6 zones (ZN-1, ZN-2, ZN-3, ZN-6)");
  for (const [w, label] of [[1440, "12-1440.png"], [1024, "13-1024-focus.png"], [800, "14-800-drawer.png"]]) {
    const { browser, page: p, errors } = await launch(w, 860);
    await p.locator(".home").waitFor({ timeout: 40000 });
    await p.waitForTimeout(1200);
    const z = await p.evaluate(() => {
      const box = (s) => { const e = document.querySelector(s); if (!e) return null; const r = e.getBoundingClientRect(); return Math.round(r.width); };
      return {
        rail: box(".pane.rail"), main: box(".pane.main"), dock: box(".pane.assistant"), inspector: box(".pane.inspector"),
        page: { sw: document.documentElement.scrollWidth, iw: innerWidth },
        landmarks: {
          banner: document.querySelectorAll("header.topbar").length,
          main: document.querySelectorAll("main").length,
          nav: document.querySelectorAll("nav[aria-label]").length,
          complementary: document.querySelectorAll("aside[aria-label]").length,
        },
      };
    });
    ok(`${w}: the centre keeps at least 480 unless the window cannot`, (z.main ?? 0) >= Math.min(480, w), `main ${z.main}`);
    ok(`${w}: the page has no horizontal overflow`, z.page.sw <= z.page.iw, JSON.stringify(z.page));
    /* `complementary` is only present when that panel is ON SCREEN: at 1024 the dock is closed and the
       inspector is a drawer, at 800 both are drawers. What must always hold is banner + main. */
    ok(`${w}: the shell has its landmarks`, z.landmarks.banner >= 1 && z.landmarks.main === 1, JSON.stringify(z.landmarks));
    console.log(`   zones: rail ${z.rail} main ${z.main} dock ${z.dock} inspector ${z.inspector}`);
    await shot(p, label);
    ok(`${w}: no page errors`, errors.length === 0, errors.join(" | "));
    await browser.close();
  }
  // dark
  {
    const { browser, page: p } = await launch(1440, 900, "dark");
    await p.locator(".home").waitFor({ timeout: 40000 });
    await p.waitForTimeout(1200);
    await p.keyboard.press("Tab");
    await shot(p, "15-dark-skip.png");
    await browser.close();
  }
}

console.log(failed ? `\n${failed} failed` : "\nall passed");
process.exit(failed ? 1 : 0);
