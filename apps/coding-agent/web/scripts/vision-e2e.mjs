#!/usr/bin/env node
/** Vision, proven: can the agent READ a picture, not just receive one?
 *
 *   APP_URL=http://127.0.0.1:8071 node scripts/vision-e2e.mjs
 *
 * Every other scene in this repository asserts that a request was made. This one asserts that the answer
 * is RIGHT — against images whose content cannot be guessed:
 *
 *   - three block digits, chosen at random at run time (1000 possibilities). A model that cannot see has
 *     no way to answer; one that answers correctly has read the pixels.
 *   - a text-only model must NOT invent the digits, which is the failure mode that started all of this:
 *     a model that never received an image "explaining" that it cannot see one.
 *
 * That distinction matters here more than anywhere: this feature failed four times while every request
 * looked correct, and the first "proof" I accepted was a solid-colour image — a six-way guess.
 *
 * Requires a REAL agent and a vision-capable model:
 *   APP_AGENT_MODE=stdio APP_AGENT_CWD=/tmp/agent-probe DATABRICKS_HOST=... APP_DEV_TOKEN=...
 */
import { mkdirSync } from "node:fs";
import { chromium } from "playwright";

const APP = process.env.APP_URL ?? "http://127.0.0.1:8071";
const OUT = new URL("../../../../specs/009-attach-file-clipboard-support/e2e/vision/", import.meta.url).pathname;
mkdirSync(OUT, { recursive: true });
const MODELS = (process.env.VISION_MODELS
  ?? "databricks/databricks-gemma-3-12b,databricks/databricks-llama-4-maverick").split(",");
const BLIND = process.env.TEXT_MODEL ?? "databricks/databricks-gpt-oss-120b";

/** 5x7 block glyphs, drawn as pixels. Unambiguous on purpose: an earlier fixture's slashed zero was read
 *  as an 8 by inspection, which would have failed the test for the wrong reason. */
const GLYPHS = {
  "0": ["01110","10001","10001","10001","10001","10001","01110"],
  "1": ["00100","01100","00100","00100","00100","00100","01110"],
  "2": ["01110","10001","00001","00010","00100","01000","11111"],
  "3": ["11111","00010","00100","00010","00001","10001","01110"],
  "4": ["00010","00110","01010","10010","11111","00010","00010"],
  "5": ["11111","10000","11110","00001","00001","10001","01110"],
  "6": ["00110","01000","10000","11110","10001","10001","01110"],
  "7": ["11111","00001","00010","00100","01000","01000","01000"],
  "8": ["01110","10001","10001","01110","10001","10001","01110"],
  "9": ["01110","10001","10001","01111","00001","00010","01100"],
};

/** Draw a code into a PNG in the page, with a canvas: no binary fixtures, no encoder. */
async function digitsPng(page, code) {
  return page.evaluate(({ code, glyphs }) => {
    const scale = 9, pad = 14, gap = 10, gw = 5, gh = 7;
    const w = pad * 2 + gw * scale * code.length + gap * (code.length - 1);
    const h = pad * 2 + gh * scale;
    const c = document.createElement("canvas");
    c.width = w; c.height = h;
    const g = c.getContext("2d");
    g.fillStyle = "#ffffff"; g.fillRect(0, 0, w, h);
    g.fillStyle = "#000000";
    let x = pad;
    for (const ch of code) {
      const rows = glyphs[ch];
      for (let r = 0; r < gh; r += 1) {
        for (let col = 0; col < gw; col += 1) {
          if (rows[r][col] === "1") g.fillRect(x + col * scale, pad + r * scale, scale, scale);
        }
      }
      x += gw * scale + gap;
    }
    return c.toDataURL("image/png").split(",")[1];
  }, { code, glyphs: GLYPHS });
}

const randomCode = () => Array.from({ length: 3 }, () => Math.floor(Math.random() * 10)).join("");

/** Create a session, upload the image as a blob, send it, and wait for a terminal state. */
async function askWithImage(request, model, b64, name, text) {
  const created = await request.post(`${APP}/api/sessions`, { data: { folder: "/tmp/agent-probe", model } });
  if (!created.ok()) throw new Error(`session create failed: ${created.status()} ${await created.text()}`);
  const sid = (await created.json()).id;

  const up = await request.post(`${APP}/api/blobs`,
    { data: { sessionId: sid, name, mime: "image/png", content: b64 } });
  if (!up.ok()) throw new Error(`upload failed: ${up.status()} ${await up.text()}`);
  const blobId = (await up.json()).blobId;

  const sent = await request.post(`${APP}/api/sessions/${sid}/messages`,
    { data: { text, attachments: [{ kind: "blob", ref: blobId, name }] } });
  if (!sent.ok()) throw new Error(`send failed: ${sent.status()} ${await sent.text()}`);

  let status = "";
  for (let i = 0; i < 60; i += 1) {
    await new Promise((r) => setTimeout(r, 1500));
    const d = await (await request.get(`${APP}/api/sessions/${sid}`)).json();
    status = d.turns?.at(-1)?.status ?? "";
    if (["completed", "failed", "blocked"].includes(status)) break;
  }

  /* A FINITE read of the same event log. `/stream` never closes — correct for a live turn, useless for
     "tell me what happened", where it meant holding the connection until a timeout. */
  const { events } = await (await request.get(`${APP}/api/sessions/${sid}/events`)).json();
  const answer = events.filter((e) => e.type === "message.delta" && e.text).map((e) => e.text).join("");
  return { sid, status, answer };
}

let failures = 0;
const check = (name, ok, detail = "") => {
  if (!ok) failures += 1;
  console.log(`  ${ok ? "PASS" : "FAIL"} ${name}${detail ? ` — ${detail}` : ""}`);
};

const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || undefined });
const ctx = await browser.newContext();
const page = await ctx.newPage();
await page.goto(`${APP}/`, { waitUntil: "domcontentloaded" });

for (const model of MODELS) {
  console.log(`\n== ${model}: three random codes it cannot have guessed`);
  const rows = [];
  for (let round = 1; round <= 3; round += 1) {
    const code = randomCode();
    const b64 = await digitsPng(page, code);
    const { status, answer } = await askWithImage(ctx.request, model, b64, `code${round}.png`,
      "Read the three digits in the attached image. Reply with only the digits.");
    const got = (answer.match(/\d/g) ?? []).join("").slice(0, 3);
    check(`round ${round}: ${code}`, got === code, `model said "${answer.trim().slice(0, 40)}" (${status})`);
    rows.push({ round, want: code, got, status, answer: answer.trim().slice(0, 200) });
  }
  const name = model.replace(/[^\w-]+/g, "_");
  (await import("node:fs")).writeFileSync(`${OUT}/${name}.json`,
    JSON.stringify({ model, rounds: rows }, null, 1));
}

console.log(`\n== ${BLIND}: it must not invent the digits`);
{
  const b64 = await digitsPng(page, "492");
  const { answer } = await askWithImage(ctx.request, BLIND, b64, "code.png",
    "Read the three digits in the attached image. Reply with only the digits.");
  const claimed = (answer.match(/\d/g) ?? []).join("");
  check("it does not claim the hidden code", claimed !== "492", `it said "${answer.trim().slice(0, 60)}"`);
}

await browser.close();
console.log(failures === 0 ? "\nall vision checks passed" : `\n${failures} vision check(s) FAILED`);
process.exit(failures === 0 ? 0 : 1);
