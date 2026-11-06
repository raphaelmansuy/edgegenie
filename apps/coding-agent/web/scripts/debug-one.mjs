/** Debug one card click: print console, network and DOM state. No screenshots. */
import { chromium } from "playwright";
import { spawn } from "node:child_process";
import { setTimeout as sleep } from "node:timers/promises";

const app = new URL("../../", import.meta.url).pathname;
const port = 8012;
const srv = spawn(`${app}.venv/bin/python`, ["-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", String(port)], {
  cwd: app, stdio: ["ignore", "pipe", "pipe"],
  env: { ...process.env, APP_AGENT_MODE: "fake", APP_DEMO_SCENARIO: "notebook", APP_DEV_USER: "you@example.com",
         APP_DEFAULT_MODEL: "fake/model-a", APP_ALLOWED_MODELS: '["fake/model-a"]' },
});
srv.stdout.on("data", (d) => process.stdout.write(`srv: ${d}`));
srv.stderr.on("data", (d) => process.stdout.write(`srv!: ${d}`));
for (let i = 0; i < 80; i++) {
  try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) break; } catch { /* wait */ }
  await sleep(200);
}

const b = await chromium.launch({ executablePath: process.env.CHROME_PATH });
const p = await b.newPage({ viewport: { width: 1440, height: 940 } });
p.on("console", (m) => console.log("console:", m.type(), m.text().slice(0, 240)));
p.on("pageerror", (e) => console.log("pageerror:", String(e).slice(0, 300)));
p.on("requestfailed", (r) => console.log("reqfailed:", r.url(), r.failure()?.errorText));
p.on("response", async (r) => {
  if (!r.url().includes("/api/")) return;
  let body = "";
  try { body = (await r.text()).slice(0, 160); } catch { /* stream */ }
  console.log("api:", r.status(), r.url().replace(/^.*\/api/, "/api"), body);
});

await p.goto(`http://127.0.0.1:${port}/`, { waitUntil: "domcontentloaded" });
const card = p.getByRole("button", { name: /Build a notebook/i });
await card.waitFor({ state: "visible", timeout: 20000 });
console.log("cards visible:", await p.locator(".card").count());
await card.click();
await sleep(9000);
console.log("turns:", await p.locator(".turn").count(), "evidence:", await p.locator(".evidence").count(),
  "blocked:", await p.locator(".blocked").count());
console.log("strip:", await p.locator(".strip").innerText().catch(() => "(none)"));

await b.close();
srv.kill();
