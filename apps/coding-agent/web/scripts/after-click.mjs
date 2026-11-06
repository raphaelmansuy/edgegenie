import { chromium } from "playwright";
import { spawn } from "node:child_process";
import { setTimeout as sleep } from "node:timers/promises";
const app = new URL("../../", import.meta.url).pathname;
const port = 8013;
const srv = spawn(`${app}.venv/bin/python`, ["-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", String(port)], {
  cwd: app, stdio: "ignore",
  env: { ...process.env, APP_AGENT_MODE: "fake", APP_DEMO_SCENARIO: "notebook", APP_DEV_USER: "you@example.com",
         APP_DEFAULT_MODEL: "fake/model-a", APP_ALLOWED_MODELS: '["fake/model-a"]' } });
for (let i = 0; i < 80; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) break; } catch {} await sleep(200); }
const b = await chromium.launch({ executablePath: process.env.CHROME_PATH });
const ctx = await b.newContext({ viewport: { width: 1440, height: 940 } });
const p = await ctx.newPage();
p.on("pageerror", (e) => console.log("pageerror:", String(e).slice(0, 200)));
await p.goto(`http://127.0.0.1:${port}/`, { waitUntil: "domcontentloaded" });
const card = p.getByRole("button", { name: /Build a notebook/i });
await card.waitFor({ state: "visible" });
await sleep(700);
await card.click();
await sleep(3000).catch(()=>{});
console.log("cards now:", await p.locator(".card").count());
console.log("empty now:", await p.locator(".empty").count());
console.log("turns:", await p.locator(".turn").count());
console.log("body text:", (await p.locator("body").innerText()).replace(/\s+/g, " ").slice(0, 260));
await b.close(); srv.kill();
