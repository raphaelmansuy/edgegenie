/** Submission feedback against the local app; no Databricks workspace access. */
import { chromium, expect } from '@playwright/test';
import { localApp } from './mission-test-server.mjs';
const app = await localApp();
const browser = await chromium.launch();
try {
  for (const [width, scheme] of [[1440, 'light'], [390, 'dark']]) {
    const context = await browser.newContext({ viewport: { width, height: 960 }, colorScheme: scheme, reducedMotion: 'reduce' });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(app.url);
    let release;
    const held = new Promise(resolve => { release = resolve; });
    await page.route('**/api/sessions/*/messages', async route => { await held; await route.continue(); });
    const box = page.locator('.composer textarea:visible').first();
    await box.fill('Explain execution. Do not use tools. [[scenario:longrun]]');
    await box.press('Enter');
    await expect(page.locator('.composer-send-status:visible')).toContainText('Sending mission');
    await expect(page.getByRole('button', { name: 'Sending…' })).toBeDisabled();
    await expect(box).toHaveValue(/Explain execution/);
    await page.screenshot({ path: `/tmp/edgegenie-submission-${width}.png` });
    release();
    await expect(page.locator('.composer-send-status:visible')).toContainText('Mission accepted');
    await expect(box).toHaveValue('');
    await page.unroute('**/api/sessions/*/messages');
    await page.route('**/api/sessions/*/messages', route => route.fulfill({ status: 403, contentType: 'application/json', body: JSON.stringify({ detail: 'Permission denied for this test' }) }));
    const input = page.locator('.composer textarea:visible').first();
    await input.fill('Also check revenue');
    await expect(page.getByRole('button', { name: /Send.*⌘/ })).toBeEnabled();
    await input.press('Enter');
    await expect(page.locator('.composer-error:visible')).toContainText('Permission denied');
    await expect(input).toHaveValue('Also check revenue');
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false);
    expect(errors).toEqual([]);
    console.log(`PASS delayed acceptance, follow-up refusal, retained draft: ${width}px ${scheme}`);
    await context.close();
  }
} finally {
  await browser.close();
  await app.stop();
}
