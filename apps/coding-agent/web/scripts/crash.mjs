import { chromium } from "playwright";
import { spawn } from "node:child_process";
import { setTimeout as sleep } from "node:timers/promises";
const app = new URL("../../", import.meta.url).pathname;
const port = 8014;
const srv = spawn(`${app}.venv/bin/python`, ["-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", String(port)], {
  cwd: app, stdio: "ignore",
  env: { ...process.env, APP_AGENT_MODE: "fake", APP_DEMO_SCENARIO: "notebook", APP_DEV_USER: "you@example.com",
         APP_DEFAULT_MODEL: "fake/model-a", APP_ALLOWED_MODELS: '["fake/model-a"]' } });
for (let i = 0; i < 80; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) break; } catch {} await sleep(200); }
const b = await chromium.launch({ executablePath: process.env.CHROME_PATH });
const page = await b.newPage({ viewport: { width: 1440, height: 940 } });
page.on("crash", () => console.log("!! PAGE CRASHED"));
let renders = 0;
await page.addInitScript(() => {
  (window).__n = 0;
});
await page.exposeFunction("reportRender", (n) => { renders = n; });
await page.addInitScript(() => {
  const raf = window.requestAnimationFrame;
  let count = 0;
  window.requestAnimationFrame = (cb) => raf(() => { (count += 1); (window).__frames = count; return cb(performance.now()); });
});
await page.goto(`http://127.0.0.1:${port}/`, { waitUntil: "domcontentloaded" });
const card = page.getByRole("button", { name: /Build a notebook/i });
await card.waitFor({ state: "visible" });
await sleep(600);
await card.click();
for (let i = 0; i < 12; i++) {
  await sleep(300);
  try {
    const st = await page.evaluate(() => ({ frames: (window).__frames, turns: document.querySelectorAll(".turn").length,
      nodes: document.getElementsByTagName("*").length }));
    console.log(`t=${(i + 1) * 300}ms frames=${st.frames} turns=${st.turns} nodes=${st.nodes}`);
  } catch (e) {
    console.log(`t=${(i + 1) * 300}ms evaluate failed: ${String(e).slice(0, 60)}`);
    break;
  }
}
await b.close(); srv.kill();
