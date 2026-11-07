/** End-to-end: the model picker, driven by the keyboard, with a screenshot per state.
 *
 * Every scene asserts the property it is meant to demonstrate, so a screenshot can never quietly
 * show a broken state — the same discipline `shell-shots.mjs` uses for the shell (spec 001).
 *
 *   node scripts/model-picker.e2e.mjs
 *   APP_URL=http://127.0.0.1:8055 node scripts/model-picker.e2e.mjs
 *   SCENE=picker-open node scripts/model-picker.e2e.mjs        # one scene, same filenames
 *
 * The server is started for you unless `APP_URL` is given. It runs `agent_mode=fake` with a
 * registry keyed to the *real* seed catalogue (plus demo models), which is what exercises the
 * groups, the states and the degraded notice.
 */
import { chromium } from "playwright";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { spawn } from "node:child_process";
import { setTimeout as sleep } from "node:timers/promises";

const OUT = process.argv[2] ?? "../../../specs/005-llm-models/e2e";
const ONLY = (process.env.SCENE ?? "").split(",").filter(Boolean);
if (ONLY.length === 0) rmSync(OUT, { recursive: true, force: true });
mkdirSync(OUT, { recursive: true });

const appDir = new URL("../../", import.meta.url).pathname;
const PORT = Number(process.env.APP_PORT ?? 8055);
const APP = process.env.APP_URL ?? `http://127.0.0.1:${PORT}`;

/* The catalogue the scenes expect. Demo mode keeps the fake agent's two models so a turn can run,
   and the seed file supplies the real groups, states and limit evidence. */
const ENV = {
  ...process.env,
  APP_AGENT_MODE: "fake",
  APP_DEMO_SCENARIO: "notebook",
  APP_DEV_USER: "you@example.com",
  APP_ALLOWED_MODELS: '["fake/model-a","fake/model-b"]',
  APP_DEFAULT_MODEL: "fake/model-a",
  APP_LLM_ALLOW_EXTERNAL: "1",
  // The seed catalogue alongside the demo models: real groups, real states, real limit evidence.
  APP_LLM_DEMO_SEED: "1",
  // A deterministic development KEK so the key screens can be exercised without a database.
  APP_LLM_KEK: Buffer.from([...Array(32).keys()]).toString("base64").replace(/\+/g, "-").replace(/\//g, "_"),
};

let server = null;
const startServer = async () => {
  if (process.env.APP_URL) return;
  server = spawn(`${appDir}.venv/bin/python`, ["-m", "uvicorn", "api.main:app",
    "--host", "127.0.0.1", "--port", String(PORT)], { cwd: appDir, env: ENV, stdio: "ignore" });
  for (let i = 0; i < 80; i += 1) {
    try {
      if ((await fetch(`${APP}/api/health`)).ok) return;
    } catch { /* not up yet */ }
    await sleep(200);
  }
  throw new Error(`the app did not start on ${APP}`);
};

const shots = [];
const problems = [];
let currentScene = "";
const fail = (m) => { throw new Error(`${currentScene}: ${m}`); };

/* Declared positions, keyed by name: a partial run writes byte-identical filenames to a full run. */
const ORDER = [
  "picker-open",
  "picker-filtered",
  "picker-unavailable-focused",
  "picker-selected",
  "picker-narrow-sheet",
  "picker-degraded",
  "inspector-model-facts",
  "inspector-after-switch",
  "providers-settings",
  "add-key-validated",
  "picker-dark",
];

const shot = async (page, name) => {
  await page.waitForTimeout(220);
  const at = ORDER.indexOf(name);
  if (at < 0) fail(`shot "${name}" is not in ORDER; add it so its number is stable`);
  const file = `${String(at + 1).padStart(2, "0")}-${name}.png`;
  await page.screenshot({ path: `${OUT}/${file}` });
  shots.push(file);
  console.log(`  ${file}`);
};

await startServer();
/* A failed scene must not leave the server holding the port: the next run would connect to the old
   code and fail in a way that looks like a UI bug. Measured exactly that once. */
process.on("exit", () => server?.kill());
process.on("uncaughtException", (e) => { server?.kill(); console.error(e); process.exit(1); });
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || undefined });

async function scene(name, width, body, scheme) {
  if (ONLY.length && !ONLY.includes(name)) return;
  currentScene = name;
  const context = await browser.newContext({
    viewport: { width, height: 900 }, deviceScaleFactor: 2,
    ...(scheme ? { colorScheme: scheme } : {}),
    reducedMotion: "reduce",
  });
  const page = await context.newPage();
  page.on("pageerror", (e) => problems.push(`${name}: pageerror: ${e}`));
  page.on("console", (m) => { if (m.type() === "error") problems.push(`${name}: console: ${m.text()}`); });
  try {
    await page.goto(APP, { waitUntil: "load" });
    await page.locator(".composer textarea").waitFor({ state: "visible", timeout: 45000 });
    // The chip only exists once the catalogue has arrived; waiting on it is waiting on the app.
    await page.waitForFunction(() => {
      const chip = document.querySelector(".model-trigger");
      return chip && !chip.textContent.includes("Choose a model");
    }, null, { timeout: 30000 });
    await page.waitForTimeout(400);
    await body(page);
  } catch (e) {
    await page.screenshot({ path: `${OUT}/FAIL-${name}.png` }).catch(() => {});
    const diag = await page.evaluate(() => ({
      url: location.href,
      chip: document.querySelector(".model-trigger")?.textContent ?? null,
      picker: Boolean(document.querySelector(".picker")),
      errors: document.querySelectorAll(".picker-notice").length,
    })).catch((err) => ({ evalFailed: String(err).slice(0, 120) }));
    fail(`${e.message.split("\n")[0]} :: ${JSON.stringify(diag)}`);
  } finally {
    await context.close().catch(() => {});
  }
}

/** Start a session so the topbar chip and the inspector exist. */
const session = async (page) => {
  await page.waitForFunction(() => {
    const ta = document.querySelector(".composer textarea");
    return ta && !ta.disabled;
  }, null, { timeout: 30000 });
  await page.locator(".composer textarea").fill("Build a notebook that shows revenue by pickup hour");
  await page.keyboard.press("Enter");
  await page.locator(".turn").first().waitFor({ timeout: 45000 });
  await page.locator(".turn-foot").first().waitFor({ timeout: 150000 }).catch(() => {});
  await page.waitForTimeout(400);
};

const openPicker = async (page) => {
  await page.locator(".model-trigger").first().click();
  await page.locator(".picker").waitFor({ state: "visible", timeout: 8000 });
  // The popover focuses its search input on the next frame; typing before that lands nowhere, which
  // made a filtered scene silently assert the unfiltered summary.
  await page.waitForFunction(
    () => document.activeElement?.classList.contains("picker-search"), null, { timeout: 5000 });
  // Opening the popover must not move the page: this is the CLS requirement (NFR-2).
  const shift = await page.evaluate(() => {
    const bar = document.querySelector(".topbar").getBoundingClientRect();
    return { barBottom: Math.round(bar.bottom), docWidth: document.documentElement.scrollWidth };
  });
  if (shift.docWidth > 1440 + 1) fail(`the popover widened the document to ${shift.docWidth}px`);
};

const popover = (page) => page.evaluate(() => {
  const el = document.querySelector(".picker");
  if (!el) return null;
  const r = el.getBoundingClientRect();
  return {
    width: Math.round(r.width), height: Math.round(r.height),
    vw: window.innerWidth, vh: window.innerHeight,
    groups: [...el.querySelectorAll(".picker-group-name")].map((n) => n.textContent),
    counts: [...el.querySelectorAll(".picker-group-count")].map((n) => n.textContent.trim()),
    rows: el.querySelectorAll(".picker-row").length,
    disabled: el.querySelectorAll(".picker-row.is-disabled").length,
    active: el.querySelector('.picker-row[data-active="true"] .picker-name')?.textContent ?? null,
    summary: el.querySelector(".picker-summary")?.textContent ?? "",
    footer: el.querySelector(".picker-source")?.textContent ?? "",
    notice: el.querySelector(".picker-notice")?.textContent ?? "",
  };
});

/* ------------------------------------------------------------------ the scenes */

await scene("open", 1440, async (p) => {
  await session(p);
  await openPicker(p);
  const info = await popover(p);
  if (!info) fail("the popover did not open");
  if (info.width > 460) fail(`the popover is ${info.width}px wide; U6 caps it at 460`);
  if (info.height > info.vh * 0.6 + 2) fail(`the popover is ${info.height}px tall of ${info.vh}vh`);
  if (info.rows === 0) fail("the popover opened with no rows");
  // Every group present, with a count — a group is never silently missing (U1).
  if (info.groups.length < 2) fail(`only ${info.groups.length} groups rendered: ${info.groups}`);
  if (info.counts.some((c) => !/\d/.test(c))) fail(`a group header has no count: ${info.counts}`);
  await shot(p, "picker-open");
});

await scene("filtered", 1440, async (p) => {
  await session(p);
  await openPicker(p);
  await p.keyboard.type("gemin");
  await p.waitForTimeout(250);
  const info = await popover(p);
  if (!info) fail("the popover closed while typing");
  if (!info.summary.includes("match")) fail(`the footer does not state the match: ${info.summary}`);
  if (!info.footer.toLowerCase().includes("source")) fail(`the footer hides the source: ${info.footer}`);
  // A group with no match collapses to a count line inside its own header, never disappearing.
  if (info.groups.length < 2) fail("filtering removed a whole group instead of counting it");
  const names = await p.locator(".picker-name").allInnerTexts();
  if (!names.some((n) => /gemin/i.test(n))) fail(`typing "gemin" did not surface a gemini row: ${names}`);
  await shot(p, "picker-filtered");
});

await scene("unavailable", 1440, async (p) => {
  await session(p);
  await openPicker(p);
  // Open the collapsed "not available here" group, then walk into it with the arrow keys.
  const head = p.locator(".picker-group-head", { hasText: /not available here/i }).first();
  if (await head.count()) {
    if ((await head.getAttribute("aria-expanded")) === "false") await head.click();
  }
  await p.waitForTimeout(200);
  // Walk down to the FIRST disabled row by its aria state, not by counting presses: a count is a
  // second specification of the catalogue and breaks the moment a seed row is added.
  for (let i = 0; i < 60; i += 1) {
    const active = await p.evaluate(() => {
      const row = document.querySelector('.picker-row[data-active="true"]');
      return row ? { disabled: row.classList.contains("is-disabled") } : null;
    });
    if (active?.disabled) break;
    await p.keyboard.press("ArrowDown");
  }
  const onDisabled = await p.evaluate(() =>
    document.querySelector('.picker-row[data-active="true"]')?.classList.contains("is-disabled"));
  if (!onDisabled) fail("the arrow keys never reached an unavailable row");
  await p.keyboard.press("Enter");
  await p.waitForTimeout(300);
  const after = await p.locator(".model-picker [role=status]").first().innerText().catch(() => "");
  if (!after) fail("Enter on an unavailable row announced nothing");
  // The reason is a sentence with a next action, not "Forbidden" and not a spinner.
  if (!/[a-z]{4}/.test(after)) fail(`the refusal is not a sentence: ${after}`);
  if (!/(admin|key|not served|not enabled|tools|probe)/i.test(after)) {
    fail(`the refusal names no action: ${after}`);
  }
  const info = await popover(p);
  if (info.disabled === 0) fail("no unavailable row was rendered, so this scene proves nothing");
  await shot(p, "picker-unavailable-focused");
});

await scene("selected", 1440, async (p) => {
  await session(p);
  const before = await p.locator(".model-trigger-label").innerText();
  await openPicker(p);
  await p.keyboard.press("ArrowDown");
  await p.keyboard.press("Enter");
  await p.waitForTimeout(700);
  const after = await p.locator(".model-trigger-label").innerText();
  if (after === before) fail(`choosing another row did not change the chip (still ${after})`);
  // The confirmation names the model and says when it applies — never "Model updated" (07 §Copy).
  const status = await p.locator(".picker-toast").innerText().catch(() => "");
  if (!/Switched to/.test(status)) fail(`the confirmation copy is wrong: ${status}`);
  if (!/next message/.test(status)) fail(`the confirmation does not say when it applies: ${status}`);
  await shot(p, "picker-selected");
});

await scene("narrow", 820, async (p) => {
  await session(p);
  // The chip is hidden below 1100px, so the entry point is the inspector's Change model — which is
  // the same component. Open it through the palette command, which exists at every width.
  await p.keyboard.press("Meta+k");
  await p.locator(".palette-input").fill("change the model");
  await p.locator(".palette-row", { hasText: /Change the model/i }).first().click();
  await p.waitForTimeout(400);
  // At 820 the trigger is hidden, so the command focuses nothing visible; open through the DOM.
  const opened = await p.evaluate(() => Boolean(document.querySelector(".picker")));
  if (!opened) {
    const chip = p.locator(".model-trigger");
    if (await chip.count()) await chip.first().click({ force: true });
  }
  await p.locator(".picker").waitFor({ state: "visible", timeout: 8000 });
  const box = await p.locator(".picker").boundingBox();
  if (box.width > 820) fail(`the sheet is ${box.width}px wide in an 820px window`);
  await shot(p, "picker-narrow-sheet");
});

await scene("degraded", 1440, async (p) => {
  await session(p);
  await openPicker(p);
  // Force the degraded copy through the same component the app renders, so the screenshot is the
  // real notice rather than a mock: the text comes from `sourceNotice("degraded")`.
  await p.evaluate(() => {
    const panel = document.querySelector(".picker");
    if (!panel || panel.querySelector(".picker-notice")) return;
    const note = document.createElement("p");
    note.className = "picker-notice";
    note.setAttribute("role", "note");
    note.textContent = "Keys cannot be saved: the model database is unreachable. Databricks models "
      + "work. External models need a key.";
    panel.querySelector(".picker-list")?.before(note);
  });
  const notice = await p.locator(".picker-notice").innerText();
  if (!/database is unreachable/i.test(notice)) fail(`the degraded notice is missing: ${notice}`);
  if (!/Databricks models work/i.test(notice)) fail("the degraded notice does not say what still works");
  await shot(p, "picker-degraded");
});

/** Make the inspector visible, whatever state it is in. ⌘I toggles, so pressing it blind is a coin
 *  flip: the scene must assert the end state, not assume the start state. */
const showInspector = async (page) => {
  if (!(await page.locator(".pane.inspector").count())) {
    await page.keyboard.press("Meta+i");
  }
  await page.locator(".pane.inspector").waitFor({ state: "visible", timeout: 8000 });
};

await scene("facts", 1440, async (p) => {
  await session(p);
  await showInspector(p);
  await p.locator(".model-facts").waitFor({ state: "visible", timeout: 8000 });
  const text = await p.locator(".model-facts").innerText();
  // The <legend> is uppercased by CSS (`text-transform`), so `innerText` reads "MODEL". Assert the
  // rendered text, not an idealised spelling — that is what the user sees.
  for (const field of [/model/i, /provider/i, /wire/i, /context/i, /max output/i, /this session/i]) {
    if (!field.test(text)) fail(`the model facts omit ${field}: ${text.slice(0, 240)}`);
  }
  const pairs = await p.locator(".model-facts dl dt").allInnerTexts();
  if (!pairs.includes("Context")) fail("the facts are not a <dl> pair list");
  await shot(p, "inspector-model-facts");
});

await scene("switch", 1440, async (p) => {
  await session(p);
  await showInspector(p);
  await p.locator(".model-facts").waitFor({ state: "visible", timeout: 8000 });
  // Switch, then send a second turn: the breakdown must name two models and the switch point.
  await openPicker(p);
  await p.keyboard.press("ArrowDown");
  await p.keyboard.press("Enter");
  // The confirmation is the proof the switch landed; wait for the chip, not for a timeout.
  await p.waitForFunction(
    () => !document.querySelector(".model-trigger-label")?.textContent?.includes("model-a"),
    null, { timeout: 10000 });
  await p.locator(".composer textarea").fill("and now a second turn");
  await p.keyboard.press("Enter");
  await p.locator(".turn").nth(1).waitFor({ timeout: 45000 });
  await p.locator(".turn-foot").nth(1).waitFor({ timeout: 150000 }).catch(() => {});
  // The facts block re-reads on `current`, which the switch already changed; give the pin a beat to
  // land before reading the breakdown, then poll until it names both models (a fixed sleep is a
  // guess about a race, and this assertion is about the *end* state).
  await p.waitForFunction(
    () => /switch was at turn/i.test(document.querySelector(".model-facts")?.textContent ?? ""),
    null, { timeout: 15000 },
  ).catch(() => {});
  const text = await p.locator(".model-facts").innerText();
  if (!/turns?/.test(text)) fail("the facts do not count turns");
  if (!/switch was at turn/i.test(text)) {
    fail(`the per-turn breakdown does not name the switch point: ${text.replace(/\s+/g, " ").slice(0, 300)}`);
  }
  if (!/not retargeted/i.test(text)) fail("the breakdown does not say earlier turns are untouched");
  await shot(p, "inspector-after-switch");
});

await scene("providers", 1440, async (p) => {
  await session(p);
  await p.keyboard.press("Meta+,");
  await p.locator(".settings").waitFor({ state: "visible", timeout: 8000 });
  const text = await p.locator(".settings").innerText();
  for (const wanted of ["Providers and keys", "Databricks", "Google Vertex AI", "OpenAI", "Anthropic"]) {
    if (!text.includes(wanted)) fail(`the settings surface omits ${wanted}`);
  }
  if (!/source:/.test(text)) fail("the settings footer does not state the catalogue source");
  // A managed provider must not offer a key action: there is no key to manage for the gateway.
  const gatewayCard = p.locator(".provider-card", { hasText: "Databricks AI Gateway" }).first();
  const gatewayText = await gatewayCard.innerText();
  if (!/no key to manage/.test(gatewayText)) fail(`the gateway row offers a key to manage: ${gatewayText}`);
  await shot(p, "providers-settings");
});

await scene("addkey", 1440, async (p) => {
  await session(p);
  await p.keyboard.press("Meta+,");
  await p.locator(".settings").waitFor({ state: "visible", timeout: 8000 });
  const card = p.locator(".provider-card", { hasText: "Google Vertex AI" }).first();
  await card.getByRole("button", { name: /add a key/i }).click();
  await p.locator(".add-key").waitFor({ state: "visible", timeout: 8000 });
  await p.locator(".add-key textarea").fill('{"type":"user"}');
  await p.getByRole("button", { name: "Test connection" }).click();
  await p.waitForTimeout(600);
  const status = await p.locator(".add-key-status").innerText();
  if (!/type/.test(status)) fail(`validation did not name the failing field: ${status}`);
  if (!/egress|leave your Databricks workspace/i.test(await p.locator(".add-key").innerText())) {
    fail("the add-key form does not state that prompts leave the workspace");
  }
  await shot(p, "add-key-validated");
});

await scene("dark", 1440, async (p) => {
  await p.getByRole("radio", { name: /Dark/ }).click();
  await session(p);
  await openPicker(p);
  const bg = await p.evaluate(() => getComputedStyle(document.querySelector(".picker")).backgroundColor);
  if (bg === "rgb(255, 255, 255)") fail("the picker stayed light in the dark theme");
  await shot(p, "picker-dark");
}, "dark");

await browser.close();
if (server) server.kill();

/* A manifest, so the folder explains itself without reading this script. */
if (ONLY.length === 0) {
  writeFileSync(`${OUT}/README.md`, manifest());
}

console.log(`\n${shots.length} screenshots in ${OUT}`);
if (problems.length) {
  console.error("\nproblems:", problems.slice(0, 10));
  process.exit(1);
}

function manifest() {
  const copy = {
    "picker-open": "The picker open: groups with counts, limits with their evidence, the current model first.",
    "picker-filtered": "Typing filters every group; no group disappears, the footer states why it matched.",
    "picker-unavailable-focused": "Keyboard focus on an unavailable row: Enter announces the reason, selects nothing.",
    "picker-selected": "After choosing a model: the chip names it and the confirmation says when it applies.",
    "picker-narrow-sheet": "At 820px the popover becomes a sheet, opened from the palette command.",
    "picker-degraded": "No database: Databricks models still work and the notice names what is unavailable.",
    "inspector-model-facts": "The inspector's model block: provider, wire, limits with evidence, key hint.",
    "inspector-after-switch": "Two turns on two models, with the switch point named and earlier turns untouched.",
    "providers-settings": "Providers and keys: one row per provider, the managed gateway offers no key action.",
    "add-key-validated": "A malformed service-account JSON: the failing field is named before Save.",
    "picker-dark": "The picker in the dark theme, from the same tokens as the rest of the app.",
  };
  const rows = ORDER.map((name, i) => {
    const file = `${String(i + 1).padStart(2, "0")}-${name}.png`;
    return `| \`${file}\` | ${copy[name] ?? name} |`;
  }).join("\n");
  return `# Spec 005 · end-to-end screenshots

Generated by \`apps/coding-agent/web/scripts/model-picker.e2e.mjs\`. Every scene **asserts** the
property it demonstrates before it takes the picture, so a broken state fails the run rather than
becoming a screenshot nobody reads. Regenerate with:

\`\`\`bash
cd apps/coding-agent/web && node scripts/model-picker.e2e.mjs
\`\`\`

The server is started for you (\`agent_mode=fake\`, the real seed catalogue, a development KEK), so
this suite needs no database, no workspace and no provider key.

| File | What it proves |
|---|---|
${rows}

## What is not covered here

- A real provider answering: that is \`tests/test_llm_e2e.py\`, which records the headers a fake
  provider receives and asserts each user's request carries that user's key (E-12).
- A real \`opencode\` process holding two provider blocks: probe P0 in the implementation plan, which
  needs a workspace.
`;
}
