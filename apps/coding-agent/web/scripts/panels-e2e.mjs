/** Every panel must be recoverable from every reachable state, at every width.
 *
 * The bug this exists for: the layout menu listed Navigator and Inspector but not the Assistant, and
 * the inspector's every control was disabled when no session was open — so a panel could be hidden
 * with no way back (`specs/007-ux-ui-improve`, `ZN-7`).
 *
 * The invariant, asserted as a property rather than as three ad-hoc checks:
 *
 *   For every zone Z, at every width W, in every session state S:
 *     hide Z  ⇒  some ENABLED, VISIBLE control restores it  ⇒  Z is drawn again.
 *
 * "Visible" means hit-testable at its centre, not merely `offsetParent !== null`: a control clipped by
 * an `overflow: hidden` ancestor is present and unclickable, which the first audit missed entirely.
 *
 *   APP_URL=http://127.0.0.1:8062 node scripts/panels-e2e.mjs
 */
import { mkdirSync } from "node:fs";
const OUT = new URL("../../../../specs/007-ux-ui-improve/e2e/screenshot/", import.meta.url).pathname;
process.env.OUT = OUT;
mkdirSync(OUT, { recursive: true });
const { launch, shot } = await import("./parity-lib.mjs");

const NB = "/Users/raphael.mansuy@gmail.com/agent_scratch/tall_demo";
/* `hide`/`show` name the TOP-BAR toggle for each zone, and they must match it and nothing else: the
   edge handle is a second control with a related name, and once both matched, `getByRole(...).first()`
   could resolve to either — strict-mode ambiguity in one run and a wrong element in the next. The
   handle is checked separately, below, precisely because it is a different control with a different
   job. `handle` is the word drawn on that handle, which its accessible name must contain (WCAG 2.5.3).
   `drawer` is the class the inspector gets when it has no track of its own. */
const ZONES = [
  { name: "navigator", sel: ".pane.rail", hide: /^Hide the navigator$/, show: /^Show the navigator$/, handle: /Files panel/ },
  { name: "assistant", sel: "#dock", hide: /^Hide the assistant$/, show: /^Show the assistant$/, handle: /Chat panel/ },
  { name: "inspector", sel: ".insp-body", hide: /^Hide the inspector$/, show: /^Show the inspector$/, handle: /Context panel/ },
];
let failed = 0;
const ok = (n, c, d = "") => { console.log(`  ${c ? "PASS" : "FAIL"} ${n}${d ? ` — ${d}` : ""}`); if (!c) failed++; };

/** Is this element actually reachable: on screen, not clipped, and topmost at its centre? */
const reachable = (p, selector) => p.evaluate((sel) => {
  const el = document.querySelector(sel);
  if (!el) return { present: false };
  const r = el.getBoundingClientRect();
  if (r.width === 0 || r.height === 0) return { present: true, why: "zero size" };
  const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
  if (cx < 0 || cy < 0 || cx > innerWidth || cy > innerHeight) return { present: true, why: `centre off screen (${Math.round(cx)},${Math.round(cy)})` };
  const top = document.elementFromPoint(cx, cy);
  const hit = top === el || el.contains(top) || top?.closest("button, a, [role=menuitemcheckbox]") === el;
  return { present: true, reachable: hit, why: hit ? "" : `covered by ${top?.tagName}.${(top?.className || "").toString().split(" ")[0]}` };
}, selector);

const drawn = (p, selector) => p.evaluate((sel) => !!document.querySelector(sel), selector);

for (const width of [1440, 1135, 1024, 900, 800, 700]) {
  for (const session of [false, true]) {
    const { browser, page: p, errors } = await launch(width, 900);
    await p.locator(".home").waitFor({ timeout: 40000 });
    if (session) { await p.locator("textarea").last().fill("hello"); await p.keyboard.press("Enter"); await p.waitForTimeout(3800); }
    await p.evaluate((h) => { location.hash = h; }, `#/notebook${NB}`);
    await p.locator(".cell-block").first().waitFor({ timeout: 45000 });
    await p.waitForTimeout(1300);
    console.log(`\n--- ${width}px, ${session ? "with" : "without"} a session`);

    for (const z of ZONES) {
      if (!(await drawn(p, z.sel))) {
        // Not drawn to begin with: the recovery control must still be able to draw it.
        const ctl = p.getByRole("button", { name: z.show }).first();
        const n = await ctl.count();
        ok(`${z.name}: an enabled control can draw it from hidden`, n > 0 && (await ctl.isEnabled()));
        if (n > 0 && await ctl.isEnabled()) { await ctl.click({ force: true }); await p.waitForTimeout(700); }
        ok(`${z.name}: …and it is drawn`, await drawn(p, z.sel));
        continue;
      }
      const hide = p.getByRole("button", { name: z.hide }).first();
      if ((await hide.count()) === 0) { ok(`${z.name}: has a hide control`, false); continue; }
      await hide.click({ force: true });
      await p.waitForTimeout(500);
      ok(`${z.name}: hides`, !(await drawn(p, z.sel)));
      const show = p.getByRole("button", { name: z.show }).first();
      const exists = (await show.count()) > 0;
      ok(`${z.name}: a restore control exists and is enabled`, exists && (await show.isEnabled().catch(() => false)));
      if (!exists) continue;
      const hit = await reachable(p, `.shell-toggle[aria-label="${await show.getAttribute("aria-label")}"]`);
      ok(`${z.name}: …and it is actually clickable`, hit.reachable === true, hit.why ?? "");
      await show.click({ force: true });
      await p.waitForTimeout(700);
      ok(`${z.name}: restores`, await drawn(p, z.sel));
    }

    /* The edge handle: the way back that is WHERE the panel would be. The top-bar toggle proving the
       panel recoverable is not enough — the report was a discoverability failure, so the handle is a
       requirement, not a convenience. A handle is shown for a hidden panel and never for a shown one. */
    const handleLabels = await p.evaluate(() =>
      [...document.querySelectorAll(".edge-handle")].map((b) => b.getAttribute("aria-label") || ""));
    for (const z of ZONES) {
      const shown = await drawn(p, z.sel);
      // The handle's name contains the word it draws, so match on that word — and also assert the
      // word is really there, which is the Label-in-Name guarantee (WCAG 2.5.3).
      const offered = handleLabels.some((l) => z.handle.test(l));
      ok(`${z.name}: edge handle ${shown ? "absent while shown" : "present while hidden"}`,
        shown ? !offered : offered, JSON.stringify(handleLabels));
    }

    // The layout menu must offer all three, from any state.
    await p.getByRole("button", { name: /Layout and panels/i }).click();
    await p.waitForTimeout(400);
    const items = await p.evaluate(() => [...document.querySelectorAll("[role=menu] [role^=menuitem]")]
      .map((b) => ({ text: b.textContent.replace(/\s+/g, " ").trim(), disabled: b.disabled })));
    const named = (re) => items.find((i) => re.test(i.text));
    ok("the layout menu lists the navigator", Boolean(named(/Navigator/)), JSON.stringify(items));
    ok("the layout menu lists the assistant", Boolean(named(/Assistant/)));
    ok("the layout menu lists the inspector", Boolean(named(/Inspector/)));
    ok("…and none of the three is disabled", [named(/Navigator/), named(/Assistant/), named(/Inspector/)].every((i) => i && !i.disabled));
    await p.keyboard.press("Escape");
    await p.waitForTimeout(300);

    if (width === 1440 && session) {
      // Hide all three, then restore all three — the state the report came from.
      for (const z of ZONES) {
        const hide = p.getByRole("button", { name: z.hide }).first();
        if (await hide.count()) { await hide.click({ force: true }); await p.waitForTimeout(350); }
      }
      await shot(p, "30-all-panels-hidden.png");
      for (const z of ZONES) {
        const show = p.getByRole("button", { name: z.show }).first();
        if (await show.count()) { await show.click({ force: true }); await p.waitForTimeout(450); }
      }
      const all = await Promise.all(ZONES.map((z) => drawn(p, z.sel)));
      ok("all three panels come back after being hidden", all.every(Boolean), JSON.stringify(all));
      /* Opening the conversation must not close the inspector: on the right they are siblings, and a
         shared drawer slot made one close the other (`ZN-9`). */
      ok("the conversation and the inspector coexist", (await drawn(p, "#dock")) && (await drawn(p, ".insp-body")));
      await shot(p, "31-all-panels-restored.png");
    }
    if (width === 1440 && !session) {
      const insp = p.getByRole("button", { name: /inspector/i }).first();
      /* The loop above has already toggled the inspector twice, so its state here is not known: ask
         for the state we want instead of toggling blindly. Clicking a toggle whose state you assume
         is how this check failed twice while the app was correct. */
      if ((await p.locator(".insp-body").count()) === 0 && (await insp.count())) {
        await insp.click({ force: true });
      }
      // The drawer animates in; read it once it is on screen, not 700 ms into a 160 ms animation
      // that had not started (the first run read an empty body and reported a false failure).
      await p.locator(".insp-body").waitFor({ timeout: 8000 }).catch(() => {});
      await p.waitForTimeout(400);
      const text = await p.locator(".insp-body").innerText().catch(() => "");
      ok("with no session the inspector still explains itself", text.length > 40, text.slice(0, 60).replace(/\n/g, " "));
      await shot(p, "32-inspector-no-session.png");
    }
    ok(`${width}/${session}: no page errors`, errors.length === 0, errors.join(" | "));
    await browser.close();
  }
}
console.log(failed ? `\n${failed} failed` : "\nall passed");
process.exit(failed ? 1 : 0);
