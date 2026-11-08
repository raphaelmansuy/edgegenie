/** Shared helpers for the Genie Code parity scenes (specs/006-databricks/e2e/improve-parity-databricks). */
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

export const APP = process.env.APP_URL ?? "http://127.0.0.1:8062";
/* Resolved against THIS file, not the shell's cwd: a relative OUT used to land screenshots in
   whatever directory the script happened to be run from, which is how 007's pictures ended up in the
   006 folder. An explicit OUT is honoured as a filesystem path. */
export const OUT = process.env.OUT
  ?? new URL("../../../../specs/006-databricks/e2e/improve-parity-databricks/", import.meta.url).pathname;
export const NOTEBOOK = process.env.NOTEBOOK ?? "parity_demo";
mkdirSync(OUT, { recursive: true });

export async function launch(width = 1440, height = 900, scheme = "light") {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 2, colorScheme: scheme });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto(APP, { waitUntil: "load" });
  await page.waitForSelector(".topbar", { timeout: 20000 });
  return { browser, page, errors };
}

/** Open the seeded notebook through the Files tree, the way a person does. */
export async function openNotebook(p, name = NOTEBOOK) {
  await p.getByRole("tab", { name: /Files/i }).click();
  await p.waitForTimeout(600);
  await p.getByPlaceholder("Search notebooks and files…").fill(name);
  const hit = p.locator(".result").first();
  await hit.waitFor({ timeout: 60000 });
  await hit.click();
  await p.locator(".editor-surface").waitFor({ timeout: 30000 });
  await p.locator(".cell-block").first().waitFor({ timeout: 30000 });
  await p.waitForTimeout(900);
}

export const shot = async (p, file, opts = {}) => {
  await p.waitForTimeout(250);
  await p.screenshot({ path: `${OUT}/${file}`, ...opts });
  console.log(`  ${file}`);
};

let failed = 0;
export const check = (name, ok, detail = "") => {
  if (!ok) failed += 1;
  console.log(`  ${ok ? "PASS" : "FAIL"} ${name}${detail ? ` — ${detail}` : ""}`);
};
export const finish = async (browser, errors = []) => {
  check("no page errors", errors.length === 0, errors.join(" | "));
  await browser.close();
  console.log(failed ? `\n${failed} failed` : "\nall passed");
  process.exit(failed ? 1 : 0);
};
