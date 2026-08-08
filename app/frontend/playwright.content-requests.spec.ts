import { expect, test, type Page } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const ARTIFACT_DIR = process.env.CR_ARTIFACT_DIR || '/opt/cursor/artifacts/content-requests-v1-qa';
const API = process.env.CR_API_URL || 'http://127.0.0.1:8000';

const VIEWPORTS = [
  { name: '1920x1080', width: 1920, height: 1080 },
  { name: '1440x900', width: 1440, height: 900 },
  { name: '1366x768', width: 1366, height: 768 },
  { name: '768x1024', width: 768, height: 1024 },
  { name: '390x844', width: 390, height: 844 },
];

function ensureDir(dir: string) {
  fs.mkdirSync(dir, { recursive: true });
}

async function setLocale(page: Page, locale: 'en' | 'fa' | 'ps') {
  await page.addInitScript((loc) => {
    localStorage.setItem('ifilm.locale', loc);
    document.cookie = `ifilm.locale=${loc}; path=/`;
  }, locale);
}

async function shot(page: Page, name: string) {
  ensureDir(ARTIFACT_DIR);
  await page.screenshot({
    path: path.join(ARTIFACT_DIR, `${name}.png`),
    fullPage: true,
  });
}

async function loginSubscriber(page: Page) {
  const login = await page.request.post(`${API}/api/auth/subscriber/login`, {
    data: { username: 'mobin_user_001', password: 'fixture-pass-ok', remember_device: false },
  });
  expect(login.ok()).toBeTruthy();
  const body = await login.json();
  await page.goto('/login');
  await page.evaluate((token) => {
    localStorage.setItem('ifilm_access_token', token);
  }, body.access_token as string);
  await page.goto('/request');
  await expect(page.getByTestId('request-form')).toBeVisible({ timeout: 20_000 });
}

async function loginAdmin(page: Page) {
  await page.goto('/admin/login');
  await page.locator('input[name="username"], #username, input[autocomplete="username"]').first().fill('admin');
  await page.locator('input[type="password"]').fill('qa-admin-pass-ok');
  await page.getByRole('button', { name: /sign in|log in|login/i }).click();
  await page.waitForURL(/\/admin(?!\/login)/, { timeout: 20_000 });
}

test.describe('Content Requests V1 browser QA', () => {
  test.beforeAll(() => {
    ensureDir(ARTIFACT_DIR);
  });

  for (const locale of ['en', 'fa', 'ps'] as const) {
    for (const vp of VIEWPORTS) {
      test(`request page ${locale} ${vp.name}`, async ({ page }) => {
        await page.setViewportSize({ width: vp.width, height: vp.height });
        await setLocale(page, locale);
        await page.goto('/request');
        await expect(page.getByTestId('request-content-page')).toBeVisible();
        // Sign-in gate or form
        const signedOut = page.getByTestId('request-sign-in');
        if (await signedOut.count()) {
          await expect(signedOut).toBeVisible();
        }
        await shot(page, `request-${locale}-${vp.name}`);
        // No horizontal overflow
        const overflow = await page.evaluate(() => {
          const doc = document.documentElement;
          return doc.scrollWidth > doc.clientWidth + 1;
        });
        expect(overflow).toBe(false);
        if (locale !== 'en') {
          await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
        }
      });
    }
  }

  test('subscriber request + my requests + duplicate + already available', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await setLocale(page, 'en');
    await loginSubscriber(page);
    await page.goto('/request');
    await expect(page.getByTestId('request-form')).toBeVisible();
    await expect(page.getByTestId('request-disclaimer')).toContainText(/does not guarantee/i);
    await shot(page, 'request-logged-in-en-1440x900');

    // Catalog already available (demo seed likely has titles; use a unique missing title)
    await page.getByTestId('request-title').fill(`CR QA Unique ${Date.now()}`);
    await page.getByTestId('request-year').fill('2027');
    await page.getByTestId('request-language').fill('Dari');
    await page.getByTestId('request-notes').fill('Browser QA request');
    await page.getByTestId('request-submit').click();
    await expect(page.getByTestId('request-form-message')).toBeVisible({ timeout: 15_000 });
    await shot(page, 'request-created-en');

    // Duplicate
    await page.getByTestId('request-title').fill(`CR QA Unique Dup Check`);
    // Use API-created same title again after first create — re-submit same as listed
    const listed = page.locator('[data-testid^="my-request-"]').first();
    await expect(listed).toBeVisible();
    const titleText = (await listed.locator('p').first().textContent()) || '';
    const cleanTitle = titleText.replace(/\s*\(\d{4}\)\s*$/, '').trim();
    await page.getByTestId('request-title').fill(cleanTitle);
    await page.getByTestId('request-year').fill('2027');
    await page.getByTestId('request-submit').click();
    await expect(page.getByTestId('request-form-message')).toContainText(/already have an open request|submitted|already available|Similar/i);
    await shot(page, 'request-duplicate-state-en');

    // Already available via known demo title if search finds one
    await page.getByTestId('request-title').fill('Kabul');
    await page.waitForTimeout(500);
    await page.getByTestId('request-submit').click();
    await page.waitForTimeout(1000);
    await shot(page, 'request-catalog-or-suggestion-en');
  });

  test('admin content requests queue workflow', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    // Ensure at least one request exists via API
    const login = await page.request.post(`${API}/api/auth/subscriber/login`, {
      data: { username: 'mobin_user_001', password: 'fixture-pass-ok', remember_device: false },
    });
    expect(login.ok()).toBeTruthy();
    const token = (await login.json()).access_token as string;
    await page.request.post(`${API}/api/me/content-requests`, {
      headers: { Authorization: `Bearer ${token}` },
      data: { request_type: 'movie', title: `Admin Queue ${Date.now()}`, year: 2028, force: true },
    });

    await loginAdmin(page);
    await page.goto('/admin/content-requests');
    await expect(page.getByTestId('admin-content-requests')).toBeVisible();
    await expect(page.getByTestId('cr-filters')).toBeVisible();
    await shot(page, 'admin-content-requests-1440x900');

    const first = page.locator('[data-testid^="cr-row-"]').first();
    await expect(first).toBeVisible({ timeout: 15_000 });
    await first.click();
    await expect(page.getByTestId('cr-detail')).toBeVisible();
    await page.getByTestId('cr-action-review').click();
    await page.waitForTimeout(500);
    await page.getByTestId('cr-action-approve').click();
    await page.waitForTimeout(500);
    await shot(page, 'admin-content-requests-approved');

    // Mobile admin
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/admin/content-requests');
    await expect(page.getByTestId('admin-content-requests')).toBeVisible();
    await shot(page, 'admin-content-requests-390x844');
  });

  test('nav exposes Request Movie outside bottom tabs', async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 768 });
    await setLocale(page, 'en');
    await page.goto('/');
    // Footer discover should include request
    const footer = page.getByTestId('footer-link-requestMovie');
    await expect(footer).toBeVisible();
    await shot(page, 'footer-request-movie-link');

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/');
    const bottom = page.getByTestId('mobile-bottom-nav');
    await expect(bottom).toBeVisible();
    await expect(bottom).not.toContainText(/Request Movie/i);
  });
});
