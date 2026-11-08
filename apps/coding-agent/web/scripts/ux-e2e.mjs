/** Look at the shell: palette, shortcut sheet, keyboard-only navigation. Saves shots to /tmp/genie-ux. */
import { chromium } from "playwright";
import { mkdirSync, readFileSync } from "node:fs";

const out = process.env.OUT ?? "/tmp/genie-ux";
mkdirSync(out, { recursive: true });
const b = await chromium.launch({ executablePath: process.env.CHROME_PATH || undefined });
// Against a deployed app the Databricks proxy needs a signed-in identity: pass an OAuth bearer.
const bearer = process.env.BEARER_FILE ? readFileSync(process.env.BEARER_FILE, "utf8").trim() : "";
const p = await b.newPage({
  viewport: { width: 1480, height: 940 }, deviceScaleFactor: 2,
  extraHTTPHeaders: bearer ? { Authorization: `Bearer ${bearer}` } : {},
});
const problems = [];
p.on("pageerror", (e) => problems.push(`pageerror: ${e}`));
p.on("console", (m) => { if (m.type() === "error") problems.push(`console: ${m.text()}`); });
let n = 0;
const shot = (name) => p.screenshot({ path: `${out}/${String(++n).padStart(2, "0")}-${name}.png` });
const ok = (c, m) => { if (!c) throw new Error(m); };

await p.goto(process.env.APP_URL ?? "http://127.0.0.1:8040", { waitUntil: "domcontentloaded" });
await p.waitForTimeout(1200);

// start a session so the full three-pane layout is visible
const box = p.getByRole("textbox", { name: "Message the agent" });
await box.fill("Build a notebook that shows revenue by pickup hour");
await p.keyboard.press("Meta+Enter");
await p.locator(".turn").first().waitFor({ timeout: 20000 });
await p.locator(".turn-foot").first().waitFor({ timeout: 60000 });
await p.waitForTimeout(500);
await shot("shell");

// palette
await p.keyboard.press("Meta+k");
await p.locator(".palette").waitFor({ timeout: 5000 });
await shot("palette-empty");
await p.locator(".palette-input").fill("shcut");
await p.waitForTimeout(300);
const titles = await p.locator(".palette-title").allInnerTexts();
ok(titles.length > 0, "an abbreviation found nothing");
ok(/keyboard shortcuts/i.test(titles[0]), `best match for "shcut" was ${titles[0]}`);
await p.locator(".palette-input").fill("new conv");
await p.waitForTimeout(200);
ok(/new conversation/i.test((await p.locator(".palette-title").allInnerTexts())[0]), "a prefix did not rank first");
await shot("palette-query");
await p.keyboard.press("Escape");
ok((await p.locator(".palette").count()) === 0, "escape did not close the palette");

// shortcut sheet from the keyboard
await p.keyboard.press("Meta+/");
await p.locator(".keys-sheet").waitFor({ timeout: 5000 });
ok((await p.locator(".keys-row").count()) >= 15, "shortcut sheet is missing rows");
await shot("shortcuts");
await p.keyboard.press("Escape");

// the palette also searches the workspace and the catalog, not just open things
await p.keyboard.press("Meta+k");
await p.locator(".palette-input").fill("nyctaxi");
await p.waitForTimeout(900);
const live = await p.locator(".palette-row").allInnerTexts();
ok(live.some((t) => /trips/.test(t)), `palette did not find the table live: ${JSON.stringify(live.slice(0, 5))}`);
await shot("palette-live");
await p.keyboard.press("Escape");

// panels
await p.keyboard.press("Meta+2");
ok((await p.locator(".rail-tab[aria-selected=true]").innerText()).toLowerCase() === "files", "⌘2 did not open Files");
await p.keyboard.press("Meta+b");
ok((await p.locator(".pane.rail").count()) === 0, "⌘B did not hide the rail");
await shot("rail-hidden");
await p.keyboard.press("Meta+b");
ok((await p.locator(".pane.rail").count()) === 1, "⌘B did not bring the rail back");
await p.keyboard.press("Meta+i");
ok((await p.locator(".pane.inspector").count()) === 0, "⌘I did not hide the inspector");
await p.keyboard.press("Meta+i");

// Enter sends, Shift+Enter does not (the convention every chat box follows now)
await p.keyboard.press("Meta+l");
const before = await p.locator(".turn").count();
await p.keyboard.type("a follow-up question");
await p.keyboard.down("Shift");
await p.keyboard.press("Enter");
await p.keyboard.up("Shift");
ok((await p.locator(".turn").count()) === before, "Shift+Enter sent the message");
await p.locator("textarea").fill("");

// focus composer
await p.keyboard.press("Meta+l");
const focused = await p.evaluate(() => document.activeElement?.getAttribute("aria-label"));
ok(focused === "Message the agent", `⌘L focused ${focused}`);

// tab strip is keyboard-operable, once there is more than one tab
await p.keyboard.press("Meta+2");
const search = p.getByPlaceholder("Search notebooks and files…");
await search.fill("taxi");
await p.locator(".result").first().click({ timeout: 30000 });
const docTab = p.locator(".doc-tabs .doc-tab").nth(1);
await docTab.waitFor({ timeout: 20000 });
await p.locator(".doc-tabs .doc-tab").first().focus();
await p.keyboard.press("ArrowRight");
const selected = await p.locator('.doc-tabs .doc-tab[aria-selected="true"]').innerText();
ok(selected.length > 0, "ArrowRight did not select a tab");
await p.keyboard.press("Meta+w");
// closing the last document also hides the strip: Chat is the only view left, so there is no tab bar
ok((await p.locator(".doc-tabs .doc-tab").count()) === 0, "⌘W did not close the document tab");
ok((await p.locator(".viewer").count()) === 0, "the closed document is still on screen");

// Nothing may spill out of its box, at this width or a narrow one.
const spills = await p.evaluate(() => {
  const out = [];
  for (const el of Array.from(document.querySelectorAll("*"))) {
    const st = getComputedStyle(el);
    if (st.display === "none" || st.visibility === "hidden" || el.classList.contains("sr-only")) continue;
    if (st.overflowX !== "visible" || st.overflowY !== "visible") continue;
    if (el.scrollWidth > el.clientWidth + 1 && st.textOverflow !== "ellipsis") {
      out.push(`${el.tagName.toLowerCase()}.${String(el.className).split(" ")[0]} ${el.scrollWidth}>${el.clientWidth}`);
    }
  }
  return out;
});
ok(spills.length === 0, `content spills out of its box: ${spills.slice(0, 5).join(", ")}`);

console.log("problems:", problems.length ? problems : "none");
await b.close();
process.exit(problems.length ? 1 : 0);
