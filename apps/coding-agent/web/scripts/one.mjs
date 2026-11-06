/** Diagnose one scenario: start a server, open one card, print what the DOM actually shows. */
import { chromium } from "playwright";
import { spawn } from "node:child_process";
import { setTimeout as sleep } from "node:timers/promises";

const app = new URL("../../", import.meta.url).pathname;
const port = 8011;
const card = process.argv[2] ?? "Document tables";

const srv = spawn(`${app}.venv/bin/python`, ["-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", String(port)], {
  cwd: app, stdio: "ignore",
  env: { ...process.env, APP_AGENT_MODE: "fake", APP_DEMO_SCENARIO: "notebook", APP_DEV_USER: "you@example.com",
         APP_DEFAULT_MODEL: "fake/model-a", APP_ALLOWED_MODELS: '["fake/model-a"]' },
});
for (let i = 0; i < 80; i++) {
  try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) break; } catch { /* not up */ }
  await sleep(200);
}

const b = await chromium.launch({ executablePath: process.env.CHROME_PATH });
const p = await b.newPage({ viewport: { width: 1440, height: 940 } });
await p.goto(`http://127.0.0.1:${port}/`, { waitUntil: "domcontentloaded" });
const target = p.getByRole("button", { name: new RegExp(card, "i") });
await target.waitFor({ state: "visible", timeout: 20000 });
await target.click();
await p.waitForSelector(".evidence, .blocked", { timeout: 30000 }).catch(() => console.log("(no panel)"));
await p.waitForTimeout(600);

const txt = async (sel) => (await p.locator(sel).first().innerText().catch(() => "(none)")).slice(0, 110);
console.log("SESSIONS:", await p.locator(".rail-item").allInnerTexts());
console.log("PROMPT  :", JSON.stringify(await txt(".prompt")));
console.log("THOUGHT :", JSON.stringify(await txt(".thought-body")));
console.log("TOOLS   :", await p.locator(".tool .name").allInnerTexts());
console.log("ANSWER  :", JSON.stringify(await txt(".answer")));
console.log("EVIDENCE:", await p.locator(".evidence-row").count(), "BLOCKED:", await p.locator(".blocked").count());

await b.close();
srv.kill();
