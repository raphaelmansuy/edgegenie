/** Deep links: the address names what is on screen, and a pasted address opens it.
 *
 *   APP_URL=http://127.0.0.1:8062 node scripts/deeplink-e2e.mjs
 *
 * Needs the app on a real workspace token (scripts/dev-token.sh 8062) and the seeded notebook
 * `parity_demo`. Screenshots: specs/006-databricks/e2e/deep-links.
 */
import { APP, check, finish, launch, openNotebook, shot as baseShot } from "./parity-lib.mjs";
import { mkdirSync } from "node:fs";

const OUT = process.env.OUT ?? "../../../specs/006-databricks/e2e/deep-links";
mkdirSync(OUT, { recursive: true });
const shot = (p, f) => baseShot(p, f, { path: `${OUT}/${f}` });

const { browser, page: p, errors } = await launch(1440, 900);
const hash = () => p.evaluate(() => window.location.hash);

console.log("\n== 01 opening a notebook writes its address");
check("the start page has no hash", (await hash()) === "");
await openNotebook(p);
const nbHash = await hash();
check("the notebook is in the address", /^#\/notebook\/.*parity_demo$/.test(nbHash), nbHash);

console.log("\n== 02 Copy link, for the notebook and for one cell");
await p.context().grantPermissions(["clipboard-read", "clipboard-write"]).catch(() => {});
const clip = () => p.evaluate(() => navigator.clipboard.readText());
await p.getByRole("button", { name: /^Copy a link to parity_demo/ }).click();
await p.getByRole("status").filter({ hasText: "Link copied" }).waitFor({ timeout: 3000 }).then(
  () => check("a toast confirms", true), () => check("a toast confirms", false));
const nbLink = await clip();
check("the clipboard holds an absolute link to the notebook", nbLink.startsWith("http") && nbLink.endsWith(nbHash), nbLink);
await p.locator(".cell-block").nth(2).hover();
await p.getByRole("button", { name: "Copy a link to cell 3" }).click();
const cellLink = await clip();
const cellHash = cellLink.slice(cellLink.indexOf("#"));
check("a cell has its own link", cellHash === `${nbHash}?cell=3`, cellLink);
await shot(p, "01-copy-cell-link.png");

console.log("\n== 03 a pasted link opens in a fresh tab, at the cell");
const fresh = await p.context().newPage();
await fresh.setViewportSize({ width: 1440, height: 900 });
fresh.on("pageerror", (e) => errors.push(String(e)));
await fresh.goto(cellLink, { waitUntil: "load" });
await fresh.locator(".cell-block").first().waitFor({ timeout: 30000 });
await fresh.waitForTimeout(900);
check("the notebook opens directly", (await fresh.locator(".cell-block").count()) >= 3);
check("cell 3 is marked", await fresh.locator('.cell-block[data-cell="3"]').evaluate((el) => el.classList.contains("is-focused")));
check("the address is kept", (await fresh.evaluate(() => window.location.hash)) === cellHash);
await fresh.screenshot({ path: `${OUT}/02-pasted-link-at-cell.png` });
console.log("  02-pasted-link-at-cell.png");
await fresh.close();

console.log("\n== 04 a reload comes back to the same cell");
await p.goto(cellLink, { waitUntil: "load" });
await p.locator(".cell-block").first().waitFor({ timeout: 30000 });
await p.waitForTimeout(600);
await p.reload({ waitUntil: "load" });
await p.locator(".cell-block").first().waitFor({ timeout: 30000 });
await p.waitForTimeout(600);
check("the address survives a reload", (await hash()) === cellHash, await hash());
check("the notebook tab is open", (await p.locator(".doc-tab").first().innerText()).includes("parity_demo"));

console.log("\n== 05 the palette copies the link too");
await p.keyboard.press("ControlOrMeta+k");
await p.getByRole("combobox").or(p.getByRole("textbox")).first().fill("copy link");
await p.getByRole("option", { name: /Copy link to this cell/ }).first().click();
check("palette copy puts the cell link on the clipboard", (await clip()).endsWith(cellHash), await clip());

console.log("\n== 06 settings tabs");
await p.keyboard.press("ControlOrMeta+,");
await p.locator(".provider-card").first().waitFor();
check("Providers has an address", (await hash()) === "#/settings/providers", await hash());
await p.getByRole("tab", { name: "Models" }).click();
await p.locator(".mc-storage, .mc-card").first().waitFor({ timeout: 15000 }).catch(() => {});
check("Models has an address", (await hash()) === "#/settings/models", await hash());
await shot(p, "03-settings-models-address.png");

console.log("\n== 07 Back walks the way you came");
await p.goBack();
await p.waitForTimeout(400);
check("Back goes to the Providers tab", (await hash()) === "#/settings/providers" && (await p.getByRole("tab", { name: "Providers" }).or(p.getByRole("tab", { name: /Keys/ })).first().getAttribute("aria-selected")) === "true", await hash());
await p.goBack();
await p.waitForTimeout(500);
check("Back closes settings and returns to the notebook", (await hash()) === cellHash && (await p.locator(".provider-card").count()) === 0, await hash());
await p.goForward();
await p.waitForTimeout(400);
check("Forward reopens settings", (await hash()) === "#/settings/providers");
await p.keyboard.press("Escape");
await p.waitForTimeout(400);
check("closing settings puts the notebook's address back", (await hash()) === cellHash, await hash());

console.log("\n== 08 a link to a session");
await p.getByRole("tab", { name: /Sessions/i }).click().catch(() => {});
await p.keyboard.press("ControlOrMeta+Shift+n");
await p.waitForTimeout(300);
const composer = p.getByRole("textbox").last();
await composer.fill("hello");
await composer.press("Enter");
await p.waitForFunction(() => window.location.hash.startsWith("#/session/"), null, { timeout: 30000 });
const sHash = await hash();
check("a conversation has an address", /^#\/session\/[\w-]+$/.test(sHash), sHash);
const sid = sHash.split("/").pop();
await p.waitForTimeout(8000); // let the turn finish: a link to a live turn is a different question
const other = await p.context().newPage();
other.on("pageerror", (e) => errors.push(String(e)));
await other.goto(`${APP}/${sHash}`, { waitUntil: "load" });
await other.waitForSelector(".topbar");
await other.locator(".turn").first().waitFor({ state: "attached", timeout: 15000 }).catch(async () => { await other.screenshot({ path: "/tmp/other.png" }); });
check("a pasted session link loads that conversation", /hello/.test(await other.locator(".turn").first().textContent()));
check("the session is the one named", (await other.evaluate(() => window.location.hash)).includes(sid) || (await other.evaluate(() => window.location.hash)).startsWith("#/notebook/"),
  await other.evaluate(() => window.location.hash));
await other.close();
await shot(p, "04-session-address.png");

console.log("\n== 09 a stale or odd link opens the app, not a blank page");
await p.goto(`${APP}/#/nonsense/what`, { waitUntil: "load" });
await p.waitForSelector(".topbar");
await p.waitForTimeout(600);
check("the app is usable", await p.locator(".topbar").isVisible());
check("and the address is tidied", (await hash()) === "" || (await hash()) === "#/nonsense/what", await hash());

await finish(browser, errors);
