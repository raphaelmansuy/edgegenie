import { chromium } from "playwright";
import { spawn } from "node:child_process";
import { setTimeout as sleep } from "node:timers/promises";
const app = new URL("../../", import.meta.url).pathname;
const port = 8015;
const srv = spawn(`${app}.venv/bin/python`, ["-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", String(port)], {
  cwd: app, stdio: "ignore",
  env: { ...process.env, APP_AGENT_MODE: "fake", APP_DEV_USER: "you@example.com",
         APP_DEFAULT_MODEL: "fake/model-a", APP_ALLOWED_MODELS: '["fake/model-a"]' } });
for (let i = 0; i < 80; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) break; } catch {} await sleep(200); }
const b = await chromium.launch({ executablePath: process.env.CHROME_PATH });
const p = await b.newPage();
p.on("console", (m) => console.log("console:", m.type(), m.text().slice(0, 300)));
p.on("pageerror", (e) => console.log("pageerror:", String(e).slice(0, 400)));
p.on("response", (r) => { if (r.status() >= 400) console.log("http:", r.status(), r.url()); });
await p.goto(`http://127.0.0.1:${port}/`, { waitUntil: "networkidle" });
await sleep(1500);
console.log("root html len:", (await p.locator("#root").innerHTML()).length);
await b.close(); srv.kill();
