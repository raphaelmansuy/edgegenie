/** End-to-end scenes for the editing surface (spec 003).
 *
 *   node scripts/editor-shots.mjs                 # all scenes
 *   SCENE=editor-open,editor-dirty node scripts/editor-shots.mjs
 *
 * Every scene asserts what it claims to show before it takes the picture, so a screenshot cannot
 * silently become a picture of an error state. Filenames come from a declared ORDER keyed by name,
 * so a partial run writes byte-identical names to a full run and a doc link never dangles (a lesson
 * from 001-perfect-shell, where a partial run renumbered the folder).
 */
import { chromium } from "playwright";
import { mkdirSync, readFileSync, rmSync } from "node:fs";

const APP = process.env.APP_URL ?? "http://127.0.0.1:8040";
const OUT = process.env.OUT ?? "../../../specs/003-improve-dev-ux-ui/e2e/screenshots";
const bearer = process.env.BEARER_FILE ? readFileSync(process.env.BEARER_FILE, "utf8").trim() : "";
const only = (process.env.SCENE ?? "").split(",").map((s) => s.trim()).filter(Boolean);

const ORDER = [
  "editor-open",
  "editor-dirty",
  "editor-saved",
  "notebook-add-cell",
  "notebook-edit-md",
  "notebook-convert",
  "fence-outside",
  "approval-sheet",
  "conflict",
  "draft-recovery",
  "editor-dark",
  "editor-narrow",
];

const shots = [];
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || undefined });
const fail = (m) => { throw new Error(m); };

if (!only.length) {
  rmSync(OUT, { recursive: true, force: true });
}
mkdirSync(OUT, { recursive: true });

const shot = async (page, name, clip) => {
  await page.waitForTimeout(220);
  const at = ORDER.indexOf(name);
  if (at < 0) throw new Error(`shot "${name}" is not in ORDER`);
  const file = `${String(at + 1).padStart(2, "0")}-${name}.png`;
  await page.screenshot({ path: `${OUT}/${file}`, ...(clip ? { clip } : {}) });
  shots.push(file);
  console.log(`  ${file}`);
};

async function scene(name, width, body, opts = {}) {
  if (only.length && !only.includes(name)) return;
  const context = await browser.newContext({
    viewport: { width, height: 900 }, deviceScaleFactor: 2,
    colorScheme: opts.scheme ?? "light",
    ...(bearer ? { extraHTTPHeaders: { Authorization: `Bearer ${bearer}` } } : {}),
  });
  const page = await context.newPage();
  /** Every save the app attempts, so a failure names the HTTP status instead of timing out. */
  const saves = [];
  page.on("response", async (r) => {
    if (!r.url().includes("/workspace/save")) return;
    saves.push(`${r.status()} ${(await r.text().catch(() => "")).slice(0, 160)}`);
  });
  try {
    await page.goto(APP, { waitUntil: "load" });
    await page.locator(".composer textarea").waitFor({ state: "visible", timeout: 45000 });
    await page.waitForTimeout(700);
    /* Isolate the scene. A draft left by the previous scene would make this one show a
       "recover your changes" banner it did not ask for, and a stale version token would turn its
       first save into a conflict. Both are correct app behaviour and both are noise here. */
    if (!opts.keepDrafts) {
      await page.evaluate(() => {
        for (const k of Object.keys(localStorage)) {
          if (k.startsWith("coding-agent:draft:")) localStorage.removeItem(k);
        }
      });
    }
    await body(page);
  } catch (e) {
    await page.screenshot({ path: `${OUT}/FAIL-${name}.png` }).catch(() => {});
    throw new Error(`${name}: ${e.message.split("\n")[0]} | saves: ${saves.join(" ; ") || "none"}`);
  } finally {
    await context.close().catch(() => {});
  }
}

/** Start a session so the working folder exists and the fence allows saves.
 *
 * Waits for a *usable* composer first. Sending before /api/models resolves posts the placeholder
 * "model-a" instead of "fake/model-a", and the server correctly rejects it with a 422 — the failure
 * then surfaces 90 seconds later as "no turn appeared", which is a misleading place to look.
 */
async function withSession(p) {
  await p.waitForFunction(() => {
    // The empty state carries the model select; once a session is active the top bar does. Either
    // way, a real model id (it contains a "/") is the signal that /api/models has landed.
    const sel = document.querySelector(".setup select, .topbar select");
    return !!sel && String(sel.value).includes("/");
  }, null, { timeout: 30000 });
  await p.locator(".composer textarea").fill("Build a notebook that shows revenue by pickup hour");
  await p.keyboard.press("Enter");
  await p.locator(".turn-foot").first().waitFor({ timeout: 90000 });
  await p.waitForTimeout(500);
}

/** Open the notebook the agent produced, through the Files tree. */
async function openNotebook(p) {
  await p.getByRole("tab", { name: /Files/i }).click();
  await p.waitForTimeout(700);
  await p.getByPlaceholder("Search notebooks and files…").fill("taxi");
  const hit = p.locator(".result").first();
  await hit.waitFor({ timeout: 45000 });
  await hit.click();
  await p.locator(".editor-surface").waitFor({ timeout: 30000 });
  await p.locator(".cm-editor, .cell-rendered").first().waitFor({ timeout: 30000 });
  await p.waitForTimeout(1200);
}


/** Write a known-good notebook through the real fenced save path, and return its path.
 *
 * This is what makes the scenes independent. It uses the same HTTP endpoints the editor uses, with
 * the session's own scope, so it also proves the write path works before any scene leans on it.
 */
async function seedNotebook(p, marker = "e2e seed") {
  const path = await p.evaluate(async (marker) => {
    const sessions = await (await fetch("/api/sessions")).json();
    const sid = sessions.sessions?.[0]?.id ?? null;
    const folder = sessions.sessions?.[0]?.folder ?? "";
    const target = `${folder}/e2e_notes`;
    const text = [
      "# Databricks notebook source",
      "# MAGIC %md",
      "# MAGIC # " + marker,
      "# MAGIC",
      "# MAGIC A cell written by the end-to-end suite.",
      "",
      "# COMMAND ----------",
      "",
      "df = spark.table(\"samples.nyctaxi.trips\")",
      "df.groupBy(\"pickup_hour\").count().show()",
      "",
      "# COMMAND ----------",
      "",
      "dbutils.notebook.exit(\"ok\")",
      "",
    ].join("\n");
    const body = { path: target, version: "", text, sessionId: sid, language: "PYTHON" };
    for (let attempt = 0; attempt < 3; attempt += 1) {
      const r = await fetch("/api/workspace/save", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      if (r.ok) return target;
      body.version = "";                 // a retry is always a deliberate overwrite of our own seed
    }
    return "";
  }, marker).catch(() => "");
  if (!path) fail("could not seed the notebook");
  return path;
}

/** Open a specific path from the command palette, which is faster and steadier than the tree. */
async function openPath(p, path) {
  /* Through the Files tree, not the palette. The palette lists *open documents* and commands, not
     the workspace, so it cannot open a file nobody has opened — verified by driving it. The tree is
     driven by name and does reach the workspace. */
  const name = path.split("/").pop();
  await p.getByRole("tab", { name: /Files/i }).click();
  await p.waitForTimeout(500);
  await p.getByPlaceholder("Search notebooks and files…").fill(name);
  const hit = p.locator(".result").first();
  await hit.waitFor({ timeout: 60000 });
  await hit.click();
  await p.locator(".editor-surface").waitFor({ timeout: 30000 });
  await p.locator(".cm-editor, .cell-rendered").first().waitFor({ timeout: 30000 });
  await p.waitForTimeout(900);
}

const cellCount = (p) => p.locator(".cell-block").count();
const dirty = (p) => p.locator(".editor-dirty").count();

await scene("editor-open", 1440, async (p) => {
  await withSession(p);
  const path = await seedNotebook(p);
  await openPath(p, path);
  const cells = await cellCount(p);
  if (cells < 2) fail(`expected notebook cells, got ${cells}`);
  if (await p.locator(".cm-editor").count() < 1) fail("no code editor mounted");
  if (await p.locator(".cell-rendered").count() < 1) fail("a markdown cell did not render as prose");
  if (await dirty(p)) fail("a freshly opened document must not be dirty");
  const chip = (await p.locator(".fence-text").textContent())?.trim();
  if (!chip) fail("no fence chip");
  await shot(p, "editor-open", { x: 260, y: 52, width: 860, height: 700 });
});

await scene("editor-dirty", 1440, async (p) => {
  await withSession(p);
  const path = await seedNotebook(p);
  await openPath(p, path);
  await p.locator(".cm-content").first().click();
  await p.keyboard.type("# edited in the e2e suite\n");
  await p.waitForTimeout(500);
  if (!(await dirty(p))) fail("typing did not mark the document dirty");
  if (await p.locator(".editor-bar .btn.primary").isDisabled()) fail("Save stayed disabled with unsaved changes");
  await shot(p, "editor-dirty", { x: 260, y: 52, width: 860, height: 420 });
});

await scene("editor-saved", 1440, async (p) => {
  await withSession(p);
  const path = await seedNotebook(p);
  await openPath(p, path);
  await p.locator(".cm-content").first().click();
  await p.keyboard.type("# saved by the e2e suite\n");
  await p.waitForTimeout(400);
  await p.keyboard.press("Meta+s");
  /* Assert the outcome that lasts, not the notice that fades: the "saved" message clears itself
     after four seconds, so waiting on it is a race by construction. A clean buffer with an enabled
     Save button that is now disabled is what "saved" means. */
  await p.waitForFunction(() => !document.querySelector(".editor-dirty"), null, { timeout: 30000 });
  if (await dirty(p)) fail("the document is still dirty after a successful save");
  if (!(await p.locator(".editor-bar .btn.primary").isDisabled())) fail("Save stayed enabled after a save");
  const text = (await p.locator(".editor-notice").textContent().catch(() => ""))?.trim() ?? "";
  if (text && !/saved/i.test(text)) fail(`unexpected save notice: ${text}`);
  await shot(p, "editor-saved", { x: 260, y: 52, width: 860, height: 420 });
});

await scene("notebook-add-cell", 1440, async (p) => {
  await withSession(p);
  const path = await seedNotebook(p);
  await openPath(p, path);
  const before = await cellCount(p);
  await p.locator(".cells-add .btn").last().click();
  await p.waitForTimeout(900);
  const after = await cellCount(p);
  if (after !== before + 1) fail(`adding a cell gave ${after} cells, expected ${before + 1}`);
  await shot(p, "notebook-add-cell", { x: 260, y: 52, width: 860, height: 700 });
});

await scene("notebook-edit-md", 1440, async (p) => {
  await withSession(p);
  const path = await seedNotebook(p);
  await openPath(p, path);
  const rendered = p.locator(".cell-rendered").first();
  if (!(await rendered.count())) fail("no markdown cell to click");
  await rendered.click();
  await p.waitForTimeout(900);
  const editors = await p.locator(".cm-editor").count();
  if (editors < 2) fail("clicking a markdown cell did not make it editable");
  await shot(p, "notebook-edit-md", { x: 260, y: 52, width: 860, height: 520 });
});

await scene("notebook-convert", 1440, async (p) => {
  await withSession(p);
  const path = await seedNotebook(p);
  await openPath(p, path);
  const md = await p.locator(".cell-block.is-md").count();
  if (!md) fail("no markdown cell to convert");
  await p.locator(".cell-block.is-md .cell-act").first().click();
  await p.waitForTimeout(800);
  const mdAfter = await p.locator(".cell-block.is-md").count();
  if (mdAfter !== md - 1) fail(`conversion did not change the kind: ${md} -> ${mdAfter}`);
  await shot(p, "notebook-convert", { x: 260, y: 52, width: 860, height: 520 });
});

await scene("fence-outside", 1440, async (p) => {
  /* A document that is NOT in the session's working folder. The previous version of this scene
     clicked a folder in the tree and then looked for an editor bar — a folder opens no editor, so
     the assertion was wrong, not the app. Seed a file in /Shared, open it, and require the chip to
     warn before any keystroke (WR-5). */
  await withSession(p);
  const outside = await p.evaluate(async () => {
    /* Outside the session's working folder but inside the user's home, so the Files tree can
       reach it by default search. That is the realistic case — a notebook sitting next to your
       scratch folder, not in it — and it is what WR-5 is about. */
    const s = await (await fetch("/api/sessions")).json();
    const home = (s.sessions?.[0]?.folder ?? "").replace(/\/agent_scratch\/?$/, "");
    const path = `${home}/e2e_outside_fence`;
    const text = "# Databricks notebook source\noutside = True\n";
    const r = await fetch("/api/workspace/fence", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path, version: "" }),
    });
    const fence = await r.json();
    const save = await fetch("/api/workspace/save", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path, text, version: "", approval: fence.approval, language: "PYTHON" }),
    });
    return save.ok ? path : "";
  }).catch(() => "");
  if (!outside) fail("could not create a document outside the working folder");

  await p.getByRole("tab", { name: /Files/i }).click();
  await p.waitForTimeout(500);
  await p.getByPlaceholder("Search notebooks and files…").fill("e2e_outside_fence");
  const hit = p.locator(".result").first();
  await hit.waitFor({ timeout: 60000 });
  await hit.click();
  await p.locator(".editor-surface").waitFor({ timeout: 30000 });
  await p.locator(".cm-editor, .cell-rendered").first().waitFor({ timeout: 30000 });
  await p.waitForTimeout(1200);

  const chip = (await p.locator(".fence-text").textContent().catch(() => ""))?.trim() ?? "";
  if (!chip) fail("no fence chip");
  if (!/ask|outside/i.test(chip)) fail(`the fence did not warn outside the folder: "${chip}"`);
  await shot(p, "fence-outside", { x: 260, y: 52, width: 860, height: 300 });
});

await scene("approval-sheet", 1440, async (p) => {
  await openNotebook(p);
  const chip = (await p.locator(".fence-text").textContent())?.trim() ?? "";
  if (!/ask/i.test(chip)) fail(`expected the fence to warn, got "${chip}"`);
  await p.locator(".cm-content").first().click();
  await p.keyboard.type("# outside the folder\n");
  await p.waitForTimeout(400);
  await p.keyboard.press("Meta+s");
  await p.locator(".ask-banner").waitFor({ timeout: 30000 });
  const text = (await p.locator(".ask-banner").textContent()) ?? "";
  /* The sheet must explain itself in terms a person can act on. It used to name an internal
     placeholder (`__no_scope__`) as if it were a folder; the assertion is therefore "it names the
     situation", not "it contains one particular word". */
  if (!/no session|outside/i.test(text)) fail(`the approval sheet does not say why: "${text.slice(0, 90)}"`);
  if (/__no_scope__/.test(text)) fail("the sheet leaks an internal placeholder");
  await shot(p, "approval-sheet", { x: 260, y: 52, width: 860, height: 340 });
});

await scene("conflict", 1440, async (p) => {
  await withSession(p);
  const path = await seedNotebook(p);
  await openPath(p, path);
  await p.locator(".cm-content").first().click();
  await p.keyboard.type("# mine\n");
  await p.waitForTimeout(500);
  /* Make the server's copy move underneath us, the way a second tab would: save the same document
     from the page's own fetch, with the version we are holding. Then our save is stale. */
  const raced = await p.evaluate(async () => {
    const path = document.querySelector(".viewer-path")?.textContent?.trim() ?? "";
    if (!path) return "no path";
    /* A second writer WITH the session — i.e. another tab of the same user. Sending no session made
       the fence treat the write as outside every folder and refuse it with 403, which is correct
       behaviour and the wrong test: nothing was written, so nothing could conflict. */
    const sessions = await (await fetch("/api/sessions")).json();
    const sid = sessions.sessions?.[0]?.id ?? null;
    const obj = await (await fetch(`/api/workspace/object?path=${encodeURIComponent(path)}`)).json();
    const r = await fetch("/api/workspace/save", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path, version: obj.version ?? "", text: "# theirs\n", sessionId: sid }),
    });
    return r.status;
  }).catch(() => 0);
  await p.keyboard.press("Meta+s");
  await p.waitForTimeout(3000);
  if (!(await p.locator(".conflict-panel").count())) fail(`no conflict panel (racing write returned ${raced})`);
  const text = (await p.locator(".conflict-panel").textContent()) ?? "";
  if (!/keep mine/i.test(text)) fail("the conflict panel offers no choice");
  await shot(p, "conflict", { x: 260, y: 52, width: 860, height: 380 });
});

await scene("draft-recovery", 1440, async (p) => {
  await withSession(p);
  const path = await seedNotebook(p);
  await openPath(p, path);
  await p.locator(".cm-content").first().click();
  await p.keyboard.type("# a thought I have not saved\n");
  await p.waitForTimeout(900);
  await p.reload({ waitUntil: "load" });
  await p.locator(".composer textarea").waitFor({ timeout: 45000 });
  await p.waitForTimeout(700);
  /* Reopen the SAME document. `openNotebook` searches for "taxi" and would open the agent's
     notebook — a different file, with no draft — so the banner could never appear. The draft is
     keyed by path, so the path must be the one we typed into. */
  await openPath(p, path);
  /* Generous, because this scene reloads the whole app and then re-walks the Files search before
     the banner can appear. Measured end to end at ~3 s on a warm server, but the search alone has
     been observed at 10 s on a large workspace. */
  await p.locator(".draft-banner").waitFor({ timeout: 60000 });
  const text = (await p.locator(".draft-banner").textContent()) ?? "";
  if (!/unsaved changes/i.test(text)) fail("the draft banner does not explain itself");
  await shot(p, "draft-recovery", { x: 260, y: 52, width: 860, height: 320 });
});

await scene("editor-dark", 1440, async (p) => {
  await withSession(p);
  const path = await seedNotebook(p);
  await openPath(p, path);
  await p.getByRole("radio", { name: /Dark/ }).click();
  await p.waitForTimeout(800);
  if (await p.locator(".cm-editor").count() < 1) fail("the editor vanished in dark mode");
  await shot(p, "editor-dark", { x: 260, y: 52, width: 860, height: 700 });
}, { scheme: "dark" });

await scene("editor-narrow", 900, async (p) => {
  await withSession(p);
  const path = await seedNotebook(p);
  await openPath(p, path);
  const box = await p.locator(".editor-surface").boundingBox();
  if (!box || box.width < 500) fail(`the surface is too narrow at 900px: ${box?.width}`);
  await shot(p, "editor-narrow");
});

await browser.close();
console.log(`\n${shots.length} screenshots in ${OUT}`);
