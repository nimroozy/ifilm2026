import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: '.',
  testMatch: 'playwright.perf-waterfall.spec.ts',
  timeout: 180_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list'], ['json', { outputFile: '/opt/cursor/artifacts/perf-customer-browsing-v1/playwright-report.json' }]],
  use: {
    baseURL: process.env.PERF_BASE_URL || 'http://127.0.0.1:8010',
    headless: true,
    ignoreHTTPSErrors: true,
    video: 'off',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
});
