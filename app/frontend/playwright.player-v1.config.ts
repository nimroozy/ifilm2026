import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: '.',
  testMatch: 'playwright.player-v1.spec.ts',
  timeout: 180_000,
  expect: { timeout: 25_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list'], ['json', { outputFile: '/opt/cursor/artifacts/pr62-playwright.json' }]],
  use: {
    baseURL: process.env.PLAYER_V1_BASE_URL || 'http://127.0.0.1:8020',
    headless: true,
    ignoreHTTPSErrors: true,
    video: 'retain-on-failure',
    screenshot: 'on',
    locale: 'en-US',
  },
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
});
