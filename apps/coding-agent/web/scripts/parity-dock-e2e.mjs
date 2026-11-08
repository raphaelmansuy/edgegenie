/** Genie Code parity scenes for the assistant dock: follow-ups, history, the conversation menu and the
 * slash commands. Runs against the fake agent WITHOUT a workspace token, because a turn there completes
 * (with a token the audit checks the fake agent's hard-coded paths against the real workspace and,
 * correctly, blocks it).
 *
 *   APP_URL=http://127.0.0.1:8071 node scripts/parity-dock-e2e.mjs
 */
import { readFile } from "node:fs/promises";
import { check, finish, launch, shot } from "./parity-lib.mjs";

const { browser, page: p, errors } = await launch(1440, 900);

/* A finished turn to work with. */
await p.getByRole("button", { name: /Build a notebook/ }).click().catch(() => {});
const box0 = p.locator(".pane.assistant textarea").first();
await box0.fill("Build a notebook that shows revenue by month");
await box0.press("Enter");
await p.locator(".turn-foot").first().waitFor({ timeout: 90000 });
await p.waitForTimeout(800);

/* 06 · follow-ups after the answer */
console.log("\n== 06 follow-ups");
await p.locator(".followups").waitFor({ timeout: 30000 }).catch(() => {});
const fu = await p.locator(".followup").allInnerTexts();
check("the answer ends with next steps derived from what happened", fu.length >= 1 && fu.length <= 3, fu.join(" | "));
await shot(p, "06-follow-ups.png");

/* 09 · history in the dock */
console.log("\n== 09 history");
await p.getByRole("button", { name: "Conversation history" }).click();
const hist = p.locator(".dock-history");
await hist.waitFor({ timeout: 5000 });
check("history lists conversations under day headings", (await hist.locator(".rail-item").count()) >= 1 && (await hist.locator(".rail-group").count()) >= 1,
  `${await hist.locator(".rail-item").count()} rows`);
const box = await hist.boundingBox();
check("the popover stays inside the window", box.x >= 0 && box.x + box.width <= 1440 && box.y + box.height <= 900, JSON.stringify(box));
await shot(p, "09-dock-history.png");
await p.keyboard.press("Escape");

/* 10 · the conversation menu */
console.log("\n== 10 conversation menu");
await p.getByRole("button", { name: "More conversation actions" }).click();
check("the menu offers copy, download and new", await p.getByRole("menuitem", { name: /Copy conversation/ }).isEnabled()
  && await p.getByRole("menuitem", { name: /Download as Markdown/ }).isEnabled() && await p.getByRole("menuitem", { name: /New conversation/ }).isVisible());
await shot(p, "10-conversation-menu.png");
const [download] = await Promise.all([p.waitForEvent("download"), p.getByRole("menuitem", { name: /Download as Markdown/ }).click()]);
const name = download.suggestedFilename();
check("the download is a .md file with a safe name", /^[a-z0-9-]+\.md$/.test(name), name);
const text = await (await import("node:fs/promises")).readFile(await download.path(), "utf8");
check("it contains the question and the answer, and no plumbing", /## You/.test(text) && /## Agent/.test(text) && !/tokens/.test(text));

/* 11 · slash commands are discoverable */
console.log("\n== 11 slash menu");
const dockBox = p.locator(".pane.assistant textarea").first();
await dockBox.click();
await dockBox.fill("");
await dockBox.type("/");
const cmds = p.locator(".mention[aria-label='Commands']");
await cmds.waitFor({ timeout: 5000 });
const count = await cmds.locator(".mention-opt").count();
check("a bare / lists every command", count >= 10, `${count} commands`);
await p.keyboard.press("ArrowDown");
check("arrow keys move the selection", (await cmds.locator(".mention-opt.is-active .mention-name").innerText()) === "fix");
await shot(p, "11-slash-commands.png");
await p.keyboard.press("Escape");

await finish(browser, errors);
