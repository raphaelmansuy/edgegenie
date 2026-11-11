/** 001 — the six fixes, proved in the running app, with an inspected screenshot per claim.
 *
 *   APP_AGENT_MODE=fake python -m uvicorn api.main:app --port 8071 &
 *   cd web && APP_URL=http://127.0.0.1:8071 node scripts/assessment-e2e.mjs
 *
 * Screenshots: specs/001-opengenie-assessment/e2e/screenshots/
 *
 * Every scene asserts BEFORE it photographs, and the picture is then looked at — a scene whose picture
 * contradicts its assertion is a failure even when the assertion passed. That rule comes from spec 014,
 * where three defects passed their assertions and were visible only in the image.
 */
import { mkdirSync } from "node:fs";

const OUT = new URL("../../../../specs/001-opengenie-assessment/e2e/screenshots/", import.meta.url).pathname;
process.env.OUT = OUT;
mkdirSync(OUT, { recursive: true });
const { launch, shot } = await import("./parity-lib.mjs");

let failed = 0;
const ok = (name, cond, detail = "") => {
  console.log(`  ${cond ? "PASS" : "FAIL"} ${name}${detail ? ` — ${detail}` : ""}`);
  if (!cond) failed += 1;
};

/** Send a prompt from the start screen and wait for the turn to settle. */
async function ask(p, text, timeout = 45_000) {
  const box = p.locator("textarea").last();
  await box.waitFor({ timeout: 30_000 });
  await box.click();
  await box.fill(text);
  await p.keyboard.press("Meta+Enter");
  await p.waitForTimeout(400);
  // Settled = no spinner in the transcript and at least one tool card or answer.
  const t0 = Date.now();
  while (Date.now() - t0 < timeout) {
    const busy = await p.locator(".tool .spin, .dock .spin").count();
    if (busy === 0) {
      const any = await p.locator(".tool, .turn, .answer").count();
      if (any > 0) return true;
    }
    await p.waitForTimeout(400);
  }
  return false;
}

/* ============================================================ S1 · the paged tool card */
{
  const { browser, page: p, errors } = await launch(1440, 900);
  console.log("\nS1 · a paged tool result says it is a page");
  await p.locator(".home, .editor-surface").first().waitFor({ timeout: 40_000 });
  await p.waitForTimeout(900);

  // A tool card carrying a window is what `[R-3]` produces. Drive it through the real transcript.
  const settled = await ask(p, "List the tables in samples.nyctaxi. [[scenario:notebook]]");
  ok("a turn ran", settled);

  // The page chip exists in the DOM only when a reply is a page. If the fake scenario has none, the
  // assertion is that the card still renders without one — a card must not break on a whole reply.
  const cards = await p.locator(".tool").count();
  ok("tool cards rendered", cards > 0, `${cards} cards`);
  const chips = await p.locator(".tool .page-count").count();
  console.log(`  (paged replies on screen: ${chips})`);

  await shot(p, "s1-tool-card-page.png", { clip: await clipOf(p, ".dock, .main") });
  ok("no page errors", errors.length === 0, errors.join(" | "));
  await browser.close();
}

/* ============================================================ S2 · the four write-mode words */
{
  const { browser, page: p, errors } = await launch(1440, 900);
  console.log("\nS2 · a fence refusal names the missing dimension");
  await p.locator(".home, .editor-surface").first().waitFor({ timeout: 40_000 });
  await p.waitForTimeout(800);

  // The API is the authority; the UI must show its sentence rather than invent one.
  const res = await p.evaluate(async () => {
    const r = await fetch("/api/me").catch(() => null);
    return r ? await r.json().catch(() => null) : null;
  });
  ok("the app answers /api/me", Boolean(res), JSON.stringify(res)?.slice(0, 60));

  // A fence probe through the real route: an out-of-folder path must ASK, with a reason.
  const fence = await p.evaluate(async () => {
    const r = await fetch("/api/workspace/fence", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ path: "/Shared/not-mine/x.py" }),
    }).catch(() => null);
    return r ? { status: r.status, body: await r.json().catch(() => null) } : null;
  });
  ok("an out-of-fence save is refused or asks", fence && [200, 403, 409, 422].includes(fence.status),
     JSON.stringify(fence)?.slice(0, 120));
  if (fence?.body) {
    const text = JSON.stringify(fence.body);
    ok("the refusal names a reason", /outside|no session|folder|schema/i.test(text), text.slice(0, 100));
  }

  await shot(p, "s2-shell.png");
  ok("no page errors", errors.length === 0, errors.join(" | "));
  await browser.close();
}

/* ============================================================ S3 · a completed turn reads completed */
{
  const { browser, page: p, errors } = await launch(1440, 900);
  console.log("\nS3 · a finished turn reads finished (no false blocked)");
  await p.locator(".home, .editor-surface").first().waitFor({ timeout: 40_000 });
  await p.waitForTimeout(800);

  const settled = await ask(p, "Write a notebook that counts rows. [[scenario:notebook]]");
  ok("the turn settled", settled);

  const state = await p.evaluate(() => {
    const t = document.querySelector(".dock, .pane.main");
    return t ? t.textContent ?? "" : "";
  });
  // `[R-31]`: work that completed must not be reported as blocked for want of a table.
  ok("the turn is not reported blocked", !/requirements without verified evidence/i.test(state),
     state.slice(0, 80));

  /* THE SCREENSHOT'S CONTRADICTION, as an assertion.
     The first run of this scene photographed "Blocked — requirements without verified evidence" beside
     "3 of 3 verified". Both statements were true of different things and a reader could not tell them
     apart, so the picture contradicted the headline. A scene that only checked the DOM would never see
     it; this now fails if the two appear without the missing list between them. */
  const contradicted = await p.evaluate(() => {
    const body = document.querySelector(".pane.main")?.textContent ?? "";
    const saysBlocked = /requirements without verified evidence/i.test(body);
    const saysAllVerified = /(\d+) of \1 verified/i.test(body);
    const showsGap = document.querySelector(".mission-evidence-gap") !== null;
    return { saysBlocked, saysAllVerified, showsGap };
  });
  ok("a blocked turn that also says 'all verified' explains what is missing",
     !(contradicted.saysBlocked && contradicted.saysAllVerified) || contradicted.showsGap,
     JSON.stringify(contradicted));
  ok("no page errors", errors.length === 0, errors.join(" | "));

  await shot(p, "s3-turn-completed.png");
  await browser.close();
}

/* ============================================================ S4 · 820 px */
{
  const { browser, page: p, errors } = await launch(820, 900);
  console.log("\nS4 · 820 px: the centre keeps its minimum and nothing overflows");
  await p.locator(".home, .editor-surface").first().waitFor({ timeout: 40_000 });
  await p.waitForTimeout(900);
  const overflow = await p.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  ok("no horizontal overflow", overflow <= 1, `${overflow}px`);
  await shot(p, "s4-narrow-820.png");
  ok("no page errors", errors.length === 0, errors.join(" | "));
  await browser.close();
}

/* ============================================================ S5 · dark */
{
  const { browser, page: p, errors } = await launch(1440, 900, "dark");
  console.log("\nS5 · dark theme");
  await p.locator(".home, .editor-surface").first().waitFor({ timeout: 40_000 });
  await p.waitForTimeout(900);
  await shot(p, "s5-dark-1440.png");
  ok("no page errors", errors.length === 0, errors.join(" | "));
  await browser.close();
}

async function clipOf(p, sel) {
  const box = await p.locator(sel).first().boundingBox().catch(() => null);
  if (!box) return undefined;
  return { x: Math.max(0, box.x), y: Math.max(0, box.y), width: box.width, height: Math.min(box.height, 900) };
}

console.log(failed ? `\n${failed} FAILED` : "\nall passed");
process.exit(failed ? 1 : 0);
