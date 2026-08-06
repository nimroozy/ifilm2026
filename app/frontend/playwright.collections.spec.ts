/**
 * Collections V1 browser QA screenshots.
 * Run: cd app/frontend && pnpm exec playwright test ../../scripts/collections-qa.pw.ts
 */
import { test, expect, chromium, type Page } from '@playwright/test';
import path from 'node:path';
import fs from 'node:fs';

const BASE = process.env.QA_BASE_URL || 'http://127.0.0.1:5173';
const API = process.env.QA_API_URL || 'http://127.0.0.1:8001/api';
const OUT = process.env.QA_OUT || '/opt/cursor/artifacts/pr48-qa';
const ADMIN_USER = process.env.ADMIN_BOOTSTRAP_USERNAME || 'admin';
const ADMIN_PASS = process.env.ADMIN_BOOTSTRAP_PASSWORD || 'unit-test-admin-pass-ok';

const VIEWPORTS = [
  { name: '1280x720', width: 1280, height: 720 },
  { name: '1366x768', width: 1366, height: 768 },
  { name: '1440x900', width: 1440, height: 900 },
  { name: '1920x1080', width: 1920, height: 1080 },
  { name: '390x844', width: 390, height: 844 },
  { name: '430x932', width: 430, height: 932 },
  { name: '768x1024', width: 768, height: 1024 },
];

fs.mkdirSync(OUT, { recursive: true });

async function loginAdmin(page: Page) {
  const resp = await page.request.post(`${API}/admin/auth/login`, {
    data: { username: ADMIN_USER, password: ADMIN_PASS },
  });
  expect(resp.ok()).toBeTruthy();
  const body = await resp.json();
  await page.addInitScript((token) => {
    localStorage.setItem('ifilm_admin_token', token as string);
  }, body.access_token);
}

function isIgnorableConsole(text: string): boolean {
  return /favicon|Download the React DevTools|Failed to load resource|Content Security Policy|script-src|422|404/i.test(
    text
  );
}

async function shot(page: Page, name: string) {
  const file = path.join(OUT, `${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  return file;
}

test.describe('Collections V1 browser QA', () => {
  for (const vp of VIEWPORTS) {
    test(`public collections @ ${vp.name}`, async () => {
      const browser = await chromium.launch();
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        locale: 'en-US',
      });
      const page = await context.newPage();
      const errors: string[] = [];
      page.on('pageerror', (err) => errors.push(String(err)));
      page.on('console', (msg) => {
        if (msg.type() === 'error') errors.push(msg.text());
      });

      await page.goto(`${BASE}/collections`, { waitUntil: 'networkidle' });
      await expect(page.getByTestId('collections-index-page')).toBeVisible({ timeout: 15000 });
      await shot(page, `public-index-${vp.name}`);

      await page.goto(`${BASE}/collections/popular-movies`, { waitUntil: 'networkidle' });
      await expect(page.getByTestId('collection-detail-page')).toBeVisible({ timeout: 15000 });
      await shot(page, `public-detail-${vp.name}`);

      await page.goto(`${BASE}/collections/does-not-exist-xyz`, { waitUntil: 'networkidle' });
      await expect(page.getByTestId('not-found-page')).toBeVisible({ timeout: 15000 });
      await shot(page, `public-404-${vp.name}`);

      await page.goto(`${BASE}/`, { waitUntil: 'networkidle' });
      await shot(page, `home-${vp.name}`);

      // RTL sample at one mobile + one desktop size
      if (vp.name === '1280x720' || vp.name === '390x844') {
        await page.evaluate(() => localStorage.setItem('ifilm.locale', 'fa'));
        await page.goto(`${BASE}/collections`, { waitUntil: 'networkidle' });
        await shot(page, `public-index-fa-${vp.name}`);
        await page.evaluate(() => localStorage.setItem('ifilm.locale', 'ps'));
        await page.goto(`${BASE}/collections/popular-movies`, { waitUntil: 'networkidle' });
        await shot(page, `public-detail-ps-${vp.name}`);
        await page.evaluate(() => localStorage.setItem('ifilm.locale', 'en'));
      }

      expect(errors.filter((e) => !isIgnorableConsole(e))).toEqual([]);
      await browser.close();
    });
  }

  test('admin collections workflow @ 1280 and 390', async () => {
    for (const vp of [
      { name: '1280x720', width: 1280, height: 720 },
      { name: '390x844', width: 390, height: 844 },
    ]) {
      const browser = await chromium.launch();
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
      });
      const page = await context.newPage();
      await loginAdmin(page);
      await page.goto(`${BASE}/admin/collections`, { waitUntil: 'networkidle' });
      await expect(page.getByTestId('collections-list-page')).toBeVisible({ timeout: 20000 });
      await shot(page, `admin-list-${vp.name}`);

      await page.goto(`${BASE}/admin/collections/1/edit`, { waitUntil: 'networkidle' });
      await expect(page.getByTestId('collection-form-page')).toBeVisible({ timeout: 20000 });
      await shot(page, `admin-edit-details-${vp.name}`);

      // Items tab
      const itemsTab = page.getByRole('tab', { name: /items/i });
      if (await itemsTab.count()) {
        await itemsTab.dispatchEvent('mousedown');
        await page.waitForTimeout(300);
        await shot(page, `admin-edit-items-${vp.name}`);
      }

      // Preview tab
      const previewTab = page.getByRole('tab', { name: /preview/i });
      if (await previewTab.count()) {
        await previewTab.dispatchEvent('mousedown');
        await page.waitForTimeout(300);
        await shot(page, `admin-edit-preview-${vp.name}`);
      }

      await browser.close();
    }
  });
});
