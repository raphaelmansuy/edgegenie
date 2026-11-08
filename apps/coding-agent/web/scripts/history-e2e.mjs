/** History (search, day groups, delete-with-confirm) and the account menu.
 *   APP_URL=http://127.0.0.1:8071 node scripts/history-e2e.mjs [outdir]
 */
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const APP = process.env.APP_URL ?? "http://127.0.0.1:8071";
const out = process.argv[2] ?? "/tmp/history-e2e";
mkdirSync(out, { recursive: true });
let failed = 0;
const check = (n, ok, d = "") => { if (!ok) failed += 1; console.log(`  ${ok ? "PASS" : "FAIL"} ${n}${d ? ` — ${d}` : ""}`); };

const b = await chromium.launch();
const p = await (await b.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
const errors = [];
p.on("pageerror", (e) => errors.push(String(e)));

// Seed six conversations through the API so the search box appears.
for (let i = 0; i < 6; i++) {
  await p.request.post(`${APP}/api/sessions`, { data: { folder: "/tmp/agent-work", title: `Seed ${i}` } });
}
await p.goto(APP, { waitUntil: "domcontentloaded" });
await p.waitForSelector(".rail-item");
const rows = () => p.locator(".rail-item").count();
const n0 = await rows();
check("history lists conversations under a day heading", n0 >= 6 && (await p.locator(".rail-group").count()) >= 1,
  `${n0} rows, headings: ${await p.locator(".rail-group").allTextContents()}`);
check("search box is shown once there is enough to search", await p.locator(".rail-search input").isVisible());
await p.screenshot({ path: `${out}/01-history.png` });

await p.fill(".rail-search input", "zzz-no-such");
check("a search with no match says so", await p.getByText("Nothing matches").isVisible());
await p.screenshot({ path: `${out}/02-no-match.png` });
await p.keyboard.press("Escape");
await p.locator(".rail-search input").focus();
await p.keyboard.press("Escape");
check("Escape clears the search", (await p.inputValue(".rail-search input")) === "" && (await rows()) === n0);

const small = await p.evaluate(() => [...document.querySelectorAll(".rail-del, .rail-search-clear, .avatar-btn")]
  .map((e) => e.getBoundingClientRect()).filter((r) => r.width && (r.width < 24 || r.height < 24)).length);
check("history and account controls meet the 24px target size", small === 0, `${small} too small`);

// delete: cancel first, then confirm
const first = p.locator(".rail-row").first();
await first.hover();
await first.locator(".rail-del").click();
check("delete asks first", await p.getByText("Delete this conversation?").isVisible());
await p.screenshot({ path: `${out}/03-confirm.png` });
await p.getByRole("button", { name: "Cancel" }).click();
check("cancel keeps the row", (await rows()) === n0);
await first.hover();
await first.locator(".rail-del").click();
await p.getByRole("button", { name: "Delete", exact: true }).click();
await p.waitForFunction((n) => document.querySelectorAll(".rail-item").length === n - 1, n0, { timeout: 5000 }).catch(() => {});
check("confirm removes the row", (await rows()) === n0 - 1, `${await rows()} rows`);
await p.reload({ waitUntil: "domcontentloaded" });
await p.waitForSelector(".rail-item");
check("and it stays deleted after a reload", (await rows()) === n0 - 1);

// account menu
await p.getByRole("button", { name: /^Account:/ }).click();
check("account menu shows identity and folder", await p.locator(".account-pop .account-name").isVisible()
  && await p.locator(".account-facts").isVisible());
await p.screenshot({ path: `${out}/04-account.png` });
await p.keyboard.press("Escape");
check("Escape closes the account menu", !(await p.locator(".account-pop").isVisible()));
await p.getByRole("button", { name: /^Account:/ }).click();
await p.getByRole("menuitem", { name: "Keyboard shortcuts" }).click();
check("menu entry opens the shortcut sheet", await p.locator(".keys-sheet").isVisible());
check("no page errors", errors.length === 0, errors.join(" | "));
await b.close();
console.log(failed ? `\n${failed} failed` : "\nall passed");
process.exit(failed ? 1 : 0);
