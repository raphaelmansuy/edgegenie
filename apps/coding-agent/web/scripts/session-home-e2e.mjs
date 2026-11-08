/** The centre while a conversation runs in the dock and nothing is open lists what exists so far.
 *   APP_URL=http://127.0.0.1:8062 node scripts/session-home-e2e.mjs   (fake agent) */
import { check, finish, launch, shot as baseShot } from "./parity-lib.mjs";
import { mkdirSync } from "node:fs";
const OUT = process.env.OUT ?? "../../../specs/006-databricks/e2e/session-home";
mkdirSync(OUT, { recursive: true });
const { browser, page: p, errors } = await launch(1440, 900);
await p.getByRole("textbox").last().fill("Create a notebook that calculates pi");
await p.keyboard.press("Enter");
await p.locator(".tab-close, [aria-label^=\"Close\"]").first().waitFor({ timeout: 20000 }).catch(() => {});
await p.waitForTimeout(3000);
await p.locator("[aria-label^=\"Close\"]").first().click().catch(() => {});
await p.locator(".session-home").waitFor({ timeout: 15000 }).then(() => check("the centre says what exists, not the first-run screen", true), () => check("the centre says what exists", false));
check("the first-run title is gone", (await p.getByText("What should we build today?").count()) === 0);
await p.waitForTimeout(4000);
await baseShot(p, "01-session-home.png", { path: `${OUT}/01-session-home.png` });
await finish(browser, errors);
