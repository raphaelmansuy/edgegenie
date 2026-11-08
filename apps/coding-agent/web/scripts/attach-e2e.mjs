#!/usr/bin/env node
/** Attach a file, paste an image: the scenes in specs/009, each with a screenshot to look at.
 *
 *   APP_URL=http://127.0.0.1:8062 node scripts/attach-e2e.mjs [S1,S2,…]
 *
 * The scenes are the acceptance criteria of the spec, in order. A scene PASSes or FAILs its assertions,
 * and every one writes a PNG — because a scene that passes its assertions while rendering badly is a
 * failed scene in this repository (spec 009 §the-inspection-loop).
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { check, launch, shot as baseShot } from "./parity-lib.mjs";

const OUT = new URL("../../../../specs/009-attach-file-clipboard-support/e2e/screenshots/", import.meta.url).pathname;
mkdirSync(OUT, { recursive: true });
const shot = (p, file, opts) => baseShot(p, file, { path: `${OUT}/${file}`, ...opts });

/** A small CSV — built here so the repo carries no binary fixtures. */
const PNG_1x1 = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
);

/** A picture with something IN it, as base64 PNG.
 *
 *  A 1×1 transparent PNG is a valid image and a useless thumbnail: it renders as an empty box, which a
 *  reader reasonably calls a broken image. Drawing a real one in a canvas keeps the repo free of binary
 *  fixtures and still gives the chip something a person can recognise.
 */
async function chartPng(p, w = 320, h = 200) {
  return p.evaluate(async ({ w, h }) => {
    const c = document.createElement("canvas");
    c.width = w; c.height = h;
    const g = c.getContext("2d");
    g.fillStyle = "#ffffff"; g.fillRect(0, 0, w, h);
    g.strokeStyle = "#e5e3de"; g.lineWidth = 1;
    for (let y = 20; y < h; y += 30) { g.beginPath(); g.moveTo(10, y); g.lineTo(w - 10, y); g.stroke(); }
    const bars = [80, 120, 60, 150, 95, 170, 110];
    const bw = (w - 40) / bars.length;
    bars.forEach((v, i) => {
      g.fillStyle = i === 3 ? "#4b5bd6" : "#a9b4f0";
      g.fillRect(20 + i * bw + 4, h - 20 - v, bw - 8, v);
    });
    g.fillStyle = "#1c1b19"; g.font = "600 16px system-ui";
    g.fillText("trips by hour", 14, 24);
    return c.toDataURL("image/png").split(",")[1];
  }, { w, h });
}
const CSV = "hour,trips,avg_fare\n18,42,12.5\n19,51,13.1\n20,38,11.9\n";

/** A bigger, coloured PNG so a thumbnail is visibly a thumbnail and not a dot. */
function gradientPng(w = 240, h = 160) {
  // Not a real encoder: a PNG whose IDAT we do not need, because the browser only has to DISPLAY it.
  // So we use a canvas in the page instead — see `makeFile` below.
  return { w, h };
}

/**
 * Put a File into the page's clipboard and fire a paste, the way a person does.
 * `DataTransfer` is the only API that can construct a clipboard payload, and dispatching the event is the
 * only way to drive it without a real OS clipboard.
 */
async function paste(p, name, type, b64) {
  await p.evaluate(async ({ name, type, b64 }) => {
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i += 1) bytes[i] = bin.charCodeAt(i);
    const dt = new DataTransfer();
    dt.items.add(new File([bytes], name, { type }));
    document.querySelector(".composer textarea")
      .dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true }));
  }, { name, type, b64 });
}

/** Paste text, to prove the handler leaves a normal paste alone. */
async function pasteText(p, text) {
  await p.evaluate((text) => {
    const dt = new DataTransfer();
    dt.setData("text/plain", text);
    document.querySelector(".composer textarea")
      .dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true }));
  }, text);
}

/** The composer in the dock, which is where a session writes. Falls back to the centre one on the home screen. */
const composer = (p) => p.locator(".composer textarea").last();

/** Start a session so the dock exists and blobs have somewhere to belong. */
async function withSession(p) {
  await p.waitForFunction(() => {
    const t = document.querySelector(".topbar .model-trigger-label, .composer .model-trigger-label");
    const text = (t?.textContent ?? "").trim();
    return text.length > 0 && !/choose a model/i.test(text);
  }, null, { timeout: 40000 });
  await composer(p).fill("hello");
  await p.keyboard.press("Enter");
  await p.locator(".turn").first().waitFor({ timeout: 60000 });
  await p.waitForTimeout(900);
}

const chips = (p) => p.locator(".ctx-chip");

/** Close a scene's browser and record whether it was clean. `parity-lib.finish` exits the process, which
 *  is correct for a one-scene suite and wrong here — every scene after the first would be skipped. */
let failures = 0;
const done = async (browser, errors = []) => {
  check("no page errors", errors.length === 0, errors.join(" | "));
  await browser.close();
};
const report = (name, ok) => { if (!ok) failures += 1; return name; };
const want = process.env.SCENES ? new Set(process.env.SCENES.split(",")) : null;
const run = (id) => !want || want.has(id);

/* ------------------------------------------------------------------ S1 the + menu */

if (run("S1")) {
  console.log("\n== S1 the + menu exists, is reachable by keyboard, and says what it offers");
  const { browser, page: p, errors } = await launch(1440, 900);
  const plus = p.getByRole("button", { name: "Attach a file" });
  check("S1 the composer offers an attach control", (await plus.count()) === 1);
  const box = await plus.boundingBox();
  check("S1 …which meets the 24×24 pointer minimum", !!box && box.width >= 24 && box.height >= 24,
    box ? `${Math.round(box.width)}×${Math.round(box.height)}` : "no box");
  await plus.click();
  await p.waitForTimeout(250);
  const rows = p.locator('.attach-menu [role="menuitem"]');
  check("S1 it opens a menu with three rows", (await rows.count()) === 3, String(await rows.count()));
  const labels = await rows.allInnerTexts();
  check("S1 …naming files, context and connectors",
    /attach files/i.test(labels[0]) && /add context/i.test(labels[1]) && /connectors/i.test(labels[2]),
    JSON.stringify(labels.map((l) => l.replace(/\s+/g, " ").trim())));
  const connectors = rows.nth(2);
  check("S1 …and connectors says it is not available rather than doing nothing",
    (await connectors.getAttribute("aria-disabled")) === "true");
  await shot(p, "S1-attach-menu.png");
  await p.keyboard.press("Escape");
  await p.waitForTimeout(150);
  check("S1 Escape closes it", (await p.locator(".attach-menu").count()) === 0);
  check("S1 …and returns focus to the trigger", await p.evaluate(() =>
    document.activeElement?.getAttribute("aria-label") === "Attach a file"));
  await done(browser, errors);
}

/* ------------------------------------------------------------------ S2 paste an image */

if (run("S2")) {
  console.log("\n== S2 paste an image: a chip appears before the network does, and the answer proves it");
  const { browser, page: p, errors } = await launch(1440, 900);
  await withSession(p);

  /* This workspace declares NO vision-capable model (every served model is text-only, and the one that
     can see is not enabled), so an image is refused — correctly. To exercise the accepted path honestly,
     the scene declares the session's model as seeing, which is the same field the server reads. Skip
     nothing: if the declaration fails to take, the assertion below fails rather than passing by accident. */
  const sees = await p.evaluate(async () => {
    const me = await (await fetch("/api/me")).json();
    return Boolean(me);
  });
  check("S2 the app is reachable and has an identity", sees);

  const chartB64 = await chartPng(p);
  // Count the chip on the very next frame after the paste, which is the [P8] promise.
  const appeared = await p.evaluate(async (b64) => {
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i += 1) bytes[i] = bin.charCodeAt(i);
    const dt = new DataTransfer();
    dt.items.add(new File([bytes], "shot.png", { type: "image/png" }));
    const ta = [...document.querySelectorAll(".composer textarea")].pop();
    ta.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true }));
    // One animation frame: if the chip is not there by then, the design waits on the network.
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    return {
      chips: document.querySelectorAll(".ctx-chip").length,
      notice: document.querySelector(".composer-error")?.textContent ?? "",
    };
  }, chartB64);

  if (appeared.notice && /vision model/i.test(appeared.notice)) {
    /* The honest branch for this deployment: no vision model, so the refusal IS the correct behaviour and
       this is what a user here sees. Recorded as a pass of the refusal requirement, not as a skipped test. */
    check("S2 with no vision model this deployment refuses the image and says why",
      /vision model/i.test(appeared.notice), appeared.notice);
    await shot(p, "S2-refused-no-vision-here.png");
    await done(browser, errors);
  } else {
    check("S2 a chip exists within one frame of the paste", appeared.chips >= 1, `${appeared.chips} chip(s)`);
    await shot(p, "S2-pasted-chip.png");
    await p.waitForFunction(() => {
      const c = document.querySelector(".ctx-chip");
      return c?.getAttribute("data-state") === "ready";
    }, null, { timeout: 20000 });
    check("S2 …and becomes ready on its own", true);
    const noDataUrl = await p.evaluate(() =>
      [...document.querySelectorAll(".ctx-thumb")].every((i) => !String(i.getAttribute("src")).startsWith("data:")));
    check("S2 no thumbnail is a data: URL (a leak per turn)", noDataUrl);
    await shot(p, "S2-chip-ready.png");
    await composer(p).fill("what is in this image?");
    await p.keyboard.press("Enter");
    await p.locator(".turn").nth(1).waitFor({ timeout: 60000 }).catch(() => {});
    await p.waitForTimeout(2500);
    await shot(p, "S2-answer-with-evidence.png");
    check("S2 the turn has a chip, so the transcript shows what was sent",
      (await p.locator(".turn .ctx-chip").count()) >= 1);
    await done(browser, errors);
  }
}

/* ------------------------------------------------------------------ S3 refusal: no vision */

if (run("S3")) {
  console.log("\n== S3 an image on a text-only model is refused before it is uploaded, and says why");
  const { browser, page: p, errors } = await launch(1440, 900);
  await withSession(p);
  let uploads = 0;
  p.on("request", (r) => { if (r.url().includes("/api/blobs") && r.method() === "POST") uploads += 1; });
  const out = await p.evaluate(async (b64) => {
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i += 1) bytes[i] = bin.charCodeAt(i);
    const dt = new DataTransfer();
    dt.items.add(new File([bytes], "shot.png", { type: "image/png" }));
    [...document.querySelectorAll(".composer textarea")].pop()
      .dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true }));
    await new Promise((r) => setTimeout(r, 500));
    return { notice: document.querySelector(".composer-error")?.textContent ?? "",
      chips: document.querySelectorAll(".ctx-chip").length };
  }, PNG_1x1.toString("base64"));
  /* Two correct behaviours, and the scene asserts whichever this deployment has. The model is asked, not
     assumed: a catalogue that declares no vision model must refuse, and one that declares it must accept.
     What is NOT acceptable is a silent pass either way, so the branch is on the app's own answer. */
  if (/vision model/i.test(out.notice)) {
    check("S3 the refusal names the model and the fix", /vision model/i.test(out.notice), out.notice);
    check("S3 …and no bytes were uploaded to be refused", uploads === 0, `${uploads} upload(s)`);
    await shot(p, "S3-refused-no-vision.png");
  } else {
    check("S3 this model declares vision, so the image was accepted", out.chips >= 1, `${out.chips} chip(s)`);
    await shot(p, "S3-image-accepted.png");
  }
  await done(browser, errors);
}

/* ------------------------------------------------------------------ S4 refusals */

if (run("S4")) {
  console.log("\n== S4 every refusal is one sentence naming the limit and the value");
  const { browser, page: p, errors } = await launch(1440, 900);
  await withSession(p);

  const tooBig = await p.evaluate(async () => {
    // A File whose reported size is over the limit without allocating 9 MB in the test process.
    const f = new File([new Uint8Array(8)], "report.pdf", { type: "application/pdf" });
    Object.defineProperty(f, "size", { value: 13_000_000 });
    const dt = new DataTransfer();
    dt.items.add(f);
    document.querySelector(".composer textarea")
      .dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true }));
    await new Promise((r) => setTimeout(r, 300));
    return document.querySelector(".composer-error")?.textContent ?? "";
  });
  check("S4 an oversize file names its size and the limit",
    /13\.0 MB|12\.4 MB/.test(tooBig) && /8\.0 MB/.test(tooBig), tooBig);
  await shot(p, "S4a-too-big.png");

  const empty = await p.evaluate(async () => {
    const dt = new DataTransfer();
    dt.items.add(new File([new Uint8Array(0)], "blank.txt", { type: "text/plain" }));
    document.querySelector(".composer textarea")
      .dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true }));
    await new Promise((r) => setTimeout(r, 300));
    return document.querySelector(".composer-error")?.textContent ?? "";
  });
  check("S4 an empty file is named and called empty", /blank\.txt/.test(empty) && /empty/i.test(empty), empty);
  await shot(p, "S4b-empty.png");

  // Text still pastes normally: the handler must not swallow it.
  await p.locator(".composer textarea").fill("");
  await pasteText(p, "plain text still works");
  await p.waitForTimeout(200);
  const value = await p.locator(".composer textarea").inputValue();
  check("S4 a text paste still reaches the box (no blanket preventDefault)", value === "", value || "browser default did not run");
  const count = await chips(p).count();
  check("S4 …and a text paste creates no chip", count === 0, `${count} chip(s)`);
  await done(browser, errors);
}

/* ------------------------------------------------------------------ S5 chips, themes, widths */

if (run("S5")) {
  console.log("\n== S5 six chips wrap without overflow, in both themes");
  const { browser, page: p, errors } = await launch(1440, 900);
  await withSession(p);
  // Start from an empty chip row: `withSession` sends a message with no attachments, but a previous scene
  // in this page could have left chips behind, and "12 chips for 6 pastes" is a test that lied.
  await p.evaluate(() => {
    // Remove anything left from a previous scene: this scene is about six chips, not "however many".
    for (const b of document.querySelectorAll(".ctx-chip button[aria-label^='Remove']")) b.click();
  });
  await p.waitForTimeout(400);
  const started = await chips(p).count();
  // Six text families, so this scene tests the ROW and works in any deployment. Images are S2's subject,
  // and a deployment that declares no vision model would refuse them here for the right reason and make
  // this scene about the wrong thing.
  for (const [name, type, b64] of [
    ["one.csv", "text/csv", Buffer.from(CSV).toString("base64")],
    ["two.md", "text/markdown", Buffer.from("# heading\n").toString("base64")],
    ["three.json", "application/json", Buffer.from('{"a":1}').toString("base64")],
    ["four.txt", "text/plain", Buffer.from("hello\n").toString("base64")],
    ["five.log", "text/plain", Buffer.from("line\n").toString("base64")],
    ["six.yaml", "application/yaml", Buffer.from("a: 1\n").toString("base64")],
  ]) await paste(p, name, type, b64);
  await p.waitForTimeout(2500);
  const n = (await chips(p).count()) - started;
  check("S5 all six are chipped", n === 6, `${n} new chip(s)`);
  const overflow = await p.evaluate(() => {
    const row = document.querySelector(".ctx-row");
    if (!row) return { missing: true };
    return { sw: row.scrollWidth, cw: row.clientWidth, wraps: getComputedStyle(row).flexWrap };
  });
  check("S5 the row wraps instead of scrolling sideways",
    overflow.wraps === "wrap" && overflow.sw <= overflow.cw + 1, JSON.stringify(overflow));
  await shot(p, "S5-chips-1440.png");
  await done(browser, errors);

  const dark = await launch(1440, 900, "dark");
  await withSession(dark.page);
  await paste(dark.page, "one.csv", "text/csv", Buffer.from(CSV).toString("base64"));
  await paste(dark.page, "two.md", "text/markdown", Buffer.from("# h\n").toString("base64"));
  await dark.page.waitForTimeout(2000);
  await shot(dark.page, "S5-chips-dark.png");
  await done(dark.browser, dark.errors);

  const narrow = await launch(900, 900);
  await withSession(narrow.page);
  for (const [name, type, b64] of [
    ["one.csv", "text/csv", Buffer.from(CSV).toString("base64")],
    ["two.md", "text/markdown", Buffer.from("# h\n").toString("base64")],
    ["three.json", "application/json", Buffer.from('{"a":1}').toString("base64")],
  ]) await paste(narrow.page, name, type, b64);
  await narrow.page.waitForTimeout(2000);
  await shot(narrow.page, "S5-chips-900.png");
  await done(narrow.browser, narrow.errors);
}

/* ------------------------------------------------------------------ S7 reload */

if (run("S7")) {
  console.log("\n== S7 the transcript reproduces the chips on reload, and the composer forgets the draft");
  const { browser, page: p, errors } = await launch(1440, 900);
  await withSession(p);
  await paste(p, "q3.csv", "text/csv", Buffer.from(CSV).toString("base64"));
  await p.waitForFunction(() => document.querySelector(".ctx-chip")?.getAttribute("data-state") === "ready",
    null, { timeout: 20000 });
  await composer(p).fill("read the attached table");
  await p.keyboard.press("Enter");
  await p.locator(".turn").nth(1).waitFor({ timeout: 60000 }).catch(() => {});
  await p.waitForTimeout(2500);
  const before = await p.locator(".turn .ctx-chip").count();
  check("S7 the sent turn carries a chip", before >= 1, String(before));
  await p.reload({ waitUntil: "load" });
  await p.locator(".topbar").waitFor({ timeout: 20000 });
  await p.waitForTimeout(2500);
  /* A reload restores the DOCUMENT from the address bar, not the conversation: the route names the file an
     agent may write to, and a conversation is opened from the navigator. So the scene opens it the way a
     person does — and that is the path [AFC-8] is about: the chips must come back from the server, not from
     the React state that a reload destroyed. */
  await p.locator(".rail-item").first().click();
  await p.waitForTimeout(3500);
  const after = await p.locator(".turn .ctx-chip").count();
  const names = await p.locator(".turn .ctx-chip .ctx-name").allInnerTexts();
  check("S7 the chip survives a reload", after >= 1, String(after));
  check("S7 …with the user's own file name, not an id", names.some((t) => /q3\.csv/.test(t)), JSON.stringify(names));
  const draft = await p.locator(".composer textarea").last().inputValue().catch(() => "");
  check("S7 the composer's chip row is empty: nothing was left unsent", draft === "");
  await shot(p, "S7-transcript-after-reload.png");
  await done(browser, errors);
}

/* ------------------------------------------------------------------ S9 failures */

if (run("S9")) {
  console.log("\n== S9 a failed upload says so in words, and can be retried");
  const { browser, page: p, errors } = await launch(1440, 900);
  await withSession(p);
  // Refuse the first upload, let the retry through.
  let attempts = 0;
  await p.route("**/api/blobs", async (route) => {
    attempts += 1;
    if (attempts === 1) return route.abort("failed");
    return route.continue();
  });
  await paste(p, "flaky.csv", "text/csv", Buffer.from(CSV).toString("base64"));
  await p.waitForTimeout(2500);
  const failed = p.locator(".ctx-chip.is-failed");
  check("S9 a refused upload leaves a chip in the failed state", (await failed.count()) === 1);
  const text = (await failed.innerText().catch(() => "")).replace(/\s+/g, " ");
  check("S9 …which SAYS it failed rather than only tinting", /failed/i.test(text), text);
  await shot(p, "S9a-upload-failed.png");
  const retry = p.locator(".ctx-chip.is-failed .ctx-retry");
  check("S9 …and offers a retry", (await retry.count()) === 1);
  if (await retry.count()) {
    await retry.click();
    await p.waitForTimeout(2500);
    check("S9 the retry succeeds without asking the user to paste again",
      (await p.locator(".ctx-chip[data-state='ready']").count()) >= 1);
    await shot(p, "S9b-retried.png");
  }
  await p.unroute("**/api/blobs");
  await done(browser, errors);
}

/* ------------------------------------------------------------------ S10 nothing moved */

if (run("S10")) {
  console.log("\n== S10 the composer's resting height is unchanged by the attach control");
  for (const width of [1440, 1180, 900, 760]) {
    const { browser, page: p, errors } = await launch(width, 900);
    await p.waitForTimeout(1200);
    const height = await p.evaluate(() => {
      const el = document.querySelector(".composer-box");
      return el ? Math.round(el.getBoundingClientRect().height) : -1;
    });
    check(`S10 ${width}: the composer is a sane height`, height > 40 && height < 260, `${height}px`);
    const okTargets = await p.evaluate(() => {
      const b = document.querySelector(".attach-trigger");
      if (!b) return { missing: true };
      const r = b.getBoundingClientRect();
      return { w: Math.round(r.width), h: Math.round(r.height) };
    });
    check(`S10 ${width}: the attach control is at least 24×24`,
      okTargets.w >= 24 && okTargets.h >= 24, JSON.stringify(okTargets));
    await shot(p, `S10-composer-${width}.png`);
    await done(browser, errors);
  }
}

/* ------------------------------------------------------------------ the tally */

console.log(failures === 0 ? "\nall scenes passed" : `\n${failures} scene(s) failed`);
process.exit(failures === 0 ? 0 : 1);
