/** Model configuration screens: add, default, switch off, remove, read-only, narrow and dark.
 *  Screenshots: specs/005-llm-models/e2e/config-screens. Needs a demo server with APP_LLM_DEMO_SEED=true
 *  and APP_LLM_ADMINS=dev@example.com (default 8073); READONLY_URL points at one where the user is not an admin. */
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const APP = process.env.APP_URL ?? "http://127.0.0.1:8073";
const READONLY = process.env.READONLY_URL ?? "";
const OUT = process.env.OUT ?? "../../../specs/005-llm-models/e2e/config-screens";
mkdirSync(OUT, { recursive: true });

let failed = 0;
const check = (name, ok, detail = "") => { if (!ok) failed += 1; console.log(`  ${ok ? "PASS" : "FAIL"} ${name}${detail ? ` — ${detail}` : ""}`); };

async function open(browser, url, { width = 1440, height = 900, scheme = "light" } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 2, colorScheme: scheme });
  const p = await ctx.newPage();
  const errors = [];
  p.on("pageerror", (e) => errors.push(String(e)));
  p.on("dialog", (d) => d.accept());
  await p.goto(url, { waitUntil: "load" });
  await p.waitForSelector(".topbar", { timeout: 20000 });
  return { p, errors };
}
const shot = async (p, name) => { await p.waitForTimeout(250); await p.screenshot({ path: `${OUT}/${name}` }); console.log(`  ${name}`); };
const openModels = async (p) => {
  await p.keyboard.press("ControlOrMeta+,");
  await p.getByRole("tab", { name: "Models" }).click();
  await p.locator(".mc-storage").waitFor();
};

const browser = await chromium.launch();
const { p, errors } = await open(browser, APP);

console.log("keys tab still works");
await p.keyboard.press("ControlOrMeta+,");
await p.locator(".provider-card").first().waitFor();
check("the Keys tab lists providers", (await p.locator(".provider-card").count()) > 0);

console.log("models tab");
await p.getByRole("tab", { name: "Models" }).click();
await p.locator(".mc-card").first().waitFor();
check("storage line is shown", (await p.locator(".mc-storage").innerText()).length > 10);
check("administrator can change", /You can change this/.test(await p.locator(".mc-storage").innerText()));
check("one card per external provider", (await p.locator(".mc-card[aria-label]").count()) >= 3);
check("the Databricks provider is not editable here", (await p.locator('.mc-card[aria-label="Databricks AI Gateway"]').count()) === 0);
await shot(p, "01-models-tab.png");

console.log("add a model: validation first");
const vertex = p.locator('.mc-card[aria-label="Google Vertex AI"]');
await vertex.getByRole("button", { name: "Add a model" }).click();
const form = p.getByRole("form", { name: /Add a model to Google Vertex AI/ });
await form.getByLabel("Model name").fill("bad name!");
await form.getByLabel("Max output").fill("2M");
await form.getByLabel("Model name").blur();
await form.getByLabel("Max output").blur();
check("a bad name is explained at the field", /letters, digits/.test(await form.innerText()));
check("output larger than context is explained", /larger than the context/.test(await form.innerText()));
check("Add stays disabled while invalid", await form.getByRole("button", { name: "Add model" }).isDisabled());
await shot(p, "02-add-invalid.png");

console.log("add a model: valid");
await form.getByLabel("Model name").fill("google/gemini-9-e2e");
await form.getByLabel("Display name").fill("gemini-9-e2e");
await form.getByLabel("Context window").fill("2M");
await form.getByLabel("Max output").fill("64k");
await form.getByText("Make it the default model").click();
await shot(p, "03-add-valid.png");
await form.getByRole("button", { name: "Add model" }).click();
await p.locator(".settings-ok").waitFor();
check("the confirmation names the model", /gemini-9-e2e added/.test(await p.locator(".settings-ok").innerText()));
const row = vertex.locator("tr", { hasText: "gemini-9-e2e" });
check("the row shows the limits as stated by the user", /2M in · 64k out/.test(await row.innerText()) && /documented/.test(await row.innerText()));
check("it is marked default", (await row.locator(".mc-chip", { hasText: "default" }).count()) === 1);
check("the default selector follows", (await p.getByRole("combobox", { name: "Default model" }).inputValue()) === "google_vertex/google/gemini-9-e2e");
await shot(p, "04-model-added-default.png");

console.log("switch off and guards");
check("the default cannot be switched off", await row.getByRole("switch").isDisabled());
check("the default cannot be removed", await row.getByRole("button", { name: /Remove/ }).isDisabled());
const flash = vertex.locator("tr", { hasText: "gemini-3.8-flash" });
await flash.getByRole("button", { name: "Make default" }).click();
await p.locator(".settings-ok", { hasText: "is now the default" }).waitFor();
check("another model became the default", (await flash.locator(".mc-chip", { hasText: "default" }).count()) === 1);
await row.getByRole("switch").click();
await p.locator(".settings-ok", { hasText: "switched off" }).waitFor();
check("the row is shown as switched off", /switched off/.test(await row.innerText()));
await shot(p, "05-model-switched-off.png");
await row.getByRole("button", { name: /Remove/ }).click();
await p.locator(".settings-ok", { hasText: "removed" }).waitFor();
check("a removed model leaves the table", (await vertex.locator("tr", { hasText: "gemini-9-e2e" }).count()) === 0);

console.log("provider address");
const openai = p.locator('.mc-card[aria-label="OpenAI"]');
await openai.getByLabel("OpenAI address").fill("http://insecure.example");
check("an http address is refused at the field", /must start with https/.test(await openai.innerText()));
check("and cannot be saved", await openai.getByRole("button", { name: "Save address" }).isDisabled());
await openai.getByLabel("OpenAI address").fill("https://proxy.example/v1");
await openai.getByRole("button", { name: "Save address" }).click();
await p.locator(".settings-ok", { hasText: "Address saved" }).waitFor();

console.log("a reload keeps the tab and the choices");
await p.reload({ waitUntil: "load" });
await p.waitForSelector(".topbar");
await p.keyboard.press("ControlOrMeta+,");
await p.locator(".mc-card").first().waitFor();
check("the Models tab is restored from the address", (await p.getByRole("tab", { name: "Models" }).getAttribute("aria-selected")) === "true");
check("the default survived", (await p.getByRole("combobox", { name: "Default model" }).inputValue()).includes("gemini-3.8-flash"));
await shot(p, "06-after-reload.png");
check("no page errors (light)", errors.length === 0, errors.join(" | "));

console.log("dark and narrow");
{
  const d = await open(browser, APP, { scheme: "dark" });
  await d.p.goto(`${APP}/#settings/models`, { waitUntil: "load" });
  await d.p.keyboard.press("ControlOrMeta+,");
  await d.p.locator(".mc-card").first().waitFor();
  await shot(d.p, "07-dark.png");
  const n = await open(browser, APP, { width: 760, height: 900 });
  await n.p.goto(`${APP}/#settings/models`, { waitUntil: "load" });
  await n.p.keyboard.press("ControlOrMeta+,");
  await n.p.locator(".mc-card").first().waitFor();
  const overflow = await n.p.evaluate(() => document.querySelector(".mc-body").scrollWidth > document.querySelector(".mc-body").clientWidth + 1);
  check("no horizontal overflow at 760px", !overflow);
  await n.p.locator('.mc-card[aria-label="OpenAI"]').getByRole("button", { name: "Add a model" }).click();
  await shot(n.p, "08-narrow-add.png");
  check("no page errors (dark/narrow)", d.errors.length + n.errors.length === 0, [...d.errors, ...n.errors].join(" | "));
}

if (READONLY) {
  console.log("read only");
  const r = await open(browser, READONLY);
  await r.p.keyboard.press("ControlOrMeta+,");
  await r.p.getByRole("tab", { name: "Models" }).click();
  await r.p.locator(".mc-card").first().waitFor();
  check("says read only", /Read only/.test(await r.p.locator(".mc-storage").innerText()));
  check("controls are disabled", await r.p.getByRole("button", { name: "Add a model" }).first().isDisabled());
  check("a reason is given", (await r.p.locator(".mc-why").count()) === 1);
  await shot(r.p, "09-read-only.png");
}

await browser.close();
console.log(failed ? `\n${failed} failed` : "\nall passed");
process.exit(failed ? 1 : 0);
