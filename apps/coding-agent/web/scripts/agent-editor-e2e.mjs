import { chromium, expect } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { localApp } from "./mission-test-server.mjs";
const root = resolve(dirname(fileURLToPath(import.meta.url)), "../../../..");
const iteration = process.env.ITERATION || "editor-01",
  shots = resolve(root, "specs/014-improve-agent/e2e/screenshots", iteration);
mkdirSync(shots, { recursive: true });
const app = await localApp({ agentWork: true }),
  browser = await chromium.launch();
const captures = [],
  errors = [];
const post = (path, body = {}) =>
  app.json(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
const context = await browser.newContext({
    viewport: { width: 1600, height: 1000 },
    reducedMotion: "reduce",
  }),
  page = await context.newPage();
page.on("pageerror", (e) => errors.push(e.message));
async function shot(name) {
  await page.screenshot({ path: resolve(shots, name + ".png") });
  captures.push(name);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
  ).toBeTruthy();
}
let serial = 0;
async function create() {
  const folder = "/Users/mission@example.test/agent_scratch/editor-" + ++serial;
  const s = await post("/api/sessions", { folder, model: "fake/model-a" });
  await post(`/api/sessions/${s.id}/messages`, {
    text: "Change cell 3 and verify. [[scenario:workreview]]",
  });
  await page.goto(`${app.url}/#/session/${s.id}`);
  await expect(
    page.getByRole("button", { name: "Apply change", exact: true }),
  ).toBeVisible({ timeout: 30000 });
  return { sid: s.id, path: folder + "/revenue" };
}
async function editor(path) {
  await page.evaluate((p) => (location.hash = "#/notebook" + p), path);
  await expect(page.locator(".cell-block").first()).toBeVisible();
}
try {
  const a = await create();
  await editor(a.path);
  const first = page.locator('.cm-content[contenteditable="true"]').first();
  await first.click();
  await first.press("Meta+End");
  await first.press("Enter");
  await first.pressSequentially("# local draft survives");
  await expect
    .poll(() =>
      page.evaluate(
        (p) => localStorage.getItem("coding-agent:draft:v1:" + p),
        a.path,
      ),
    )
    .toContain("local draft survives");
  await shot("01-unsaved-local");
  await page.getByRole("button", { name: "Apply change", exact: true }).click();
  await expect(
    page.getByRole("alertdialog", { name: "The notebook changed" }),
  ).toBeVisible({ timeout: 30000 });
  await expect(first).toContainText("local draft survives");
  await shot("02-incoming-preserves-local");
  await page.reload();
  await expect(
    page.getByRole("button", { name: "Restore", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Restore", exact: true }).click();
  await expect(page.locator(".cm-content").first()).toContainText(
    "local draft survives",
  );
  const actual = await app.json(
    "/api/workspace/object?path=" + encodeURIComponent(a.path),
  );
  expect(actual.cells[3].source).toContain("print(300)");
  await shot("03-local-recovered");
  const b = await create();
  await editor(b.path);
  await page.getByRole("button", { name: "Apply change", exact: true }).click();
  await expect(
    page.getByText("This notebook was updated", { exact: true }),
  ).toBeVisible({ timeout: 30000 });
  await expect(page.locator(".cell-block").nth(3)).toContainText("print(300)");
  await shot("04-live-editor-refreshed");
  expect(errors).toEqual([]);
  writeFileSync(
    resolve(shots, "../..", iteration + ".json"),
    JSON.stringify(
      {
        pass: true,
        captures,
        errors,
        scope:
          "Real local editor and app routes, draft recovery and ledger-triggered source refresh.",
      },
      null,
      2,
    ),
  );
  console.log({ pass: true, captures });
} finally {
  await browser.close();
  await app.stop();
}
