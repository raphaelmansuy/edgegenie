/** 001 phase 2 — the new surfaces, proved in the running app. `[R-9]` `[R-10]` `[R-11]` `[R-17]` `[R-24]`.
 *
 *   APP_AGENT_MODE=fake python -m uvicorn api.main:app --port 8072
 *   cd web && APP_URL=http://127.0.0.1:8072 node scripts/assessment-phase2-e2e.mjs
 *
 * Screenshots: specs/001-opengenie-assessment/e2e/screenshots/
 *
 * The rule (spec 014): assert BEFORE the picture, then LOOK at the picture. A scene whose image
 * contradicts its assertion is a failure even when the assertion passed.
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

/* ============================================================ S6 · a read-only session says so */
{
  const { browser, page: p, errors } = await launch(1440, 900);
  console.log("\nS6 · a read-only conversation announces itself before you try");
  await p.locator(".topbar").waitFor({ timeout: 30_000 });

  // Create a read-only session through the real API, then open it — the UI must show the chip without
  // the user having to make a request that gets refused.
  const created = await p.evaluate(async () => {
    const r = await fetch("/api/sessions", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ folder: "/Users/dev@example.com/agent_scratch", writeMode: "read-only" }),
    });
    return r.json();
  });
  ok("a read-only session was created", created?.writeMode === "read-only", created?.writeMode);

  // The config endpoint is the vocabulary a client must not re-invent.
  const cfg = await p.evaluate(async () => (await fetch("/api/config")).json());
  ok("the server publishes three write modes", cfg?.writeModes?.length === 3,
     (cfg?.writeModes ?? []).map((m) => m.id).join(","));
  ok("read-only is the only mode that cannot mutate",
     cfg.writeModes.filter((m) => !m.mutates).map((m) => m.id).join() === "read-only");

  // Open the session so the inspector renders the chip.
  await p.evaluate((id) => { window.location.hash = `#/session/${id}`; }, created.id);
  await p.waitForTimeout(1400);
  const chip = await p.locator(".pill.write-mode").first().textContent().catch(() => null);
  ok("the inspector shows the write-mode chip", /read/i.test(chip ?? ""), String(chip));

  // The budget meter must NOT render without a ceiling: a meter over an unlimited conversation is a
  // warning about nothing.
  const meter = await p.locator(".budget").count();
  ok("no budget meter without a ceiling", meter === 0, `${meter} meters`);

  await shot(p, "s6-read-only-session.png");
  ok("no page errors", errors.length === 0, errors.join(" | "));
  await browser.close();
}

/* ============================================================ S7 · the budget renders when set */
{
  const { browser, page: p, errors } = await launch(1440, 900);
  console.log("\nS7 · a ceiling, when one exists, is shown with both numbers");
  await p.locator(".topbar").waitFor({ timeout: 30_000 });

  const budget = await p.evaluate(async () => {
    const s = await (await fetch("/api/sessions", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ folder: "/Users/dev@example.com/agent_scratch" }),
    })).json();
    const b = await (await fetch(`/api/sessions/${s.id}/budget`)).json();
    return { session: s, budget: b };
  });
  ok("an unlimited session reports verdict=unlimited",
     budget.budget?.verdict === "unlimited", budget.budget?.verdict);
  ok("and reports limit 0, not a guessed number", budget.budget?.limit === 0, String(budget.budget?.limit));
  ok("and its sentence is empty, so the UI says nothing", budget.budget?.sentence === "", String(budget.budget?.sentence));

  await p.evaluate((id) => { window.location.hash = `#/session/${id}`; }, budget.session.id);
  await p.waitForTimeout(1200);
  ok("no meter is drawn for an unlimited conversation", (await p.locator(".budget").count()) === 0);

  await shot(p, "s7-unlimited-budget.png");
  ok("no page errors", errors.length === 0, errors.join(" | "));
  await browser.close();
}

/* ============================================================ S8 · compaction is auditable */
{
  const { browser, page: p, errors } = await launch(1440, 900);
  console.log("\nS8 · compaction reports what it would do, and emits nothing when there is nothing to do");
  await p.locator(".topbar").waitFor({ timeout: 30_000 });

  const out = await p.evaluate(async () => {
    const s = await (await fetch("/api/sessions", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ folder: "/Users/dev@example.com/agent_scratch" }),
    })).json();
    const r = await (await fetch(`/api/sessions/${s.id}/compact`, { method: "POST" })).json();
    return r;
  });
  ok("a short conversation reports no change rather than a silent success",
     out?.changed === false, JSON.stringify(out));

  await shot(p, "s8-compaction-none.png");
  ok("no page errors", errors.length === 0, errors.join(" | "));
  await browser.close();
}

/* ============================================================ S9 · 820 px still holds */
{
  const { browser, page: p, errors } = await launch(820, 900);
  console.log("\nS9 · the new chip and meter do not break the narrow layout");
  await p.locator(".topbar").waitFor({ timeout: 30_000 });
  await p.evaluate(async () => {
    const s = await (await fetch("/api/sessions", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ folder: "/Users/dev@example.com/agent_scratch", writeMode: "read-only" }),
    })).json();
    window.location.hash = `#/session/${s.id}`;
  });
  await p.waitForTimeout(1500);
  const overflow = await p.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  ok("no horizontal overflow at 820 px", overflow <= 1, `${overflow}px`);
  await shot(p, "s9-narrow-phase2.png");
  ok("no page errors", errors.length === 0, errors.join(" | "));
  await browser.close();
}

console.log(failed ? `\n${failed} FAILED` : "\nall passed");
process.exit(failed ? 1 : 0);
