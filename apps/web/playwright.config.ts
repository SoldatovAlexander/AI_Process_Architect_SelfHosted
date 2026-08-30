import { defineConfig, devices } from '@playwright/test'

const remoteBaseUrl = process.env.PLAYWRIGHT_BASE_URL
const video = process.env.PLAYWRIGHT_VIDEO === 'on' ? 'on' : 'off'
const slowMo = Number(process.env.PLAYWRIGHT_SLOW_MO || 0)
const outputDir = process.env.PLAYWRIGHT_OUTPUT_DIR || '../../output/playwright/results'
const reportDir = process.env.PLAYWRIGHT_REPORT_DIR || '../../output/playwright/report'

export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.pw.ts',
  timeout: 180_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list'], ['html', { outputFolder: reportDir, open: 'never' }]],
  outputDir,
  use: {
    baseURL: remoteBaseUrl || 'http://127.0.0.1:5174',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video,
    launchOptions: slowMo > 0 ? { slowMo } : undefined,
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: remoteBaseUrl ? undefined : [
    {
      command: './e2e/start-api.sh',
      url: 'http://127.0.0.1:8001/health',
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command: 'VITE_API_TARGET=http://127.0.0.1:8001 npm run dev -- --port 5174',
      url: 'http://127.0.0.1:5174',
      reuseExistingServer: false,
      timeout: 30_000,
    },
  ],
})
