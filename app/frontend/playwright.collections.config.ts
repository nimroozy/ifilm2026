import { defineConfig } from '@playwright/test';

const ARTIFACT_DIR = process.env.QA_OUT || '/opt/cursor/artifacts/pr48-qa';

export default defineConfig({
  testDir: '.',
  testMatch: 'playwright.collections.spec.ts',
  timeout: 120_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list'], ['json', { outputFile: `${ARTIFACT_DIR}/playwright-report.json` }]],
  use: {
    baseURL: process.env.QA_BASE_URL || 'http://127.0.0.1:5173',
    headless: true,
    ignoreHTTPSErrors: true,
    video: 'off',
    screenshot: 'only-on-failure',
    locale: 'en-US',
  },
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
  outputDir: `${ARTIFACT_DIR}/test-results`,
});
