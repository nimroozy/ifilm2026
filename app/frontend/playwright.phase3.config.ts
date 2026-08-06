import { defineConfig } from '@playwright/test';

const ARTIFACT_DIR = process.env.PR46_ARTIFACT_DIR || '/opt/cursor/artifacts/pr46-qa';

export default defineConfig({
  testDir: '.',
  testMatch: 'playwright.phase3.spec.ts',
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list'], ['json', { outputFile: `${ARTIFACT_DIR}/playwright-report.json` }]],
  use: {
    baseURL: process.env.PHASE3_BASE_URL || 'http://127.0.0.1:4173',
    headless: true,
    ignoreHTTPSErrors: true,
    video: 'off',
    screenshot: 'only-on-failure',
    locale: 'en-US',
  },
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
  outputDir: `${ARTIFACT_DIR}/test-results`,
});
