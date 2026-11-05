import { defineConfig } from '@playwright/test'

// Fixed E2E suite: `npm run e2e`. Reuses :6400 / :5173 when they answer, otherwise starts them.
export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.spec.js',
  outputDir: process.env.E2E_OUTPUT || './e2e/artifacts/test-results',
  globalSetup: './e2e/global-setup.js',
  workers: 1,
  fullyParallel: false,
  timeout: 120_000,
  expect: { timeout: 20_000 },
  reporter: [['list']],
  use: {
    baseURL: process.env.E2E_WEB || 'http://localhost:5173',
    browserName: 'chromium',
    trace: 'retain-on-failure',
  },
})
